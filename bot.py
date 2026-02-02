import os, io, re, logging, secrets, string, httpx
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.constants import ParseMode

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
KEFU_URL = "https://t.me/your_telegram_id" # 可以在这里改你的客服链接

# 内部运行状态
current_model = "anthropic/claude-3.7-sonnet:thinking"
authorized_users = {int(ADMIN_ID)} if ADMIN_ID else set()
valid_keys = {}

# 强制合并输出，防止文件太碎
SYSTEM_PROMPT = """你是一个专业的全栈工程师。
1. 请提供完整、可直接运行的代码。
2. 请将修复后的代码合并到一个完整的文件中输出，不要拆分成多个代码块。
3. 代码块第一行必须是：# filename: 文件名.扩展名
"""

logging.basicConfig(level=logging.INFO)
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# --- 菜单逻辑 ---
def get_menu(uid):
    """根据身份返回不同的底部菜单"""
    is_admin = str(uid) == str(ADMIN_ID)
    is_auth = uid in authorized_users
    
    if is_admin:
        return ReplyKeyboardMarkup([
            ["💰 切换 3.7 (省钱)", "💎 切换 4.5 (土豪)"],
            ["🔑 生成激活码", "💳 查看余额"],
            ["🛑 停止思考", "☎️ 联系客服"]
        ], resize_keyboard=True)
    elif is_auth:
        return ReplyKeyboardMarkup([
            ["💰 3.7 (省钱)", "💎 4.5 (土豪)"],
            ["🛑 停止思考", "☎️ 联系客服"]
        ], resize_keyboard=True)
    else:
        # 陌生人看到的菜单
        return ReplyKeyboardMarkup([["✨ 申请授权", "☎️ 联系客服"]], resize_keyboard=True)

async def get_balance():
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    async with httpx.AsyncClient() as c:
        try:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers, timeout=5)
            return r.json()['data']['limit_remaining']
        except: return "查询失败"

# --- 核心指令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    menu = get_menu(uid)
    msg = "🚀 欢迎使用私人 AI 编程助手！\n\n"
    if uid not in authorized_users and str(uid) != str(ADMIN_ID):
        msg += "⚠️ 您当前未获得授权。请输入激活码或点击下方按钮联系客服。"
    else:
        msg += f"✅ 状态：已授权\n🎯 当前模型：{current_model}"
    await update.message.reply_text(msg, reply_markup=menu)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 处理激活码
    if text in valid_keys:
        authorized_users.add(uid)
        del valid_keys[text]
        await update.message.reply_text("🎉 激活成功！全功能菜单已开启。", reply_markup=get_menu(uid))
        return

    # 2. 处理菜单按钮
    if text == "💰 切换 3.7 (省钱)":
        current_model = "anthropic/claude-3.7-sonnet:thinking"
        await update.message.reply_text("已切换至 3.7 Sonnet (高性价比)")
        return
    if text == "💎 切换 4.5 (土豪)":
        current_model = "anthropic/claude-4.5-opus"
        await update.message.reply_text("已切换至 4.5 Opus (请注意余额消耗)")
        return
    if text == "💳 查看余额":
        bal = await get_balance()
        await update.message.reply_text(f"💰 账户剩余：<b>${bal}</b>", parse_mode='HTML')
        return
    if text == "🔑 生成激活码" and str(uid) == str(ADMIN_ID):
        key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
        valid_keys[key] = uid
        await update.message.reply_text(f"🔑 新密钥：`{key}`\n(直接发给用户即可)", parse_mode='Markdown')
        return
    if text == "🛑 停止思考":
        context.user_data.clear()
        await update.message.reply_text("⏹ 已强制中断并清理上下文。")
        return
    if text in ["☎️ 联系客服", "✨ 申请授权"]:
        await update.message.reply_text(f"请联系管理员申请授权：\n{KEFU_URL}")
        return

    # 3. 权限校验
    if uid not in authorized_users and str(uid) != str(ADMIN_ID):
        await start(update, context)
        return

    # 4. 调用 AI
    await process_ai(update, context, text)

async def process_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    status_msg = await update.message.reply_text(f"🔍 {current_model.split('/')[-1]} 正在思考...")
    try:
        response = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
        
        # 提取并发送文件
        blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)\n```", reply)
        # 过滤掉正文中的长代码，让对话框清爽
        text_only = re.sub(r"```(?:\w+)?\n[\s\S]*?\n```", "【代码已打包为下方文件】", reply)
        
        await status_msg.edit_text(f"<b>分析结果：</b>\n<pre>{text_only[:3500]}</pre>", parse_mode='HTML')

        for i, code in enumerate(blocks):
            name_match = re.search(r"#\s*filename:\s*([\w\.\-]+)", code)
            fname = name_match.group(1) if name_match else f"solution_{i+1}.py"
            f_io = io.BytesIO(code.encode('utf-8'))
            f_io.name = fname
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f_io)
    except Exception as e:
        await status_msg.edit_text(f"❌ 运行错误: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in authorized_users and str(uid) != str(ADMIN_ID):
        await start(update, context)
        return
    
    status_msg = await update.message.reply_text("📥 收到文件，正在深度读取内容...")
    try:
        doc = update.message.document
        new_file = await context.bot.get_file(doc.file_id)
        f_bytes = await new_file.download_as_bytearray()
        content = f_bytes.decode('utf-8', errors='ignore')
        caption = update.message.caption or "分析代码逻辑并给出重构建议"
        await status_msg.delete()
        await process_ai(update, context, f"【文件分析】文件名: {doc.file_name}\n内容:\n{content}\n要求: {caption}")
    except Exception as e:
        await status_msg.edit_text(f"❌ 文件解析失败: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
