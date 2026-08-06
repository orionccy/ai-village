"""
============================================================
agent_graph.py — Agent 决策的 LangGraph 工作流
============================================================
这是每个 Agent 在每个 tick 执行的"大脑"——一条 5 节点的决策流水线。

工作流: 感知 → 思考(LLM) → 校验 → 执行 → 记忆

设计要点:
- 只有 think 节点调用 LLM（remember 可选调用）
- validate 是"防火墙"：LLM 输出不合法时自动降级
- 降级策略分三层：正常 → 修正 → 纯规则
- 对话通过独立的 conversation_graph 模块处理
- 记忆通过 MemoryManager 持久化到 JSON 文件
============================================================
"""

import json
import logging
import random
from typing import TypedDict, Optional, Literal

from backend.agents.base_agent import Agent
from backend.world.locations import get_location_name_at, get_location_at
from backend.world.map import is_valid_cell, get_adjacent_cells, get_move_direction
from backend.llm.client import llm_invoke_json, llm_invoke
from backend.llm.prompts import build_decision_prompt, MEMORY_PROMPT
from backend.agents.routines import get_routine_prompt
from backend.memory.manager import MemoryManager
from backend.graph.conversation_graph import run_conversation

logger = logging.getLogger("ai_village.graph")

# ============================================================
# 状态定义
# ============================================================

class AgentState(TypedDict):
    """
    Agent 在一次决策中的完整状态。

    这个 TypedDict 定义了 LangGraph 工作流中节点间的数据传递格式。
    每个节点可以读写这些字段。
    """

    # ---- 输入（由外部填充）----
    agent_id: str
    agent_profile: str          # "小明，28岁，教师"
    behavior_guide: str         # 性格指南文本
    skills_text: str            # 技能描述文本
    relationships_text: str     # 关系描述文本
    home_str: str               # 家坐标文本 "(0, 0)"
    current_time: str           # "14:30"
    time_period: str            # "上午工作"
    constraint_text: str        # 作息约束文本
    x: int                      # 当前 X
    y: int                      # 当前 Y
    location_name: str          # "公园"
    activity: str               # 上一 tick 的活动
    mood_value: float           # 心情
    energy_value: float         # 精力
    nearby_text: str            # "小明, 小红"
    nearby_locations_text: str  # "公园, 市场"
    memories_text: str          # 记忆文本

    # ---- LLM 输出（think 节点填充）----
    thought: str                # LLM 内心独白
    action_type: str            # move | chat | do | rest
    action_detail: str          # 动作细节
    action_reason: str          # 决策理由

    # ---- 执行结果（act 节点填充）----
    action_success: bool
    action_result: str          # 执行结果描述
    degrade_level: int          # 0=正常, 1=修正, 2=完全降级

    # ---- 记忆（remember 节点填充）----
    new_memory: str             # 新记忆文本
    memory_importance: float    # 0~1


# ============================================================
# 节点实现
# ============================================================

def perceive_node(state: AgentState) -> AgentState:
    """
    感知节点 — 纯逻辑，不需要 LLM。

    收集 Agent 做出决策所需的所有上下文信息：
    - 当前在哪、周围有谁
    - 当前时段的作息约束
    - 附近有哪些地点可去

    这些信息会被格式化为 LLM Prompt 的一部分（在 think 节点构建）。
    """
    agent_id = state["agent_id"]
    x, y = state["x"], state["y"]

    # 获取当前位置的地点名
    location_name = get_location_name_at(x, y)
    state["location_name"] = location_name

    # 记录感知
    logger.debug(
        f"👁 [{state['agent_id']}] 感知: ({x},{y}) {location_name}"
        f" | 附近: {state['nearby_text'] or '无人'}"
    )

    return state


