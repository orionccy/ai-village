"""
============================================================
client.py — LLM 客户端封装
============================================================
封装 DeepSeek Flash API，提供统一的调用接口。

三种调用模式：
1. 正常模式 — 调用 API，返回 LLM 响应
2. 降级模式 — API Key 未配置时，返回 None
3. 超时/错误处理 — 超时自动返回 None，由调用方走规则降级

设计原则：
- 所有 LLM 调用通过此模块，统一超时和错误处理
- 调用方（LangGraph）不需要关心具体的 API 细节
- 返回 None 表示调用失败，调用方负责降级处理
============================================================
"""

import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import SecretStr

from backend.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_ENABLED,
)

logger = logging.getLogger("ai_village.llm")

# ============================================================
# LLM 实例 (单例)
# ============================================================

_llm_instance: Optional[ChatOpenAI] = None


def get_llm() -> Optional[ChatOpenAI]:
    """
    获取 LLM 客户端实例（单例模式）。

    首次调用时创建，后续返回同一实例。
    如果 API Key 未配置，返回 None。

    Returns:
        ChatOpenAI 实例，或 None（表示 LLM 不可用）
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    if not LLM_ENABLED:
        logger.warning("⚠️  LLM 未配置 (DEEPSEEK_API_KEY 为空)，将使用规则降级")
        return None

    try:
        _llm_instance = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=SecretStr(DEEPSEEK_API_KEY),
            base_url=DEEPSEEK_BASE_URL,
            temperature=0.8,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
            max_completion_tokens=256,  # 决策输出不需要太长
        )
        logger.info(f"🤖 LLM 客户端已创建: {DEEPSEEK_MODEL}")
        return _llm_instance
    except Exception as e:
        logger.error(f"❌ LLM 客户端创建失败: {e}")
        return None


# ============================================================
# 调用接口
# ============================================================

async def llm_invoke(
    system_prompt: str,
    user_prompt: str,
) -> Optional[str]:
    """
    调用 LLM，发送 system prompt + user prompt，返回响应文本。

    这是所有 LLM 调用的统一入口。

    Args:
        system_prompt: 系统提示词（角色设定、行为指南）
        user_prompt: 用户提示词（当前状态、决策要求）

    Returns:
        LLM 响应的文本内容。失败时返回 None。
        调用方应检查 None 并走降级逻辑。
    """
    llm = get_llm()

    if llm is None:
        # 降级: 无 LLM 可用
        logger.debug("LLM 不可用，降级为规则决策")
        return None

    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)

        # 提取文本内容（兼容 str 和 list 类型）
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            # content blocks → 拼接所有 text 块
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw
            )
        else:
            content = str(raw) if raw else ""

        # 记录消耗的 token
        _record_token_usage(response)

        return content.strip() if content else None

    except Exception as e:
        logger.warning(f"⚠️  LLM 调用失败: {type(e).__name__}: {e}")
        return None


async def llm_invoke_json(
    system_prompt: str,
    user_prompt: str,
) -> Optional[dict]:
    """
    调用 LLM 并解析 JSON 响应。

    比 llm_invoke 多了一层 JSON 解析。
    解析失败时返回 None。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词（应包含 "请以 JSON 格式返回" 指令）

    Returns:
        解析后的字典，或 None
    """
    import json
    import re

    text = await llm_invoke(system_prompt, user_prompt)

    if text is None:
        return None

    # 尝试多种方式解析 JSON
    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 尝试提取 ```json ... ``` 代码块中的内容
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. 尝试提取第一个 { ... } 对象
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"⚠️  LLM 返回了非 JSON 格式的内容: {text[:100]}...")
    return None


# ============================================================
# Token 统计
# ============================================================

# 全局 token 计数器
_total_tokens = 0
_total_calls = 0


def _record_token_usage(response):
    """
    从 LLM 响应中提取并记录 token 消耗。

    使用 langchain 的 response_metadata 获取 token 信息。
    """
    global _total_tokens, _total_calls
    _total_calls += 1

    try:
        meta = getattr(response, "response_metadata", {})
        usage = meta.get("token_usage", {}) if isinstance(meta, dict) else {}
        tokens = usage.get("total_tokens", 0)
        _total_tokens += tokens
    except Exception:
        pass  # token 统计不是关键功能，失败不影响运行


def get_token_stats() -> dict:
    """获取 token 使用统计。"""
    return {
        "total_tokens": _total_tokens,
        "total_calls": _total_calls,
        "avg_tokens": round(_total_tokens / _total_calls, 1) if _total_calls > 0 else 0,
    }
