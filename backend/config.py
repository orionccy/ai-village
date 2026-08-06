"""
AI Village 全局配置模块
=======================
从 .env 文件和环境变量读取所有配置项。

设计原则:
- 所有可调参数集中在一个文件，方便修改
- 提供合理的默认值，即使不配置 .env 也能跑（LLM 降级为规则模式）
- 使用 python-dotenv 加载 .env 文件
"""

import os
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件
load_dotenv()


# ============================================================
# LLM 配置
# ============================================================

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
"""DeepSeek API Key，从 https://platform.deepseek.com/api_keys 获取"""

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
"""DeepSeek API 的基础 URL，使用 OpenAI 兼容接口"""

DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
"""模型名称。deepseek-chat = DeepSeek Flash (推荐)"""

LLM_TIMEOUT_SECONDS = 5.0
"""LLM 调用超时时间（秒）。超过此时间自动走降级策略"""

LLM_MAX_RETRIES = 1
"""LLM 调用最大重试次数"""

LLM_ENABLED = bool(DEEPSEEK_API_KEY)
"""是否启用 LLM。无 API Key 时自动降级为纯规则模式"""


# ============================================================
# 世界引擎配置
# ============================================================

TICK_INTERVAL_SECONDS = 1.5
"""每个 tick 的间隔时间（真实秒）。1.5 秒 = 15 虚拟分钟"""

TIME_SPEED_MULTIPLIER = 10
"""时间加速倍率。1 真实秒 = 10 虚拟分钟"""

DAY_START_HOUR = 6
"""一天开始时间（虚拟小时），6 点天亮"""

DAY_END_HOUR = 23
"""一天结束时间（虚拟小时），23 点强制睡觉"""

SLEEP_DURATION_SECONDS = 3.0
"""睡眠阶段持续的真实秒数。23:00-06:00 的快进等待时间"""

MAP_WIDTH = 10
"""地图宽度（格子数）"""

MAP_HEIGHT = 10
"""地图高度（格子数）"""

AGENT_PERCEPTION_RANGE = 3
"""Agent 感知范围（曼哈顿距离），能"看到"3 格内的人和地点"""


# ============================================================
# Agent 配置
# ============================================================

NEARBY_DISTANCE = 1
"""判定"相邻"的距离（格数）。用于对话触发条件"""

CONVERSATION_COOLDOWN_TICKS = 3
"""对话冷却时间（tick 数）。防止同一对人每 tick 都聊"""

MAX_CONVERSATION_ROUNDS = 4
"""单次对话最大轮数"""

MIN_CONVERSATION_ROUNDS = 2
"""单次对话最小轮数"""

MOOD_BASELINE = 0.7
"""心情基准值。每天醒来后重置到此值"""

ENERGY_MORNING = 0.9
"""早晨初始精力值"""


# ============================================================
# 记忆系统配置
# ============================================================

SHORT_TERM_MEMORY_SIZE = 10
"""短期记忆条数（始终带入 LLM 上下文）"""

LONG_TERM_MEMORY_MAX = 100
"""长期记忆最大条数，超出时触发遗忘"""

RELEVANT_MEMORY_COUNT = 3
"""按标签匹配取相关记忆的条数"""


# ============================================================
# 监测配置
# ============================================================

EVALUATION_INTERVAL_TICKS = 20
"""LLM-as-Judge 评估间隔（tick 数）"""


# ============================================================
# 路径配置
# ============================================================

import os as _os

# 项目根目录
PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

# 数据目录
DATA_DIR = _os.path.join(PROJECT_ROOT, "backend", "data")

# Agent 配置文件
AGENTS_CONFIG_PATH = _os.path.join(DATA_DIR, "agents.json")

# 技能池配置文件
SKILLS_POOL_PATH = _os.path.join(DATA_DIR, "skills_pool.json")

# 记忆存储目录
MEMORIES_DIR = _os.path.join(DATA_DIR, "memories")

# 前端静态文件目录
FRONTEND_DIR = _os.path.join(PROJECT_ROOT, "frontend")
