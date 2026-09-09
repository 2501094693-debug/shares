"""文本加载。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document


def _load_single_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(path))
    elif suffix in {".md", ".markdown", ".txt", ".csv", ".json"}:
        loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    else:
        return []

    docs = loader.load()
    for doc in docs:
        doc.metadata.setdefault("source", str(path))
    return docs


def load_documents(source: Path) -> list[Document]:
    """从文件或目录加载文档。"""
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"路径不存在: {source}")

    if source.is_file():
        return _load_single_file(source)

    patterns = {
        "**/*.pdf": PyPDFLoader,
        "**/*.txt": TextLoader,
        "**/*.md": TextLoader,
        "**/*.markdown": TextLoader,
    }
    documents: list[Document] = []
    for glob_pattern, loader_cls in patterns.items():
        loader_kwargs = {"encoding": "utf-8", "autodetect_encoding": True} if loader_cls is TextLoader else {}
        loader = DirectoryLoader(
            str(source),
            glob=glob_pattern,
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs,
            show_progress=True,
            use_multithreading=True,
        )
        documents.extend(loader.load())

    if not documents:
        raise ValueError(f"未在 {source} 中找到支持的文档（pdf/txt/md）")

    for doc in documents:
        doc.metadata.setdefault("source", doc.metadata.get("source", str(source)))
    return documents
