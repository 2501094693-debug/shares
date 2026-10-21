"""风险评估服务：七维巨潮检索 + 维内轻量处理。"""
from __future__ import annotations

from typing import Any

from .extract import CninfoRiskExtractor
from .report import to_json, to_markdown


class RiskAssessmentService:
    def __init__(self, code: str) -> None:
        self.code = code.strip()

    def scan(self) -> dict[str, Any]:
        """主入口：按七维返回检索方式 / 怎么看 / 检索结果。"""
        return CninfoRiskExtractor(self.code).run_dimensions()

    def scan_markdown(self) -> str:
        data = self.scan()
        return to_markdown(data)

    def scan_json(self) -> str:
        data = self.scan()
        return to_json(data)
