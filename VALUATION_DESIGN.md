# 估值分析方案设计（基于系统现有功能）

## 一、设计目标

为单只 A 股公司输出一份完整的估值分析报告，覆盖三层：

| 层 | 内容 | 回答的问题 |
|---|---|---|
| 绝对估值 | DCF 现金流折现内在价值 | 公司本身值多少钱？ |
| 相对估值 | PE/PB/PS 历史分位 + 同业对比 | 市场怎么定价？是否偏离历史/同业？ |
| 安全边际 | 内在价值 vs 当前股价 | 现在买是否安全？ |

**核心原则**：不新增外部数据源，全部复用系统已有模块；全部计算为确定性 Python，不依赖任何 AI/大模型；对可选重依赖（akshare 行情画像、同业竞争）做容错降级。

---

## 二、复用的现有能力

| 现有模块 | 职责 | 在估值中用途 |
|---|---|---|
| `company.analysis.financialreport.engine.analyze_rows` | 东财 F10 八看指标（ROE/ROA/毛利率/经营利润率/OCF/FCF/资本开支/负债率/现金储备） | 提供 DCF 的基期 FCF、净债务、营收 CAGR |
| `company.news.financialreport.fetcher.get_financial_report` | 拉取 F10 三大表 + 主要指标，返回 `merged` / `annual` | 财报数据源 |
| `company.profile.get_stock_profile` | 个股盘口：当前价、总市值、总股本、PE/PB/PS、行业 | 当前价、每股内在价值分母、安全边际比较 |
| `company.statistics.quote.fetch.fetch_pe_history` | 东财每日 PE_TTM/PE静/PB/PS 序列（默认 ~1500 个交易日，约 3-5 年） | 相对估值的历史分位 |
| `company.analysis.competition.compare.compare_peers` | 同申万三级行业「八看」横截面对比 | 解析行业归属 + 同业样本（用于取每只同业最新倍数） |

---

## 三、模块结构

新建目录 `backend/company/analysis/valuation/`：

```
valuation/
├── __init__.py        # 对外导出
├── dcf.py             # DCF 绝对估值引擎（纯计算，无网络）
├── relative.py        # 相对估值（历史分位 + 同业对比）
├── engine.py          # 编排引擎：串联财报/盘口/历史/同业 → DCF + 相对 + 安全边际
└── api.py             # FastAPI 路由
```

已在 `backend/app.py` 注册路由 `valuation_router`。

---

## 四、核心实现细节

### 4.1 DCF（dcf.py）

**输入**：`metrics`（财报八看产出）、`profile`（盘口）、`annual_series`（年度报表，用于推导营收 CAGR）、`DcfAssumptions`。

**计算步骤**：
1. **基期 FCF**：优先取披露的 `FCFF_BACK/FCFF_FORWARD`；否则用 `经营现金流 - 资本开支`；再退化为净利润代理并打标。
2. **显性期增长率**：优先用传入值；否则按年度营收首尾 CAGR 计算，并截断到 `[-10%, 20%]`，避免过高增长不可持续。
3. **净债务**：`金融性负债 - 货币资金`（无金融性负债时退化为总负债 - 货币资金）。
4. **显性期折现**：`FCF_t = FCF_0 × (1+g)^t`，`PV_t = FCF_t / (1+WACC)^t`，累加 5 年（可配置）。
5. **终值**：戈登增长模型 `TV = FCF_n × (1+g_terminal) / (WACC - g_terminal)`，要求 `g_terminal < WACC`。
6. **企业价值 EV = ΣPV_t + PV(终值)**；**股权价值 = EV - 净债务**；**每股内在价值 = 股权价值 / 总股本**。
7. **安全边际** = (每股内在价值 - 当前价) / 每股内在价值。
8. **敏感性矩阵**：WACC ±1% × 终值增长 ±0.5% 的每股内在价值网格，供上层展示不确定性。

**默认假设**：WACC 9%、永续增长 2.5%、预测 5 年，均可通过 API 参数覆盖。

### 4.2 相对估值（relative.py）

**当前倍数**：从盘口取 `pe_ttm / pb / ps_ttm / pe_static / pe_dyn`。

**历史统计**：对 `fetch_pe_history` 返回序列，按倍数分别计算中位数、均值、最小、最大、P25/P75、以及当前倍数在历史样本中的分位（低于比例 + 等值一半）。剔除非正 PE（负市盈率无经济含义）。

**历史定性**（核心倍数 PE/PB/PS 分位均值）：
- ≤20：历史低估区；20-40：偏低；40-60：合理；60-80：偏高；≥80：历史高估区。

**同业对比**：对同业每只公司取最新 `PE/PB/PS`，计算同业中位数，得出目标公司溢价/折价百分比，定性为“显著低于/低于/相当于/高于/显著高于同业”。

**总体结论**：优先参考历史分位，同业作旁证 →「相对低估 / 相对合理 / 相对高估 / 数据不足」。

### 4.3 安全边际与定性结论（engine.py）

```
安全边际 = (DCF 每股内在价值 - 当前价) / DCF 每股内在价值
```

定性结论（非投资建议，仅供参考）：
- DCF 安全边际充足（≥30%）且相对估值偏低 → 「可考虑」
- 任一方高估 → 「回避」或「观望」
- 两者信号分歧 → 「观望（绝对与相对估值信号分歧）」
- 数据不足 → 「数据不足，无法定论」

