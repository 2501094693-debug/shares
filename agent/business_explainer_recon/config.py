"""业务解读智能体（复原版）— 配置。

复原自 2026-09-08 提交 7b1dd54 的 ``ai/config.py``：
- 落盘目录改为本子文件夹下的 ``reports/``，避免污染现有 ``agent/reports``；
- ``BACKEND_ROOT`` 默认指向仓库内 ``backend/``（原版默认指向开发机绝对路径）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parents[1]

_ROOT_ENV = _REPO_ROOT / ".env"
load_dotenv(_ROOT_ENV, override=True)
load_dotenv(override=True)

PROJECT_ROOT = _PKG_ROOT
REPORTS_DIR = PROJECT_ROOT / "reports"

BACKEND_ROOT = Path(
    os.getenv(
        "BACKEND_ROOT",
        str(_REPO_ROOT / "backend"),
    )
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")


def _resolve_llm_model() -> str:
    """LLM_MODEL 优先，其次 OPENAI_MODEL；DeepSeek 接口不接受 gpt-* 名称。"""
    explicit = (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
    base = (os.getenv("OPENAI_BASE_URL") or "").lower()
    if "deepseek" in base:
        if not explicit or explicit.lower().startswith("gpt-"):
            return "deepseek-v4-pro"
        return explicit
    return explicit or "gpt-4o"


LLM_MODEL = _resolve_llm_model()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "600"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

DATA_LOOKBACK_DAYS = int(os.getenv("DATA_LOOKBACK_DAYS", "365"))
