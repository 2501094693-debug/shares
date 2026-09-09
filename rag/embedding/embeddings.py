"""文本嵌入。"""

from langchain_openai import OpenAIEmbeddings

from rag.config import EMBEDDING_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL


def get_embeddings() -> OpenAIEmbeddings:
    """获取 Embedding 模型实例。"""
    kwargs = {
        "model": EMBEDDING_MODEL,
        "api_key": OPENAI_API_KEY,
    }
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAIEmbeddings(**kwargs)
