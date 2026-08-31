# 巨潮公告：怎么设参数，怎么解析数据

巨潮官网：[公告查询页](https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search)

代码按职责拆开：`params.py` 设计参数，`request.py` 发请求，`parse.py` 解析，`fetch.py` 把三步串起来。查公告要先认出这家公司，再按条件拉列表。

一个容易踩的坑：**不能只传 `600519` 这种 6 位代码。** 巨潮认的是「代码 + 公司编号」绑在一起，比如 `600519,gssh0600519`。这个公司编号叫 `orgId`。

---

## 一、怎么设计参数

想清楚三件事：查谁、查哪一类、查哪段时间。其余都是把人话翻译成巨潮要的表单。

### 1. 先认出公司（拿到 orgId）

给人一个代码或简称（`600519`、`贵州茅台`），先问巨潮「这是谁」。

请求：

```
POST .../topSearch/query?keyWord=600519&maxNum=10
```

回来大概是：

```json
[
  {
    "code": "600519",
    "orgId": "gssh0600519",
    "zwjc": "贵州茅台"
  }
]
```

怎么挑：

- 你传的是 6 位代码，就在结果里找代码对得上的那一条
- 对不上，用第一条
- 联想没结果，再翻一份本地股票表（`szse_stock.json`）碰运气
- B 股不能直接查。深市 `200xxx` 改成对应的 `000xxx`；沪市 `900xxx` 尽量从 `orgId` 里抠出 A 股代码，再问一次

找不到 `orgId` 就别硬查列表。函数会返回空结果并带一句 `error`，不会把程序打崩。

认好之后，列表接口的 `stock` 必须写成：

```text
600519,gssh0600519
```

中间是英文逗号，不能只有代码。

查全市场（不指定个股）时，`stock` 留空，但一定要自己带上市场、分类、日期，否则会把整站往下翻。

### 2. 查哪一类

对外函数是 `fetch_announcements`。人比较好记的几个参数，最后都会填进同一张表单。

**市场 `column`：上交所、深交所，还是北交所**

- `sse` / `sh` → 上交所
- `szse` / `sz` → 深交所
- `bj` / `bse` → 北交所
- 不传或 `auto`：按代码号段自己猜，猜不出来默认深交所

这是市场栏目，不是主板/创业板那种板块。板块另有一个 `plate`（`szmb` 深圳主板、`shkcp` 科创板等），查单只股票时一般不用填。

**页签 `tab`：公告、调研，还是督导**

- 不传 → 普通公告（`fulltext`）
- `调研` / `relation` → 投资者关系、调研记录
- `督导` / `supervise` → 持续督导

**分类 `category`：只要年报，还是只要问询函那一类**

可以写人话，代码会翻译成巨潮内部代号：

| 你这么写 | 实际发给巨潮 |
|----------|----------------|
| `年报` / `annual` | `category_ndbg_szsh` |
| `半年报` / `semi` | `category_bndbg_szsh` |
| `一季报` / `q1` | `category_yjdbg_szsh` |
| `三季报` / `q3` | `category_sjdbg_szsh` |
| `业绩预告` / `forecast` | `category_yjygjxz_szsh` |
| `董事会` / `board` | `category_dshgg_szsh` |
| `股东大会` / `shareholder` | `category_gddh_szsh` |
| `股权激励` / `incentive` | `category_gqjl_szsh` |

也可以直接写原始代号 `category_ndbg_szsh`。要好几种，用逗号隔开：`年报,一季报`，发出去会变成用分号拼在一起的一串。不传分类 = 这个页签下什么都要。不认识的词会直接报错。

**标题关键词 `keyword`**

只想看标题里带「问询函」的，填 `问询函`。对应表单里的 `searchkey`。

几个现成入口其实只是帮你预设了上面这些：

- 定期报告 → 填好年报/季报分类
- 搜标题 → 填关键词
- 调研 / 督导 → 换页签

### 3. 查哪段时间

巨潮要的日期长这样，中间是波浪号：

```text
2024-01-01~2024-12-31
```

怎么从你的入参算出来：

- 只说「最近 90 天」：从今天往回倒 90 天
- 只给起始日：从那天到今天
- 起止都给：按你给的区间；起止写反了会自动调过来
- 什么都不说：默认最近一年

### 4. 翻页

官网一页最多 30 条。单只股票默认最多翻 50 页（大约 1500 条），全市场默认只翻 5 页，免得把整站拉下来。页与页之间停一下（0.25 秒）。