async def think_node(state: AgentState) -> AgentState:
    """
    思考节点 — 调用 LLM 做出决策。

    这是整个工作流中最重要的节点。它：
    1. 构建完整的 System Prompt + User Prompt
    2. 调用 DeepSeek LLM
    3. 解析 JSON 响应
    4. 如果 LLM 失败，标记降级

    返回的 state 中填充了 thought/action_type/action_detail/action_reason。
    """
    # 1. 构建 Prompt
    system_prompt, user_prompt = build_decision_prompt(
        agent_profile=state["agent_profile"],
        behavior_guide=state["behavior_guide"],
        skills_text=state["skills_text"],
        relationships_text=state["relationships_text"],
        home=state["home_str"],
        current_time=state["current_time"],
        time_period=state["time_period"],
        constraint_text=state["constraint_text"],
        x=state["x"],
        y=state["y"],
        location_name=state["location_name"],
        activity=state["activity"],
        mood_value=state["mood_value"],
        energy_value=state["energy_value"],
        nearby_text=state["nearby_text"],
        nearby_locations_text=state["nearby_locations_text"],
        memories_text=state["memories_text"],
    )

    # 2. 调用 LLM
    result = await llm_invoke_json(system_prompt, user_prompt)

    # 3. 处理结果
    if result is None:
        # LLM 调用失败，标记降级
        state["degrade_level"] = 3  # 完全降级
        logger.warning(f"⚠️ [{state['agent_id']}] LLM 调用失败，将使用规则降级")
        return state

    # 4. 提取字段
    state["thought"] = result.get("thought", "")
    state["action_type"] = result.get("action_type", "rest")
    state["action_detail"] = result.get("action_detail", "原地休息")
    state["action_reason"] = result.get("action_reason", "需要休息")
    state["degrade_level"] = 0  # 正常

    logger.info(
        f"💭 [{state['agent_id']}] "
        f"思考: \"{state['thought'][:40]}...\"" if len(state["thought"]) > 40
        else f"💭 [{state['agent_id']}] 思考: \"{state['thought']}\""
    )
    logger.info(
        f"   → 行动: {state['action_type']}/{state['action_detail']} "
        f"(理由: {state['action_reason'][:30]})"
    )

    return state


def validate_node(state: AgentState) -> AgentState:
    """
    校验节点 — 检查 LLM 输出的合法性。

    这是防止 Agent "发疯"的防火墙。检查项：
    - action_type 是否在合法范围内
    - move 方向是否在地图内
    - chat 对象是否在附近
    - do/rest 是否有有效的描述

    校验失败 → 降级到规则决策。
    """
    # 如果已经在降级状态，跳过校验
    if state["degrade_level"] >= 3:
        return state

    action_type = state["action_type"]
    action_detail = state["action_detail"]
    x, y = state["x"], state["y"]

    valid = True

    if action_type == "move":
        # 校验移动方向
        valid_directions = ["向上", "向下", "向左", "向右", "停留"]
        if action_detail not in valid_directions:
            logger.warning(f"⚠️ [{state['agent_id']}] 非法移动方向: {action_detail}")
            valid = False
        else:
            # 检查目标格是否在地图内
            dx, dy = 0, 0
            if action_detail == "向上":
                dy = -1
            elif action_detail == "向下":
                dy = 1
            elif action_detail == "向左":
                dx = -1
            elif action_detail == "向右":
                dx = 1

            if not is_valid_cell(x + dx, y + dy):
                logger.warning(f"⚠️ [{state['agent_id']}] 移动出界: ({x+dx},{y+dy})")
                valid = False

    elif action_type == "chat":
        # 检查聊天对象是否在附近
        nearby = state["nearby_text"]
        target_found = any(
            name.strip() in nearby for name in action_detail.replace("想和", "").replace("聊聊", "").split("聊聊关于")[0].split("关于")
        )
        # 简化校验：只要附近有人就认为可以尝试
        if not nearby:
            logger.warning(f"⚠️ [{state['agent_id']}] 想聊天但附近没人")
            valid = False

    elif action_type not in ("do", "rest"):
        logger.warning(f"⚠️ [{state['agent_id']}] 非法 action_type: {action_type}")
        valid = False

    if not valid:
        state["degrade_level"] = max(state["degrade_level"], 1)  # L2 修正

    return state


