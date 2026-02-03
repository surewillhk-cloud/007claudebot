import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# 已更新为你的正确 ID: 7663163793
ADMIN_ID_VAL = os.getenv("ADMIN_ID", "7663163793").strip()
ADMIN_ID = int(ADMIN_ID_VAL) if ADMIN_ID_VAL.isdigit() else 7663163793
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o": "openai/gpt-4o",
    "🚀 o1": "openai/o1"
}

# --- 数据库操作 ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"users": {}, "keys": {}}

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f: json.dump(data, f)
    except: pass

db = load_db()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
logging.basicConfig(level=logging.INFO)

# --- 菜单逻辑 ---
def get_main_menu(uid):
    buttons = [["💰 3.7 Sonnet", "💎 4.5 Opus"], ["🧠 GPT-4o", "🚀 o1"]]
    if uid == ADMIN_ID:
        buttons.append(["🔑 生成KEY", "📊 系统余额"])
    else:
        buttons.append(["💳 我的余额", "🛑 停止清理"])
    buttons.append(["☎️ 联系客服"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 核心处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # 鉴权逻辑：管理员或已授权用户
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        await update.message.reply_text(f"👋 您好！您的 ID 是：`{uid}`\n⚠️ 请联系客服获取激活码以开启权限。", parse_mode='Markdown')
    else:
        await update.message.reply_text("✅ 认证成功，请选择模型：", reply_markup=get_main_menu(uid))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 管理员：生成 KEY (后台5.0U，前台显10.00U)
    if text == "🔑 生成KEY" and uid == ADMIN_ID:
        key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][key] = {"days": 30, "balance": 5.0} 
        save_db(db)
        # MarkdownV2 格式：点击 Key 即可自动复制
        await update.message.reply_text(f"🔑 *新密钥已生成*（点击复制）：\n\n`{key}`\n\n🎁 充值额度：$10\\.00\n⏳ 有效期：30天", parse_mode='MarkdownV2')
        return

    # 2. 激活逻辑
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            exp = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": exp, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！\n💰 账户余额：$10.00\n⏰ 有效期至：{exp}", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效或已被使用。")
        return

    # 3. 余额查询 (虚拟显示：成本*2)
    if text == "💳 我的余额":
        u = db["users"].get(str(uid))
        if u:
            show_bal = round(u["balance"] * 2, 2)
            await update.message.reply_text(f"👤 账户状态：正常\n💰 剩余额度：${show_bal}\n⏰ 到期时间：{u['expire']}")
        return

    # 4. 其他功能
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 切换成功：{text}")
    elif text == "📊 系统余额" and uid == ADMIN_ID:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            bal = r.json()['data'].get('limit_remaining', '未设定')
            await update.message.reply_text(f"📊 官方总池余额：${bal}")
    elif text == "🛑 停止清理":
        context.user_data.clear()
