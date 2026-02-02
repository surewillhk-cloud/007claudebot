import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ParseMode

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
KEFU_URL = "https://t.me/your_telegram_id"  # 👈 这里可以改成你的客服链接
DB_FILE = "users_db.json"

# 模型配置
MODELS = {
    "💰 3.7 Sonnet (省钱)": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus (土豪)": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o (通用)": "openai/gpt-4o",
    "🚀 o1 (推理版)": "openai/o1"
}

# 强制合并代码的指令
SYSTEM_PROMPT = """你是一个专业的全栈工程师。
1. 请提供完整、可直接运行的代码，严禁拆分代码块。
2. 即使修复多个问题，也请汇总到一个完整文件中。
3. 代码块第一行格式：# filename: 文件名.扩展名
"""

# --- 数据库持久化 ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"users": {}, "keys": {}}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

db = load_db()
logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 余额查询增强版 ---
async def get_balance():
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as c:
        try:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers, timeout=10)
            data = r.json().get('data', {})
            limit_rem = data.get('limit_remaining')
            if limit_rem is not None:
                return f"${round(float(limit_rem), 2)}"
            return "暂无数据"
        except: return "查询失败"

# --- 菜单生成器 ---
def get_main_menu(uid):
    is_admin = (uid == ADMIN_ID)
    is_auth = str(uid) in db["users"]
    
    if is_admin:
        return ReplyKeyboardMarkup([
            ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
            ["🧠 GPT-4o (通用)", "🚀 o1 (推理版)"],
            ["🔑 生成30天密钥", "💳 查看余额"],
            ["🛑 停止/清理", "☎️ 联系客服"]
        ], resize_keyboard=True)
    elif is_auth:
        return ReplyKeyboardMarkup([
            ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
            ["🛑 停止/清理", "☎️ 联系客服"]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([["✨ 申请授权", "☎️ 联系客服"]], resize_keyboard=True)

# --- 指令与消息处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    menu = get_menu = get_main_menu(uid)
    
    if str(uid) not in db["users"] and uid != ADMIN_ID:
        keyboard = [[InlineKeyboardButton("📩 点击联系客服申请", url=KEFU_URL)]]
        await update.message.reply_text(
            "👋 您好！这是私人 AI 助手。\n⚠️ 您尚未获得授权，请发送激活码或联系客服。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("✅ 认证成功，请选择模型或直接提问。", reply_markup=menu)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 激活码逻辑
    if text.startswith("KEY-"):
        if text in db["keys"]:
            days = db["keys"].pop(text)
            expire_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = expire_at
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！有效期至：{expire_at}", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效。")
        return

    # 2. 菜单功能
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 模型已切换至：{text}")
        return
    
    if text == "🔑 生成30天密钥" and uid == ADMIN_ID:
        new_key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][new_key] = 30
        save_db(db)
        await update.message.reply_text(f"🔑 新密钥：`{new_key}`")
        return

    if text == "💳 查看余额":
        bal = await get_balance()
        await update.message.reply_text(f"💰 账户余额：<b>{bal}</b>", parse_mode='HTML')
        return

    if text == "🛑 停止/清理":
        context.user_data.clear()
        await update.message.reply_text("⏹ 已清理记忆并停止思考。")
        return

    if text in ["☎️ 联系客服", "✨ 申请授权"]:
        await update.message.reply_text(f"客服链接：{KEFU_URL}")
        return

    # 3. 鉴权与到期检查
    if uid != ADMIN_ID:
        if str(uid) not in db["users"]:
            await start(update, context); return
        exp = datetime.strptime(db["users"][str(uid)], "%Y-%m-%d %H:%M:%S")
        if exp < datetime.now():
            del db["users"][str(uid)]; save_db(db)
            await update.message.reply_text("⏰ 授权已过期。"); return

    # 4. 话题延续与 AI 调用
    await run_ai(update, context, text)

async def run_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet (省钱)"])
    status_msg = await update.message.reply_text(f"🔍 {model.split('/')[-1]} 思考中...")
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + context.user_data["history"][-6:]
        )
        ans = response.choices[0].message.content
        context.user_data["history"].append({"role": "assistant", "content": ans})
        
        # 提取文件
        blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", ans)
        clean_text = re.sub(r"```(?:\w+)?\n[\s\S]*?\n```", "【代码已生成文件，请查看下方附件】", ans)
        
        await status_msg.edit_text(f"<b>回复：</b>\n<pre>{clean_text[:3500]}</pre>", parse_mode='HTML')
        
        for i, code in enumerate(blocks):
            name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", code)
            fname = name_match.group(1) if name_match else f"output_{i+1}.py"
            f_io = io.BytesIO(code.encode('utf-8'))
            f_io.name = fname
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)
    except Exception as e:
        await status_msg.edit_text(f"❌ 出错：{str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_text))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
