import os
import io
import re
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置区 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MODEL_ID = os.getenv("MODEL_ID", "anthropic/claude-4.5-opus")
BASE_URL = "https://openrouter.ai/api/v1"
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID") 

SYSTEM_PROMPT = """你是一个专业的全栈工程师。
1. 请提供完整、可运行的代码。
2. 每个文件必须放在独立的代码块(```)中。
3. 代码块第一行格式：# filename: 文件名.扩展名
"""

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(base_url=BASE_URL, api_key=OPENROUTER_API_KEY)

def extract_code_files(text):
    blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", text)
    files = []
    for block in blocks:
        name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", block)
        filename = name_match.group(1) if name_match else f"generated_file_{len(files)+1}.py"
        files.append({"name": filename, "content": block})
    return files

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Claude 4.5 机器人已就绪！\n\n✅ 发送需求文字即可生成代码。\n✅ 发送 .py/.txt 文件并附带说明即可分析。")

async def process_ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str):
    """统一处理 AI 请求逻辑"""
    status_msg = await update.message.reply_text("⏳ Claude 4.5 正在深度分析中...")
    
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

        # 分段发送长文本，防止超过 TG 限制
        if len(reply) > 4000:
            for i in range(0, len(reply), 4000):
                await context.bot.send_message(chat_id=update.effective_chat.id, text=reply[i:i+4000])
        else:
            await status_msg.edit_text(reply)

        for f in files:
            f_io = io.BytesIO(f["content"].encode('utf-8'))
            f_io.name = f["name"]
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)

    except Exception as e:
        logger.error(f"API Error: {e}")
        await status_msg.edit_text(f"❌ API 响应失败: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and str(update.effective_user.id) != str(ALLOWED_USER_ID):
        return
    # 修正：传递 context 参数
    await process_ai_response(update, context, update.message.text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理并分析上传的文件"""
    if ALLOWED_USER_ID and str(update.effective_user.id) != str(ALLOWED_USER_ID):
        return

    status_msg = await update.message.reply_text("📥 正在解析文件...")
    
    try:
        doc = update.message.document
        # 限制只读取常见的文本/代码后缀，防止误读二进制文件导致乱码
        allowed_ext = ('.py', '.txt', '.log', '.js', '.html', '.css', '.json', '.md')
        if not doc.file_name.lower().endswith(allowed_ext):
            await status_msg.edit_text(f"⚠️ 暂时不支持分析 {doc.file_name} 类型的文件。")
            return

        new_file = await context.bot.get_file(doc.file_id)
        file_byte_array = await new_file.download_as_bytearray()
        
        # 尝试解码
        try:
            content = file_byte_array.decode('utf-8')
        except UnicodeDecodeError:
            content = file_byte_array.decode('gbk', errors='ignore')

        user_comment = update.message.caption or "请详细分析这段代码的逻辑并指出潜在问题。"
        full_prompt = f"【文件分析任务】\n文件名: {doc.file_name}\n内容如下:\n---\n{content}\n---\n用户要求: {user_comment}"
        
        await status_msg.delete()
        # 修正：传递 context 参数
        await process_ai_response(update, context, full_prompt)

    except Exception as e:
        await status_msg.edit_text(f"❌ 文件解析失败: {str(e)}")

def main():
    if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
        print("❌ 环境变量缺失！")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🤖 机器人已成功启动...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
