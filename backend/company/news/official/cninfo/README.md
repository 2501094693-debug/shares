# 巨潮资讯公告（`company.news.official.cninfo`）

本目录是巨潮资讯网公告查询的独立接入包，对应官网 [公告查询页](https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search)。

它只做一件事：按股票或全市场条件，从巨潮拉公告列表，收成统一字段。不做分类、不去重其它来源、不写 HTTP 路由。上层 `company.news.query` / `feed` 会把它和上交所、深交所、北交所的公告揉在一起；媒体站、东财、雪球也会借这里的 `resolve_org` 认出公司简称。

**不能只传 `600519` 这种 6 位代码。** 列表接口的 `stock` 必须是「代码 + 公司编号」绑在一起，例如 `600519,gssh0600519`。这个公司编号叫 `orgId`。找不到 `orgId` 时返回空包并带 `error`，不会把程序打崩。

---

## 目录里有什么

```
cninfo/
  constants.py   接口地址、请求头、市场/页签/分类对照表
  params.py      认出公司，把人话收成巨潮表单字段
  request.py     发请求：联想 orgId、翻页拉列表、下 PDF
  parse.py       原始 JSON → 统一字段
  fetch.py       把上面三步串成对外入口
  cli.py         命令行
  __init__.py    对外导出
  __main__.py    python -m company.news.official.cninfo
```

固定流水线：

```
入参（代码 / 分类 / 日期）
    → params.for_stock / for_market     算出 stock、column、seDate …
    → request.fetch_pages               翻页，只存各页原始 JSON
    → parse.parse_pack                  去高亮、补 PDF 地址、去重
    → 统一公告包
```

`fetch.py` 是唯一把三步接起来的地方。`params` 不发网；`request` 不改字段含义；`parse` 不请求。

---

## 各文件

### `constants.py` — 接口常量和对照表

巨潮相关的字面量都集中在这里，其它文件只引用，不散写 URL。

| 常量 | 含义 |
|------|------|
| `SEARCH_URL` | 联想公司：`/new/information/topSearch/query` |
| `QUERY_URL` | 公告列表：`/new/hisAnnouncement/query` |
| `PDF_PREFIX` | 附件前缀 `https://static.cninfo.com.cn/` |
| `STOCK_LIST_URLS` | 静态股票表（含 orgId）。沪市那份当前 404，只用深市 `szse_stock.json` 兜底 |
| `PAGE_SIZE` | 官网一页最多 30 条 |
| `MAX_PAGES` | 个股默认最多翻 50 页（约 1500 条） |
| `REQUEST_PAUSE_SEC` | 翻页间隔 0.25 秒 |
| `HEADERS` / `FORM_HEADERS` | 带官网 `Origin` / `Referer`，否则接口会拒 |

三张对照表把人话译成接口值：

- **`COLUMNS`**：市场栏目。`sse`/`sh` → 上交所，`szse`/`sz` → 深交所，`bj`/`bse` → 北交所。这是交易所栏目，不是主板/创业板。
- **`TABS`**：页签。`fulltext`（公告）、`relation`（调研）、`supervise`（持续督导）。中文别名「公告 / 调研 / 督导」也能用。
- **`CATEGORIES`**：公告分类。`年报` / `annual` → `category_ndbg_szsh`，其余见文件。键是别名，值是接口 `category`。
- **`PLATES`**：板块过滤（`szmb` 深圳主板、`shkcp` 科创板等）。查单只股票时一般留空。

### `params.py` — 参数设计

把「查谁、查哪一类、查哪段时间」收成巨潮要的表单字段。这里会调 `request.search_orgs` / `load_org_map` 认公司，但自己不拼 HTTP。

**认出公司 `resolve_org(code_or_name)`**

1. 先走联想：`POST topSearch/query?keyWord=600519&maxNum=10`
2. 你传的是 6 位代码，就在结果里找代码对得上的那一条；对不上用第一条
3. 联想没结果，再翻本地股票表 `szse_stock.json`
4. B 股不能直接查：深市 `200xxx` 改成对应 `000xxx`；沪市 `900xxx` 尽量从 `orgId` 里抠出 A 股代码，再问一次（`a_share_code`）
5. 结果缓存在模块级 `_ORG_CACHE`，同一进程里重复查不会反复打联想

认好之后，列表接口的 `stock` 必须写成 `600519,gssh0600519`，中间是英文逗号。

**市场 / 页签 / 分类**

- `resolve_column`：不传或 `auto` 时按代码号段猜交易所，猜不出默认深交所
- `resolve_tab`：不认识的词退回 `fulltext`
- `resolve_category`：别名或原始 `category_xxx` 都接受；多个用逗号/分号隔开，发出去用分号拼接。不传 = 这个页签下什么都要。不认识的词直接 `ValueError`

