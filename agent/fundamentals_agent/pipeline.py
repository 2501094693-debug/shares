"""流水线编排：Collect → Ledger → Gauge → Brief → Save。无图框架依赖。"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Callable

from agent.config import REPORTS_DIR
from agent.fundamentals_agent.brief import compose_report, write_all_sections
from agent.fundamentals_agent.collect import collect
from agent.fundamentals_agent.gauge import run_gauge
from agent.fundamentals_agent.ledger import build_ledger
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, str], None]


def run_fundamentals(
    company: str,
    *,
    skip_llm: bool = False,
    stock: dict[str, str] | None = None,
) -> dict[str, Any]:
    company = (company or "").strip()
    if not company:
        raise ValueError("缺少公司名称或代码")

    report("fv_resolve", f"正在解析 {company}…", phase="resolve", status="running")
    resolved = stock or resolve_company(company)
    report(
        "fv_resolve",
        f"已解析：{resolved['name']} ({resolved['code']})",
        phase="done",
        status="done",
    )

    pack = collect(company, resolved)

    report("fv_ledger", "构建财务台账…", phase="analyze", status="running")
    ledger = build_ledger(pack)
    report(
        "fv_ledger",
        f"台账完成 · 年报 {len(ledger.years)} 期",
        phase="done",
        status="done",
    )

    report("fv_gauge", "运行仪表盘规则…", phase="analyze", status="running")
    gauge = run_gauge(ledger)
    report(
        "fv_gauge",
        f"仪表盘完成 · 态度 {gauge.stance}",
        phase="done",
        status="done",
    )

    report("fv_brief", "撰写分节解读…", phase="llm", status="running")
    notes = write_all_sections(
        stock_name=pack["stock_name"],
        stock_code=pack["stock_code"],
        ledger=ledger,
        gauge=gauge,
        skip_llm=skip_llm,
    )
    report("fv_brief", "分节解读完成", phase="llm_done", status="done")

    cutoff = pack.get("data_cutoff_date") or date.today().isoformat()
    report_text = compose_report(
        stock_name=pack["stock_name"],
        stock_code=pack["stock_code"],
        cutoff=cutoff,
        ledger=ledger,
        gauge=gauge,
        notes=notes,
        sources=list(pack.get("sources_used") or []),
        errors=list(pack.get("errors") or []),
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", pack["stock_name"] or company)
    code = pack["stock_code"]
    stem = f"{safe_name}_{code}" if code and code not in safe_name else safe_name
    path = REPORTS_DIR / f"{stem}财务估值_{cutoff.replace('-', '')}.md"
    report("fv_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(report_text, encoding="utf-8")
    report("fv_save", f"已保存至 {path.name}", phase="done", status="done")

    return {
        "stock_code": pack["stock_code"],
        "stock_name": pack["stock_name"],
        "stock_market": pack.get("stock_market") or "",
        "data_cutoff_date": cutoff,
        "report": report_text,
        "report_path": str(path),
        "stance": gauge.stance,
        "anchor_iv": gauge.anchor_iv,
        "anchor_mos": gauge.anchor_mos,
        "dims": [d.__dict__ for d in gauge.dims],
        "ledger": ledger.to_dict(),
        "gauge": gauge.to_dict(),
        "sources_used": pack.get("sources_used") or [],
        "errors": pack.get("errors") or [],
    }
