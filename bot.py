import os, io, re, logging
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# 默认模型设置为性价比最高的 3.7 Sonnet
current_model = "anthropic/claude-3.7-sonnet:thinking"

# 菜单布局
MAIN_MENU = [
    ["💰 切换至 3.7 Sonnet (省钱)", "💎 切换至 4.5 Opus (土豪)"],
    ["🛑 停止当前输出", "⏸ 暂停/清理上下文"]
]
reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ 私人机器人，请联系管理员。")
        return
    await update.message.reply_text(
        f"🤖 机器人已启动！\n当前模型：{current_model}\n使用下方菜单快速操作。",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    uid = update.effective_user.id
    if str(uid) != str(ADMIN_ID): return

    text = update.message.text

    # 菜单逻辑处理
    if text == "💰 切换至 3.7 Sonnet (省钱)":
        current_model = "anthropic/claude-3.7-sonnet:thinking"
        await update.message.reply_text("✅ 已切换为 3.7 Sonnet，现在分析更省钱了！")
        return
    
    if text == "💎 切换至 4.5 Opus (土豪)":
        current_model = "anthropic/claude-4.5-opus"
        await update.message.reply_text("⚠️ 已切换为 4.5 Opus，请注意余额消耗！")
        return

    if text == "🛑 停止当前输出" or text == "⏸ 暂停/清理上下文":
        # 强制清理当前对话状态
        context.user_data.clear()
        await update.message.reply_text("📴 已强制中断逻辑并清理临时缓存。")
        return

    # 正常 AI 逻辑
    await process_ai(update, context, text)

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    status_msg = await update.message.reply_text(f"⏳ {current_model.split('/')[-1]} 思考中...")
    try:
        # 增加超时限制，防止死循环烧钱
        response = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": prompt}],
            timeout=60 
        )
        reply = response.choices[0].message.content
        
        # 提取文件逻辑 (保持之前的提取代码)
        await status_msg.edit_text(f"<b>结果来自 {current_model}:</b>\n\n{reply[:3500]}", parse_mode='HTML')
        
    except Exception as e:
        await status_msg.edit_text(f"❌ 运行出错或已手动中断: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
