import os, io, re, logging
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from config import OPENROUTER_API_KEY, TELEGRAM_TOKEN, MODEL_ID, BASE_URL, SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)
# 初始化 OpenRouter 客户端
client = OpenAI(base_url=BASE_URL, api_key=OPENROUTER_API_KEY)

async def handle_code_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    if not user_input: return
    
    status_msg = await update.message.reply_text("正在调用 Claude 4.5 处理您的代码需求...")

    try:
        # 调用 OpenRouter API
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ]
        )
        
        reply_text = response.choices[0].message.content
        
        # 1. 发送文字说明 (截断保护)
        display_text = reply_text[:4000] if len(reply_text) < 4000 else reply_text[:3900] + "...\n(说明过长，请查看下方文件)"
        await status_msg.edit_text(display_text)

        # 2. 提取代码块并打包文件
        code_blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", reply_text)
        
        for i, code in enumerate(code_blocks):
            # 搜索文件名标识
            name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", code)
            fname = name_match.group(1) if name_match else f"code_{i+1}.py"
            
            # 内存流转换
            file_stream = io.BytesIO(code.encode('utf-8'))
            file_stream.name = fname
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_stream,
                caption=f"✅ 已生成文件: {fname}"
            )

    except Exception as e:
        await status_msg.edit_text(f"❌ 发生错误: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_request))
    print("🚀 机器人已启动并连接至 OpenRouter...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
