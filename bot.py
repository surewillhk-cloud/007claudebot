import os, io, re, logging, secrets, string
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置中心 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MODEL_ID = os.getenv("MODEL_ID", "anthropic/claude-4.5-opus")
ADMIN_ID = os.getenv("ADMIN_ID") # 记得在 Railway 设置你的数字 ID

# 内存授权系统
authorized_users = set()
if ADMIN_ID: authorized_users.add(int(ADMIN_ID))
valid_keys = {}

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# 强制合并输出的提示词
SYSTEM_PROMPT = """你是一个专业的全栈工程师。
1. 请提供完整、可直接运行的代码。
2. 严禁分段提供多个小文件，除非用户明确要求。
3. 请将所有相关的修改合并到一个主要文件中输出。
4. 代码块第一行格式：# filename: 文件名.扩展名
"""

async def check_auth(update: Update):
    if update.effective_user.id not in authorized_users:
        keyboard = [[InlineKeyboardButton("📩 联系客服申请授权", url="https://t.me/你的客服ID")]]
        await update.message.reply_text("⛔ 您尚未获得授权。请输入激活密钥或联系客服。", reply_markup=InlineKeyboardMarkup(keyboard))
        return False
    return True

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    status_msg = await update.message.reply_text("⏳ Claude 4.5 正在全力编码中...")
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
        
        # 提取并发送代码文件
        blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", reply)
        await status_msg.edit_text(reply[:4000])

        for i, code in enumerate(blocks):
            name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", code)
            fname = name_match.group(1) if name_match else f"solution_{i+1}.py"
            f_io = io.BytesIO(code.encode('utf-8'))
            f_io.name = fname
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)
    except Exception as e:
        await status_msg.edit_text(f"❌ 运行错误: {str(e)}")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 密钥激活逻辑
    if text in valid_keys:
        authorized_users.add(uid)
        del valid_keys[text]
        await update.message.reply_text("🎉 激活成功！现在可以开始使用。")
        return

    if not await check_auth(update): return
    await process_ai(update, context, text)

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    status_msg = await update.message.reply_text("📥 正在读取并分析文件内容...")
    try:
        doc = update.message.document
        new_file = await context.bot.get_file(doc.file_id)
        f_bytes = await new_file.download_as_bytearray()
        content = f_bytes.decode('utf-8', errors='ignore')
        caption = update.message.caption or "分析代码逻辑"
        await status_msg.delete()
        await process_ai(update, context, f"文件: {doc.file_name}\n内容:\n{content}\n要求: {caption}")
    except Exception as e:
        await status_msg.edit_text(f"❌ 分析失败: {str(e)}")

async def make_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    valid_keys[key] = update.effective_user.id
    await update.message.reply_text(f"🔑 生成密钥：`{key}`")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_msg))
    app.add_handler(CommandHandler("makekey", make_key))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.run_polling(drop_pending_updates=True) # 增加此参数防止更新堆积

if __name__ == "__main__":
    main()
