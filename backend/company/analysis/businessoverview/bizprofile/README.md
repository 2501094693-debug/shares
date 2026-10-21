# 主营业务画像（bizprofile）

分章节 Markdown 报告 —— **确定性渲染，不调用任何模型**。

本模块是 `company.analysis.businessoverview` 的**派生层**：只消费其取数与
格式统一结果，不修改其语义，也不改变其「不做二次加工」的承诺。

## 定位

| | businessoverview | bizprofile（本模块） |
|---|---|---|
| 职责 | 取数 + 格式统一 | 派生指标 + 章节排版 |
| 是否加工 | 否 | 是（派生指标、结论句） |
| 是否调模型 | 否 | **否** |
| 产出 | 结构化 pack | Markdown 报告 |

## 章节结构

```
一、公司与主营业务速览      main_business / product_type / product_name_list / scope
二、主营构成总览            三维度对照 + CR3 / HHI / 整体毛利率
三、分维度构成明细          按产品 / 按行业 / 按地区 三张分部表
四、收入结构与变化          占比迁移（本期 vs 上期）+ 合计收入与同比
五、盈利结构                分部毛利率 / 毛利贡献 / 负毛利清单
尾注：数据来源与局限        来源说明 + 命中的口径告警
```

## 取数：2 次 HTTP

| 步骤 | 函数 | HTTP |
|---|---|---|
| 三维度主营构成 | `fetch_operate_dimensions` | 1（接口本就返回 product/industry/area 三块） |
| 主营介绍 | `fetch_operate_text_blocks` | 1（SSR 页面） |

对比：旧路径 `fetch_operate_analysis` 需 3 次（1 JSON + 2 次 SSR 抓同��� URL）。

## 口径护栏（G1–G10）

护栏**不修改任何数据**，只如实披露口径问题，避免读者把不同口径的数字放在一起比较。
每条都对应一个实测踩过的坑：

| 编号 | 风险 | 实测证据 |
|---|---|---|
| G1 | `totals.gross_profit_rate` 不是毛利率 | 600990 为 `1.164` 而真实毛利率 `0.147` |
| G2 | `gross_profit_ratio` 是「毛利占总毛利」不是毛利率 | Σ = 1.000000 |
| G3 | `level=2` 子项与 `level=1` 重复计数 | 600332 开子项后合计 1.0031 |
| G4 | `revenue_yoy` 可能缺失，缺失 ≠ 0 | 600332 多个分部为 `None` |
| G5 | 最新期可能是半年报/季报累计口径 | 同花顺 45 期含 06-30 / 09-30 |
| G6 | 分部跨期改名，按名匹配会漏配 | 600990「雷达及雷达配套产品」→「雷达及配套产品」 |
| G7 | 三维度可得期数不同 | product 25 / industry 10 / area 10 |
| G9 | 某维度数据严重过期 | 600990 按地区只更新到 2010-12-31 |
| G10 | 占比合计可能 ≠ 100%（抵销行） | 不强行归一 |

## 运行

```bash
cd backend

# 打印到标准输出
python -m company.analysis.businessoverview.bizprofile 600990

# 写入文件
python -m company.analysis.businessoverview.bizprofile 600990 --out ../agent/reports/600990主营构成_20261020.md

# 结构化 JSON（含 Markdown 全文）
python -m company.analysis.businessoverview.bizprofile 600990 --json

# 不抓主营介绍
python -m company.analysis.businessoverview.bizprofile 600990 --no-text
```

HTTP：

```
GET /api/stocks/biz-profile?code=600990&text=1&markdown=1
```

报告固定取最近 2 期（最新期展示 + 上一期做占比迁移），不再开放期数参数。

返回字段：

| 字段 | 说明 |
|---|---|
| `code` / `name` / `source` / `source_label` / `page` / `cutoff_date` | 身份与来源 |
| `primary` / `primary_label` | 主维度 |
| `dim_periods` / `dim_latest` | 各维度可得期数与最新报告期 |
| `intro` | 主营业务 / 产品类型 / 主要产品 / 经营范围 |
| `dimensions[]` | 三维度结构化视图：分部、迁移、集中度、整体毛利率 |
| `guardrails[]` | 命中的口径告警 |
| `markdown` | 完整 Markdown 报告（`markdown=0` 时不返回） |

前端接入：公司详情 → 研判 → **业务简述** → 规则视角（`frontend/shared/js/ai-modes.js` 的
`bizprofile` 模式，`kind: "engine"`；与 AI 视角同属「业务简述」入口，用视角切换）。前端读 `dimensions` 等结构化字段原生渲染
表格，不解析 Markdown；`markdown=0` 可省掉全文传输。

深链：`/company?code=600990&tab=judgment&judgment=bizprofile`

## 代码结构

```
bizprofile/
├── __init__.py     build_profile / render_markdown / build_report
├── engine.py       取数编排 + 派生指标（集中度、整体毛利率、占比迁移）
├── render.py       Markdown 渲染（纯函数，不取数不计算）
├── guardrails.py   口径校验（纯函数）
├── api.py          HTTP 路由
└── __main__.py     CLI
```

`engine.py` 与 `render.py` 严格分离：engine 只产出结构化中间产物，
render 只做排版，便于单测与替换渲染风格。

## 边界

- **不调用模型**，输出可复现、可审计。
- **不用词典给业务贴标签**：不谈业务归类，只呈现数字与派生指标。
- **不归一化**：占比合计不为 100% 时如实披露，不强行凑数。
- **不横向比较**：三维度由公司分别披露，期数与口径不同，报告中并列展示而非合并。