def degrade_node(state: AgentState) -> AgentState:
    """
    降级节点 — 当 LLM 输出不合法或调用失败时，使用规则生成决策。

    规则决策策略：
    1. 如果有作息约束 → 执行约束建议的行为
    2. 如果附近有人且性格外向 → 尝试聊天
    3. 如果在工作时段 → 做工作相关的事
    4. 否则 → 随机探索附近格子
    """
    logger.info(f"🔧 [{state['agent_id']}] 降级决策 (L{state['degrade_level']})")

    constraint = state.get("constraint_text", "")
    time_period = state["time_period"]
    x, y = state["x"], state["y"]

    # 规则 1: 如果是强制回家时段
    if "必须马上回家" in constraint:
        # 向家方向移动
        home_str = state["home_str"]
        hx, hy = map(int, home_str.strip("()").split(","))
        direction = get_move_direction(x, y, hx, hy)
        state["action_type"] = "move"
        state["action_detail"] = direction
        state["action_reason"] = "该回家了"
        state["thought"] = "天晚了，该回家了"
        state["degrade_level"] = 2
        return state

    # 规则 2: 在工作时段做工作相关的事
    if "工作" in time_period:
        activities = ["在工作", "专注工作", "处理事务"]
        state["action_type"] = "do"
        state["action_detail"] = random.choice(activities)
        state["action_reason"] = "工作时间"
        state["thought"] = "该工作了"
        state["degrade_level"] = 2
        return state

    # 规则 3: 自由时间随机探索
    adjacent = get_adjacent_cells(x, y)
    if adjacent:
        tx, ty = random.choice(adjacent)
        direction = get_move_direction(x, y, tx, ty)
        state["action_type"] = "move"
        state["action_detail"] = direction
        state["action_reason"] = "随便走走"
        state["thought"] = "到处逛逛吧..."
        state["degrade_level"] = 2
    else:
        state["action_type"] = "rest"
        state["action_detail"] = "在原地休息"
        state["action_reason"] = "没地方可去"
        state["thought"] = "休息一下..."
        state["degrade_level"] = 2

    return state


def decide_after_validate(state: AgentState) -> str:
    """
    条件路由：校验通过 → act，校验失败 → degrade。
    """
    if state["degrade_level"] >= 1:
        return "degrade"
    return "act"


async def act_node(state: AgentState, agent: Agent, agent_manager) -> AgentState:
    """
    执行节点 — 根据决策结果更新世界状态。

    这个节点接收 agent 和 agent_manager 作为额外参数（在构建 graph 时通过
    闭包传递，因为 LangGraph 编译后无法直接传入外部对象）。
    """
    action_type = state["action_type"]
    action_detail = state["action_detail"]
    x, y = state["x"], state["y"]

    result = ""
    success = True

    if action_type == "move":
        # 计算新坐标
        dx, dy = 0, 0
        direction_map = {
            "向上": (0, -1), "向下": (0, 1),
            "向左": (-1, 0), "向右": (1, 0), "停留": (0, 0),
        }
        dx, dy = direction_map.get(action_detail, (0, 0))

        new_x, new_y = x + dx, y + dy

        # 尝试移动
        if agent_manager.try_move(state["agent_id"], new_x, new_y):
            state["x"] = new_x
            state["y"] = new_y
            loc_name = get_location_name_at(new_x, new_y)
            result = f"移动到了 ({new_x}, {new_y}) — {loc_name}"
            agent.activity = f"在{loc_name}走动"
        else:
            result = f"无法移动到 ({new_x}, {new_y})，有人或出界"
            success = False

    elif action_type == "chat":
        # 提取聊天目标
        chat_target = action_detail
        for prefix in ["想和", "找", "约"]:
            if prefix in chat_target:
                chat_target = chat_target.split(prefix)[-1]
                for suffix in ["聊聊", "聊天", "说话", "谈谈"]:
                    if suffix in chat_target:
                        chat_target = chat_target.split(suffix)[0].strip()
                break

        # 尝试匹配 Agent
        target_agent = agent_manager.get_by_name(chat_target)
        if target_agent:
            result = f"想和 {chat_target} 聊天"
            agent.activity = f"和{chat_target}聊天"
            # TODO 阶段 6: 对话匹配和实际对话逻辑
        else:
            result = f"找不到 {chat_target}"
            success = False

    elif action_type == "do":
        agent.activity = action_detail
        result = f"开始: {action_detail}"

    elif action_type == "rest":
        agent.activity = f"休息: {action_detail}"
        result = f"休息: {action_detail}"

    state["action_success"] = success
    state["action_result"] = result

    logger.info(f"⚡ [{state['agent_id']}] 执行: {result}")

    return state


