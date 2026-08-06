"""
============================================================
base_agent.py — Agent 数据基类
============================================================
定义单个 Agent 的所有属性和基础方法。

Agent = 静态属性 (身份/性格/技能) + 动态状态 (位置/心情/关系/记忆)

设计原则:
- 使用 dataclass，清晰可读，方便序列化
- 动态状态和静态属性分离，方便"重置"（如每天醒来）
- 技能是一个 dict[str, float]，天然支持扩展
============================================================
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from backend.agents.personalities import Personality


@dataclass
class Agent:
    """
    AI Village 中的一个 Agent。

    包含静态身份信息和动态运行时状态。
    所有属性都有详细的注释说明。
    """

    # ========================
    # 静态身份（创建后不变）
    # ========================

    id: str
    """唯一标识符，如 "agent_xiaoming" """

    name: str
    """显示名称，如 "小明" """

    age: int
    """年龄"""

    job: str
    """职业，如 "教师"、"面包师" """

    emoji: str
    """在地图上显示的 emoji 头像，如 "👨‍🏫" """

    home: tuple[int, int]
    """家的坐标 (x, y)。睡眠和某些时段需要回家"""

    personality: Personality
    """性格配置（外向性/开放性/尽责性）"""

    skills: dict[str, float]
    """技能熟练度。key=技能名, value=0~1 熟练度。如 {"教学": 0.9, "园艺": 0.3}"""

    # ========================
    # 动态状态（运行时变化）
    # ========================

    x: int = 0
    """当前 X 坐标"""

    y: int = 0
    """当前 Y 坐标"""

    activity: str = "睡觉"
    """当前活动描述，如 "散步"、"聊天"、"工作" """

    mood: float = 0.7
    """当前心情，0~1（0=很差, 0.5=正常, 1=极好）"""

    energy: float = 0.9
    """当前精力，0~1（0=筋疲力尽, 1=精力充沛）"""

    # ========================
    # 社交状态
    # ========================

    relationships: dict[str, float] = field(default_factory=dict)
    """与其他 Agent 的关系值。{agent_id: -10~+10}。正数=友好，负数=不睦"""

    conversation_cooldown: int = 0
    """对话冷却倒计时（tick 数）。>0 时不能发起新对话，防止话痨"""

    # ========================
    # 记忆
    # ========================

    short_term: deque = field(default_factory=lambda: deque(maxlen=10))
    """短期记忆（最近 10 条，自动限制长度）"""

    long_term_count: int = 0
    """长期记忆中保存的条数（实际数据在 memory/store.py 中）"""

    # ========================
    # 统计
    # ========================

    tick_count: int = 0
    """该 Agent 自启动以来执行的总 tick 数"""

    total_tokens: int = 0
    """该 Agent 累计消耗的 LLM token 数"""

    degradation_count: int = 0
    """降级次数（LLM 失败走规则的次数）"""

    # ========================
    # 方法
    # ========================

    def to_dict(self) -> dict:
        """
        将 Agent 序列化为字典，用于 API 响应和 WebSocket 广播。

        Returns:
            包含 Agent 关键信息的字典（不含完整记忆列表）
        """
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "job": self.job,
            "emoji": self.emoji,
            "x": self.x,
            "y": self.y,
            "activity": self.activity,
            "mood": self.mood,
            "energy": self.energy,
            "skills": self.skills,
            "relationships": {
                aid: round(val, 1)
                for aid, val in self.relationships.items()
            },
            "tick_count": self.tick_count,
            "total_tokens": self.total_tokens,
        }

    def to_detail_dict(self) -> dict:
        """
        将 Agent 的详细信息序列化（含记忆），用于 Agent 详情面板。

        Returns:
            包含完整 Agent 信息的字典
        """
        data = self.to_dict()
        data["personality"] = {
            "extraversion": self.personality.extraversion,
            "openness": self.personality.openness,
            "conscientiousness": self.personality.conscientiousness,
            "traits": self.personality.traits,
            "description": self.personality.describe(),
        }
        data["home"] = list(self.home)
        data["short_term_memories"] = list(self.short_term)
        data["conversation_cooldown"] = self.conversation_cooldown
        return data

    def get_skills_text(self) -> str:
        """
        生成技能描述文本，用于 LLM Prompt。

        技能按熟练度分三档：
        - 精通 (≥0.8): "你能烤出全镇最好的面包"
        - 熟练 (≥0.5): "家常菜不在话下"
        - 入门 (<0.5): "基本的账目能算清楚"

        Returns:
            格式化的技能列表文本
        """
        if not self.skills:
            return "暂无特殊技能。"

        lines = []
        for skill, level in sorted(self.skills.items(), key=lambda x: -x[1]):
            if level >= 0.8:
                desc = self._skill_desc(skill, "精通")
            elif level >= 0.5:
                desc = self._skill_desc(skill, "熟练")
            else:
                desc = self._skill_desc(skill, "入门")
            lines.append(f"- {skill}({desc})")

        return "\n".join(lines)

    def _skill_desc(self, skill: str, tier: str) -> str:
        """根据技能名和等级生成描述。"""
        descriptions = {
            ("烘焙", "精通"): "你能烤出全镇最好的面包，大家都喜欢你做的可颂",
            ("烘焙", "熟练"): "你烤的面包很受欢迎",
            ("烘焙", "入门"): "你能烤些简单的面包",
            ("教学", "精通"): "你是镇上最好的老师，学生都喜欢你的课",
            ("教学", "熟练"): "你教学经验丰富",
            ("教学", "入门"): "你偶尔能教教别人",
            ("花艺", "精通"): "你设计的花束是全镇最美的",
            ("花艺", "熟练"): "你对花艺很有心得",
            ("花艺", "入门"): "你认得大多数花，会简单搭配",
            ("绘画", "精通"): "你的画作充满灵气，有人专程来看",
            ("绘画", "熟练"): "你画得不错，有自己的风格",
            ("绘画", "入门"): "你刚开始学画画，还不太熟练",
            ("诊断", "精通"): "你是镇上最信赖的医生，经验丰富",
            ("诊断", "熟练"): "你能准确诊断大多数常见病",
            ("诊断", "入门"): "你学过一些基础医学知识",
            ("下棋", "精通"): "你的棋艺在镇上罕有对手",
            ("下棋", "熟练"): "你的棋下得不错",
            ("下棋", "入门"): "你刚学会下棋不久",
            ("烹饪", "精通"): "你做的菜让人回味无穷",
            ("烹饪", "熟练"): "家常菜不在话下",
            ("烹饪", "入门"): "你能做几道简单的菜",
            ("摄影", "精通"): "你拍的照片能捕捉最美的瞬间",
            ("摄影", "熟练"): "你拍照技术不错",
            ("摄影", "入门"): "你喜欢拍照但还在学习中",
            ("木工", "精通"): "你能做出精美的木制家具",
            ("木工", "熟练"): "家里的东西坏了自己能修",
            ("木工", "入门"): "你会一些简单的木工活",
            ("音乐", "精通"): "你精通乐器，弹奏动人",
            ("音乐", "熟练"): "你会弹几首曲子",
            ("音乐", "入门"): "你刚开始学乐器",
            ("创意", "精通"): "你的灵感如泉涌，总有新奇的点子",
            ("创意", "熟练"): "你经常有些不错的创意",
            ("创意", "入门"): "你偶尔能想出些新点子",
        }
        return descriptions.get((skill, tier), f"{tier}水平")

    def get_relationships_text(self) -> str:
        """
        生成关系描述文本，用于 LLM Prompt。

        Returns:
            类似 "小明(朋友, +3), 老王(忘年交, +5)" 的文本
        """
        if not self.relationships:
            return "你目前还不认识镇上的其他人。"

        lines = []
        for agent_id, value in self.relationships.items():
            if value >= 6:
                label = "挚友"
            elif value >= 3:
                label = "朋友"
            elif value >= 1:
                label = "认识"
            elif value >= -1:
                label = "陌生"
            elif value >= -5:
                label = "有点不愉快"
            else:
                label = "关系紧张"
            lines.append(f"{agent_id}({label}, {value:+.1f})")

        return ", ".join(lines)

    def modify_mood(self, delta: float):
        """调整心情，并钳制在 [0, 1] 范围内。"""
        self.mood = max(0.0, min(1.0, self.mood + delta))

    def modify_energy(self, delta: float):
        """调整精力，并钳制在 [0, 1] 范围内。"""
        self.energy = max(0.0, min(1.0, self.energy + delta))

    def modify_relationship(self, other_id: str, delta: float):
        """
        调整与另一个 Agent 的关系值，并钳制在 [-10, 10] 范围内。

        如果之前没有关系记录，自动初始化为 0。
        """
        current = self.relationships.get(other_id, 0.0)
        self.relationships[other_id] = max(-10.0, min(10.0, current + delta))

    def reset_daily(self):
        """
        每日重置 —— 在新一天开始时调用。
        重置心情到基准值，精力回满。
        """
        self.mood = 0.7
        self.energy = 0.9
        self.activity = "刚起床"
        self.conversation_cooldown = 0
