# 主营业务取数与格式统一（无模型、无二次加工）

只做两件事：

1. **取数** —— 同花顺 F10「经营分析」（唯一数据源）；
2. **格式统一** —— 把取到的数据抹平成统一字段契约。

**不做任何二次加工**：不剔除任何分部行、不合并小业务、不改名、不分级、
不打分、不打标、不做交叉校验、不生成描述文字、不渲染报告。
取到什么就是什么，只是字段名、字段集、类型、单位、日期格式、维度键被统一。

## 目录结构

```
businessoverview/
├── README.md
├── __init__.py            聚合导出
├── __main__.py            python -m 入口（转发到 interfaces）
│
├── interfaces/            ★ 对外接口（集中一处）
│   ├── __init__.py        router + cli_main 统一出口
│   ├── api.py             HTTP 路由（4 个端点）
│   └── __main__.py        统一 CLI（report / raw / periods）
│
├── core/                  编排层（与数据源无关）
│   ├── __init__.py
│   ├── source.py          数据源统一适配器 Source + 注册表
│   ├── normalize.py       ★ 格式统一层（字段契约的唯一出处）
│   └── engine.py          采集 → 格式统一
│
├── tonghuashun/           ★ 同花顺接入（唯一数据源）
│   ├── __init__.py        SOURCE 适配器
│   └── fetcher.py         主营构成 / 主营介绍 / 董事会经营评述
│
├── bizprofile/            ★ 派生层：分章节 Markdown 报告（确定性渲染，不调模型）
│   ├── __init__.py        build_profile / render_markdown / build_report
│   ├── engine.py          取数编排 + 派生指标（集中度 / 整体毛利率 / 占比迁移）
│   ├── render.py          Markdown 渲染（纯函数）
│   ├── guardrails.py      口径校验 G1–G10
│   ├── api.py             HTTP 路由（1 个端点）
│   ├── __main__.py        CLI
│   └── README.md          模块文档
│
└── rules/                 已下线（保留知识资产，主链路不引用）
    ├── lexicon.py         业务词典（由 bizprofile 引用）
    ├── glossary.py        术语白话表（由 bizprofile 引用）
    └── __init__.py
```

## 格式统一做了什么

`core/normalize.py` 是格式契约的唯一出处，**纯函数、无状态、可单测**。

### 分部字段契约 `SEGMENT_FIELDS`

| 字段 | 类型 | 口径 |
|---|---|---|
| `code` | str | 股票代码 |
| `report_date` | str | `YYYY-MM-DD` |
| `dimension` | str | 中文标签：按产品 / 按行业 / 按地区 |
| `dimension_key` | str | 统一键：`product` / `industry` / `area` |
| `item_name` | str | 分部名称（原文，不改写） |
| `level` | str | 层级；缺失时为 `None` |
| `revenue` | float | 营业收入，单位**元** |
| `revenue_ratio` | float | 收入占比，**0~1 小数** |
| `revenue_yoy` | float | 收入同比，0~1 小数 |
| `cost` | float | 营业成本，元 |
| `cost_ratio` | float | 成本占比，0~1 小数 |
| `gross_profit` | float | 毛利，元 |
| `gross_profit_ratio` | float | 毛利占比，0~1 小数 |
| `gross_margin` | float | 毛利率，0~1 小数 |
| `source` / `channel` | str | 来源标记 |

### 顶层字段契约 `PACK_FIELDS`

`code` `name` `source` `source_label` `page` `error` `dimension` `dimension_key`
`report_date` `report_dates` `all_periods` `period_count` `segments` `periods`
`total_ratio` `totals` `scope` `reviews` `review_dates` `main_business`
`product_type` `product_name` `product_name_list`

其中 `periods` 是按报告期归组后的视图（`report_date` / `count` /
`total_ratio` / `totals` / `segments`），**只是重新分组，没有增删任何行**。

顶层 `total_ratio` 与 `totals` / `report_date` 口径一致，**只对应最新一期**；
跨期求和会让 N 期得到 N 倍占比（3 期得 300%），故不可跨期累加。
各期自身的合计见 `periods[i].total_ratio`。

### 统一规则清单

- 字段名：统一为契约字段（`item_name` / `revenue` / `revenue_ratio` / ...）
- 字段集：源里没有的字段一律 `None`，**不做任何推断填充**
- 类型：金额/比率一律 `float`（`-1e10` 哨兵、`'-'`、`'--'`、空串、`NaN` → `None`）
- 单位：金额元；比率 0~1 小数
- 日期：`YYYY-MM-DD`
- 维度键：`1`/`2`/`3`、`product`/`industry`/`area`、`按产品`/`按行业`/`按地区` 全部归一
- 排序：报告期降序 → 同期内占比降序

### 明确不做的事