**日期 `se_date`**

巨潮要 `2024-01-01~2024-12-31`（中间波浪号）：

- 只说最近 N 天：从今天往回倒
- 只给起始日：从那天到今天
- 起止都给：按区间；写反了自动调过来
- 什么都不说：个股默认最近一年，全市场默认最近 7 天

**两套查询计划**

| 函数 | 用途 | `stock` | 默认翻页 |
|------|------|---------|----------|
| `for_stock` | 个股。先 `resolve_org`，失败则带 `error`、不发列表请求 | `代码,orgId` | 50 |
| `for_market` | 全市场切片。必须自己带市场、分类、日期，否则会把整站往下翻 | 空 | 5 |

`list_form` 把计划收成一页 `application/x-www-form-urlencoded` 表单，字段如下。

| 表单字段 | 例子 | 含义 |
|----------|------|------|
| `stock` | `600519,gssh0600519` | 查谁；空 = 全市场 |
| `column` | `sse` | 哪个交易所 |
| `tabName` | `fulltext` | 公告 / 调研 / 督导 |
| `seDate` | `2024-01-01~2024-12-31` | 哪段日子 |
| `category` | `category_ndbg_szsh` | 哪种公告；空 = 全部 |
| `searchkey` | `问询函` | 标题里要有的词 |
| `pageNum` | `1` | 从 1 开始 |
| `pageSize` | `30` | 最大 30 |
| `plate` | 空 | 板块，查单股一般空着 |
| `isHLtitle` | `true` | 标题要不要加搜索高亮 |

`secid`、`trade`、排序字段空着：公司身份已经在 `stock` 里，默认按披露时间从新到旧。

### `request.py` — 发请求

只负责网络，返回原始 JSON，不改字段含义。

| 函数 | 做什么 |
|------|--------|
| `search_orgs` | 联想公司。失败记日志并返回 `[]` |
| `load_org_map` | 拉静态股票表，进程内缓存。某份 URL 失败就跳过 |
| `query_page` | 查一页 `hisAnnouncement`。非 dict 响应收成空页 |
| `fetch_pages` | 按 `params` 翻页，直到列表空、到 `totalpages` 且 `hasMore` 为假、或到页数上限。返回 `{"pages": [...], "total": N}` |
| `download_pdf` / `download_announcements` | 按解析后的 `url` 落盘。文件名用标题（去掉非法字符，最长 80 字） |

总条数优先看 `totalAnnouncement`，没有再看 `totalRecordNum`。接口说的总数可能比实际拿到的多，因为后面的页被上限截掉了。

### `parse.py` — 解析

把各页原始 JSON 收成统一公告包。

联想结果：`parse_orgs` / `parse_org_row` 取出 `code` / `org_id` / `name`（`zwjc`）/ `pinyin`。静态表：`parse_org_map` 做成 `代码 → org` 字典。

一条公告走 `parse_item`：

1. **标题**：去掉 `isHLtitle` 留下的 `<em>`。剥完是空的，整行丢掉
2. **时间**：`announcementTime` 是毫秒戳，换成北京时间 `2024-04-01 00:00:00`。大于 `1e12` 先除以 1000。原始数字另留 `published_ms`
3. **PDF**：`adjunctUrl` 前面补 `https://static.cninfo.com.cn/`；已经是完整 `http(s)` 则原样用
4. **缺的名字**：这一行没带代码或简称时，用认公司时记下的代码、名字、orgId 补上

`parse_pack` 把各页拼起来，用 `announcement_id` 去重；没有 id 就用「标题 + 日期」。认公司失败时直接返回带 `error` 的空包，不再翻页。

### `fetch.py` — 对外入口

所有业务入口都在这里，内部只是 `for_stock`/`for_market` → `fetch_pages` → `parse_pack`。

| 函数 | 实际做的事 |
|------|------------|
| `fetch_announcements` | 主入口。个股 + 任意分类 / 页签 / 关键词 |
| `fetch_periodic_reports` | 预设定期报告分类（年报 / 半年报 / 一季报 / 三季报），默认回溯 5 年 |
| `search_announcements` | 标题关键词（对应表单 `searchkey`） |
| `fetch_surveys` | `tab=relation`，投资者关系 / 调研 |
| `fetch_supervise` | `tab=supervise`，持续督导 |
| `fetch_market_announcements` | 不指定个股的全市场切片 |

后四个都是对 `fetch_announcements`（或 `for_market`）的薄封装。

### `cli.py` / `__main__.py` / `__init__.py`

命令行走 `cli.main`。`python -m company.news.official.cninfo` 和 `...cninfo.cli` 是同一入口。

`__init__.py` 把常用符号再导出一层，外部应 `from company.news.official.cninfo import fetch_announcements, resolve_org`，不要深挖子模块。

