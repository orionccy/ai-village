"""
============================================================
metrics.py — 运行时指标采集
============================================================
每个 tick 自动采集 Agent 的行为指标，无需 LLM。

采集指标:
- 决策耗时、Token 消耗
- 降级次数
- 社交活跃度
- 心情均值、活动多样性
============================================================
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentTickMetric:
    """单个 Agent 在单个 tick 的指标。"""
    agent_id: str
    tick: int
    action_type: str = ""
    degrade_level: int = 0
    new_memory: str = ""
    mood: float = 0.5


class MetricsCollector:
    """
    指标采集器。

    收集所有 Agent 在每个 tick 的行为数据，
    用于监测面板和 LLM-as-Judge 评估。
    """

    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self.history: list[AgentTickMetric] = []
        self._degradation_total = 0

    def record(self, agent_id: str, tick: int, action_type: str,
               degrade_level: int, new_memory: str, mood: float):
        """记录一次 tick 的指标。"""
        metric = AgentTickMetric(
            agent_id=agent_id,
            tick=tick,
            action_type=action_type,
            degrade_level=degrade_level,
            new_memory=new_memory,
            mood=mood,
        )
        self.history.append(metric)

        if degrade_level >= 2:
            self._degradation_total += 1

        # 裁剪
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_recent(self, n_ticks: int = 20) -> list[AgentTickMetric]:
        """获取最近 n 个 tick 的指标。"""
        return self.history[-n_ticks * 7:]  # 7 agents per tick

    def get_degradation_rate(self) -> float:
        """降级率 = 降级次数 / 总记录数。"""
        if not self.history:
            return 0.0
        degraded = sum(1 for m in self.history if m.degrade_level >= 2)
        return round(degraded / len(self.history), 4)

    def get_summary(self) -> dict:
        """获取汇总统计。"""
        if not self.history:
            return {"total_records": 0}

        actions = [m.action_type for m in self.history]
        moods = [m.mood for m in self.history]

        return {
            "total_records": len(self.history),
            "degradation_rate": self.get_degradation_rate(),
            "action_distribution": {
                "move": actions.count("move"),
                "chat": actions.count("chat"),
                "do": actions.count("do"),
                "rest": actions.count("rest"),
            },
            "avg_mood": round(sum(moods) / len(moods), 3) if moods else 0,
        }


# 全局实例
metrics_collector = MetricsCollector()
