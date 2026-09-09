#!/usr/bin/env python3
"""RAG 命令行入口。

用法:
    python -m rag.main ingest documents/
    python -m rag.main query "文档的主要内容是什么？"
    python -m rag.main chat
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rag.config import DOCUMENTS_DIR, OPENAI_API_KEY, VECTOR_STORE_DIR
from rag.loading import load_documents
from rag.query import ask, retrieve_sources
from rag.splitting import split_documents
from rag.vectorstore import build_vector_store, get_retriever, vector_store_exists


def cmd_ingest(source: Path, *, rebuild: bool) -> int:
    if not OPENAI_API_KEY:
        print("错误: 请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        return 1

    if rebuild and VECTOR_STORE_DIR.exists():
        shutil.rmtree(VECTOR_STORE_DIR)

    print(f"加载文档: {source}")
    documents = load_documents(source)
    print(f"  共 {len(documents)} 页/篇")

    chunks = split_documents(documents)
    print(f"  切分为 {len(chunks)} 个片段，正在写入向量库...")

    build_vector_store(chunks)
    print(f"  向量库已保存: {VECTOR_STORE_DIR}")
    return 0


def cmd_query(question: str, *, show_sources: bool) -> int:
    if not OPENAI_API_KEY:
        print("错误: 请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        return 1
    if not vector_store_exists():
        print(
            f"错误: 向量库不存在，请先执行 ingest，例如:\n"
            f"  python -m rag.main ingest {DOCUMENTS_DIR}",
            file=sys.stderr,
        )
        return 1

    retriever = get_retriever()
    if show_sources:
        docs = retrieve_sources(question, retriever)
        print("【检索到的片段】")
        for index, doc in enumerate(docs, start=1):
            source = doc.metadata.get("source", "unknown")
            preview = doc.page_content.replace("\n", " ")[:160]
            print(f"  {index}. {source}\n     {preview}...\n")

    answer = ask(question, retriever)
    print("【回答】")
    print(answer)
    return 0


def cmd_chat(*, show_sources: bool) -> int:
    if not OPENAI_API_KEY:
        print("错误: 请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        return 1
    if not vector_store_exists():
        print(
            f"错误: 向量库不存在，请先执行 ingest，例如:\n"
            f"  python -m rag.main ingest {DOCUMENTS_DIR}",
            file=sys.stderr,
        )
        return 1

    retriever = get_retriever()
    print("RAG 对话模式，输入 exit 或 quit 退出。\n")
    while True:
        try:
            question = input("问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break

        if show_sources:
            docs = retrieve_sources(question, retriever)
            print("【检索到的片段】")
            for index, doc in enumerate(docs, start=1):
                source = doc.metadata.get("source", "unknown")
                preview = doc.page_content.replace("\n", " ")[:120]
                print(f"  {index}. {source} — {preview}...")

        answer = ask(question, retriever)
        print(f"\n{answer}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LangChain RAG")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="加载文档并构建向量库")
    ingest_parser.add_argument(
        "source",
        nargs="?",
        default=str(DOCUMENTS_DIR),
        help="文档文件或目录路径（默认 rag/documents）",
    )
    ingest_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="重建向量库（删除旧索引）",
    )

    query_parser = subparsers.add_parser("query", help="单次问答")
    query_parser.add_argument("question", help="问题")
    query_parser.add_argument(
        "--sources",
        action="store_true",
        help="显示检索到的文档片段",
    )

    chat_parser = subparsers.add_parser("chat", help="交互式问答")
    chat_parser.add_argument(
        "--sources",
        action="store_true",
        help="显示检索到的文档片段",
    )

    args = parser.parse_args()

    if args.command == "ingest":
        return cmd_ingest(Path(args.source), rebuild=args.rebuild)
    if args.command == "query":
        return cmd_query(args.question, show_sources=args.sources)
    if args.command == "chat":
        return cmd_chat(show_sources=args.sources)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
