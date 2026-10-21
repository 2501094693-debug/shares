"""CLI：``python -m company.analysis.businessoverview.bizprofile 600990``

产出分章节 Markdown 报告（确定性渲染，无模型）。

    python -m company.analysis.businessoverview.bizprofile 600990
    python -m company.analysis.businessoverview.bizprofile 600990 --out ../agent/reports/600990主营构成_20261020.md
    python -m company.analysis.businessoverview.bizprofile 600990 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from company.analysis.businessoverview.bizprofile.engine import build_profile
from company.analysis.businessoverview.bizprofile.render import render_markdown


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="主营业务画像：分章节 Markdown 报告（确定性渲染，无模型）"
    )
    parser.add_argument("code", help="股票代码，如 600990")
    parser.add_argument(
        "-n", "--latest-n", type=int, default=2, help="取最近 N 个报告期（默认 2）"
    )
    parser.add_argument(
        "--no-text", action="store_true", help="不抓取主营介绍"
    )
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON（含 Markdown）")
    parser.add_argument("--out", default="", help="Markdown 输出路径")
    args = parser.parse_args(argv)

    try:
        profile = build_profile(
            args.code,
            latest_n=args.latest_n,
            with_text=not args.no_text,
        )
    except ValueError as exc:
        _print(f"错误：{exc}")
        return 400
    except Exception as exc:  # noqa: BLE001
        _print(f"错误：{exc}")
        return 500

    markdown = render_markdown(profile)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        _print(f"已写入 {path}")
        return 0

    if args.json:
        _print(json.dumps(
            {
                "code": profile.get("code"),
                "name": profile.get("name"),
                "source": profile.get("source"),
                "page": profile.get("page"),
                "primary": profile.get("primary"),
                "dim_periods": profile.get("dim_periods"),
                "dim_latest": profile.get("dim_latest"),
                "guardrails": profile.get("guardrails"),
                "markdown": markdown,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    _print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
