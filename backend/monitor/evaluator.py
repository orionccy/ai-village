"""
============================================================
evaluator.py — LLM-as-Judge 定期评估
============================================================
每 20 个 tick 调用 LLM 从 5 个维度评估 Agent 表现。
"""

import logging
from backend.llm.client import llm_invoke_json
from backend.llm.prompts import EVALUATION_PROMPT

logger = logging.getLogger("ai_village.evaluator")


async def evaluate_agent(agent_profile: str, behavior_log: str) -> dict:
    """
    对单个 Agent 进行 LLM 评估。

    Returns:
        {"role_consistency": 7, "social_reasonableness": 8, ...}
    """
    user_prompt = EVALUATION_PROMPT.format(
        agent_profile=agent_profile,
        behavior_log=behavior_log[:1000],  # 限制长度
    )
    result = await llm_invoke_json("你是 AI Village 观察员。只输出 JSON。", user_prompt)

    if result:
        return result

    # 降级：返回默认评分
    return {
        "role_consistency": 5,
        "social_reasonableness": 5,
        "memory_accuracy": 5,
        "behavior_diversity": 5,
        "emotion_authenticity": 5,
        "overall": 5,
        "comment": "评估暂不可用",
    }


async def run_evaluation(agent_manager, metrics_collector, tick: int) -> list[dict]:
    """
    对所有 Agent 运行评估。

    Returns:
        [{agent_id, name, scores, ...}]
    """
    results = []
    for agent in agent_manager.get_all():
        # 收集最近的行为日志
        recent = [m for m in metrics_collector.get_recent(20)
                  if m.agent_id == agent.id]
        behavior_log = "\n".join(
            f"Tick {m.tick}: {m.action_type} (降级L{m.degrade_level}) 心情={m.mood:.2f}"
            for m in recent[-10:]
        )

        if not behavior_log:
            continue

        profile = f"{agent.name}，{agent.age}岁，{agent.job}，" \
                  f"性格: {agent.personality.describe()}"

        scores = await evaluate_agent(profile, behavior_log)
        results.append({
            "agent_id": agent.id,
            "name": agent.name,
            "scores": scores,
        })

    return results