### 4.4 容错设计

`get_stock_profile` 和 `compare_peers` 依赖 `akshare`（行业树/行情画像），该库在部分环境下可能不可用。引擎对三个可选模块做**模块级可容错导入**：缺失时仅在 `errors` 里记录，不阻断 DCF（仍可输出企业价值/股权价值总额）和历史相对估值（`fetch_pe_history` 独立可用）。

---

## 五、API 接口

基地址：`GET http://<host>:5000`

### 5.1 完整估值报告

```
GET /api/stocks/valuation
Query:
  code            必填，6 位股票代码（或 company 中带 6 位代码）
  company         可选，公司查询串（含 6 位代码即可）
  name            可选，公司简称，仅回显
  report_type     annual(默认)\|semi\|q1\|q3
  force           0\|1，1=绕过缓存强制刷新
  peer_limit      0~20，同业公司上限，缺省 6
  wacc            0~1，折现率，缺省 0.09
  terminal_growth 0~1，永续增长率，缺省 0.025
  projection_years 1~10，DCF 预测期，缺省 5
  first_stage_growth -1~1，显性期增长率，缺省由营收 CAGR 推导
  safety_discount 0~1，对内在价值的额外安全发令
```

返回示例（精简）：
```json
{
  "ok": true,
  "data": {
    "code": "600519",
    "name": "贵州茅台",
    "report_type": "annual",
    "data_available": true,
    "industry": {"code": "...", "name": "白酒", ...},
    "profile": {"price": "...", "total_shares": "...", "pe_ttm": ..., ...},
    "dcf": {
      "intrinsic_value_per_share": 62.47,
      "enterprise_value": 2210962000000,
      "equity_value": ...,
      "net_debt": ...,
      "margin_of_safety_pct": 19.96,
      "revenue_cagr_used": 17.3,
      "fcf_projection": [{ "year":1,"fcf":...,"pv":... }, ...],
      "sensitivity": [{ "wacc":8.0,"terminal_growth":2.0,"intrinsic_per_share":... }, ...],
      "notes": [...]
    },
    "relative": {
      "current": {"pe_ttm":15.0,"pb":2.0,"ps_ttm":3.0,...},
      "history": {"pe_ttm":{"median":..,"percentile":..,"samples":..}, ...},
      "peers": {"count":..,"multiples":{"pe_ttm":{"peer_median":..,"premium_pct":..,"verdict":"低于同业"}, ...}},
      "history_verdict": "历史低估区",
      "peer_verdict": "显著低于同业",
      "overall": "相对低估"
    },
    "margin_of_safety_pct": 19.96,
    "verdict": "观望（估值合理，等待更大安全边际）",
    "notes": [...],
    "errors": [...]
  }
}
```

### 5.2 单项接口

- `GET /api/stocks/valuation/dcf` → 仅返回 `dcf` 与 `margin_of_safety_pct`
- `GET /api/stocks/valuation/relative` → 仅返回 `relative` 与 `verdict`
- `GET /api/stocks/valuation/meta` → 报告口径与默认假设说明，供前端构建表单

---

## 六、调用示例（Python）

```python
from company.analysis.valuation.engine import run_valuation

# 完整估值
res = run_valuation("600519", name="贵州茅台", report_type="annual", peer_limit=6)
data = res["data"] if res.get("ok") else res
print(data["verdict"])                     # 定性结论
print(data["margin_of_safety_pct"])        # 安全边际 %
print(data["dcf"]["intrinsic_value_per_share"])   # DCF 每股内在价值
print(data["relative"]["overall"])         # 相对估值：相对低估/合理/高估

# 自定义 DCF 假设
res = run_valuation("600519", wacc=0.10, terminal_growth=0.02, projection_years=5, safety_discount=0.1)
```

HTTP：
```bash
curl "http://127.0.0.1:5000/api/stocks/valuation?code=600519&report_type=annual&peer_limit=6"
```

---

## 七、与「八看」财报分析的关系

估值模块是对现有「八看」财报分析的**上层延伸**：

- 八看已给出：ROE、ROA、毛利率、经营利润率、OCF、FCF、资本开支、负债率、现金储备、风险标志。
- 估值模块在此基础上：把 FCF 折现为内在价值（绝对估值），把 PE/PB/PS 放到历史和同业中定位（相对估值），最后用安全边际判定买入价位是否安全。

两者可组合使用：先用「八看」判断公司是否好（护城河、盈利质量、资产负债表），再用估值模块判断价格是否好（内在价值、安全边际、历史/同业分位），最终落脚到「好公司 + 好价格 + 足够安全边际」。

---

## 八、已知限制

1. `company.profile.get_stock_profile` 与 `compare_peers` 依赖 `akshare`；若环境中 `akshare`/`py_mini_racer` 不可用，盘口价格/总股本与同业倍数将缺失，DCF 仍可输出企业/股权价值总额，但无法算每股内在价值与安全边际；`errors` 字段会明确提示。
2. DCF 对增长率、折现率、终值假设敏感，输出为**区间/敏感性矩阵**而非单一确定值，建议结合悲观/中性/乐观三档参考。
3. 历史分位依赖 `fetch_pe_history` 覆盖的交易日长度（缺省约 3-5 年），样本不足时分位不可靠，会在 `notes` 说明。
4. 定性结论（可考虑/观望/回避）仅供参考，**不构成投资建议**。
