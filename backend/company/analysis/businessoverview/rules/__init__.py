"""规则层：已下线（不参与取数与输出）。

历史背景
--------
本目录曾包含「分部清洗规则」，用于剔除二级子项、剔除抵销行、
合并占比过小的业务。这属于**二次加工**，与当前定位冲突，
已随 :mod:`company.analysis.businessoverview.core.normalize` 的引入而移除。

现状
----
主链路（取数 → 格式统一 → 输出）**不引用本目录任何内容**：

* :mod:`company.analysis.businessoverview.core.normalize` —— 唯一在场规则，
  只做格式统一（字段名/字段集/类型/单位/日期/维度键/排序），不做加工。

派生层 :mod:`company.analysis.businessoverview.bizprofile` 引用本目录的静态
知识表（属「派生」而非「格式统一」）：

* :mod:`company.analysis.businessoverview.rules.glossary` —— 术语白话表，
  用于把财报术语替换为通俗说法。
"""

from __future__ import annotations

__all__: list[str] = []
