"""仪表盘规则单测：不依赖网络。"""

from __future__ import annotations

from agent.fundamentals_agent.gauge import run_gauge
from agent.fundamentals_agent.ledger import HistoryMult, Ledger, Snapshot, YearPoint


def _years() -> list[YearPoint]:
    return [
        YearPoint(
            period="2024",
            revenue=100e8,
            op_profit=12e8,
            net_profit=10e8,
            gross_margin=35,
            op_margin=12,
            roe=18,
            roa=8,
            ocf=11e8,
            capex=2e8,
            fcf=9e8,
            ocf_ni=110,
            cash=20e8,
            total_liab=40e8,
            debt_ratio=35,
            current_ratio=2.0,
            quick_ratio=1.5,
            short_loan=5e8,
        ),
        YearPoint(
            period="2023",
            revenue=90e8,
            op_profit=10e8,
            net_profit=9e8,
            gross_margin=34,
            op_margin=11,
            roe=16,
            roa=7.5,
            ocf=10e8,
            capex=2e8,
            fcf=8e8,
            ocf_ni=110,
            cash=18e8,
            debt_ratio=36,
            current_ratio=1.9,
            quick_ratio=1.4,
        ),
        YearPoint(
            period="2022",
            revenue=80e8,
            op_profit=9e8,
            net_profit=8e8,
            gross_margin=33,
            op_margin=11,
            roe=15,
            roa=7,
            ocf=9e8,
            capex=2e8,
            fcf=7e8,
            ocf_ni=112,
            cash=16e8,
            debt_ratio=37,
            current_ratio=1.8,
            quick_ratio=1.3,
        ),
    ]


def test_gauge_healthy_company_has_mos():
    years = _years()
    ledger = Ledger(
        years=years,
        snap=Snapshot(price=50.0, mcap=500e8, pe_ttm=20, pb=3, ps_ttm=4, eps=2.5, shares=10e8),
        history={
            "pe_ttm": HistoryMult("pe_ttm", count=100, median=25, low=15, high=40, latest=20),
            "pb": HistoryMult("pb", count=100, median=3.5, low=2, high=5, latest=3),
            "ps_ttm": HistoryMult("ps_ttm", count=100, median=4.5, low=3, high=6, latest=4),
        },
        growth={"rev_cagr": 0.12, "ni_cagr": 0.12, "op_cagr": 0.15, "n": 3},
        quality={
            "roe_med": 16,
            "roa_med": 7.5,
            "gm_med": 34,
            "opm_med": 11,
            "ocf_ni_med": 110,
            "fcf_med": 8e8,
            "debt_latest": 35,
            "cash_latest": 20e8,
            "current_latest": 2.0,
            "quick_latest": 1.5,
        },
    )
    gauge = run_gauge(ledger)
    assert gauge.anchor_iv is not None
    assert gauge.anchor_mos is not None
    assert gauge.stance in {"具备安全边际", "谨慎乐观", "观望", "偏贵", "回避"}
    assert len(gauge.dims) == 5
    assert all(d.light in {"green", "yellow", "red", "gray"} for d in gauge.dims)
    assert "dashboard" in gauge.tables
    assert "intrinsic" in gauge.tables


def test_gauge_expensive_red_valuation():
    years = _years()
    ledger = Ledger(
        years=years,
        snap=Snapshot(price=100.0, mcap=1000e8, pe_ttm=60, pb=8, ps_ttm=12, eps=1.5, shares=10e8),
        history={
            "pe_ttm": HistoryMult("pe_ttm", count=100, median=20, low=12, high=30, latest=60),
            "pb": HistoryMult("pb", count=100, median=3, low=2, high=4, latest=8),
            "ps_ttm": HistoryMult("ps_ttm", count=100, median=4, low=2, high=5, latest=12),
        },
        growth={"rev_cagr": 0.02, "ni_cagr": -0.1, "op_cagr": -0.05, "n": 3},
        quality={
            "roe_med": 6,
            "roa_med": 2,
            "gm_med": 12,
            "opm_med": 3,
            "ocf_ni_med": 30,
            "fcf_med": -1e8,
            "debt_latest": 80,
            "cash_latest": 2e8,
            "current_latest": 0.8,
            "quick_latest": 0.5,
        },
    )
    # override years[0] fcf negative for cash dim
    years[0].fcf = -1e8
    years[1].fcf = -1e8
    years[2].fcf = -1e8
    gauge = run_gauge(ledger)
    lights = {d.key: d.light for d in gauge.dims}
    assert lights["valuation"] == "red"
    assert gauge.stance in {"回避", "偏贵", "观望"}
