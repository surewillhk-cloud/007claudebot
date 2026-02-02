import os, io, re, logging, secrets, string
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler, CallbackQueryHandler

# --- 配置中心 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MODEL_ID = os.getenv("MODEL_ID", "anthropic/claude-4.5-opus")
ADMIN_ID = os.getenv("ADMIN_ID") # 在 Railway 设置你的数字 ID

# 存储数据 (生产环境建议用数据库，这里先用内存演示)
authorized_users = set() 
if ADMIN_ID: authorized_users.add(int(ADMIN_ID))
valid_keys = {} # 格式: {密钥: 生成者ID}

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 辅助函数 ---
def generate_key(length=12):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))

# --- 指令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in authorized_users:
        await update.message.reply_text("✅ 您已获得授权，请直接发送需求或文件。")
    else:
        keyboard = [[InlineKeyboardButton("📩 联系客服申请授权", url="https://t.me/@ch007b")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⛔ 您尚未获得授权。\n请联系客服获取激活密钥后发送给机器人。", reply_markup=reply_markup)

async def make_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员生成密钥"""
    if str(update.effective_user.id) != str(ADMIN_ID): return
    new_key = generate_key()
    valid_keys[new_key] = update.effective_user.id
    await update.message.reply_text(f"🔑 成功生成密钥：\n`{new_key}`\n请将其发给用户。")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 检查是否是激活尝试
    if text in valid_keys:
        authorized_users.add(uid)
        del valid_keys[text]
        await update.message.reply_text("🎉 激活成功！您现在可以开始使用 Claude 4.5 了。")
        return

    # 2. 权限拦截
    if uid not in authorized_users:
        await start(update, context)
        return

    # 3. 正常 AI 逻辑 (此处调用你之前的 process_ai 逻辑)
    await process_ai(update, context, text)

# --- 这里的 process_ai 和 handle_doc 保持之前版本逻辑，仅需注意调用方式 ---
async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    # (保持之前处理 OpenAI 请求的代码)
    status_msg = await update.message.reply_text("⏳ Claude 正在思考...")
    try:
        response = client.chat.completions.create(model=MODEL_ID, messages=[{"role":"user","content":prompt}])
        await status_msg.edit_text(response.choices[0].message.content[:4000])
    except Exception as e:
        await status_msg.edit_text(f"❌ 错误: {str(e)}")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in authorized_users:
        await start(update, context)
        return
    # (保持之前 handle_document 的逻辑)
    await update.message.reply_text("📥 文件已收到，正在分析...")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("makekey", make_key)) # 管理员指令
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.run_polling()

if __name__ == "__main__":
    main()
