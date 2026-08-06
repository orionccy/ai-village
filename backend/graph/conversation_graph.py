"""
============================================================
conversation_graph.py — Agent 间对话模块
============================================================
当两个 Agent 双向选择聊天时，在此模块中执行多轮对话。

对话流程:
1. 随机决定对话轮数 (2-4 轮)
2. 双方轮流发言（A → B → A → B → ...）
3. 每轮发言调用 LLM 生成（带对话上下文）
4. 对话结束后，LLM 评估对话质量
5. 更新双方关系值
6. 双方各自存储对话记忆

对话是异步协程，不阻塞 tick 循环中的其他 Agent。
============================================================
"""

import logging
import random
from typing import Optional

from backend.agents.base_agent import Agent
from backend.llm.client import llm_invoke, llm_invoke_json
from backend.llm.prompts import CONVERSATION_SYSTEM_PROMPT, CONVERSATION_USER_PROMPT, EVAL_CONVERSATION_PROMPT
from backend.memory.manager import MemoryManager

logger = logging.getLogger("ai_village.conversation")


# ============================================================
# 对话执行
# ============================================================

async def run_conversation(
    agent_a: Agent,
    agent_b: Agent,
    location_name: str,
    current_time: str,
) -> dict:
    """
    执行两个 Agent 之间的一次对话。

    Args:
        agent_a: 发起对话的 Agent
        agent_b: 被对话的 Agent
        location_name: 当前位置名称
        current_time: 当前虚拟时间

    Returns:
        对话结果字典:
        {
            "rounds": 实际对话轮数,
            "history": [{"speaker": "小明", "message": "..."}, ...],
            "quality_score": 0.0~1.0,
            "summary": 对话摘要文本
        }
    """
    rounds = random.randint(2, 4)
    logger.info(f"💬 [{agent_a.name}] ↔ [{agent_b.name}] 开始对话 ({rounds} 轮) — 地点: {location_name}")

    history = []
    speaker = agent_a
    listener = agent_b

    for i in range(rounds):
        # 生成当前发言者的话
        message = await _generate_turn(
            speaker=speaker,
            listener=listener,
            history=history,
            location_name=location_name,
            current_time=current_time,
        )

        if message is None:
            # LLM 调用失败，提前结束
            break

        history.append({"speaker": speaker.name, "message": message})
        logger.debug(f"  [{speaker.name}]: {message[:50]}...")

        # 交换发言者
        speaker, listener = listener, speaker

    if not history:
        return {"rounds": 0, "history": [], "quality_score": 0.0, "summary": "对话未发生"}

    # 评估对话质量
    quality_score = await _evaluate_conversation(history)

    # 生成总结
    summary = _generate_summary(history, quality_score)

    logger.info(
        f"💬 [{agent_a.name}]↔[{agent_b.name}] 对话结束: "
        f"{len(history)} 轮, 质量 {quality_score:.2f} — {summary}"
    )

    return {
        "rounds": len(history),
        "history": history,
        "quality_score": quality_score,
        "summary": summary,
    }


# ============================================================
# 内部辅助
# ============================================================

async def _generate_turn(
    speaker: Agent,
    listener: Agent,
    history: list[dict],
    location_name: str,
    current_time: str,
) -> Optional[str]:
    """
    生成当前发言者的对话内容。

    Args:
        speaker: 当前发言的 Agent
        listener: 听众 Agent
        history: 之前的对话历史
        location_name: 当前位置
        current_time: 当前时间

    Returns:
        发言文本，失败返回 None
    """
    # 构建对话历史文本
    if history:
        history_text = "\n".join(
            f"{h['speaker']}: {h['message']}" for h in history
        )
    else:
        history_text = "（对话刚开始，你先开口）"

    # 关系描述
    rel_value = speaker.relationships.get(listener.id, 0.0)
    if rel_value >= 5:
        relationship_text = f"你和{listener.name}是好朋友，关系很好"
    elif rel_value >= 2:
        relationship_text = f"你和{listener.name}关系不错"
    elif rel_value >= 0:
        relationship_text = f"你和{listener.name}认识，关系一般"
    else:
        relationship_text = f"你和{listener.name}之间有点不愉快"

    # 最近记忆
    mem_manager = MemoryManager(speaker.id)
    memories_text = mem_manager.get_context_memories(location_name)

    # 构建 Prompt
    system_prompt = CONVERSATION_SYSTEM_PROMPT.format(
        agent_profile=f"{speaker.name}，{speaker.age}岁，{speaker.job}",
        behavior_guide=speaker.personality.get_behavior_guide(),
        skills_text=speaker.get_skills_text(),
    )

    user_prompt = CONVERSATION_USER_PROMPT.format(
        current_time=current_time,
        location_name=location_name,
        listener_name=listener.name,
        relationship_text=relationship_text,
        history_text=history_text,
        memories_text=memories_text[:300],  # 限制长度
    )

    # 调用 LLM（纯文本，不需要 JSON）
    response = await llm_invoke(system_prompt, user_prompt)

    if response:
        # 清理响应（去掉可能的多余格式）
        response = response.strip().strip('"').strip("'")
        # 限制长度
        if len(response) > 100:
            response = response[:100] + "..."
        return response

    # 降级：用简单模板
    fallback_messages = [
        f"你好呀，{listener.name}！",
        "今天天气真不错。",
        f"你最近怎么样？",
        "这里环境真好。",
        "很高兴见到你！",
    ]
    return random.choice(fallback_messages)


async def _evaluate_conversation(history: list[dict]) -> float:
    """
    评估对话质量。

    使用 LLM 对对话进行打分 (0~1)。
    如果 LLM 不可用，使用启发式规则。

    Returns:
        质量分数 0~1
    """
    if not history:
        return 0.0

    # 构建对话文本
    conversation_text = "\n".join(
        f"{h['speaker']}: {h['message']}" for h in history
    )

    # 调用 LLM 评估
    result = await llm_invoke_json(
        "你是一个对话质量评估员。只输出 JSON。",
        EVAL_CONVERSATION_PROMPT.format(conversation_text=conversation_text),
    )

    if result and "quality_score" in result:
        return max(0.0, min(1.0, result["quality_score"]))

    # 降级：启发式评估
    # 轮数越多、消息越长 → 质量越高（粗略估计）
    avg_length = sum(len(h["message"]) for h in history) / len(history)
    base_score = min(0.7, len(history) * 0.15)  # 最多 4 轮 → 0.6
    length_bonus = min(0.3, avg_length / 50 * 0.1)  # 长消息加分
    return base_score + length_bonus


def _generate_summary(history: list[dict], quality: float) -> str:
    """
    生成对话摘要文本。

    Args:
        history: 对话历史
        quality: 质量分数

    Returns:
        摘要文本，如 "小明和小红聊了3轮，相谈甚欢"
    """
    speaker_names = list(set(h["speaker"] for h in history))
    names = "和".join(speaker_names[:2])

    if quality >= 0.7:
        desc = "相谈甚欢"
    elif quality >= 0.4:
        desc = "简短交流了一下"
    else:
        desc = "话不投机"

    topic_hint = ""
    if history:
        first_msg = history[0]["message"][:20]
        topic_hint = f"，聊到了{first_msg}"

    return f"{names}聊了{len(history)}轮，{desc}{topic_hint}"
