"""综合深度研判智能体 — Prompt 模板。"""

from __future__ import annotations

from agent.config import DATA_LOOKBACK_DAYS

ANALYST_SYSTEM = """你是一位资深股票基本面分析师，擅长从财报、业务与估值三个维度做深度研判。

## 核心原则
1. **只能使用**用户消息中已采集的资料，禁止用训练知识编造财务数字
2. **先数据、后解释**：每节先引用原始数据或规则引擎输出，再写解读
3. **累计口径**：中报=上半年，三季报=前三季度，年报=全年
4. **诚实留白**：未披露就写「公开资料未披露」
5. **不构成投资建议**：只做分析框架与情景推演，不给买卖建议
6. 重要论断标注 `〔来源：…〕`"""


def build_business_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    data_context: str,
    mda_text: str,
) -> str:
    return f"""请分析 **{stock_name}**（{stock_code}）的业务构成与关键驱动因素。

数据截止：{data_cutoff_date}

## 已采集资料
{data_context}

## 年报/半年报 MD&A 摘录
{mda_text or "（无 PDF 正文，请基于结构化数据）"}

---

请输出以下结构：

### 业务构成
- 按产品/服务/地区拆分收入占比（近 3 年趋势，引用数据）
- 各分部毛利率、增速
- 收入集中度（Top1/Top3 占比）

### 商业模式
- B2B/B2C/平台/制造/渠道
- 收入确认方式
- 客户结构与大客户依赖

### 关键驱动因素（JSON 块）
在文末输出一个 JSON 数组，每项格式：
```json
[{{"factor": "因素名", "direction": "+/-/±", "horizon": "短/中/长期", "confidence": "高/中/低", "note": "一句话说明"}}]
```

### 解读
用 3-5 段话总结业务核心逻辑与近期变化。"""


def build_balance_prompt(stock_name: str, stock_code: str, rules_text: str, data_context: str) -> str:
    return f"""请解读 **{stock_name}**（{stock_code}）的资产负债表。

## 规则引擎预分析
{rules_text}

## 原始财务数据（节选）
{data_context[:12000]}

---

请输出：
### 原始数据引用
抄录规则引擎中的关键表格数字

### 资产质量
货币资金、应收/营收、存货/营收、商誉/净资产

### 负债与偿债
资产负债率、有息负债、短债/长债、流动/速动比率

### 异常科目
其他应收、其他流动资产等突增项

### 结论
3-5 条明确判断，附来源标注"""


def build_income_prompt(stock_name: str, stock_code: str, rules_text: str, data_context: str) -> str:
    return f"""请解读 **{stock_name}**（{stock_code}）的利润表。

## 规则引擎预分析
{rules_text}

## 原始财务数据（节选）
{data_context[:12000]}

---

请输出：
### 原始数据引用
抄录趋势表关键数字

### 收入质量
营收增速、分部增速、收入确认政策变化

### 盈利能力
毛利率、净利率、ROE、ROIC 趋势与驱动

### 费用结构
销售/管理/研发/财务费用率变化

### 利润质量
扣非 vs 归母、非经常性损益占比

### 结论
3-5 条明确判断"""


def build_cashflow_prompt(stock_name: str, stock_code: str, rules_text: str, data_context: str) -> str:
    return f"""请解读 **{stock_name}**（{stock_code}）的现金流量表。

## 规则引擎预分析
{rules_text}

## 原始财务数据（节选）
{data_context[:12000]}

---

请输出：
### 原始数据引用
抄录现金流趋势表

### 经营现金流
OCF/净利润、OCF 增速、利润含金量

### 投资与筹资
资本开支强度、并购、分红、回购、再融资

### 自由现金流
FCFF 趋势、FCF Yield、扩张/收缩判断

### 现金流类型
经营型/投资型/融资型（彼得·林奇分类）

### 结论
3-5 条明确判断"""


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    balance_analysis: str,
    income_analysis: str,
    cashflow_analysis: str,
    cross_validate: str,
) -> str:
    return f"""请对 **{stock_name}**（{stock_code}）做三表汇总与交叉验证分析。

## 资产负债表分析
{balance_analysis}

## 利润表分析
{income_analysis}

## 现金流量表分析
{cashflow_analysis}

## 程序交叉验证
{cross_validate or "（无）"}

---

请输出：
### 三表勾稽关系
净利润 vs 经营现金流、营收 vs 应收 vs 存货、资本开支 vs 折旧 vs 收入增长

### 财务健康度评分（1-5）
分项：盈利质量、偿债能力、现金流质量、资产质量

### 核心财务画像
用一段话概括这家公司财务上的「性格」

### 需持续跟踪的财务变量
列出 3-5 个关键指标"""


def build_valuation_prompt(
    stock_name: str,
    stock_code: str,
    scenarios_text: str,
    data_context: str,
) -> str:
    return f"""请解读 **{stock_name}**（{stock_code}）的估值。

## 三情景估值（程序预计算）
{scenarios_text}

## 估值与同业原始数据
{data_context[:8000]}

---

请输出：
### 历史估值分位解读
当前 PE/PB/PS 相对自身历史的位置

### 同业对比
相对申万三级同业的位置

### 三情景假设评审
对乐观/中性/悲观的增速与倍数假设是否合理，需调整什么

### 主估值方法选择
说明最适合该公司的估值方法及理由

### 估值区间结论
给出乐观/中性/悲观的目标价区间（引用程序计算数字）

### 免责声明
明确不构成投资建议"""


def build_outlook_prompt(
    stock_name: str,
    stock_code: str,
    key_drivers: list[dict],
    business_analysis: str,
    financial_synthesis: str,
    valuation_report: str,
    market_intel: str,
) -> str:
    drivers_text = "\n".join(
        f"- {d.get('factor', '')}（{d.get('direction', '')}，{d.get('horizon', '')}，置信度{d.get('confidence', '')}）"
        for d in (key_drivers or [])
    ) or "（未能结构化提取，请从业务分析中归纳）"

    return f"""请研判 **{stock_name}**（{stock_code}）的未来前景。

## 关键驱动因素
{drivers_text}

## 业务分析摘要
{business_analysis[:6000]}

## 财务综合判断
{financial_synthesis[:6000]}

## 估值结论
{valuation_report[:6000]}

## 市场信息与舆情
{market_intel or "（无联网补充）"}

---

请输出：
### 短期展望（6-12 月）
催化剂与风险

### 中期展望（1-3 年）
成长性与盈利能力趋势

### 长期展望（3-5 年）
行业地位与护城河演变

### 情景路径
结合关键驱动因素，分别描述乐观/中性/悲观路径

### 关键不确定性
需持续跟踪的 3-5 个变量

### 综合结论
一段话总结前景，明确不构成投资建议"""


def build_assemble_header(
    stock_name: str,
    stock_code: str,
    industry: dict,
    data_cutoff_date: str,
) -> str:
    industry_label = " / ".join(
        x for x in (
            industry.get("l1_name") or "",
            industry.get("l2_name") or "",
            industry.get("name") or industry.get("l3_name") or "",
        )
        if x
    )
    return (
        f"# {stock_name} 综合深度分析报告\n\n"
        f"> 代码: {stock_code} | 行业: {industry_label or '—'} | 数据截止: {data_cutoff_date}\n"
        f"> 范围: 近5年年报 + 近4季季报 + 历史估值 + 市场信息 | "
        f"分析窗口: 近 {DATA_LOOKBACK_DAYS} 天公告\n"
        f"> **免责声明：本报告仅供研究参考，不构成投资建议。**\n\n"
    )
