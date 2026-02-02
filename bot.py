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
KEFU_URL = "https://t.me/ch007b" # 记得改这里
DB_FILE = "users_db.json"

# 模型映射
MODELS = {
    "💰 3.7 Sonnet (省钱)": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus (土豪)": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o (通用)": "openai/gpt-4o",
    "🚀 o1 (推理版)": "openai/o1"
}

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
        # 陌生人只有这两个按钮
        return ReplyKeyboardMarkup([["✨ 申请授权", "☎️ 联系客服"]], resize_keyboard=True)

# --- 功能逻辑 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    menu = get_main_menu(uid)
    
    if str(uid) not in db["users"] and uid != ADMIN_ID:
        # 陌生人：展示带内联按钮的消息
        keyboard = [[InlineKeyboardButton("📩 点击此处私聊客服申请", url=KEFU_URL)]]
        await update.message.reply_text(
            "👋 欢迎！这是私人 AI 编程助手。\n\n⚠️ 您尚未获得授权。请点击下方按钮联系客服，或在下方输入框发送您的激活码。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # 同时弹出底部简单菜单
        await update.message.reply_text("您也可以点击下方菜单查看申请指引：", reply_markup=menu)
    else:
        await update.message.reply_text("✅ 欢迎回来！请选择模型或直接提问。", reply_markup=menu)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # 1. 自动识别密钥 (KEY-XXXXX 格式)
    if text.startswith("KEY-"):
        if text in db["keys"]:
            days = db["keys"].pop(text)
            expire_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = expire_at
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！有效期至：{expire_at}", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效或已过期。")
        return

    # 2. 菜单项拦截
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 模型已切换：{text}")
        return
    
    if text == "🔑 生成30天密钥" and uid == ADMIN_ID:
        new_key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][new_key] = 30
        save_db(db)
        await update.message.reply_text(f"🔑 已生成30天密钥：\n`{new_key}`", parse_mode='Markdown')
        return

    if text == "💳 查看余额":
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            bal = r.json()['data']['limit_remaining']
            await update.message.reply_text(f"💰 账户余额：<b>${bal}</b>", parse_mode='HTML')
        return

    if text == "🛑 停止/清理":
        context.user_data.clear()
        await update.message.reply_text("⏹ 已重置话题上下文，思考已停止。")
        return

    if text in ["☎️ 联系客服", "✨ 申请授权"]:
        keyboard = [[InlineKeyboardButton("📩 联系客服", url=KEFU_URL)]]
        await update.message.reply_text("点击下方按钮跳转至客服：", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 3. 鉴权与到期检查
    if uid != ADMIN_ID:
        if str(uid) not in db["users"]:
            await start(update, context)
            return
        expire_time = datetime.strptime(db["users"][str(uid)], "%Y-%m-%d %H:%M:%S")
        if expire_time < datetime.now():
            del db["users"][str(uid)]
            save_db(db)
            await update.message.reply_text("⏰ 您的30天授权已到期，请重新申请。")
            return

    # 4. AI 逻辑 (含话题延续)
    await run_ai_logic(update, context, text)

async def run_ai_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    # 初始化历史纪录
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet (省钱)"])
    status_msg = await update.message.reply_text(f"🔍 {model.split('/')[-1]} 思考中...")
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": "你是一个全能专家，请尽可能合并代码输出。"}] + context.user_data["history"][-6:] # 记住最近3轮对话
        )
        ans = response.choices[0].message.content
        context.user_data["history"].append({"role": "assistant", "content": ans})
        
        # 提取文件
        blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", ans)
        clean_text = re.sub(r"```(?:\w+)?\n[\s\S]*?\n```", "【代码见下方文件】", ans)
        
        await status_msg.edit_text(f"<b>响应内容：</b>\n<pre>{clean_text[:3500]}</pre>", parse_mode='HTML')
        
        for i, code in enumerate(blocks):
            name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", code)
            fname = name_match.group(1) if name_match else f"output_{i+1}.py"
            f_io = io.BytesIO(code.encode('utf-8'))
            f_io.name = fname
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)

    except Exception as e:
        await status_msg.edit_text(f"❌ 运行异常：{str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # 为非技术用户增加一键处理文件分析
    app.add_handler(MessageHandler(filters.Document.ALL, handle_text)) # 复用逻辑
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
