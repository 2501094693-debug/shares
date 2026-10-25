"""select 分析方式的参数定义、校验与默认值。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class PriceParams:
    """目标日价格在区间中的位置。"""

    start: str = ""
    end: str = ""
    target: str = ""
    order: str = "desc"
    enabled: bool = True

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.start or not self.end or not self.target:
            raise ValueError("price.start/end/target 不能为空")
        if self.start > self.end:
            raise ValueError("price.start 不能晚于 end")
        if self.order not in ("asc", "desc"):
            raise ValueError("price.order 须为 asc 或 desc")

    @classmethod
    def from_dict(cls, d: dict | None) -> "PriceParams":
        d = dict(d or {})
        return cls(
            start=str(d.get("start", "")),
            end=str(d.get("end", "")),
            target=str(d.get("target", "")),
            order=str(d.get("order", "desc")).lower(),
            enabled=bool(d.get("enabled", True)),
        )


@dataclass
class JettonParams:
    """筹码分布 jetton：区间 + 分布形态 + 换手衰减。"""

    start: str = ""
    end: str = ""
    f_mode: str = "triangle"
    k_kind: str = "flat"
    seed: str = "triangle"
    base: float = 0.05
    width: float = 0.02
    enabled: bool = True

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.start or not self.end:
            raise ValueError("jetton.start/end 不能为空")
        if self.start > self.end:
            raise ValueError("jetton.start 不能晚于 end")

    @classmethod
    def from_dict(cls, d: dict | None) -> "JettonParams":
        d = dict(d or {})
        return cls(
            start=str(d.get("start", "")),
            end=str(d.get("end", "")),
            f_mode=str(d.get("f_mode", "triangle")),
            k_kind=str(d.get("k_kind", "flat")),
            seed=str(d.get("seed", "triangle")),
            base=float(d.get("base", 0.05)),
            width=float(d.get("width", 0.02)),
            enabled=bool(d.get("enabled", True)),
        )


@dataclass
class FilterParams:
    """按模块返回结果筛选的阈值，均为可选（None = 不过滤）。"""

    price_percent_min: dict = field(default_factory=dict)
    price_percent_max: dict = field(default_factory=dict)
    profit_ratio_min: float | None = None
    profit_ratio_max: float | None = None
    conc70_max: float | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "FilterParams":
        d = dict(d or {})
        return cls(
            price_percent_min=dict(d.get("price_percent_min") or {}),
            price_percent_max=dict(d.get("price_percent_max") or {}),
            profit_ratio_min=d.get("profit_ratio_min"),
            profit_ratio_max=d.get("profit_ratio_max"),
            conc70_max=d.get("conc70_max"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SelectParams:
    """一次筛选任务的完整参数：模块参数 + 结果过滤阈值。"""

    price: PriceParams = field(default_factory=PriceParams)
    jetton: JettonParams = field(default_factory=JettonParams)
    filters: FilterParams = field(default_factory=FilterParams)
    max_workers: int = 8

    def validate(self) -> None:
        if not (self.price.enabled or self.jetton.enabled):
            raise ValueError("至少启用一种分析方式")
        self.price.validate()
        self.jetton.validate()

    @classmethod
    def from_dict(cls, d: dict) -> "SelectParams":
        d = dict(d or {})
        return cls(
            price=PriceParams.from_dict(d.get("price")),
            jetton=JettonParams.from_dict(d.get("jetton")),
            filters=FilterParams.from_dict(d.get("filters")),
            max_workers=int(d.get("max_workers", 8)),
        )

    def to_dict(self) -> dict:
        return {
            "price": asdict(self.price),
            "jetton": asdict(self.jetton),
            "filters": self.filters.to_dict(),
            "max_workers": self.max_workers,
        }
