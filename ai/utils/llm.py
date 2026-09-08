"""LLM 与工具初始化。"""

from langchain_openai import ChatOpenAI

from config import (
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_REQUEST_TIMEOUT,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)


def get_llm() -> ChatOpenAI:
    kwargs = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "api_key": OPENAI_API_KEY,
        "timeout": LLM_REQUEST_TIMEOUT,
        "max_retries": LLM_MAX_RETRIES,
    }
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**kwargs)
