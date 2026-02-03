import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o": "openai/gpt-4o",
    "🚀 o1": "openai/o1"
}

# --- 数据库 ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"users": {}, "keys": {}}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

db = load_db()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
logging.basicConfig(level=logging.INFO)

# --- 菜单逻辑 ---
def get_main_menu(uid):
    buttons = [["💰 3.7 Sonnet", "💎 4.5 Opus"], ["🧠 GPT-4o", "🚀 o1"]]
    if uid == ADMIN_ID:
        buttons.append(["🔑 生成KEY", "📊 系统余额"])
    else:
        buttons.append(["💳 我的余额", "🛑 停止清理"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 核心处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID and str(uid) not in db["users"]:
        await update.message.reply_text(f"⚠️ 权限不足。你的 ID: `{uid}`\n请联系客服获取激活码。", parse_mode='Markdown')
    else:
        await update.message.reply_text("✅ 认证成功，请选择模型：", reply_markup=get_main_menu(uid))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 管理员生成 KEY (后台逻辑5U，用户显示10U)
    if text == "🔑 生成KEY" and uid == ADMIN_ID:
        key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        # 实际扣费基数为 5.0，但用户显示余额时会显示 10.0
        db["keys"][key] = {"days": 30, "balance": 5.0} 
        save_db(db)
        # 使用 MarkdownV2 的代码块格式，点击即复制
        await update.message.reply_text(f"🔑 新密钥生成成功（点击可复制）：\n\n`{key}`\n\n🎁 内含额度：$10\\.00", parse_mode='MarkdownV2')
        return

    # 激活码逻辑
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            exp = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": exp, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！\n💰 账户额度：$10.00\n⏰ 有效期至：{exp}", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效。")
        return

    # 余额查询 (显示翻倍额度，给用户 10U 的观感)
    if text == "💳 我的余额":
        u = db["users"].get(str(uid))
        if u:
            display_bal = round(u["balance"] * 2, 2) # 逻辑：5U成本对应10U显示
            await update.message.reply_text(f"👤 个人账户信息：\n💰 剩余额度：${display_bal}\n⏰ 到期时间：{u['expire']}")
        return

    # 模型与系统功能
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 已切换至：{text}")
    elif text == "📊 系统余额" and uid == ADMIN_ID:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            bal = r.json()['data'].get('limit_remaining', '未设限')
            await update.message.reply_text(f"📊 官方 API 余额：${bal}")
    elif text == "🛑 停止清理":
        context.user_data.clear()
        await update.message.reply_text("⏹ 已重置会话记忆。")
    elif str(uid) in db["users"] or uid == ADMIN_ID:
        await run_ai(update, context, text)

async def run_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    uid = update.effective_user.id
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet"])
    status = await update.message.reply_text("🔍 正在处理...")
    
    try:
        # 【修改重点】加入 System 指令，限制 AI 废话
        system_prompt = {"role": "system", "content": "你是一个只输出结果的专家。禁止任何废话、分析建议或开场白。直接给出用户要求的核心内容，能简短绝不冗长。"}
        
        response = client.chat.completions.create(
            model=model, 
            messages=[system_prompt] + context.user_data["history"][-6:]
        )
        ans = response.choices[0].message.content
        
        # 扣费逻辑：按 0.02 单价估算
        cost = (response.usage.total_tokens / 1000) * 0.02
        
        info = ""
        if uid != ADMIN_ID:
            db["users"][str(uid)]["balance"] -= cost
            db["users"][str(uid)]["balance"] = max(0, db["users"][str(uid)]["balance"])
            save_db(db)
            # 用户端也显示翻倍扣费信息，保持 10U 总额的一致性
            info = f"\n\n💸 消耗: ${round(cost*2, 4)} | 剩余: ${round(db['users'][str(uid)]['balance']*2, 2)}"
        
        await status.edit_text(f"{ans}{info}")
        context.user_data["history"].append({"role": "assistant", "content": ans})
    except Exception as e:
        await status.edit_text(f"❌ 系统异常: {e}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)
