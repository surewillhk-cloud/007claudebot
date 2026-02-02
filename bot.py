import os, io, re, logging, secrets, string, httpx, json
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# --- 核心配置 ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
KEFU_URL = "https://t.me/ch007b" # 👈 你的客服链接
DB_FILE = "users_db.json"

MODELS = {
    "💰 3.7 Sonnet (省钱)": "anthropic/claude-3.7-sonnet:thinking",
    "💎 4.5 Opus (土豪)": "anthropic/claude-4.5-opus",
    "🧠 GPT-4o (通用)": "openai/gpt-4o",
    "🚀 o1 (推理版)": "openai/o1"
}

# --- 数据库操作 ---
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

# --- 菜单生成 ---
def get_main_menu(uid):
    is_admin = (uid == ADMIN_ID)
    is_auth = str(uid) in db["users"]
    
    # 所有已授权用户和管理员都能看到的模型菜单
    buttons = [
        ["💰 3.7 Sonnet (省钱)", "💎 4.5 Opus (土豪)"],
        ["🧠 GPT-4o (通用)", "🚀 o1 (推理版)"]
    ]
    
    # 核心按钮：管理员看总池，用户看个人
    if is_admin:
        buttons.append(["🔑 生成10U/5U额度Key", "📊 查看系统总余额"])
    elif is_auth:
        buttons.append(["💳 查看我的余额"])
    
    buttons.append(["🛑 停止/清理记忆", "☎️ 联系客服"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- 处理逻辑 ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    # 1. 密钥管理 (管理员)
    if text == "🔑 生成10U/5U额度Key" and uid == ADMIN_ID:
        new_key = "KEY-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db["keys"][new_key] = {"days": 30, "balance": 5.0} # 默认给 5U 虚拟额度
        save_db(db)
        await update.message.reply_text(f"🔑 已生成密钥：`{new_key}`\n🎁 内含虚拟额度：$5.00", parse_mode='Markdown')
        return

    # 2. 余额查询逻辑 (分权限)
    if text == "📊 查看系统总余额" and uid == ADMIN_ID:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        async with httpx.AsyncClient() as c:
            r = await c.get("https://openrouter.ai/api/v1/key", headers=headers)
            total = r.json()['data'].get('limit_remaining', '未设限')
            await update.message.reply_text(f"📉 OpenRouter 账户总池剩余：${total}")
        return

    if text == "💳 查看我的余额":
        u_data = db["users"].get(str(uid))
        if u_data:
            rem = round(u_data["balance"], 2)
            exp = u_data["expire"]
            await update.message.reply_text(f"👤 您的个人账户：\n💰 剩余虚拟额度：${rem}\n⏰ 授权到期时间：{exp}")
        return

    # 3. 激活逻辑
    if text.startswith("KEY-"):
        if text in db["keys"]:
            info = db["keys"].pop(text)
            expire_at = (datetime.now() + timedelta(days=info["days"])).strftime("%Y-%m-%d %H:%M:%S")
            db["users"][str(uid)] = {"expire": expire_at, "balance": info["balance"]}
            save_db(db)
            await update.message.reply_text(f"🎉 激活成功！额度 ${info['balance']} 已入账。", reply_markup=get_main_menu(uid))
        else:
            await update.message.reply_text("❌ 密钥无效。")
        return

    # 4. 权限与额度拦截
    if uid != ADMIN_ID:
        u_data = db["users"].get(str(uid))
        if not u_data:
            await update.message.reply_text("⛔ 请先联系客服申请授权。"); return
        if u_data["balance"] <= 0:
            await update.message.reply_text("🚫 您的额度已耗尽，请联系客服续费。"); return

    # 5. 常规功能
    if text in MODELS:
        context.user_data["model"] = MODELS[text]
        await update.message.reply_text(f"🎯 切换成功：{text}")
    elif text == "🛑 停止/清理记忆":
        context.user_data.clear()
        await update.message.reply_text("⏹ 记忆已清空。")
    elif text in ["☎️ 联系客服", "✨ 申请授权"]:
        await update.message.reply_text(f"客服通道：{KEFU_URL}")
    else:
        # 进入 AI 对话扣费流程
        await run_ai_with_billing(update, context, text)

async def run_ai_with_billing(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    uid = update.effective_user.id
    if "history" not in context.user_data: context.user_data["history"] = []
    context.user_data["history"].append({"role": "user", "content": prompt})
    
    model = context.user_data.get("model", MODELS["💰 3.7 Sonnet (省钱)"])
    status_msg = await update.message.reply_text("🔍 思考中...")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=context.user_data["history"][-6:]
        )
        ans = response.choices[0].message.content
        
        # 模拟扣费逻辑 (根据 Token 估算)
        tokens = response.usage.total_tokens
        cost = (tokens / 1000) * 0.02 # 这是一个预估均价，你可以根据模型调整
        
        billing_msg = ""
        if uid != ADMIN_ID:
            db["users"][str(uid)]["balance"] -= cost
            db["users"][str(uid)]["balance"] = max(0, db["users"][str(uid)]["balance"])
            save_db(db)
            billing_msg = f"\n\n💸 本次估算消耗：${round(cost, 4)}\n💰 剩余额度：${round(db['users'][str(uid)]['balance'], 2)}"
        
        await status_msg.edit_text(f"{ans[:3800]}{billing_msg}")
        context.user_data["history"].append({"role": assistant, "content": ans})
    except Exception as e:
        await status_msg.edit_text(f"❌ 出错：{str(e)}")

# ... (main 函数保持不变)