### 5. 发出去的表单长什么样

上面这些收好之后，真正 POST 的是一张表（`application/x-www-form-urlencoded`）。网站会检查你是不是从巨潮页面点过来的，所以请求头里要带上官网的 `Origin` 和 `Referer`。

| 表单字段 | 例子 | 人话 |
|----------|------|------|
| `stock` | `600519,gssh0600519` | 查谁；空 = 全市场 |
| `column` | `sse` | 哪个交易所 |
| `tabName` | `fulltext` | 公告 / 调研 / 督导 |
| `seDate` | `2024-01-01~2024-12-31` | 哪段日子 |
| `category` | `category_ndbg_szsh` | 哪种公告；空 = 全部 |
| `searchkey` | `问询函` | 标题里要有的词 |
| `pageNum` | `1` | 第几页，从 1 开始 |
| `pageSize` | `30` | 一页几条，最大 30 |
| `plate` | 空 | 板块，查单股一般空着 |
| `isHLtitle` | `true` | 标题要不要加搜索高亮 |

`secid`、`trade`、排序字段我们空着就行：公司身份已经在 `stock` 里，默认按披露时间从新到旧。

命令行可以对照着试：

```text
python -m company.news.official.cninfo.cli 600519
python -m company.news.official.cninfo.cli 600519 --days 90 --category 年报
python -m company.news.official.cninfo.cli 600519 --keyword 问询函
python -m company.news.official.cninfo.cli 600519 --tab 调研
python -m company.news.official.cninfo.cli --market szse --category 年报 --days 30
```

---

## 二、怎么解析数据

巨潮每次只给你一页。一页是一个大对象，公告在 `announcements` 数组里。

```json
{
  "totalAnnouncement": 86,
  "totalpages": 3,
  "hasMore": false,
  "announcements": [ { "一条公告" }, { "另一条" } ]
}
```

翻页看到什么停：

- `announcements` 空了 → 停
- 已经到 `totalpages`，并且 `hasMore` 为假 → 停
- 到了我们设的页数上限 → 停

总条数优先看 `totalAnnouncement`，没有再看 `totalRecordNum`。接口说的总数可能比我们实际拿到的多，因为后面的页被上限截掉了。

### 1. 一条原始公告里有什么

```json
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
```

人话对照：

- `secCode` / `secName`：股票代码、简称
- `announcementId`：这条公告的身份证，用来去重
- `announcementTitle`：标题。开了高亮时，里面可能夹着 `<em>` 标签
- `announcementTime`：披露时间，是**毫秒**时间戳，不是「2024-04-01」这种字
- `adjunctUrl`：PDF 的半截路径，还不是能直接打开的网址
- `announcementTypeName`：这条公告自己的中文分类，比如「年度报告」

### 2. 我们怎么收成一条

每一行走 `_normalize_item`，做四件小事：

**标题**  
去掉 `<em>`。剥完如果是空的，整行丢掉。

**时间**  
把毫秒戳换成北京时间的 `2024-04-01 00:00:00`。数字特别大（大于 `1e12`）就先除以 1000，当成毫秒。原始数字另外留一份，叫 `published_ms`。

**PDF 地址**  
前面补上 `https://static.cninfo.com.cn/`。如果人家已经给了完整 `http` 链接，就原样用。

**缺的名字**  
这一行没带代码或简称时，用第一步认公司时记下的代码、名字、orgId 补上。

收好之后长这样：

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

同一条公告出现两次（翻页重叠），用 `announcement_id` 去掉；没有 id 就用「标题 + 日期」当钥匙。

### 3. 整包怎么交出去

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
  "items": [ "上面那种一条条公告" ]
}
```

两个容易混的 `category`：

- **整包上的 `category`**：你请求时用的过滤条件（巨潮代号，可能好几个拼在一起）
- **每一条里的 `category`**：这条公告自己的中文分类（「年度报告」）

`count` 是我们真正拿到、去重后的条数。`total` 是巨潮说一共有多少。找不到公司时，`items` 是空的，多一个 `error` 字段说明原因。

上层（`query.py`、`feed.py`）还会把这些条目和上交所、深交所的公告揉在一起去重。那一层不再改巨潮字段的意思，只补一个来源标记、方便排序。

要落盘 PDF：用每条里的 `url` 下载，文件名用标题（去掉不能当文件名的符号，最长 80 个字）。
