"""
============================================================
routines.py — 日常作息约束模块
============================================================
定义 Agent 一天中的作息约束。

重要设计原则：
作息是"软约束"而非"硬指令" —— 它们以文本形式注入 LLM Prompt，
引导 Agent 的行为方向，但 LLM 在非约束时段有完全自主权。

只有 22:30-23:00 的"强制回家"是硬约束（由世界引擎强制执行）。

作息约束分为三个级别：
- FREE:     完全自由，LLM 随意决定
- SUGGEST:  建议行为，LLM 通常会遵循但可以偏离
- CONSTRAIN: 强约束，LLM 被明确告知应该做什么
- FORCE:    强制执行，跳过 LLM（由引擎直接处理，如睡眠传送）
============================================================
"""

from enum import Enum


class ConstraintLevel(Enum):
    """约束级别"""
    FREE = "free"           # 完全自由
    SUGGEST = "suggest"     # 建议
    CONSTRAIN = "constrain" # 强约束
    FORCE = "force"         # 强制执行


# ============================================================
# 作息表
# ============================================================

# 通用作息表（适用于所有 Agent）
# 每个时段有：时间范围、描述、约束级别、给 LLM 的提示文本

ROUTINE_TEMPLATE = [
    {
        "start": "06:00",
        "end": "07:00",
        "period": "早晨",
        "level": ConstraintLevel.SUGGEST,
        "prompt": (
            "现在是早晨。你刚睡醒，精力充沛。"
            "你可以在家附近活动，吃早餐，为新的一天做准备。"
            "可以考虑去市场买些新鲜食材，或在家做早餐。"
        ),
    },
    {
        "start": "07:00",
        "end": "08:00",
        "period": "通勤时间",
        "level": ConstraintLevel.CONSTRAIN,
        "prompt": (
            "通勤时间。你应该前往你的工作地点附近。"
            "{work_location_hint}"
        ),
    },
    {
        "start": "08:00",
        "end": "12:00",
        "period": "上午工作",
        "level": ConstraintLevel.CONSTRAIN,
        "prompt": (
            "上午工作时间。你应该在工作地点附近进行与职业相关的活动。"
            "{work_activity_hint}"
        ),
    },
    {
        "start": "12:00",
        "end": "13:00",
        "period": "午餐时间",
        "level": ConstraintLevel.FREE,
        "prompt": (
            "午餐时间！你可以自由选择去哪里吃、和谁一起吃。"
            "咖啡馆、市场或者公园野餐都是不错的选择。"
            "这是一个社交的好时机，可以约上朋友一起。"
        ),
    },
    {
        "start": "13:00",
        "end": "17:00",
        "period": "下午工作",
        "level": ConstraintLevel.SUGGEST,
        "prompt": (
            "下午时段。工作仍然在进行，但节奏可以放慢一些。"
            "你可以在工作间隙做一些自己喜欢的事。"
            "{work_activity_hint}"
        ),
    },
    {
        "start": "17:00",
        "end": "19:00",
        "period": "傍晚自由",
        "level": ConstraintLevel.FREE,
        "prompt": (
            "工作结束！现在是完全自由的时间。"
            "你可以散步、购物、聊天、做任何想做的事。"
            "公园和喷泉是傍晚散步的好去处。"
        ),
    },
    {
        "start": "19:00",
        "end": "21:00",
        "period": "晚间社交",
        "level": ConstraintLevel.FREE,
        "prompt": (
            "晚间社交时间。这是一个和邻居们交流的好时机。"
            "去咖啡馆坐坐，或者在广场上参加社区活动。"
            "主动和其他人聊聊今天发生的事吧。"
        ),
    },
    {
        "start": "21:00",
        "end": "22:30",
        "period": "准备回家",
        "level": ConstraintLevel.SUGGEST,
        "prompt": (
            "时间不早了。你可以开始往家的方向走。"
            "路上可以顺便散个步，但不要离家太远。"
        ),
    },
    {
        "start": "22:30",
        "end": "23:00",
        "period": "强制回家",
        "level": ConstraintLevel.FORCE,
        "prompt": (
            "很晚了，你必须马上回家！不要做任何其他事情，"
            "以最短的路径走回家。明天还有新的一天。"
        ),
    },
    {
        "start": "23:00",
        "end": "06:00",
        "period": "睡眠",
        "level": ConstraintLevel.FORCE,
        "prompt": "",
    },
]


# ============================================================
# 职业相关提示
# ============================================================

# 每个职业的工作地点和工作活动描述
JOB_HINTS: dict[str, dict[str, str]] = {
    "教师": {
        "work_location": "广场附近（那里是社区的教学点）",
        "work_activity": "你可以在广场组织学习活动，或者在咖啡馆备课、批改作业。",
    },
    "花店店主": {
        "work_location": "市场（你的花店在那里）",
        "work_activity": "在花店打理花卉、接待客人。闲暇时可以研究新的花艺设计。",
    },
    "退休老人": {
        "work_location": "没有固定工作地点，你想去哪都行",
        "work_activity": "享受退休生活——下棋、散步、和邻居聊天、打理小花园。去喷泉边最适合。",
    },
    "学生": {
        "work_location": "广场或咖啡馆（学习的好地方）",
        "work_activity": "学习新知识、完成作业、阅读。咖啡馆的安静角落是最好的学习场所。",
    },
    "面包师": {
        "work_location": "市场（你的面包店在那里）",
        "work_activity": "在面包店工作——揉面、烤面包、接待客人。凌晨就开始准备面团了。",
    },
    "医生": {
        "work_location": "广场附近（社区的诊所）",
        "work_activity": "在诊所坐诊、在社区巡诊。你关心每个邻居的健康状况。",
    },
    "艺术家": {
        "work_location": "广场或喷泉（适合写生和创作）",
        "work_activity": "寻找灵感、在广场或喷泉边画画。艺术没有固定的工作时间。",
    },
}


def get_routine_prompt(time_str: str, job: str) -> str:
    """
    根据当前时间和职业，返回应该注入 LLM Prompt 的作息约束文本。

    Args:
        time_str: 当前虚拟时间，格式 "HH:MM"
        job: Agent 的职业

    Returns:
        约束文本。如果当前时段是自由的，返回空字符串。
    """
    # 解析时间
    hour, minute = map(int, time_str.split(":"))
    total_minutes = hour * 60 + minute

    # 找到当前时段
    for slot in ROUTINE_TEMPLATE:
        sh, sm = map(int, slot["start"].split(":"))
        eh, em = map(int, slot["end"].split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em

        # 处理跨午夜的情况（23:00 - 06:00）
        if end_min < start_min:
            if total_minutes >= start_min or total_minutes < end_min:
                pass  # 睡眠时段
            continue

        if start_min <= total_minutes < end_min:
            # 找到匹配的时段
            level = slot["level"]

            # 强制执行级别——返回特殊标记
            if level == ConstraintLevel.FORCE:
                return "[系统指令] " + slot["prompt"] if slot["prompt"] else ""

            # 注入职业相关提示
            job_hint = JOB_HINTS.get(job, {})
            prompt = slot["prompt"].format(
                work_location_hint=job_hint.get("work_location", ""),
                work_activity_hint=job_hint.get("work_activity", ""),
            )

            # 自由时段不需要约束文本
            if level == ConstraintLevel.FREE:
                return ""

            # 添加约束强度前缀
            prefix = {
                ConstraintLevel.SUGGEST: "[建议] ",
                ConstraintLevel.CONSTRAIN: "[应该做] ",
            }.get(level, "")

            return prefix + prompt

    return ""  # 默认无约束
