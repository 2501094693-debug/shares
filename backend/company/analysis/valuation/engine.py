"""估值编排引擎：把 DCF 绝对估值、相对估值与安全边际串成一份报告。

调用链：
  1. 财报（东财 F10）→ metrics + 年度系列（供 DCF 营收 CAGR）
  2. 盘口画像 → 当前价、总股本、PE/PB/PS、行业
  3. 历史估值序列 → 3~5 年 PE/PB/PS 分位
  4. 同业倍数（逐只取最新 PE/PB/PS）→ 同业对比
  5. DCF → 每股内在价值；相对估值 → 历史/同业定位
  6. 安全边际 = (内在价值 - 当前价) / 内在价值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.api import err, ok
from core.codes import normalize_code
from core.fmt import to_float

from company.news.financialreport._common import is_annual
from company.news.financialreport.fetcher import get_financial_report
from company.analysis.financialreport._common import normalize_report_type
from company.analysis.financialreport.engine import analyze_rows

from .dcf import dcf_valuate, DcfAssumptions, DcfResult
from .relative import relative_valuate, RelativeResult

_YI = 1e8
DEFAULT_PEER_LIMIT = 6

# 行情/行情序列/同业模块依赖 akshare 等重依赖，在模块加载时做延迟、可容错的导入，
# 避免单一环境问题导致整个 valuation 包无法被 import。单依赖缺失时对应变量为 None。
_get_stock_profile = None
_fetch_pe_history = None
_compare_peers = None
try:
    from company.profile import get_stock_profile as _get_stock_profile  # noqa: F401
except Exception:  # noqa: BLE001
    pass
try:
    from company.statistics.quote.fetch import fetch_pe_history as _fetch_pe_history  # noqa: F401
except Exception:  # noqa: BLE001
    pass
try:
    from company.analysis.competition.compare import compare_peers as _compare_peers  # noqa: F401
except Exception:  # noqa: BLE001
    pass


@dataclass
class ValuationInput:
    code: str
    name: str = ""
    report_type: str = "annual"
    force: bool = False
    peer_limit: int = DEFAULT_PEER_LIMIT
    wacc: float | None = None
    terminal_growth: float | None = None
    projection_years: int | None = None
    first_stage_growth: float | None = None
    safety_discount: float = 0.0


@dataclass
class ValuationResult:
    code: str
    name: str
    report_type: str
    data_available: bool
    industry: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)

    dcf: DcfResult | None = None
    relative: RelativeResult | None = None

    margin_of_safety_pct: float | None = None
    verdict: str = "数据不足"          # 买入/观望/回避 的定性提示（非投资建议）
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "report_type": self.report_type,
            "data_available": self.data_available,
            "industry": self.industry,
            "profile": self.profile,
            "dcf": self._as_plain(self.dcf),
            "relative": self._as_plain(self.relative),
            "margin_of_safety_pct": self.margin_of_safety_pct,
            "verdict": self.verdict,
            "notes": self.notes,
            "errors": self.errors,
        }

    @staticmethod
    def _as_plain(obj: Any) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dataclass_fields__"):
            out: dict[str, Any] = {}
            for k in obj.__dataclass_fields__:
                v = getattr(obj, k)
                out[k] = ValuationResult._as_plain(v)
            return out
        if isinstance(obj, list):
            return [ValuationResult._as_plain(x) for x in obj]
        if isinstance(obj, dict):
            return {k: ValuationResult._as_plain(v) for k, v in obj.items()}
        return obj


def _latest_peer_multiples(companies: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """为同业公司逐只取最新 PE/PB/PS（最多 limit 家，失败单只不中断）。"""
    if _fetch_pe_history is None:
        return []
    peers: list[dict[str, Any]] = []
    taken = 0
    for c in companies:
        if c.get("is_target"):
            continue
        if taken >= limit:
            break
        code = c.get("code")
        name = c.get("name") or code
        try:
            pack = _fetch_pe_history(str(code), limit=60, force=False)
        except Exception as exc:  # noqa: BLE001
            peers.append(
                {"code": code, "name": name, "error": str(exc)[:80], "pe_ttm": None, "pb": None, "ps_ttm": None}
            )
            taken += 1
            continue
        items = list(pack.get("items") or [])
        latest = items[-1] if items else {}
        peers.append(
            {
                "code": code,
                "name": name,
                "pe_ttm": to_float(latest.get("pe_ttm")),
                "pb": to_float(latest.get("pb")),
                "ps_ttm": to_float(latest.get("ps_ttm")),
                "latest_date": latest.get("time"),
            }
        )
        taken += 1
    return peers


def run_valuation(
    code: str,
    name: str = "",
    *,
    report_type: str = "annual",
    force: bool = False,
    peer_limit: int = DEFAULT_PEER_LIMIT,
    wacc: float | None = None,
    terminal_growth: float | None = None,
    projection_years: int | None = None,
    first_stage_growth: float | None = None,
    safety_discount: float = 0.0,
) -> dict[str, Any]:
    """对单只股票跑完整估值：DCF + 相对估值 + 安全边际。

    返回可直接 JSON 化的字典（含 to_dict 兼容结构）。
    """
    rt = normalize_report_type(report_type)
    code = normalize_code(code) or ""
    if not code:
        return err("缺少有效的 6 位股票代码", 400)

    notes: list[str] = []
    errors: list[str] = []
    if _get_stock_profile is None:
        errors.append("公司画像模块不可用（依赖缺失），将无法取到当前价/总股本")
    if _fetch_pe_history is None:
        errors.append("历史估值序列模块不可用（依赖缺失），历史分位将为空")
    if _compare_peers is None:
        errors.append("同业对比模块不可用（依赖缺失），同业对比将为空")

    # ---------- 1. 财报 ----------
    try:
        pack = get_financial_report(code, scope="all", limit=60, force=force)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"财报获取失败：{exc}")
        pack = {}
    merged = list(pack.get("merged") or [])
    annual = [row for row in merged if is_annual(str(row.get("REPORT_DATE") or ""))]

    fin_result = analyze_rows(merged, rt, code=code, name=name)
    data_available = bool(fin_result.get("data_available"))
    metrics = fin_result.get("metrics") or {}
    if not data_available:
        errors.append(f"未取到 {report_type_label(rt)} 财报数据")

    # ---------- 2. 盘口画像 ----------
    profile_pack: dict[str, Any] = {}
    stock: dict[str, Any] = {}
    industry_meta: dict[str, Any] = {}
    if _get_stock_profile:
        try:
            profile_pack = _get_stock_profile(code, name=name)
            stock = profile_pack.get("stock") or {}
            industry_meta = profile_pack.get("industry") or {}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"盘口画像获取失败：{exc}")
    # 若 _get_stock_profile 为 None，errors 已在导入时记录，stock/industry 保持空

    # ---------- 3. 历史估值序列 ----------
    pe_hist_pack: dict[str, Any] = {}
    if _fetch_pe_history:
        try:
            pe_hist_pack = _fetch_pe_history(code, limit=1500, force=force)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"历史估值序列获取失败：{exc}")

    # ---------- 4. 同业倍数 ----------
    peer_multiples: list[dict[str, Any]] = []
    l3_code = (industry_meta or {}).get("code") or stock.get("l3_code") or ""
    if l3_code and _compare_peers:
        try:
            peers_pack = _compare_peers(
                code,
                industry_code=l3_code,
                report_type=rt,
                peers=peer_limit,
                force=force,
            )
            companies = list(peers_pack.get("companies") or [])
            peer_multiples = _latest_peer_multiples(companies, peer_limit)
            if peers_pack.get("flags"):
                notes.extend([f"同业：{f}" for f in peers_pack["flags"][:3]])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"同业倍数获取失败：{exc}")
    elif l3_code and not _compare_peers:
        pass  # 导入时已记录不可用
    else:
        notes.append("未识别到申万三级行业，同业对比将为空")

    # ---------- 5. DCF 绝对估值 ----------
    assumptions = DcfAssumptions(
        projection_years=projection_years or 5,
        wacc=wacc if wacc is not None else 0.09,
        terminal_growth=terminal_growth if terminal_growth is not None else 0.025,
        first_stage_growth=first_stage_growth,
        safety_discount=safety_discount,
    )
    dcf_result = dcf_valuate(
        metrics,
        profile=stock,
        assumptions=assumptions,
        annual_series=annual,
    )

    # ---------- 6. 相对估值 ----------
    relative_result = relative_valuate(
        stock,
        pe_hist_pack,
        peer_multiples=peer_multiples or None,
    )

    # ---------- 7. 安全边际与定性结论 ----------
    intrinsic = dcf_result.intrinsic_value_per_share
    current_price = stock.get("price") if stock else None
    current_price = to_float(current_price)

    margin_of_safety: float | None = None
    if intrinsic is not None and current_price and current_price > 0:
        margin_of_safety = (intrinsic - current_price) / intrinsic * 100.0

    verdict = _verdict(dcf_result, relative_result, margin_of_safety)

    result = ValuationResult(
        code=code,
        name=name or stock.get("name") or "",
        report_type=rt,
        data_available=data_available,
        industry=industry_meta,
        profile=stock,
        dcf=dcf_result,
        relative=relative_result,
        margin_of_safety_pct=round(margin_of_safety, 2) if margin_of_safety is not None else None,
        verdict=verdict,
        notes=notes,
        errors=errors,
    )
    return ok(result.to_dict())


def report_type_label(rt: str) -> str:
    return {"annual": "年报", "semi": "半年报", "q1": "一季报", "q3": "三季报"}.get(rt, rt)


def _verdict(
    dcf: DcfResult | None,
    relative: RelativeResult | None,
    margin_of_safety: float | None,
) -> str:
    """定性结论：充足安全边际 + 相对低估 → 可考虑；反之回避。仅供参考，不构成投资建议。"""
    signals: list[str] = []

    if dcf and dcf.margin_of_safety_pct is not None:
        if dcf.margin_of_safety_pct >= 30:
            signals.append("DCF 安全边际充足")
        elif dcf.margin_of_safety_pct >= 15:
            signals.append("DCF 安全边际偏薄")
        elif dcf.margin_of_safety_pct > 0:
            signals.append("DCF 接近公允价值")
        else:
            signals.append("DCF 高于市价（高估）")

    if relative:
        if relative.overall == "相对低估":
            signals.append("相对估值偏低")
        elif relative.overall == "相对高估":
            signals.append("相对估值偏高")

    if not signals:
        return "数据不足，无法定论"

    # 综合：两者都看好 → 可考虑；任一方高估 → 观望；都高估 → 回避
    bullish = any(s in ("DCF 安全边际充足", "相对估值偏低") for s in signals)
    bearish = any(s in ("DCF 高于市价（高估）", "相对估值偏高") for s in signals)
    if bearish and not bullish:
        return "回避（估值偏高，安全边际不足）"
    if bearish and bullish:
        return "观望（绝对与相对估值信号分歧）"
    if bullish and margin_of_safety is not None and margin_of_safety >= 30:
        return "可考虑（安全边际充足且相对估值偏低）"
    if bullish:
        return "观望（估值合理，等待更大安全边际）"
    return "观望"
