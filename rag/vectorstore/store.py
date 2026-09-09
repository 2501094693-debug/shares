"""向量数据库。"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from rag.config import COLLECTION_NAME, RETRIEVAL_K, VECTOR_STORE_DIR
from rag.embedding import get_embeddings


def get_vector_store(*, persist: bool = True) -> Chroma:
    """加载已有向量库。"""
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(VECTOR_STORE_DIR) if persist else None,
    )


def build_vector_store(chunks: list[Document]) -> Chroma:
    """将文本片段写入向量库。"""
    if not chunks:
        raise ValueError("没有可索引的文档片段")

    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        collection_name=COLLECTION_NAME,
        persist_directory=str(VECTOR_STORE_DIR),
    )


def get_retriever(*, search_k: int | None = None) -> VectorStoreRetriever:
    """获取检索器。"""
    store = get_vector_store()
    return store.as_retriever(search_kwargs={"k": search_k or RETRIEVAL_K})


def vector_store_exists() -> bool:
    """检查向量库是否已构建。"""
    return VECTOR_STORE_DIR.exists() and any(VECTOR_STORE_DIR.iterdir())
