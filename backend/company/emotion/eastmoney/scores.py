"""东财千股千评：社区情绪的量化快照，不是评论文本。

    https://data.eastmoney.com/stockcomment/stock/600519.html
    GET https://datacenter-web.eastmoney.com/api/data/v1/get
        reportName=RPT_DMSK_TS_STOCKNEW
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code, safe_str
from core.fmt import to_float

from company.emotion.eastmoney._common import (
    CHANNEL_SCORES,
    SCORES_API,
    SOURCE,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    resolve_keyword,
    scores_page_url,
    to_int,
)

logger = logging.getLogger(__name__)

TOKEN = "894050c76af8597a853f5b408b759f5d"


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = to_float(value)
    if number is None:
        return ""
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def query_scores(code: str) -> dict[str, Any]:
    """个股千股千评原始 JSON。"""
    stock = normalize_code(code) or safe_str(code)
    payload = get_payload(
        SCORES_API,
        params={
            "sortColumns": "SECURITY_CODE",
            "sortTypes": "1",
            "pageSize": "1",
            "pageNumber": "1",
            "reportName": "RPT_DMSK_TS_STOCKNEW",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{stock}")',
            "source": "WEB",
            "client": "WEB",
            "token": TOKEN,
        },
        headers=headers_for(scores_page_url(stock)),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def fetch_scores(code_or_name: str) -> dict[str, Any]:
    """个股千股千评：综合得分 / 关注指数 / 机构参与度 / 排名。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page = scores_page_url(code)
    if not code:
        return empty_pack(channel=CHANNEL_SCORES, error="缺少股票代码", page=page)
    try:
        payload = query_scores(code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("千股千评失败 %s: %s", code, exc)
        return empty_pack(
            code=code,
            name=name,
            channel=CHANNEL_SCORES,
            error=str(exc),
            page=page,
        )
    rows = ((payload.get("result") or {}).get("data") or [])
    row = rows[0] if isinstance(rows, list) and rows else {}
    if not row:
        return empty_pack(
            code=code,
            name=name,
            channel=CHANNEL_SCORES,
            error="无千股千评数据",
            page=page,
        )
    name = safe_str(row.get("SECURITY_NAME_ABBR")) or name
    score = to_float(row.get("TOTALSCORE"))
    focus = to_float(row.get("FOCUS"))
    rank_n = to_int(row.get("RANK"))
    title = f"综合得分 {_fmt_num(score)} · 关注 {_fmt_num(focus)} · 排名 {rank_n}"
    item = {
        "code": code,
        "name": name,
        "title": title,
        "summary": title,
        "published_at": fmt_dt(row.get("TRADE_DATE")),
        "url": page,
        "source": SOURCE,
        "channel": CHANNEL_SCORES,
        "media_name": "千股千评",
        "price": to_float(row.get("CLOSE_PRICE")),
        "change_rate": to_float(row.get("CHANGE_RATE")),
        "turnover_rate": to_float(row.get("TURNOVERRATE")),
        "pe": to_float(row.get("PE_DYNAMIC")),
        "prime_cost": to_float(row.get("PRIME_COST")),
        "org_participate": to_float(row.get("ORG_PARTICIPATE")),
        "total_score": score,
        "rank": rank_n,
        "rank_up": to_int(row.get("RANK_UP")),
        "focus": focus,
        "ratio": to_float(row.get("RATIO")),
        "ratio_3d": to_float(row.get("RATIO_3DAYS")),
        "ratio_50d": to_float(row.get("RATIO_50DAYS")),
    }
    return {
        "code": code,
        "name": name,
        "source": SOURCE,
        "channel": CHANNEL_SCORES,
        "count": 1,
        "total": 1,
        "items": [item],
        "page": page,
        "title": title,
        "total_score": score,
        "focus": focus,
        "rank": rank_n,
        "org_participate": item["org_participate"],
        "trade_date": item["published_at"],
    }
