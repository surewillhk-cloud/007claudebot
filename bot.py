import os, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# 填入你正确的 ID
ADMIN_ID = 7663163793 
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o": "openai/gpt-4o",
    "🚀 o1": "openai/o1"
}

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"users": {}, "keys": {}}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

db = load_db()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
logging.basicConfig(level=logging.INFO)

# --- 菜单 ---
def get_main_menu(uid):
    buttons = [["💰 3.7 Sonnet", "💎 4.5 Opus"], ["🧠 GPT-4o", "🚀 o1"]]
    if uid == ADMIN_ID:
        buttons.append(["🔑 生成KEY", "📊 系统余额"])
    else:
        buttons.append(["💳 我的余额", "🛑 停止清理"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 核心逻辑 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        await update.message.reply_text(f"👋 ID: `{uid}`\n请发送激活码开启权限。", parse_mode='Markdown')
    else:
        await update.message.reply_text("✅ 认证成功，请直接发送文字或代码文件：", reply_markup=get_main_menu(uid))

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = ""

    # 识别文件内容（解决你截图里的报错问题）
    if update.message.document:
        doc = await update.message.document.get_file()
        content = await doc.download_as_bytearray()
        text = f"这是文件内容，请分析：\n\n{content.decode('utf-8')}"
    elif update.message.text:
        text = update.message.text.strip()

    if not text: return

    # 管理员生成 KEY
    if text == "🔑 生成KEY" and uid == ADMIN_ID:
        key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][key] = {"days": 30, "balance": 5.0} # 后台5U
        save_db(db)
        await update.message.reply_text(f"🔑 点击复制密钥：\n`{key}`\n🎁 额度：$10\\.00", parse_mode='MarkdownV2')
        return

    # 激活与查询 (略，保持之前的逻辑)
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            exp = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": exp, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！余额：$10.00")
        return

    if text == "💳 我的余额":
        u = db["users"].get(str(uid))
        if u: await update.message.reply_text(f"💰 剩余额度：${round(u['balance']*2, 2)}")
        return

    # 鉴权
    if uid != ADMIN_ID and str(uid) not in db["users"]: return

    await run_ai(update, context, text)

async def run_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    # 限制上下文历史为 4 条，极大节省 Token 成本
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet"])
    status = await update.message.reply_text("🔍 正在秒回...")
    
    try:
        # 强制 AI 合并输出且不讲废话的系统指令
        sys_prompt = "你是一个极致精简的助手。1.严禁分段发文件，必须将所有代码和解释合并在一条消息内。2.禁止任何开场白和分析。3.直接给结果。"
        
        response = client.chat.completions.create(
            model=model, 
            messages=[{"role": "system", "content": sys_prompt}] + context.user_data["history"][-4:]
        )
        ans = response.choices[0].message.content
        
        # 虚拟 10U 扣费逻辑
        cost = (response.usage.total_tokens / 1000) * 0.02
        info = ""
        if update.effective_user.id != ADMIN_ID:
            db["users"][str(update.effective_user.id)]["balance"] -= cost
            save_db(db)
            info = f"\n\n💸 消耗: ${round(cost*2, 4)} | 余额: ${round(db['users'][str(update.effective_user.id)]['balance']*2, 2)}"

        await status.edit_text(f"{ans[:3800]}{info}")
        context.user_data["history"].append({"role": "assistant", "content": ans})
    except Exception as e:
        await status.edit_text("❌ 服务繁忙，请稍后再试。")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    # 支持文本和文档文件
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_all))
    app.run_polling(drop_pending_updates=True)