async def remember_node(state: AgentState) -> AgentState:
    """
    记忆节点 — 判断事件重要性，生成记忆。

    规则：
    - 简单移动 → 不记（不值得）
    - 社交/重要事件 → 调用 LLM 生成简洁的记忆文本
    - LLM 降级模式 → 用模板生成简单记忆
    """
    action_type = state["action_type"]
    action_result = state["action_result"]

    # 不值得记忆的事件
    if state["degrade_level"] >= 2 and action_type == "move":
        # 降级 + 移动 = 无趣
        state["memory_importance"] = 0.0
        state["new_memory"] = ""
        return state

    # 构建事件描述
    event_text = f"{action_result}（原因：{state['action_reason']}）"

    # 简单移动不调 LLM，直接用模板
    if action_type == "move":
        state["new_memory"] = f"在{state['location_name']}{state['action_detail']}"
        state["memory_importance"] = 0.1
        return state

    # 重要事件调 LLM 生成记忆
    try:
        user_prompt = MEMORY_PROMPT.format(
            event_text=event_text,
            current_time=state["current_time"],
            location_name=state["location_name"],
        )
        result = await llm_invoke_json(
            "你是一个记忆记录员。将事件转化为简洁的记忆。",
            user_prompt,
        )
        if result:
            state["new_memory"] = result.get("content", event_text[:30])
            state["memory_importance"] = result.get("importance", 0.3)
        else:
            state["new_memory"] = event_text[:40]
            state["memory_importance"] = 0.3
    except Exception:
        state["new_memory"] = event_text[:40]
        state["memory_importance"] = 0.3

    return state


# ============================================================
# Graph 构建
# ============================================================

