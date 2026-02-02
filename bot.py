import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ParseMode

# --- 1. 强化日志系统 (必须在 Railway Logs 查看) ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 2. 配置加载 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID").strip()) if os.getenv("ADMIN_ID") else None
KEFU_URL = "https://t.me/ch007b" # 👈 改成你的 TG 账号链接
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet (省钱)": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus (土豪)": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o (通用)": "openai/gpt-4o",
    "🚀 o1 (推理版)": "openai/o1"
}

# --- 3. 数据库逻辑 ---
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
        logger.error(f"数据库保存失败: {e}")

db = load_db()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 4. 菜单逻辑 ---
def get_main_menu(uid):
    is_admin = (uid == ADMIN_ID)
    is_auth = str(uid) in db["users"]
    
    buttons = [["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"], ["🧠 GPT-4o (通用)", "🚀 o1 (推理版)"]]
    
    if is_admin:
        buttons.append(["🔑 生成10U/5U额度Key", "📊 系统总池余额"])
    elif is_auth:
        buttons.append(["💳 查看我的余额"])
    
    buttons.append(["🛑 停止/清理记忆", "☎️ 联系客服"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 5. 指令与消息处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"用户 {uid} 触发 /start")
    menu = get_main_menu(uid)
    
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        keyboard = [[InlineKeyboardButton("📩 点击联系客服申请", url=KEFU_URL)]]
        await update.message.reply_text(
            f"👋 您好！您的 ID 是：`{uid}`\n⚠️ 当前未获得授权。请输入激活密钥或联系客服。",
            reply_markup=menu, parse_mode='Markdown'
        )
        await update.message.reply_text("快速客服通道：", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(f"✅ 认证通过！请选择模型开始提问。", reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    logger.info(f"收到用户 {uid} 消息: {text}")

    # 管理员功能：生成 30 天/5U 额度密钥
    if text == "🔑 生成10U/5U额度Key" and uid == ADMIN_ID:
        key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][key] = {"days": 30, "balance": 5.0} # 这里设置卖给用户的虚拟额度
        save_db(db)
        await update.message.reply_text(f"🔑 已生成密钥：`{key}`\n💰 虚拟额度：$5.00\n⏳ 有效期：30天")
        return

    # 管理员功能：查询 OpenRouter 总余额
    if text == "📊 系统总池余额" and uid == ADMIN_ID:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            total = r.json()['data'].get('limit_remaining', '未设限')
            await update.message.reply_text(f"📊 OpenRouter 账户总池剩余：${total}")
        return

    # 激活码识别
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            expire_at = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": expire_at, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！额度 ${info['balance']} 已入账。", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效。")
        return

    # 用户余额查询
    if text == "💳 查看我的余额":
        u = db["users"].get(str(uid))
        if u: await update.message.reply_text(f"💰 剩余虚拟额度：${round(u['balance'], 2)}\n⏰ 到期时间：{u['expire']}")
        return

    # 权限拦截
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        await start(update, context); return
    
    # 虚拟额度检查
    if uid != ADMIN_ID and db["users"][str(uid)]["balance"] <= 0:
        await update.message.reply_text("🚫 您的虚拟额度已用尽，请联系客服续费。"); return

    # 模型与 AI 逻辑
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 已切换至：{text}")
    elif text == "🛑 停止/清理记忆":
        context.user_data.clear()
        await update.message.reply_text("⏹ 记忆已重置。")
    elif text in ["☎️ 联系客服", "✨ 申请授权"]:
        await update.message.reply_text(f"客服链接：{KEFU_URL}")
    elif text:
        await run_ai_logic(update, context, text)

async def run_ai_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    uid = update.effective_user.id
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet (省钱)"])
    status_msg = await update.message.reply_text("🔍 正在思考...")
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=context.user_data["history"][-6:]
        )
        ans = response.choices[0].message.content
        
        # 扣费逻辑：从虚拟余额减去消耗
        cost = (response.usage.total_tokens / 1000) * 0.02 # 预估均价
        billing_info = ""
        if uid != ADMIN_ID:
            db["users"][str(uid)]["balance"] -= cost
            save_db(db)
            billing_info = f"\n\n💸 本次消耗：${round(cost, 4)}\n💰 剩余额度：${round(db['users'][str(uid)]['balance'], 2)}"

        await status_msg.edit_text(f"{ans[:3800]}{billing_info}")
        context.user_data["history"].append({"role": "assistant", "content": ans})
    except Exception as e:
        logger.error(f"AI 出错: {e}")
        await status_msg.edit_text(f"❌ 运行异常: {str(e)}")

# --- 6. 启动 ---
def main():
    logger.info("🚀 正在启动机器人并强制接管控制权...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # drop_pending_updates=True 会踢掉其他所有项目的 Token 连接
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
