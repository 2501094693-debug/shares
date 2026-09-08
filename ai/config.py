"""AI LangGraph 配置（业务简述 / 财报解读）。"""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ROOT_ENV, override=True)
load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).parent
REPORTS_DIR = PROJECT_ROOT / "reports"

BACKEND_ROOT = Path(
    os.getenv(
        "BACKEND_ROOT",
        str(Path(__file__).resolve().parents[1] / "backend"),
    )
)

def _resolve_llm_model() -> str:
    """LLM_MODEL 优先，其次 OPENAI_MODEL；DeepSeek 接口不接受 gpt-* 名称。"""
    explicit = (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
    base = (os.getenv("OPENAI_BASE_URL") or "").lower()
    if "deepseek" in base:
        if not explicit or explicit.lower().startswith("gpt-"):
            return "deepseek-v4-pro"
        return explicit
    return explicit or "gpt-4o"


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = _resolve_llm_model()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "600"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

DATA_LOOKBACK_DAYS = int(os.getenv("DATA_LOOKBACK_DAYS", "365"))

ENABLE_WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "true").lower() in {"1", "true", "yes", "on"}
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "8"))
