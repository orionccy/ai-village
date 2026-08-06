"""
============================================================
websocket.py — WebSocket 双向通信
============================================================
建立前端和后端之间的实时通信通道。

协议:
  后端 → 前端: world_update (每个 tick)
  后端 → 前端: agent_detail (请求 Agent 详情)
  前端 → 后端: command (pause/resume/set_speed/get_agent_detail)
  前端 → 后端: ping (心跳)
============================================================
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.agents.agent_manager import AgentManager
from backend.world.engine import WorldEngine

logger = logging.getLogger("ai_village.ws")

router = APIRouter()

# 已连接的客户端集合
_connected_clients: set[WebSocket] = set()


async def broadcast_world_update(world_engine: WorldEngine, agent_manager: AgentManager):
    """
    向所有已连接的 WebSocket 客户端广播世界状态。

    在每个 tick 结束时由 WorldEngine 调用。
    """
    if not _connected_clients:
        return

    # 获取 token 统计
    from backend.llm.client import get_token_stats
    token_stats = get_token_stats()

    # 构建消息
    message = {
        "type": "world_update",
        "virtual_time": world_engine.clock.time_str,
        "virtual_day": world_engine.clock.day,
        "tick": world_engine.tick_count,
        "is_sleeping": world_engine.clock.is_sleep_time,
        "time_period": world_engine.clock.get_time_period(),
        "paused": world_engine.paused,
        "agents": agent_manager.get_all_dicts(),
        "events": world_engine.get_events()[-20:],  # 最近 20 条
        "metrics_snapshot": {
            "total_tokens": token_stats["total_tokens"],
            "avg_latency_ms": round(world_engine.avg_latency_ms, 1),
            "total_llm_calls": token_stats["total_calls"],
        },
    }

    # 广播给所有客户端
    disconnected = set()
    for client in _connected_clients:
        try:
            await client.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            disconnected.add(client)

    # 清理断开的客户端
    _connected_clients -= disconnected


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点。

    每个浏览器标签页建立一个连接。
    支持双向通信：
    - 接收前端的控制命令（暂停/恢复/变速）
    - 推送世界状态更新
    """
    await websocket.accept()
    _connected_clients.add(websocket)
    logger.info(f"🔌 WebSocket 客户端已连接 (当前 {len(_connected_clients)} 个)")

    # 获取服务器组件
    world_engine: WorldEngine = websocket.app.state.world_engine
    agent_manager: AgentManager = websocket.app.state.agent_manager

    # 发送初始世界状态
    await websocket.send_text(json.dumps({
        "type": "world_update",
        "virtual_time": world_engine.clock.time_str,
        "virtual_day": world_engine.clock.day,
        "tick": world_engine.tick_count,
        "is_sleeping": world_engine.clock.is_sleep_time,
        "time_period": world_engine.clock.get_time_period(),
        "paused": world_engine.paused,
        "agents": agent_manager.get_all_dicts(),
        "events": world_engine.get_events()[-10:],
        "metrics_snapshot": {
            "total_tokens": world_engine.total_tokens,
            "avg_latency_ms": round(world_engine.avg_latency_ms, 1),
        },
    }, ensure_ascii=False))

    try:
        while True:
            # 接收前端命令
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "command":
                action = msg.get("action", "")
                if action == "pause":
                    world_engine.pause()
                elif action == "resume":
                    world_engine.resume()
                elif action == "set_speed":
                    world_engine.set_speed(float(msg.get("value", 1.0)))

            elif msg_type == "get_agent_detail":
                agent_id = msg.get("agent_id", "")
                agent = agent_manager.get(agent_id)
                if agent:
                    await websocket.send_text(json.dumps({
                        "type": "agent_detail",
                        "agent": agent.to_detail_dict(),
                    }, ensure_ascii=False))

            elif msg_type == "ping":
                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 客户端断开 (剩余 {len(_connected_clients) - 1} 个)")
    finally:
        _connected_clients.discard(websocket)
