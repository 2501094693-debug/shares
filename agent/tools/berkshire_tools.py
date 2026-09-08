"""调用 ai-berkshire 的 financial_rigor / report_audit 工具。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from config import FINANCIAL_RIGOR_SCRIPT, REPORT_AUDIT_SCRIPT


def _run_script(script: Path, args: list[str]) -> str:
    if not script.exists():
        return f"（工具未找到: {script}）"
    cmd = [sys.executable, str(script), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or f"（退出码 {result.returncode}）"


def run_financial_rigor(subcommand: str, **kwargs: str) -> str:
    args = [subcommand]
    for key, value in kwargs.items():
        if value:
            args.extend([f"--{key.replace('_', '-')}", str(value)])
    return _run_script(FINANCIAL_RIGOR_SCRIPT, args)


def extract_audit_items(report_path: str) -> str:
    return _run_script(REPORT_AUDIT_SCRIPT, ["extract", "--report", report_path])


def run_audit_verdict(results_json: str, report_name: str) -> str:
    return _run_script(
        REPORT_AUDIT_SCRIPT,
        ["verdict", "--results", results_json, "--report", report_name],
    )
