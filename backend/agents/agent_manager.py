"""
============================================================
agent_manager.py — Agent 管理器
============================================================
负责管理所有 Agent 的生命周期：

1. 从 agents.json 加载配置，创建 Agent 实例
2. 提供所有 Agent 的状态汇总（供 WebSocket 广播）
3. 处理每日重置（起床时的心情/精力恢复）
4. 处理睡眠传送（23:00 所有 Agent 回家）
5. 管理 Agent 之间的关系和心情更新

设计原则:
- AgentManager 是 Agent 状态的唯一权威来源 (single source of truth)
- 世界引擎通过 AgentManager 来获取/更新 Agent 状态
- AgentManager 不涉及 LLM 调用（那是 LangGraph 的事）
============================================================
"""

import json
import logging
import os
from collections import deque
from typing import Optional

from backend.agents.base_agent import Agent
from backend.agents.personalities import Personality
from backend.config import AGENTS_CONFIG_PATH, MOOD_BASELINE, ENERGY_MORNING

logger = logging.getLogger("ai_village.agents")


class AgentManager:
    """
    Agent 管理器。

    Usage:
        manager = AgentManager()
        manager.load_from_json("data/agents.json")
        agents = manager.get_all()
        manager.send_all_home()
        manager.wake_up_all()
    """

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        logger.info("👥 Agent 管理器已创建")

    # ---- 加载 ----

    def load_from_json(self, path: Optional[str] = None):
        """
        从 JSON 配置文件加载所有 Agent。

        JSON 中定义的是静态属性（名字、性格、技能等）。
        动态状态（位置、心情等）在加载时自动初始化。

        Args:
            path: agents.json 的路径，默认使用 config 中的路径
        """
        filepath = path or AGENTS_CONFIG_PATH

        if not os.path.exists(filepath):
            logger.error(f"❌ Agent 配置文件不存在: {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for agent_data in data.get("agents", []):
            agent = self._create_agent_from_dict(agent_data)
            self._agents[agent.id] = agent
            logger.info(f"  ✅ {agent.name} ({agent.job}) — 位置: {agent.home}")

        logger.info(f"👥 已加载 {len(self._agents)} 个 Agent")

    def _create_agent_from_dict(self, data: dict) -> Agent:
        """从 JSON 字典创建一个 Agent 实例。"""
        personality = Personality(
            extraversion=data["extraversion"],
            openness=data["openness"],
            conscientiousness=data["conscientiousness"],
            traits=data.get("traits", []),
        )

        home = tuple(data["home"])

        # 创建 Agent，初始位置设为家
        agent = Agent(
            id=data["id"],
            name=data["name"],
            age=data["age"],
            job=data["job"],
            emoji=data["emoji"],
            home=home,
            personality=personality,
            skills=data.get("skills", {}),
            x=home[0],
            y=home[1],
        )

        # 设置初始关系
        relationships = data.get("relationships", {})
        for other_id, value in relationships.items():
            agent.relationships[other_id] = float(value)

        return agent

    # ---- 查询 ----

    def get(self, agent_id: str) -> Optional[Agent]:
        """按 ID 获取 Agent。"""
        return self._agents.get(agent_id)

    def get_by_name(self, name: str) -> Optional[Agent]:
        """按名字获取 Agent。"""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def get_all(self) -> list[Agent]:
        """获取所有 Agent 的列表。"""
        return list(self._agents.values())

    def get_all_ids(self) -> list[str]:
        """获取所有 Agent 的 ID 列表。"""
        return list(self._agents.keys())

    def get_all_dicts(self) -> list[dict]:
        """获取所有 Agent 的简略信息（用于 API/WebSocket 广播）。"""
        return [agent.to_dict() for agent in self._agents.values()]

    def get_agent_at(self, x: int, y: int) -> Optional[Agent]:
        """获取位于指定坐标的 Agent（如果有的话）。"""
        for agent in self._agents.values():
            if agent.x == x and agent.y == y:
                return agent
        return None

    def get_occupied_cells(self) -> set[tuple[int, int]]:
        """获取所有被 Agent 占据的格子坐标。"""
        return {(agent.x, agent.y) for agent in self._agents.values()}

    def get_nearby_agents(self, x: int, y: int, range_cells: int = 3) -> list[str]:
        """
        获取指定坐标附近的其他 Agent 名字列表。

        Args:
            x, y: 中心坐标
            range_cells: 搜索范围（曼哈顿距离）

        Returns:
            附近 Agent 的名字列表（不含自己）
        """
        from backend.world.map import manhattan_distance

        nearby = []
        for agent in self._agents.values():
            if agent.x == x and agent.y == y:
                continue  # 跳过自己
            if manhattan_distance(x, y, agent.x, agent.y) <= range_cells:
                nearby.append(agent.name)
        return nearby

    # ---- 位置操作 ----

    def try_move(self, agent_id: str, new_x: int, new_y: int) -> bool:
        """
        尝试移动 Agent 到新坐标。

        检查合法性：
        - 坐标在地图内
        - 目标格没有人

        Args:
            agent_id: Agent ID
            new_x, new_y: 目标坐标

        Returns:
            True 如果移动成功，False 如果被阻挡
        """
        from backend.world.map import is_valid_cell

        agent = self.get(agent_id)
        if not agent:
            return False

        if not is_valid_cell(new_x, new_y):
            return False

        # 检查是否有其他 Agent 占据了目标格
        occupant = self.get_agent_at(new_x, new_y)
        if occupant and occupant.id != agent_id:
            return False

        # 移动
        agent.x = new_x
        agent.y = new_y
        return True

    # ---- 状态更新 ----

    def send_all_home(self):
        """
        将所有 Agent 传送回家（23:00 睡眠时调用）。
        这是为数不多的"强制"操作之一——LLM 无权决定是否睡觉。
        """
        for agent in self._agents.values():
            agent.x, agent.y = agent.home
            agent.activity = "睡觉"
            agent.energy = 0.1  # 最低精力
        logger.info("🏠 所有 Agent 已传送回家")

    def wake_up_all(self):
        """
        唤醒所有 Agent（06:00 起床时调用）。
        重置每日状态：心情、精力、活动。
        """
        for agent in self._agents.values():
            agent.reset_daily()
        logger.info("🌅 所有 Agent 已醒来，新的一天开始了！")

    def tick_all(self):
        """所有 Agent 的 tick 计数 +1，冷却 -1。"""
        for agent in self._agents.values():
            agent.tick_count += 1
            if agent.conversation_cooldown > 0:
                agent.conversation_cooldown -= 1

    # ---- 关系与心情 ----

    def update_relationship(self, agent_a_id: str, agent_b_id: str, delta: float):
        """
        双向更新两个 Agent 的关系值。

        关系变化是双向的（A 对 B 和 B 对 A 同时变化），
        但变化值可以不同（如 A 很喜欢 B，但 B 对 A 一般）。
        """
        a = self.get(agent_a_id)
        b = self.get(agent_b_id)
        if a and b:
            a.modify_relationship(agent_b_id, delta)
            b.modify_relationship(agent_a_id, delta * 0.8)  # B 对 A 的变化略小

    def apply_mood_update(self, agent_id: str, delta: float):
        """更新单个 Agent 的心情。"""
        agent = self.get(agent_id)
        if agent:
            agent.modify_mood(delta)

    def apply_energy_decay(self, agent_id: str, amount: float = 0.01):
        """
        每个 tick 消耗精力。

        精力消耗 = 基础消耗 + 距离家的距离加成（走得越远越累）
        """
        agent = self.get(agent_id)
        if agent:
            from backend.world.map import manhattan_distance
            dist_from_home = manhattan_distance(agent.x, agent.y, *agent.home)
            decay = amount + dist_from_home * 0.002
            agent.modify_energy(-decay)

    # ---- 统计 ----

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def avg_mood(self) -> float:
        """所有 Agent 的平均心情。"""
        if not self._agents:
            return 0.0
        return sum(a.mood for a in self._agents.values()) / len(self._agents)
