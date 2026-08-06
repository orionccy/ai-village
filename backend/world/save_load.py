"""
============================================================
save_load.py — 游戏存档模块
============================================================
"""

import json
import os
import logging
from backend.config import DATA_DIR

logger = logging.getLogger("ai_village.save")

SAVE_FILE = os.path.join(DATA_DIR, "savegame.json")


def save_exists() -> bool:
    return os.path.exists(SAVE_FILE)


def save_game(engine, agent_manager) -> dict:
    """保存世界状态和 Agent 动态数据。"""
    data = {
        "world": {
            "day": engine.clock.day,
            "hour": engine.clock.hour,
            "minute": engine.clock.minute,
            "tick": engine.tick_count,
            "total_tokens": engine.total_tokens,
        },
        "agents": [],
        "events": [e.to_dict() for e in engine.event_history[-100:]],
    }

    for a in agent_manager.get_all():
        data["agents"].append({
            "id": a.id,
            "x": a.x, "y": a.y,
            "activity": a.activity,
            "mood": a.mood,
            "energy": a.energy,
            "relationships": a.relationships,
            "conversation_cooldown": a.conversation_cooldown,
        })

    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 游戏已保存 (Day {engine.clock.day} {engine.clock.time_str} Tick {engine.tick_count})")
    return {"saved": True, "day": engine.clock.day, "time": engine.clock.time_str, "tick": engine.tick_count}


def load_game(engine, agent_manager) -> dict:
    """加载存档，恢复世界和 Agent 状态。"""
    if not save_exists():
        return {"loaded": False, "reason": "没有存档"}

    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 恢复世界状态
    w = data["world"]
    engine.clock.day = w["day"]
    engine.clock.hour = w["hour"]
    engine.clock.minute = w["minute"]
    engine.tick_count = w["tick"]
    engine.total_tokens = w.get("total_tokens", 0)

    # 恢复事件历史
    engine.event_history = []
    for e in data.get("events", []):
        from backend.world.engine import GameEvent
        engine.event_history.append(GameEvent(e["time"], e["text"]))

    # 恢复 Agent 状态
    for ad in data["agents"]:
        agent = agent_manager.get(ad["id"])
        if agent:
            agent.x = ad["x"]
            agent.y = ad["y"]
            agent.activity = ad["activity"]
            agent.mood = ad["mood"]
            agent.energy = ad["energy"]
            agent.relationships = ad["relationships"]
            agent.conversation_cooldown = ad.get("conversation_cooldown", 0)

    logger.info(f"📂 存档已加载 (Day {engine.clock.day} {engine.clock.time_str} Tick {engine.tick_count})")
    return {"loaded": True, "day": engine.clock.day, "time": engine.clock.time_str, "tick": engine.tick_count}


def delete_save():
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
        return {"deleted": True}
    return {"deleted": False}
