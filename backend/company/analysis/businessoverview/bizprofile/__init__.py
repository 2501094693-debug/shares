"""主营业务画像：分章节 Markdown 报告（确定性渲染，无模型）。

本模块是 :mod:`company.analysis.businessoverview` 的**派生层**：
只消费其取数与格式统一结果，不修改其语义。
产物
----
一份分章节的 Markdown 报告，覆盖：

  一、公司与主营业务速览
  二、主营构成总览（三维度对照 + 集中度）
  三、分维度构成明细
  四、收入结构与变化（占比迁移 + 合计同比）
  五、盈利结构
  六、经营评述摘录（原文节选）
  七、业务归类与白话解读（静态词典派生）
  尾注：数据来源与口径披露

**不调用任何模型**，输出可复现、可审计。
"""
from __future__ import annotations

from company.analysis.businessoverview.bizprofile.engine import build_profile
from company.analysis.businessoverview.bizprofile.render import render_markdown

__all__ = ["build_profile", "render_markdown", "build_report"]


def build_report(
    company: str,
    *,
    latest_n: int = 3,
    with_text: bool = True,
) -> dict:
    """取数 + 派生 + 渲染，一次拿到完整报告。

    返回 ``{"profile": ..., "markdown": ...}``。
    """
    profile = build_profile(company, latest_n=latest_n, with_text=with_text)
    return {"profile": profile, "markdown": render_markdown(profile)}