def build_agent_graph():
    """
    构建并编译 Agent 决策的 LangGraph 工作流。

    这个函数返回一个编译好的 graph 实例，
    每次调用 graph.ainvoke(state) 就会执行一次完整的决策流程。

    Returns:
        编译好的 LangGraph StateGraph
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("perceive", perceive_node)
    workflow.add_node("think", think_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("degrade", degrade_node)
    # act 和 remember 节点需要外部 agent 对象，用特殊方式注册
    workflow.add_node("act", _make_act_node_wrapper())
    workflow.add_node("remember", remember_node)

    # 设置流
    workflow.set_entry_point("perceive")
    workflow.add_edge("perceive", "think")
    workflow.add_edge("think", "validate")

    # 条件分支：校验通过 → act，否则 → degrade
    workflow.add_conditional_edges(
        "validate",
        decide_after_validate,
        {"act": "act", "degrade": "degrade"},
    )
    workflow.add_edge("degrade", "act")  # 降级后也走 act
    workflow.add_edge("act", "remember")
    workflow.add_edge("remember", END)

    return workflow.compile()


# ============================================================
# Agent Tick 函数（供 WorldEngine 回调）
# ============================================================

# 全局编译好的 graph（避免每个 tick 重新编译）
_compiled_graph = None


def _make_act_node_wrapper():
    """创建一个包装函数，避免直接在 graph 中引用外部对象。"""
    async def wrapper(state: AgentState) -> AgentState:
        # 实际 agent 和 agent_manager 通过 state 中的 agent_id 间接引用
        # 由 run_agent_tick 在调用前设置
        return state
    return wrapper


async def run_agent_tick(
    agent: Agent,
    agent_manager,
    world_context: dict,
) -> dict:
    """
    执行一个 Agent 的单个 tick 决策。

    这是 WorldEngine 的回调函数。它：
    1. 准备 AgentState 输入
    2. 运行 5 节点 LangGraph 工作流
    3. 将结果写回 Agent 对象
    4. 返回状态摘要

    Args:
        agent: Agent 对象
        agent_manager: AgentManager 实例（用于获取附近信息等）
        world_context: 世界上下文字典（来自 WorldEngine）

    Returns:
        状态摘要字典（供 WebSocket 广播）
    """
    # 获取作息约束
    constraint_text = get_routine_prompt(
        world_context["virtual_time"],
        agent.job,
    )

    # 获取附近信息
    nearby = agent_manager.get_nearby_agents(agent.x, agent.y)
    nearby_text = ", ".join(nearby) if nearby else ""

    # 获取附近地点
    from backend.world.locations import get_location_at
    nearby_locs = []
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            nx, ny = agent.x + dx, agent.y + dy
            if is_valid_cell(nx, ny) and (dx != 0 or dy != 0):
                loc = get_location_at(nx, ny)
                if loc and loc.name not in nearby_locs:
                    nearby_locs.append(loc.name)

    # 构建初始 state
    initial_state: AgentState = {
        "agent_id": agent.id,
        "agent_profile": f"{agent.name}，{agent.age}岁，{agent.job}",
        "behavior_guide": agent.personality.get_behavior_guide(),
        "skills_text": agent.get_skills_text(),
        "relationships_text": agent.get_relationships_text(),
        "home_str": str(agent.home),
        "current_time": world_context["virtual_time"],
        "time_period": world_context["time_period"],
        "constraint_text": constraint_text,
        "x": agent.x,
        "y": agent.y,
        "location_name": get_location_name_at(agent.x, agent.y),
        "activity": agent.activity,
        "mood_value": agent.mood,
        "energy_value": agent.energy,
        "nearby_text": nearby_text,
        "nearby_locations_text": ", ".join(nearby_locs[:4]),  # 最多 4 个
        "memories_text": "\n".join(list(agent.short_term)[-5:]),  # 最近 5 条

        # 以下由后续节点填充
        "thought": "",
        "action_type": "",
        "action_detail": "",
        "action_reason": "",
        "action_success": False,
        "action_result": "",
        "degrade_level": 0,
        "new_memory": "",
        "memory_importance": 0.0,
    }

    # 手动执行工作流节点（避免 LangGraph 编译复杂度）
    # 直接调用各节点函数
    state = perceive_node(initial_state)

    # think 节点
    state = await think_node(state)

    # 如果 think 失败，直接降级
    if state["degrade_level"] >= 3:
        state = degrade_node(state)
    else:
        # validate
        state = validate_node(state)
        if state["degrade_level"] >= 1:
            state = degrade_node(state)

    # act 节点（需要 agent 和 agent_manager）
    state = await _act(state, agent, agent_manager)

    # remember 节点
    state = await remember_node(state)

    # ---- 将结果写回 Agent 对象 ----
    conversation_result = None

    # 对话处理
    if state["action_type"] == "chat" and state["action_success"]:
        chat_target = state["action_detail"]
        # 从 action_detail 中提取目标名字
        for prefix in ["想和", "找", "约"]:
            if prefix in chat_target:
                chat_target = chat_target.split(prefix)[-1]
                for suffix in ["聊聊", "聊天", "说话", "谈谈", "关于"]:
                    if suffix in chat_target:
                        chat_target = chat_target.split(suffix)[0].strip()
                break

        target_agent = agent_manager.get_by_name(chat_target)
        if target_agent and agent.conversation_cooldown <= 0:
            # 检查是否在同一格或相邻格
            from backend.world.map import is_adjacent
            if is_adjacent(agent.x, agent.y, target_agent.x, target_agent.y):
                # 触发对话
                conversation_result = await run_conversation(
                    agent_a=agent,
                    agent_b=target_agent,
                    location_name=get_location_name_at(agent.x, agent.y),
                    current_time=world_context["virtual_time"],
                )

                if conversation_result and conversation_result["rounds"] > 0:
                    # 更新关系值
                    quality = conversation_result["quality_score"]
                    if quality >= 0.7:
                        rel_delta = 0.5
                    elif quality >= 0.4:
                        rel_delta = 0.2
                    else:
                        rel_delta = -0.1

                    agent_manager.update_relationship(agent.id, target_agent.id, rel_delta)

                    # 更新心情
                    if quality >= 0.6:
                        agent.modify_mood(0.1)
                    elif quality < 0.3:
                        agent.modify_mood(-0.05)

                    # 设置冷却
                    agent.conversation_cooldown = 3
                    target_agent.conversation_cooldown = 3

                    # 为双方生成对话记忆
                    mem_a = MemoryManager(agent.id)
                    mem_b = MemoryManager(target_agent.id)
                    mem_a.add_memory(
                        content=conversation_result["summary"],
                        tick=world_context.get("tick", 0),
                        virtual_time=world_context["virtual_time"],
                        importance=quality,
                        tags=["对话", target_agent.name],
                        related_agents=[target_agent.id],
                    )
                    mem_b.add_memory(
                        content=conversation_result["summary"],
                        tick=world_context.get("tick", 0),
                        virtual_time=world_context["virtual_time"],
                        importance=quality,
                        tags=["对话", agent.name],
                        related_agents=[agent.id],
                    )

                    # 设置活动
                    agent.activity = f"和{target_agent.name}聊天"
                    target_agent.activity = f"和{agent.name}聊天"

    # 保存记忆到 MemoryManager
    if state["new_memory"] and state["memory_importance"] > 0.05:
        mem = MemoryManager(agent.id)
        mem.add_memory(
            content=state["new_memory"],
            tick=world_context.get("tick", 0),
            virtual_time=world_context["virtual_time"],
            importance=state["memory_importance"],
        )

    # 添加到短期记忆
    if state["new_memory"]:
        agent.short_term.append(state["new_memory"])

    # 心情更新：做擅长的事
    if state["action_type"] == "do" and state["action_success"]:
        skill_value = agent.skills.get(state["action_detail"], 0)
        if skill_value >= 0.7:
            agent.modify_mood(0.03)  # 做擅长的事，心情微增

    # 心情更新：在喜欢的地点
    loc = get_location_at(agent.x, agent.y)
    if loc:
        if agent.personality.extraversion >= 0.7 and loc.id in ("park", "plaza", "cafe"):
            agent.modify_mood(0.02)

    # 心情更新：违背作息
    if "必须" in constraint_text and state["action_type"] != "move":
        penalty = 0.1 * agent.personality.get_mood_penalty_multiplier()
        agent.modify_mood(-penalty)

    # 记录统计
    agent.tick_count += 1

    # 返回摘要
    result = {
        "agent_id": agent.id,
        "thought": state["thought"],
        "action_type": state["action_type"],
        "action_detail": state["action_detail"],
        "action_result": state["action_result"],
        "degrade_level": state["degrade_level"],
        "new_memory": state["new_memory"],
    }

    # 如果有对话结果，加入返回
    if conversation_result:
        result["conversation"] = conversation_result

    return result


async def _act(state: AgentState, agent: Agent, agent_manager) -> AgentState:
    """内部的 act 执行函数。"""
    return await act_node(state, agent, agent_manager)
