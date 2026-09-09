"""RAG 配置。"""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ROOT_ENV, override=True)
load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).parent
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
VECTOR_STORE_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "rag_docs")


def _resolve_llm_model() -> str:
    explicit = (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
    base = (os.getenv("OPENAI_BASE_URL") or "").lower()
    if "deepseek" in base:
        if not explicit or explicit.lower().startswith("gpt-"):
            return "deepseek-v4-pro"
        return explicit
    return explicit or "gpt-4o"


def _resolve_embedding_model() -> str:
    explicit = (os.getenv("EMBEDDING_MODEL") or "").strip()
    if explicit:
        return explicit
    base = (os.getenv("OPENAI_BASE_URL") or "").lower()
    if "deepseek" in base:
        return "text-embedding-3-small"
    return "text-embedding-3-small"


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = _resolve_llm_model()
EMBEDDING_MODEL = _resolve_embedding_model()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "600"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
RETRIEVAL_K = int(os.getenv("RAG_RETRIEVAL_K", "4"))
