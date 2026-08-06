"""
============================================================
manager.py — 记忆管理器
============================================================
在 MemoryStore 之上提供高层记忆管理操作：

1. 存储新记忆（含标签生成和重要性判断）
2. 检索相关记忆（用于 LLM 决策上下文）
3. 遗忘管理（自动裁剪旧记忆）

设计原则：
- 短期记忆在 Agent.short_term (deque) 中，内存存储
- 长期记忆在 JSON 文件中，通过 MemoryStore 管理
- 管理器作为桥梁，协调两者的读写
============================================================
"""

import logging
from datetime import datetime
from typing import Optional

from backend.memory.store import memory_store, MemoryStore
from backend.config import (
    SHORT_TERM_MEMORY_SIZE,
    LONG_TERM_MEMORY_MAX,
    RELEVANT_MEMORY_COUNT,
)

logger = logging.getLogger("ai_village.memory")


class MemoryManager:
    """
    记忆管理器 — 管理单个 Agent 的记忆。

    每个 Agent 拥有一个 MemoryManager 实例。
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.store = memory_store  # 共享的存储后端

    # ---- 存储 ----

    def add_memory(
        self,
        content: str,
        tick: int,
        virtual_time: str,
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        related_agents: Optional[list[str]] = None,
    ):
        """
        添加一条长期记忆。

        自动检测是否需要生成标签（如果没有提供的话）。

        Args:
            content: 记忆内容文本
            tick: 产生时的 tick 编号
            virtual_time: 虚拟时间
            importance: 重要性 0~1
            tags: 标签列表（可选，自动推断）
            related_agents: 相关 Agent ID 列表
        """
        if not content:
            return

        # 自动生成标签（如果没有提供）
        if tags is None:
            tags = self._infer_tags(content)

        memory = {
            "tick": tick,
            "virtual_time": virtual_time,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "related_agents": related_agents or [],
        }

        # 追加到长期存储
        self.store.append(self.agent_id, memory)

        # 定期裁剪
        self.store.trim(self.agent_id, max_memories=LONG_TERM_MEMORY_MAX)

    # ---- 检索 ----

    def get_context_memories(self, current_location: str = "") -> str:
        """
        获取用于 LLM 决策上下文的记忆文本。

        组合最近记忆 + 相关记忆，格式化为 LLM 可读的文本。

        Args:
            current_location: 当前位置名（用于标签匹配）

        Returns:
            格式化的记忆文本
        """
        memories = []

        # 1. 最近记忆（始终包含）
        recent = self.store.get_recent(self.agent_id, n=SHORT_TERM_MEMORY_SIZE)
        memories.extend(recent)

        # 2. 相关记忆（基于当前位置匹配）
        if current_location:
            location_tags = [current_location]
            relevant = self.store.get_by_tags(
                self.agent_id,
                tags=location_tags,
                limit=RELEVANT_MEMORY_COUNT,
            )
            # 去重
            existing_ticks = {m["tick"] for m in memories}
            for mem in relevant:
                if mem["tick"] not in existing_ticks:
                    memories.append(mem)
                    existing_ticks.add(mem["tick"])

        # 3. 高风险记忆（importance > 0.7 但还没被包含的）
        all_memories = self.store.load(self.agent_id)
        high_importance = [m for m in all_memories if m.get("importance", 0) > 0.7]
        existing_ticks = {m["tick"] for m in memories}
        for mem in high_importance[-3:]:  # 最多额外 3 条
            if mem["tick"] not in existing_ticks:
                memories.append(mem)

        # 格式化
        return self._format_memories(memories)

    def get_recent_list(self, n: int = 10) -> list[dict]:
        """获取最近 n 条记忆的原始数据。"""
        return self.store.get_recent(self.agent_id, n=n)

    # ---- 辅助 ----

    def _infer_tags(self, content: str) -> list[str]:
        """
        根据记忆内容自动推断标签。

        使用简单的关键词匹配（不依赖 LLM）。
        """
        tags = []

        keyword_tag_map = {
            "公园": "公园", "散步": "公园",
            "市场": "市场", "购物": "市场", "买": "市场",
            "咖啡馆": "咖啡馆", "咖啡": "咖啡馆", "聊天": "咖啡馆",
            "广场": "广场", "活动": "广场",
            "喷泉": "喷泉",
            "小红": "小红", "小明": "小明", "老王": "老王",
            "阿花": "阿花", "小李": "小李", "老张": "老张", "小美": "小美",
            "工作": "工作", "休息": "休息", "学习": "学习",
            "吃饭": "饮食", "早餐": "饮食", "午餐": "饮食", "晚餐": "饮食",
            "面包": "饮食", "烘焙": "烘焙",
        }

        for keyword, tag in keyword_tag_map.items():
            if keyword in content and tag not in tags:
                tags.append(tag)

        # 如果没匹配到任何标签，给个通用标签
        if not tags:
            tags.append("日常")

        return tags[:4]  # 最多 4 个标签

    def _format_memories(self, memories: list[dict]) -> str:
        """
        将记忆列表格式化为 LLM 可读的文本。

        每条记忆输出为: "[14:30] 在公园遇到了小红..."

        Args:
            memories: 记忆列表

        Returns:
            格式化的文本
        """
        if not memories:
            return ""

        # 按 tick 排序
        sorted_memories = sorted(memories, key=lambda m: m.get("tick", 0))

        lines = []
        for mem in sorted_memories:
            time = mem.get("virtual_time", "??:??")
            content = mem.get("content", "")
            imp = mem.get("importance", 0)
            # 高重要性记忆加标记
            marker = "⭐" if imp > 0.7 else ""
            lines.append(f"[{time}] {marker}{content}")

        return "\n".join(lines)

    def forget_old(self, days: int = 3):
        """
        遗忘旧记忆：删除超过指定虚拟天数的记忆。

        Args:
            days: 保留天数
        """
        memories = self.store.load(self.agent_id)
        # 基于 tick 估算天数（每 96 tick = 1 天）
        max_age_ticks = days * 96
        current_tick = memories[-1]["tick"] if memories else 0
        cutoff_tick = current_tick - max_age_ticks

        kept = [m for m in memories if m.get("tick", 0) >= cutoff_tick]
        if len(kept) < len(memories):
            self.store.save(self.agent_id, kept)
            logger.debug(
                f"🧹 [{self.agent_id}] 遗忘 {len(memories) - len(kept)} 条旧记忆"
            )
