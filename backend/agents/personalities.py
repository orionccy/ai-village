"""
============================================================
personalities.py — 性格系统
============================================================
大五人格 (Big Five / OCEAN) 简化版，只取 3 个维度：

1. 外向性 (Extraversion) — 0=内向独处, 1=热衷社交
2. 开放性 (Openness)     — 0=保守传统, 1=好奇探索
3. 尽责性 (Conscientiousness) — 0=随性散漫, 1=严谨自律

为什么只选 3 个？
- 宜人性 (Agreeableness) 和 神经质 (Neuroticism) 在多 Agent 模拟中
  更多体现在对话语气和情绪反应上，由 LLM 自行发挥更有趣
- 3 个维度已足够区分 7 个 Agent 的行为模式
- 减少 Prompt 复杂度，让 LLM 有更多创造空间

每个性格维度都配有"LLM 行为指南"文本，会注入到决策 Prompt 中。
============================================================
"""

from dataclasses import dataclass, field


@dataclass
class Personality:
    """
    一个 Agent 的性格配置。

    Attributes:
        extraversion: 外向性 0~1
        openness: 开放性 0~1
        conscientiousness: 尽责性 0~1
        traits: 性格特征标签列表，如 ["热情", "健谈"]
    """

    extraversion: float
    openness: float
    conscientiousness: float
    traits: list[str] = field(default_factory=list)

    def describe(self) -> str:
        """
        生成一段描述此性格的文本。

        Returns:
            类似 "你是一个外向开朗、好奇心强、做事严谨的人。" 的描述
        """
        parts = []

        if self.extraversion >= 0.7:
            parts.append("外向开朗，喜欢和人交流")
        elif self.extraversion <= 0.3:
            parts.append("内向安静，享受独处时光")
        else:
            parts.append("性格适中，既喜欢社交也享受独处")

        if self.openness >= 0.7:
            parts.append("好奇心强，喜欢尝试新事物")
        elif self.openness <= 0.3:
            parts.append("保守传统，喜欢熟悉的事物和环境")
        else:
            parts.append("对新事物保持开放但不激进")

        if self.conscientiousness >= 0.7:
            parts.append("做事严谨认真，喜欢按计划行事")
        elif self.conscientiousness <= 0.3:
            parts.append("随性自由，不喜欢被规则束缚")
        else:
            parts.append("有一定的自控力，但也能灵活变通")

        return "，".join(parts) + "。"

    def get_behavior_guide(self) -> str:
        """
        生成给 LLM 的行为指南文本。
        这段文字会注入到决策 Prompt 中，指导 LLM 的角色扮演。

        Returns:
            LLM 可理解的行为指南
        """
        guides = []

        # 社交偏好
        if self.extraversion >= 0.7:
            guides.append("- 你热衷社交，在公共场所时主动找人聊天会让你开心")
        elif self.extraversion <= 0.3:
            guides.append("- 你喜欢独处，人多的地方让你有点不自在，更愿意一个人安静做事")

        # 探索偏好
        if self.openness >= 0.7:
            guides.append("- 你对新事物充满好奇，喜欢探索不常去的地方，尝试不同的活动")
        elif self.openness <= 0.3:
            guides.append("- 你偏爱熟悉的日常，习惯去固定的地方，做重复的事让你感到安心")

        # 行动风格
        if self.conscientiousness >= 0.7:
            guides.append("- 你做事有条理，倾向于按时间表行事，答应了的事一定会做到")
        elif self.conscientiousness <= 0.3:
            guides.append("- 你随性而为，不太在意时间安排，想到什么就做什么")

        return "\n".join(guides)

    def get_mood_penalty_multiplier(self) -> float:
        """
        高尽责性的 Agent 在违背作息时心情扣分更多。
        （因为严谨的人更容易因"没按计划"而焦虑）

        Returns:
            心情扣分的倍率
        """
        if self.conscientiousness >= 0.7:
            return 2.0  # 双倍焦虑
        elif self.conscientiousness <= 0.3:
            return 0.5  # 不太在意
        return 1.0


# ============================================================
# 预设性格模板
# ============================================================

# 这些是 7 个 Agent 对应的性格预设。
# 每个预设可以直接用于创建 Agent。

PERSONALITY_PRESETS: dict[str, Personality] = {
    "小明": Personality(
        extraversion=0.7,
        openness=0.6,
        conscientiousness=0.8,
        traits=["热情", "健谈", "负责", "乐于助人"],
    ),
    "小红": Personality(
        extraversion=0.8,
        openness=0.7,
        conscientiousness=0.5,
        traits=["活泼", "社交", "随和", "感性"],
    ),
    "老王": Personality(
        extraversion=0.3,
        openness=0.2,
        conscientiousness=0.9,
        traits=["安静", "规律", "怀旧", "可靠"],
    ),
    "阿花": Personality(
        extraversion=0.5,
        openness=0.9,
        conscientiousness=0.3,
        traits=["好奇", "创意", "随性", "活力"],
    ),
    "小李": Personality(
        extraversion=0.4,
        openness=0.4,
        conscientiousness=0.8,
        traits=["勤劳", "专注", "可靠", "稳重"],
    ),
    "老张": Personality(
        extraversion=0.6,
        openness=0.5,
        conscientiousness=0.9,
        traits=["稳重", "热心", "专业", "细心"],
    ),
    "小美": Personality(
        extraversion=0.3,
        openness=0.9,
        conscientiousness=0.2,
        traits=["敏感", "创意", "细腻", "独处"],
    ),
}
