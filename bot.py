import os, io, re, logging, secrets, string
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置中心 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # 你的 Telegram 数字 ID

# 状态管理
authorized_users = {int(ADMIN_ID)} if ADMIN_ID else set()
valid_keys = {}
current_model = "anthropic/claude-3.7-sonnet:thinking" # 默认开启强力且省钱的模型

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 菜单定义 ---
def get_menu(uid):
    if str(uid) == str(ADMIN_ID):
        return ReplyKeyboardMarkup([
            ["💰 切换 3.7 Sonnet (省钱)", "💎 切换 4.5 Opus (土豪)"],
            ["🎫 生成激活码", "🛑 强行终止并清理"],
            ["📊 查看当前模型"]
        ], resize_keyboard=True)
    elif uid in authorized_users:
        return ReplyKeyboardMarkup([["🛑 强行终止并清理"]], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([["📩 申请授权", "🔑 输入密钥"]], resize_keyboard=True)

# --- 处理逻辑 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        "👋 欢迎使用 Claude 4.5/3.7 编程助手。\n请使用下方菜单进行操作。",
        reply_markup=get_menu(uid)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    uid = update.effective_user.id
    text = update.message.text

    # 1. 权限拦截与申请逻辑
    if text == "📩 申请授权":
        await update.message.reply_text(f"请将您的 ID 发送给管理员: `{uid}`\n管理员生成密钥后请在此输入。")
        return
    
    if text == "🔑 输入密钥":
        await update.message.reply_text("请直接发送您获得的 12 位激活密钥。")
        return

    # 2. 密钥激活检查
    if len(text) == 12 and text.isupper() and text in valid_keys:
        authorized_users.add(uid)
        del valid_keys[text]
        await update.message.reply_text("🎉 激活成功！菜单已更新。", reply_markup=get_menu(uid))
        return

    # 3. 管理员专用功能
    if str(uid) == str(ADMIN_ID):
        if "💰 切换 3.7 Sonnet" in text:
            current_model = "anthropic/claude-3.7-sonnet:thinking"
            await update.message.reply_text(f"✅ 已切至省钱模式: {current_model}")
            return
        if "💎 切换 4.5 Opus" in text:
            current_model = "anthropic/claude-4.5-opus"
            await update.message.reply_text(f"⚠️ 已切至土豪模式: {current_model}\n请注意余额！")
            return
        if text == "🎫 生成激活码":
            new_key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
            valid_keys[new_key] = uid
            await update.message.reply_text(f"🔑 激活密钥已生成:\n`{new_key}`")
            return
        if text == "📊 查看当前模型":
            await update.message.reply_text(f"当前正在运行: \n`{current_model}`")
            return

    # 4. 强行终止逻辑
    if "🛑 强行终止" in text:
        context.user_data['abort'] = True # 设置中断信号
        await update.message.reply_text("⏹ 已尝试中断当前 AI 任务并重置状态。")
        return

    # 5. AI 任务处理
    if uid in authorized_users:
        await process_ai(update, context, text)
    else:
        await update.message.reply_text("⛔ 您尚未获得授权，请点击“申请授权”。", reply_markup=get_menu(uid))

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    status_msg = await update.message.reply_text(f"🔍 使用 {current_model.split('/')[-1]} 思考中...")
    try:
        # 重置中断信号
        context.user_data['abort'] = False
        
        response = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": prompt}],
            timeout=120
        )
        
        # 检查是否在等待期间被用户按了停止
        if context.user_data.get('abort'):
            await status_msg.edit_text("✅ 任务已手动取消。")
            return

        reply = response.choices[0].message.content
        await status_msg.edit_text(f"<b>Claude 结果:</b>\n\n{reply[:4000]}", parse_mode='HTML')
        
        # 自动提取代码文件并发送 (逻辑同前)
    except Exception as e:
        await status_msg.edit_text(f"❌ 运行错误: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message)) # 文件也走同样的逻辑
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
