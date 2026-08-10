"""公司代码 → 检索关键词。"""

from __future__ import annotations

from message.disclosure.http_util import normalize_code, safe_str
from message.disclosure.sources_cninfo import resolve_org


def resolve_keywords(code_or_name: str) -> dict[str, str]:
    """返回 code / name / keyword（优先简称，否则用入参）。"""
    raw = safe_str(code_or_name)
    code = normalize_code(raw)
    name = ""
    if code:
        meta = resolve_org(code)
        if meta:
            name = safe_str(meta.get("name"))
            code = safe_str(meta.get("code")) or code
    if not name:
        # 入参可能本身就是公司名
        if not code or raw != code:
            name = raw
    keyword = name or code or raw
    return {"code": code, "name": name, "keyword": keyword}