- 不剔除二级子项（`其中:铜精矿`）—— 原样保留
- 不剔除抵销行（负占比行）—— 原样保留
- 不合并占比 <1% 的小业务为「其他业务」—— 原样保留
- 不做占比分级（核心/重要/一般）
- 不做词典打标、不生成一句话描述、不做结构对比
- 不做覆盖率校验

## 数据源插件化

`core/source.py` 用 `Source` 描述一份插件清单，把数据源抹平成同一套接口。
目前只登记了同花顺一个插件：

```python
SOURCE = Source(
    key="tonghuashun",
    label="同花顺 F10 经营分析",
    dim_labels={"product": "按产品", "industry": "按行业", "area": "按地区"},
    dim_priority=("product", "industry", "area"),
    normalize_dim=normalize_analysis_type,
    fetch_segments=_segments,   # (code, latest_n, dimension, date)
    fetch_all=_fetch_all,       # (code, latest_n, analysis_type)
    fetch_periods=fetch_periods,
)
```

各源在自身 `__init__.py` 里用一层薄包装抹掉参数名差异，
因此 **`core/engine.py` 内没有任何 if/else 数据源分支**。
将来若新增数据源，只需在此登记一个 `Source` 插件。

| | 同花顺 |
|---|---|
| 接口 | `/basicapi/operate/index/v1/product_index_query/` |
| 三维度 | 一次请求全拿 |
| 历史期 | 不传 `date` 返回全部 |
| 同比 | 传 `yoy=1` 才有 |
| 二级分部 | `level=2&child=1` |
| 主营业务一句话 / 产品类型 / 产品名称 | ✅ |
| 董事会经营评述 | ✅ SSR |

### 一次性取全（供派生层使用）

| 函数 | HTTP 次数 | 返回 |
|---|---|---|
| `fetch_operate_dimensions(code, latest_n)` | 1 | `{"product": pack, "industry": pack, "area": pack}`；接口本就返回三块，不需发三次请求 |
| `fetch_operate_text_blocks(code)` | 1 | `{"intro": {...}, "review": {...}}`；两块同源于 SSR 页面，合并抓取 |

`fetch_operate_segments`（单维度）与 `fetch_operate_analysis`（全量）保持原行为不变。

## 运行

```bash
cd backend

# 统一格式 JSON（默认）
python -m company.analysis.businessoverview 600990

# 可读表格
python -m company.analysis.businessoverview 600990 report --text

# 接入层原始数据（未做格式统一）
python -m company.analysis.businessoverview 600990 raw
python -m company.analysis.businessoverview 600990 raw --json

# 报告期列表
python -m company.analysis.businessoverview 600990 periods

# 切换维度 / 输出
python -m company.analysis.businessoverview 600990 -d 2 --no-financial
python -m company.analysis.businessoverview 600990 --out out/600990.json
```

HTTP：

```
GET /api/stocks/business-overview?code=600990&latest_n=2&dimension=&source=&financial=1
GET /api/stocks/business-segments?code=600990&latest_n=1&dimension=2&source=tonghuashun
GET /api/stocks/business-periods?code=600990&source=tonghuashun
GET /api/stocks/business-sources          # 数据源自描述，供前端渲染切换器
```

`dimension` 接受 `1/2/3`、`product/industry/area`、`按产品/按行业/按地区`。

## 前端接入

| 模块 | 位置 | 说明 |
|---|---|---|
| 业务概述 | 公司详情 → 研判 → 业务概述 | 消费 `bizprofile` 派生层（`GET /api/stocks/biz-profile`），确定性规则渲染 |

深链：`/company?code=600990&tab=judgment&judgment=bizprofile`

## 数据源字段要点（勿"顺手修正"）

### 同花顺
- 页面 `basic.10jqka.com.cn/{code}/operate.html` 是 **GBK 编码**，必须按 gbk 解码；
- `index_value` 是**字符串**，需转 float；`account` 是占比 **0~1 小数**；
- `yoy` 默认返回 `null`，必须显式传 `yoy=1`；
- 三个维度**历史期数各不相同**，且 `area` 返回顺序是**升序**，不可假定降序；
- 「董事会经营评述」在页面上出现多次（导航+侧栏+正文标题），
  必须取**最后一个 `<h2>`** 作区块起点。

### 通用
- 显式指定维度但该股无此维度披露时，**自动回退**到优先级维度并记日志，不崩溃。
- 最新期可能是半年报/季报累计口径，横比需自行判断。
- 输出混有「其中:xxx」二级拆分行与负数抵销行——**本模块原样保留**。

## 边界

- 本模块只搬运和统一格式，**不保证分部占比合计等于 100%**（子项/抵销行原样保留所致）。
- 拆分口径以公司披露为准，与其他数据源未必同口径。
