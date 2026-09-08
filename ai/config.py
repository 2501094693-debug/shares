"""业务简述 LangGraph 配置。"""

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
        r"c:\Users\Administrator\Desktop\test\backend",
    )
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "600"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

DATA_LOOKBACK_DAYS = int(os.getenv("DATA_LOOKBACK_DAYS", "365"))
