import os

# 1. 密钥：从 Railway 环境变量读取 (Variable 名字需保持一致)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 2. 模型：根据你截图显示，目前最强的是 Opus 4.5
# 备选：anthropic/claude-3.7-sonnet:thinking (支持思考模式)
MODEL_ID = os.getenv("MODEL_ID", "anthropic/claude-4.5-opus")
BASE_URL = "https://openrouter.ai/api/v1"

# 3. 提示词：指导 Claude 如何输出代码
SYSTEM_PROMPT = """你是一个专业的全栈工程师。
要求：
1. 必须提供完整、可直接运行的代码。
2. 每个文件必须放在独立的代码块(```)中。
3. 代码块第一行格式：# filename: 文件名.扩展名
"""
