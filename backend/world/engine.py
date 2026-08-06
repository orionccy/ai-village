"""
============================================================
engine.py — 世界引擎模块
============================================================
这是整个模拟系统的"心脏"，负责：

1. 虚拟时钟管理 — 模拟一天的时间流逝
2. Tick 循环 — 驱动所有 Agent 在每个 tick 执行决策
3. 睡眠阶段处理 — 23:00-06:00 的时间快进
4. Agent 调度 — 并行运行所有 Agent 的决策流程
5. 事件广播 — 收集每个 tick 产生的事件

Tick 循环的完整流程见规划文档 1.4 节。

设计要点：
- 引擎运行在独立的 asyncio 后台任务中
- 每个 tick 内所有 Agent 并行决策 (asyncio.gather)
- 引擎可以被暂停/恢复/调速（通过控制命令）
- 睡眠阶段跳过 tick，直接快进时间
============================================================
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

from backend.config import (
    TICK_INTERVAL_SECONDS,
    TIME_SPEED_MULTIPLIER,
    DAY_START_HOUR,
    DAY_END_HOUR,
    SLEEP_DURATION_SECONDS,
)

logger = logging.getLogger("ai_village.engine")


# ============================================================
# 虚拟时钟
# ============================================================

class VirtualClock:
    """
    虚拟时钟 — 管理模拟世界中的时间。

    真实时间和虚拟时间的关系：
        1 真实秒 = TIME_SPEED_MULTIPLIER 虚拟分钟 (默认 10)
        所以 1 tick (1.5 真实秒) = 15 虚拟分钟

    每天 06:00 开始，23:00 结束。23:00-06:00 是睡眠时间，
    通过 fast_forward() 快进跳过。
    """

    def __init__(self):
        self.day: int = 1
        self.hour: int = DAY_START_HOUR  # 6
        self.minute: int = 0

    @property
    def total_minutes(self) -> int:
        """当前时间从当日 00:00 起的总分钟数。"""
        return self.hour * 60 + self.minute

    @property
    def time_str(self) -> str:
        """返回格式化的时间字符串，如 "14:30"。"""
        return f"{self.hour:02d}:{self.minute:02d}"

    @property
    def is_sleep_time(self) -> bool:
        """判断当前是否在睡眠时段 (23:00-06:00)。"""
        return self.hour >= DAY_END_HOUR or self.hour < DAY_START_HOUR

    @property
    def is_wake_up_time(self) -> bool:
        """判断当前是否刚好是起床时间。"""
        return self.hour == DAY_START_HOUR and self.minute == 0

    def advance(self, virtual_minutes: int = 15):
        """
        推进虚拟时间。

        默认每次 tick 推进 15 虚拟分钟 (= 1.5 真实秒 × 10)。

        当时钟跨越 24:00 时，自动进入新的一天。
        """
        total = self.total_minutes + virtual_minutes
        if total >= 24 * 60:
            # 跨天了
            total -= 24 * 60
            self.day += 1
            logger.info(f"🌅 新的一天开始！Day {self.day}")

        self.hour = total // 60
        self.minute = total % 60

    def fast_forward_to_morning(self):
        """
        快进到第二天早晨 06:00。
        用于睡眠阶段的跳转。
        """
        self.day += 1
        self.hour = DAY_START_HOUR
        self.minute = 0
        logger.info(f"🌅 快进到 Day {self.day} 06:00（天亮了！）")

    def get_time_period(self) -> str:
        """
        返回当前时间段的描述。

        用于 Agent 的作息约束 —— LLM 根据这个知道现在是"工作时间"还是"自由时间"。

        时间段划分：
            06:00-07:00 → 早晨
            07:00-08:00 → 通勤
            08:00-12:00 → 上午工作
            12:00-13:00 → 午餐
            13:00-17:00 → 下午工作
            17:00-19:00 → 傍晚自由
            19:00-21:00 → 晚间社交
            21:00-22:30 → 回家
            22:30-23:00 → 强制回家
            23:00-06:00 → 睡眠
        """
        h = self.hour
        m = self.minute

        if h >= 23 or h < 6:
            return "睡眠时间"
        elif 6 <= h < 7:
            return "早晨"
        elif 7 <= h < 8:
            return "通勤时间"
        elif 8 <= h < 12:
            return "上午工作"
        elif 12 <= h < 13:
            return "午餐时间"
        elif 13 <= h < 17:
            return "下午工作"
        elif 17 <= h < 19:
            return "傍晚自由"
        elif 19 <= h < 21:
            return "晚间社交"
        elif 21 <= h < 22 or (h == 22 and m < 30):
            return "准备回家"
        else:  # 22:30-23:00
            return "强制回家"


# ============================================================
# 引擎事件
# ============================================================

class GameEvent:
    """
    一条游戏事件。

    当 Agent 执行动作、对话、或其他值得记录的事情时产生。
    事件通过 WebSocket 推送到前端展示。
    """

    def __init__(self, time_str: str, text: str):
        self.time = time_str
        self.text = text

    def to_dict(self) -> dict:
        return {"time": self.time, "text": self.text}


# ============================================================
# 世界引擎
# ============================================================

class WorldEngine:
    """
    世界引擎 — 驱动整个模拟系统的运行。

    使用方法:
        engine = WorldEngine()
        engine.set_agent_tick_callback(my_agent_tick_fn)
        await engine.run()

    引擎通过回调函数与 Agent 系统解耦：
    - agent_tick_callback: 每个 tick 对每个 Agent 调用，返回该 Agent 的新状态
    - 引擎不关心 Agent 是如何做决策的（LLM 还是规则），只管调度
    """

    def __init__(self):
        # 时钟
        self.clock = VirtualClock()

        # 运行状态
        self.running: bool = False
        self.paused: bool = False
        self.speed_multiplier: float = 1.0
        self.tick_count: int = 0

        # 事件缓冲区（每个 tick 清空）
        self.events: list[GameEvent] = []
        # 事件历史（不清空，供 REST API 和前端查询）
        self.event_history: list[GameEvent] = []

        # Agent 管理器（由 main.py 在启动时注入）
        self.agent_manager: "AgentManager | None" = None  # type: ignore

        # 回调函数（由 AgentManager 注入）
        self._agent_tick_callback: Optional[Callable[[str, dict], Awaitable[dict]]] = None

        # 统计
        self.total_tokens: int = 0
        self.avg_latency_ms: float = 0

        logger.info("🌍 世界引擎已创建")

    # ---- 回调注册 ----

    def set_agent_tick_callback(
        self,
        callback: Callable[[str, dict], Awaitable[dict]],
    ):
        """
        注册 Agent tick 回调函数。

        引擎在每个 tick 会为每个 Agent 调用此回调。
        回调接收 (agent_id, world_context)，返回 agent 的新状态字典。

        Args:
            callback: 异步回调函数
        """
        self._agent_tick_callback = callback
        logger.info("🔗 Agent tick 回调已注册")

    # ---- 控制接口 ----

    def pause(self):
        """暂停引擎。"""
        self.paused = True
        logger.info("⏸ 引擎已暂停")

    def resume(self):
        """恢复引擎。"""
        self.paused = False
        logger.info("▶ 引擎已恢复")

    def set_speed(self, multiplier: float):
        """
        设置时间流速。

        Args:
            multiplier: 1.0 = 正常速度, 2.0 = 两倍速
        """
        self.speed_multiplier = multiplier
        logger.info(f"⏩ 速度设置为 {multiplier}x")

    def stop(self):
        """停止引擎。"""
        self.running = False
        logger.info("🛑 引擎正在停止...")

    # ---- 世界上下文 ----

    def get_world_context(self) -> dict:
        """
        返回当前世界的上下文信息。

        这个字典会传给每个 Agent 的决策函数，
        让 Agent 了解当前世界的状态（时间、地点等）。

        Returns:
            世界上下文字典
        """
        return {
            "virtual_time": self.clock.time_str,
            "virtual_day": self.clock.day,
            "time_period": self.clock.get_time_period(),
            "is_sleeping": self.clock.is_sleep_time,
            "tick": self.tick_count,
        }

    # ---- 主循环 ----

    async def run(self):
        """
        世界引擎主循环。

        **引擎启动时默认暂停**，等待用户在前端点击"▶ 运行"。
        """
        self.running = True
        self.paused = True  # ← 默认暂停
        logger.info("🚀 世界引擎主循环已启动（已暂停，等待用户点击运行）")

        while self.running:
            # ---- 暂停检查 ----
            if self.paused:
                await asyncio.sleep(0.5)
                continue

            # ---- 睡眠阶段处理 ----
            if self.clock.is_sleep_time:
                await self._handle_sleep()
                continue

            # ---- 一个 Tick 开始 ----
            self.tick_count += 1
            self.events.clear()  # 清空上一 tick 的事件

            # 收集世界上下文
            world_ctx = self.get_world_context()

            # ---- 并行运行所有 Agent 决策 ----
            if self.agent_manager and self._agent_tick_callback:
                agent_ids = self.agent_manager.get_all_ids()
                # 使用 asyncio.gather 并行执行所有 Agent 的决策
                results = await asyncio.gather(
                    *[self._agent_tick_callback(aid, world_ctx) for aid in agent_ids],
                    return_exceptions=True,
                )

                # 处理 Agent 的决策结果，生成事件
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.warning(f"Agent {agent_ids[i]} tick 异常: {result}")
                        continue
                    if not result or not isinstance(result, dict):
                        continue

                    agent = self.agent_manager.get(result.get("agent_id", ""))
                    if not agent:
                        continue

                    action_type = result.get("action_type", "")
                    action_result = result.get("action_result", "")

                    # 为重要行动生成事件
                    if action_type == "chat":
                        conv = result.get("conversation")
                        if conv and conv.get("rounds", 0) > 0:
                            self.add_event(conv.get("summary", f"{agent.name}和某人聊了聊"))
                        else:
                            self.add_event(f"{agent.name} 想找人聊天")
                    elif action_type == "do" and action_result:
                        self.add_event(f"{agent.name} {action_result}")
                    elif action_type == "rest" and "睡觉" not in agent.activity:
                        pass  # 普通休息不生成事件

                # 更新 tick 计数和精力衰减
                self.agent_manager.tick_all()
                for aid in agent_ids:
                    self.agent_manager.apply_energy_decay(aid)

            # ---- 推进时间 ----
            self.clock.advance(virtual_minutes=15)

            # ---- 广播 ----
            if self.agent_manager:
                try:
                    from backend.api.websocket import broadcast_world_update
                    await broadcast_world_update(self, self.agent_manager)
                except Exception:
                    pass  # WebSocket 广播失败不影响 tick 循环

            # ---- 等待下一个 Tick ----
            # 根据速度倍率调整间隔
            interval = TICK_INTERVAL_SECONDS / self.speed_multiplier
            await asyncio.sleep(interval)

            # 每 20 tick 打印一次状态
            if self.tick_count % 20 == 0:
                logger.info(
                    f"⏰ Day {self.clock.day} {self.clock.time_str} "
                    f"| Tick {self.tick_count} "
                    f"| 时段: {self.clock.get_time_period()}"
                )

        logger.info("🛑 世界引擎主循环已停止")

    async def _handle_sleep(self):
        """
        处理睡眠阶段 (23:00 - 06:00)。

        步骤:
        1. 通知所有 Agent 回家睡觉
        2. 生成"夜深了"事件
        3. 等待 SLEEP_DURATION_SECONDS 秒（给人看的动画时间）
        4. 快进到第二天 06:00
        5. 重置 Agent 状态（心情、精力）
        """
        logger.info(f"🌙 Day {self.clock.day} 23:00 — 夜深了，小镇进入睡眠...")

        # 生成睡眠事件
        self.events.append(GameEvent("23:00", "🌙 夜深了，小镇进入了梦乡..."))

        # 通知所有 Agent 回家
        if self.agent_manager:
            self.agent_manager.send_all_home()

        # 等待几秒让人看到画面
        await asyncio.sleep(SLEEP_DURATION_SECONDS)

        # 快进到第二天
        self.clock.fast_forward_to_morning()

        # 唤醒所有 Agent
        if self.agent_manager:
            self.agent_manager.wake_up_all()

        # 生成起床事件
        self.events.append(GameEvent("06:00", "🌅 天亮了！新的一天开始了！"))

        logger.info(f"🌅 Day {self.clock.day} 06:00 — 新的一天！")

    # ---- 事件 ----

    def add_event(self, text: str):
        """
        添加一条游戏事件（同时写入当前缓冲区和历史记录）。
        """
        event = GameEvent(self.clock.time_str, text)
        self.events.append(event)
        self.event_history.append(event)
        # 保持历史上限
        if len(self.event_history) > 500:
            self.event_history = self.event_history[-300:]

    def get_events(self) -> list[dict]:
        """获取当前 tick 的所有事件（返回字典列表供序列化）。"""
        return [e.to_dict() for e in self.events]

    # ---- 统计 ----

    def record_llm_call(self, tokens: int, latency_ms: float):
        """
        记录一次 LLM 调用。

        Args:
            tokens: 消耗的 token 数
            latency_ms: 调用耗时（毫秒）
        """
        self.total_tokens += tokens
        # 使用指数移动平均更新平均延迟
        alpha = 0.1
        self.avg_latency_ms = (
            alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
            if self.avg_latency_ms > 0
            else latency_ms
        )

    def get_stats(self) -> dict:
        """返回引擎统计信息。"""
        return {
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "tick_count": self.tick_count,
        }
