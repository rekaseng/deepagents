"""LLM brain — DeepSeek via langchain-deepseek (OpenAI-compatible, tool calling)."""

from functools import lru_cache

from langchain_deepseek import ChatDeepSeek

from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


@lru_cache(maxsize=1)
def get_model() -> ChatDeepSeek:
    # Like the TS side, a missing key fails at CALL time (clear 401), not boot —
    # the server and non-LLM endpoints stay usable.
    if not DEEPSEEK_API_KEY:
        print("[model] WARNING: DEEPSEEK_API_KEY not set — LLM calls will fail until configured")
    return ChatDeepSeek(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY or "missing-key",
        api_base=DEEPSEEK_BASE_URL,
        max_tokens=4096,
        max_retries=3,
    )
