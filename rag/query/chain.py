"""RAG 查询链。"""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores import VectorStoreRetriever

from rag.query.llm import get_llm

SYSTEM_PROMPT = """你是一个基于文档的问答助手。请严格依据提供的上下文回答问题。
如果上下文中没有足够信息，请明确说明「根据现有文档无法回答」，不要编造。
回答使用中文，条理清晰，必要时引用上下文要点。"""

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            "上下文:\n{context}\n\n问题: {question}\n\n请给出简洁准确的回答。",
        ),
    ]
)


def _format_docs(docs) -> str:
    parts: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        parts.append(f"[片段 {index} | {source}]\n{doc.page_content}")
    return "\n\n".join(parts)


def build_rag_chain(retriever: VectorStoreRetriever):
    llm = get_llm()
    return (
        {
            "context": retriever | _format_docs,
            "question": RunnablePassthrough(),
        }
        | PROMPT
        | llm
        | StrOutputParser()
    )


def ask(question: str, retriever: VectorStoreRetriever) -> str:
    chain = build_rag_chain(retriever)
    return chain.invoke(question)


def retrieve_sources(question: str, retriever: VectorStoreRetriever):
    return retriever.invoke(question)
