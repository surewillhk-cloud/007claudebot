import os
import io
import re
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置区 (建议在 Railway Variables 中设置) ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# 默认使用 Claude 4.5 Opus，你也可以在 Railway 改成其他 ID
MODEL_ID = os.getenv("MODEL_ID", "anthropic/claude-4.5-opus")
BASE_URL = "https://openrouter.ai/api/v1"

# [可选] 填入你的 Telegram User ID (数字)，只有你能用。如果不填则所有人都能用。
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID") 

SYSTEM_PROMPT = """你是一个专业的全栈工程师。
1. 请提供完整、可运行的代码。
2. 每个文件必须放在独立的代码块(```)中。
3. 代码块第一行必须注明文件名，格式为：# filename: 文件名.扩展名
"""

# 日志设置
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化客户端
client = OpenAI(base_url=BASE_URL, api_key=OPENROUTER_API_KEY)

def extract_code_files(text):
    """解析回复，提取代码块和文件名"""
    blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", text)
    files = []
    for block in blocks:
        name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", block)
        filename = name_match.group(1) if name_match else f"generated_file_{len(files)+1}.py"
        files.append({"name": filename, "content": block})
    return files

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Claude 4.5 机器人已就绪！\n\n✅ 你可以直接发送编程需求。\n✅ 你也可以直接发送 .py 或 .log 文件给我分析。")

async def process_ai_response(update, prompt_text):
    """通用：向 Claude 发送请求并处理返回"""
    status_msg = await update.message.reply_text("⏳ Claude 4.5 正在处理中...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text}
            ]
        )
        
        reply = response.choices[0].message.content
        files = extract_code_files(reply)

        # 发送文字回复 (截断超长内容)
        await status_msg.edit_text(reply[:4000])

        # 发送生成的文件
        for f in files:
            f_io = io.BytesIO(f["content"].encode('utf-8'))
            f_io.name = f["name"]
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)

    except Exception as e:
        logger.error(f"API Error: {e}")
        await status_msg.edit_text(f"❌ 出错啦: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文字消息"""
    if ALLOWED_USER_ID and str(update.effective_user.id) != str(ALLOWED_USER_ID):
        return
    await process_ai_response(update, update.message.text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送的文件并进行分析"""
    if ALLOWED_USER_ID and str(update.effective_user.id) != str(ALLOWED_USER_ID):
        return

    status_msg = await update.message.reply_text("📥 收到文件，正在读取内容...")
    
    try:
        # 下载文件
        doc = update.message.document
        new_file = await context.bot.get_file(doc.file_id)
        
        file_byte_array = await new_file.download_as_bytearray()
        content = file_byte_array.decode('utf-8', errors='ignore') # 忽略非文本字符
        
        # 组装 Prompt
        user_comment = update.message.caption or "请分析这个文件中的代码逻辑。"
        full_prompt = f"用户上传了文件: {doc.file_name}\n内容如下:\n\n{content}\n\n指令: {user_comment}"
        
        await status_msg.delete() # 删除临时消息
        await process_ai_response(update, full_prompt)

    except Exception as e:
        await status_msg.edit_text(f"❌ 文件读取失败: {str(e)}")

def main():
    if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
        print("❌ 错误: 请检查 Railway 变量配置！")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    # 监听文字
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # 监听文档/文件
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🤖 机器人运行中...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
