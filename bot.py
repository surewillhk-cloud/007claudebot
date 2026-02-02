import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ParseMode

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# 确保 ID 是整数
ADMIN_ID = int(os.getenv("ADMIN_ID").strip()) if os.getenv("ADMIN_ID") else None
KEFU_URL = "https://t.me/ch007b" 
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet (省钱)": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus (土豪)": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o (通用)": "openai/gpt-4o",
    "🚀 o1 (推理版)": "openai/o1"
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
    except Exception as e:
        logging.error(f"保存数据库失败: {e}")

db = load_db()
logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 菜单生成 ---
def get_main_menu(uid):
    is_admin = (uid == ADMIN_ID)
    is_auth = str(uid) in db["users"]
    
    # 基础模型
    buttons = [
        ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
        ["🧠 GPT-4o (通用)", "🚀 o1 (推理版)"]
    ]
    
    if is_admin:
        buttons.append(["🔑 生成10U/5U额度Key", "📊 查看系统总余额"])
    elif is_auth:
        buttons.append(["💳 查看我的余额"])
    
    buttons.append(["🛑 停止/清理记忆", "☎️ 联系客服"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 核心指令 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logging.info(f"用户 {uid} 触发了 /start")
    
    menu = get_main_menu(uid)
    is_auth = (uid == ADMIN_ID or str(uid) in db["users"])

    if not is_auth:
        keyboard = [[InlineKeyboardButton("📩 点击联系客服申请", url=KEFU_URL)]]
        await update.message.reply_text(
            f"👋 您好！您的 ID 是：`{uid}`\n⚠️ 您尚未获得授权。\n请发送激活密钥，或点击下方按钮联系客服。",
            reply_markup=menu, # 即便没授权也显示带有“申请”按钮的固定菜单
            parse_mode='Markdown'
        )
        await update.message.reply_text("快速客服通道：", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(
            f"✅ 认证成功！管理员：{'是' if uid==ADMIN_ID else '否'}\n请选择模型或开始提问。",
            reply_markup=menu
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 密钥识别
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            expire_at = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": expire_at, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！额度 ${info['balance']} 已入账。", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效或已使用。")
        return

    # 2. 菜单项处理 (包含余额查询)
    if text == "🔑 生成10U/5U额度Key" and uid == ADMIN_ID:
        new_key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][new_key] = {"days": 30, "balance": 5.0}
        save_db(db)
        await update.message.reply_text(f"🔑 生成成功：`{new_key}`", parse_mode='Markdown')
        return

    if text == "💳 查看我的余额":
        u_data = db["users"].get(str(uid))
        if u_data:
            await update.message.reply_text(f"💰 剩余虚拟额度：${round(u_data['balance'], 2)}\n⏰ 到期：{u_data['expire']}")
        return

    # 3. 鉴权
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        await start(update, context); return

    # 4. 模型切换与 AI 逻辑
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 切换至：{text}")
    elif text == "🛑 停止/清理记忆":
        context.user_data.clear()
        await update.message.reply_text("⏹ 记忆已清空。")
    elif text in ["☎️ 联系客服", "✨ 申请授权"]:
        await update.message.reply_text(f"客服链接：{KEFU_URL}")
    else:
        # 排除空消息
        if text: await run_ai_with_billing(update, context, text)

# ... (此处接上一版的 run_ai_with_billing 和 main 函数)
