"""
============================================================
store.py — 记忆 JSON 存储模块
============================================================
负责记忆的持久化：将 Agent 的记忆写入 JSON 文件，以及从文件读取。

存储结构:
    data/memories/
    ├── agent_xiaoming.json
    ├── agent_xiaohong.json
    └── ...

每条记忆包含:
    - tick: 产生记忆时的 tick 编号
    - virtual_time: 虚拟时间 "HH:MM"
    - content: 记忆文本
    - importance: 重要性 0~1
    - tags: 标签列表
    - related_agents: 相关 Agent ID 列表
============================================================
"""

import json
import logging
import os
from typing import Optional
from collections import deque

from backend.config import MEMORIES_DIR, SHORT_TERM_MEMORY_SIZE

logger = logging.getLogger("ai_village.memory")


# ============================================================
# 内容记忆存储
# ============================================================

class MemoryStore:
    """
    JSON 文件记忆存储。

    每个 Agent 一个 JSON 文件。文件结构:
    {
        "agent_id": "agent_xiaoming",
        "memories": [
            {"tick": 120, "virtual_time": "14:30", "content": "...",
             "importance": 0.8, "tags": [...], "related_agents": [...]}
        ]
    }
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        Args:
            base_dir: 记忆文件存储目录，默认使用 config.MEMORIES_DIR
        """
        self.base_dir = base_dir or MEMORIES_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    def _filepath(self, agent_id: str) -> str:
        """获取某个 Agent 的记忆文件路径。"""
        # 安全处理 agent_id，防止路径遍历
        safe_id = agent_id.replace("..", "").replace("/", "").replace("\\", "")
        return os.path.join(self.base_dir, f"{safe_id}.json")

    def load(self, agent_id: str) -> list[dict]:
        """
        加载某个 Agent 的所有长期记忆。

        Args:
            agent_id: Agent ID

        Returns:
            记忆列表（按 tick 升序排列）。如果文件不存在，返回空列表。
        """
        filepath = self._filepath(agent_id)
        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("memories", [])
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"⚠️  读取记忆文件失败 {filepath}: {e}")
            return []

    def save(self, agent_id: str, memories: list[dict]):
        """
        保存某个 Agent 的所有长期记忆。

        Args:
            agent_id: Agent ID
            memories: 记忆列表
        """
        filepath = self._filepath(agent_id)
        data = {
            "agent_id": agent_id,
            "memories": memories,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"❌ 保存记忆文件失败 {filepath}: {e}")

    def append(self, agent_id: str, memory: dict):
        """
        向某个 Agent 的记忆文件追加一条记忆。

        Args:
            agent_id: Agent ID
            memory: 单条记忆字典
        """
        memories = self.load(agent_id)
        memories.append(memory)
        self.save(agent_id, memories)

    def get_recent(self, agent_id: str, n: int = 10) -> list[dict]:
        """
        获取最近 n 条记忆。

        Args:
            agent_id: Agent ID
            n: 条数

        Returns:
            最近 n 条记忆（按时间倒序）
        """
        memories = self.load(agent_id)
        return memories[-n:]  # 取最后 n 条

    def get_by_tags(self, agent_id: str, tags: list[str], limit: int = 5) -> list[dict]:
        """
        按标签搜索记忆。

        匹配逻辑：记忆的 tags 中任一标签出现在搜索标签列表中即匹配。
        结果按 importance × 时效性 排序。

        Args:
            agent_id: Agent ID
            tags: 搜索标签列表
            limit: 返回条数上限

        Returns:
            匹配的记忆列表
        """
        memories = self.load(agent_id)
        if not tags:
            return []

        # 匹配
        matched = []
        for mem in memories:
            mem_tags = set(mem.get("tags", []))
            if mem_tags & set(tags):
                # 计算得分: importance × 时效性
                score = mem.get("importance", 0.5)
                matched.append((score, mem))

        # 按得分排序，取 top-N
        matched.sort(key=lambda x: -x[0])
        return [m for _, m in matched[:limit]]

    def trim(self, agent_id: str, max_memories: int = 100):
        """
        裁剪记忆：当超过最大条数时，删除最不重要的。

        使用 importance 排序，删除最低分的。

        Args:
            agent_id: Agent ID
            max_memories: 最大保留条数
        """
        memories = self.load(agent_id)
        if len(memories) <= max_memories:
            return

        # 按重要性排序
        memories.sort(key=lambda m: m.get("importance", 0.5), reverse=True)
        # 保留最重要的
        kept = memories[:max_memories]
        # 按 tick 重新排序
        kept.sort(key=lambda m: m.get("tick", 0))
        self.save(agent_id, kept)

        removed = len(memories) - max_memories
        logger.debug(f"🧹 [{agent_id}] 遗忘 {removed} 条不重要的记忆")


# ============================================================
# 全局实例
# ============================================================

# 应用级单例，其他模块通过此变量访问
memory_store = MemoryStore()