---

## 一条原始公告长什么样

巨潮每页是一个大对象，公告在 `announcements` 里：

```json
{
  "totalAnnouncement": 86,
  "totalpages": 3,
  "hasMore": false,
  "announcements": [
    {
      "secCode": "600519",
      "secName": "贵州茅台",
      "orgId": "gssh0600519",
      "announcementId": "1219612345",
      "announcementTitle": "贵州茅台酒股份有限公司2023年年度报告",
      "announcementTime": 1711900800000,
      "adjunctUrl": "finalpage/2024-04-03/1219612345.PDF",
      "adjunctType": "PDF",
      "adjunctSize": 2048,
      "announcementType": "01010503||",
      "announcementTypeName": "年度报告"
    }
  ]
}
```

收好之后：

```json
{
  "code": "600519",
  "name": "贵州茅台",
  "org_id": "gssh0600519",
  "announcement_id": "1219612345",
  "title": "贵州茅台酒股份有限公司2023年年度报告",
  "published_at": "2024-04-01 00:00:00",
  "published_ms": 1711900800000,
  "url": "https://static.cninfo.com.cn/finalpage/2024-04-03/1219612345.PDF",
  "adjunct_url": "finalpage/2024-04-03/1219612345.PDF",
  "adjunct_type": "PDF",
  "adjunct_size": 2048,
  "category": "年度报告",
  "category_code": "01010503||",
  "column": "sse",
  "tab": "fulltext",
  "source": "巨潮资讯"
}
```

整包：

```json
{
  "code": "600519",
  "name": "贵州茅台",
  "org_id": "gssh0600519",
  "column": "sse",
  "tab": "fulltext",
  "category": "category_ndbg_szsh",
  "keyword": "",
  "se_date": "2024-01-01~2024-12-31",
  "source": "cninfo",
  "count": 4,
  "total": 4,
  "items": []
}
```

两个容易混的 `category`：

- **整包上的 `category`**：请求时的过滤条件（巨潮代号，可能好几个拼在一起）
- **每一条里的 `category`**：这条公告自己的中文分类（「年度报告」）

`count` 是真正拿到、去重后的条数。`total` 是巨潮说一共有多少。找不到公司时 `items` 为空，多一个 `error`。

---

## 分类别名

| 入参 | 发给巨潮 |
|------|----------|
| `年报` / `annual` | `category_ndbg_szsh` |
| `半年报` / `semi` | `category_bndbg_szsh` |
| `一季报` / `q1` | `category_yjdbg_szsh` |
| `三季报` / `q3` | `category_sjdbg_szsh` |
| `业绩预告` / `forecast` | `category_yjygjxz_szsh` |
| `董事会` / `board` | `category_dshgg_szsh` |
| `股东大会` / `shareholder` | `category_gddh_szsh` |
| `股权激励` / `incentive` | `category_gqjl_szsh` |
| `权益分派` / `dividend` | `category_qyfpxzcs_szsh` |
| `可转债` / `cbond` | `category_kzzq_szsh` |

也可以直接写原始代号。完整对照见 `constants.CATEGORIES`。

---

## 命令行

在 `backend` 目录下：

```text
python -m company.news.official.cninfo 600519
python -m company.news.official.cninfo 600519 --days 90 --category 年报
python -m company.news.official.cninfo 600519 --keyword 问询函
python -m company.news.official.cninfo 600519 --tab 调研
python -m company.news.official.cninfo 600519 --org-only
python -m company.news.official.cninfo 000001 --download ./pdfs --limit 3
python -m company.news.official.cninfo --market szse --category 年报 --days 30 --limit 20
```

常用开关：`--start` / `--end`、`--column sse|szse|bj|auto`、`--tab`、`--category`、`--keyword`、`--plate`、`--max-pages`、`--limit`、`--json`、`--org-only`、`--market`、`--download`。

`--org-only` 只解析 `orgId`，不查列表。不传代码、只传 `--market` 时走全市场切片。

---

## 谁在用这个包

| 调用方 | 怎么用 |
|--------|--------|
| `company.news.query` | `channel=cninfo` 或 `auto` 时调 `fetch_announcements`；`resolve_keywords` 用 `resolve_org` 拿简称 |
| `company.news.feed` | `kind=cninfo` / `notices` 时走 `query_announcements(..., channel="cninfo")` |
| `company.news.official.press.*` | 七家媒体站解析标题里的公司名时，借 `resolve_org` |
| 东财 / 同花顺 / 雪球公共层 | 同样借 `resolve_org` 对齐代码和简称 |

上层只补来源标记、和其它通道去重排序，不再改巨潮字段的意思。交易所一手公告在隔壁 `official/exchange`，东财转载的监管披露在 `platforms/eastmoney/notices`，都不是本目录。
