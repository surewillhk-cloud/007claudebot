import os, io, re, logging, secrets, string, httpx
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ParseMode

# --- 配置区 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
KEFU_URL = "https://t.me/your_kefu_id" # 替换为您的客服链接

# 内部状态
current_model = "anthropic/claude-3.7-sonnet:thinking"
authorized_users = {int(ADMIN_ID)} if ADMIN_ID else set()
valid_keys = {}

# 菜单配置
def get_main_menu(uid):
    if str(uid) == str(ADMIN_ID):
        return ReplyKeyboardMarkup([
            ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
            ["🔑 生成激活密钥", "💳 查看账户余额"],
            ["🛑 停止/清理", "☎️ 联系客服"]
        ], resize_keyboard=True)
    elif uid in authorized_users:
        return ReplyKeyboardMarkup([
            ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
            ["🛑 停止/清理", "☎️ 联系客服"]
        ], resize_keyboard=True)
    else:
        return None # 未授权用户不显示菜单

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 核心功能函数 ---

async def get_balance():
    """从 OpenRouter 获取实时余额"""
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    async with httpx.AsyncClient() as c:
        try:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            data = r.json()
            # limit_remaining 是剩余额度 (USD)
            return data['data']['limit_remaining']
        except: return "未知"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    menu = get_main_menu(uid)
    
    if not menu:
        keyboard = [[InlineKeyboardButton("📩 点击此处联系客服申请", url=KEFU_URL)]]
        await update.message.reply_text(
            "👋 您好！这是私人 AI 编程助手。\n⚠️ 您目前尚未获得授权，请联系客服获取激活码。",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(f"✅ 欢迎回来！当前模型：{current_model}", reply_markup=menu)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    uid = update.effective_user.id
    text = update.message.text.strip()

    # 1. 密钥激活逻辑
    if text in valid_keys:
        authorized_users.add(uid)
        del valid_keys[text]
        await update.message.reply_text("🎉 恭喜！授权已激活。", reply_markup=get_main_menu(uid))
        return

    # 2. 菜单指令拦截
    if text == "💰 3.7 Sonnet (省钱)":
        current_model = "anthropic/claude-3.7-sonnet:thinking"
        await update.message.reply_text(f"已切换至 3.7 Sonnet（高性价比）")
        return
    if text == "💎 4.5 Opus (土豪)":
        current_model = "anthropic/claude-4.5-opus"
        await update.message.reply_text(f"已切换至 4.5 Opus（昂贵但强大）")
        return
    if text == "🔑 生成激活密钥" and str(uid) == str(ADMIN_ID):
        key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
        valid_keys[key] = uid
        await update.message.reply_text(f"新密钥已生成：\n`{key}`", parse_mode='Markdown')
        return
    if text == "💳 查看账户余额":
        bal = await get_balance()
        await update.message.reply_text(f"💰 您的 OpenRouter 剩余额度约为：<b>${bal}</b>", parse_mode='HTML')
        return
    if text == "🛑 停止/清理":
        context.user_data.clear()
        await update.message.reply_text("📴 上下文已清理，当前所有操作已中断。")
        return
    if text == "☎️ 联系客服":
        await update.message.reply_text(f"客服通道：{KEFU_URL}")
        return

    # 3. 权限检查
    if uid not in authorized_users:
        await start(update, context)
        return

    # 4. 正常 AI 请求
    await process_ai(update, context, text)

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    status_msg = await update.message.reply_text(f"🔍 使用 {current_model.split('/')[-1]} 分析中...")
    try:
        response = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
        
        # 优化显示：使用 <pre> 包装代码感内容
        await status_msg.edit_text(f"<b>Claude 响应：</b>\n<pre>{reply[:3500]}</pre>", parse_mode='HTML')
        
        # 提取文件逻辑 (此处省略，保持之前的文件提取代码即可)
    except Exception as e:
        await status_msg.edit_text(f"❌ 错误：{str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # 别忘了处理文件发送 handle_doc
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
