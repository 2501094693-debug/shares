const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();

const DEFAULT_DAYS = 3;
const CNINFO_DEFAULT_DAYS = 365;
const EXCHANGE_DEFAULT_DAYS = 365;
const PRESS_DEFAULT_DAYS = 30;
const PLATFORM_DEFAULT_DAYS = 30;
const NEWS_GROUP_OFFICIAL = "official";
const NEWS_GROUP_OTHER = "other";
const NEWS_GROUP_LABELS = {
  official: "官方",
  other: "其他",
};
const EMOTION_DEFAULT_DAYS = 3;
const EMOTION_SOURCE = "eastmoney";
const THS_EMOTION_SOURCE = "tonghuashun";
const XQ_EMOTION_SOURCE = "xueqiu";
const EMOTION_SOURCE_LABELS = {
  eastmoney: "东方财富",
  tonghuashun: "同花顺",
  xueqiu: "雪球",
};
const CNINFO_TAB_LABELS = {
  fulltext: "公告",
  relation: "调研",
  supervise: "督导",
};
const EXCHANGE_TAB_LABELS = {
  bulletin: "公告",
  inquiries: "问询",
};
const EXCHANGE_MARKET_TITLES = {
  sse: "上交所公告",
  szse: "深交所公告",
  bse: "北交所公告",
};

const PRESS_OUTLETS = [
  {
    id: "cs",
    name: "中证网",
    paper: "中国证券报",
    filters: [
      { key: "field", label: "范围", options: [["all", "全部"], ["title", "标题"], ["content", "正文"]] },
      { key: "sort", label: "排序", options: [["time", "时间"], ["relevance", "相关度"]] },
    ],
  },
  {
    id: "cnstock",
    name: "中国证券网",
    paper: "上海证券报",
    filters: [
      {
        key: "type",
        label: "类型",
        options: [
          ["news", "新闻"],
          ["all", "全部"],
          ["video", "视频"],
          ["topic", "专题"],
          ["activity", "活动"],
          ["roadshow", "路演"],
          ["stock", "股票"],
        ],
      },
    ],
  },
  {
    id: "stcn",
    name: "证券时报网",
    paper: "证券时报",
    filters: [
      {
        key: "type",
        label: "类型",
        options: [
          ["news", "资讯"],
          ["all", "全部"],
          ["report", "公告"],
          ["activity", "直播"],
          ["video", "视频"],
          ["topic", "专题"],
          ["stock", "股票"],
        ],
      },
      { key: "sort", label: "排序", options: [["time", "时间"], ["relevance", "相关度"]] },
    ],
  },
  {
    id: "zqrb",
    name: "证券日报网",
    paper: "证券日报",
    filters: [
      { key: "src", label: "来源", options: [["news", "新闻"], ["all", "全部"], ["epaper", "电子报"]] },
      { key: "field", label: "范围", options: [["title", "标题"], ["all", "全文"], ["author", "作者"]] },
      { key: "sort", label: "排序", options: [["time", "时间"], ["relevance", "相关度"]] },
    ],
  },
  {
    id: "financialnews",
    name: "金融时报网",
    paper: "金融时报",
    filters: [
      { key: "field", label: "范围", options: [["all", "全文"], ["title", "标题"], ["content", "正文"], ["author", "作者"]] },
      { key: "sort", label: "排序", options: [["time", "时间"], ["relevance", "相关度"]] },
    ],
  },
  { id: "jjckb", name: "经济参考网", paper: "经济参考报", filters: [] },
  {
    id: "chinadaily",
    name: "中国日报网",
    paper: "中国日报",
    filters: [
      { key: "type", label: "类型", options: [["story", "文章"], ["comment", "评论"], ["blog", "博客"], ["photo", "图片"]] },
      { key: "sort", label: "排序", options: [["time", "最新"], ["oldest", "最早"], ["relevance", "相关度"]] },
    ],
  },
];

const PLATFORM_HUBS = [
  {
    id: "eastmoney",
    name: "东方财富",
    tabs: [
      { id: "news", label: "新闻" },
      { id: "f10", label: "F10" },
      { id: "notices", label: "公告" },
    ],
    extras: {
      news: [
        {
          key: "type",
          label: "类型",
          options: [
            ["old", "新闻索引"],
            ["web", "网页"],
            ["all", "全部"],
          ],
        },
        {
          key: "scope",
          label: "范围",
          options: [
            ["default", "A股"],
            ["global", "全球"],
          ],
        },
        {
          key: "sort",
          label: "排序",
          options: [
            ["time", "时间"],
            ["relevance", "相关度"],
          ],
        },
      ],
    },
  },
  {
    id: "ths",
    name: "同花顺",
    tabs: [
      { id: "news", label: "新闻" },
      { id: "notices", label: "公告" },
      { id: "reports", label: "研报" },
    ],
    extras: {
      notices: [
        {
          key: "classify",
          label: "分类",
          options: [
            ["all", "全部"],
            ["earnings", "业绩"],
            ["major", "重大事项"],
            ["share", "股份变动"],
            ["resolution", "决议"],
          ],
        },
      ],
    },
  },
  {
    id: "xueqiu",
    name: "雪球",
    tabs: [
      { id: "news", label: "资讯" },
      { id: "notices", label: "公告" },
      { id: "reports", label: "研报" },
    ],
    extras: {
      reports: [
        {
          key: "sort",
          label: "排序",
          options: [
            ["time", "时间"],
            ["alpha", "热度"],
            ["reply", "评论"],
          ],
        },
      ],
    },
  },
];

const els = {
  pageTitle: document.getElementById("pageTitle"),
  pageSub: document.getElementById("pageSub"),
  backLink: document.getElementById("backLink"),
  companyBreadcrumb: document.getElementById("companyBreadcrumb"),
  companyName: document.getElementById("companyName"),
  companyCodeChip: document.getElementById("companyCodeChip"),
  metricsGrid: document.getElementById("metricsGrid"),
  metricsPanels: document.getElementById("metricsPanels"),
  chartModeSelect: document.getElementById("chartModeSelect"),
  chartAdjustSelect: document.getElementById("chartAdjustSelect"),
  chartAdjustWrap: document.getElementById("chartAdjustWrap"),
  chartMeta: document.getElementById("chartMeta"),
  chartHoverCard: document.getElementById("chartHoverCard"),
  chartWrap: document.getElementById("chartWrap"),
  priceChart: document.getElementById("priceChart"),
  chartEmpty: document.getElementById("chartEmpty"),
  chartAxisScroll: document.getElementById("chartAxisScroll"),
  chartScrollBar: document.getElementById("chartScrollBar"),
  ticksChartMeta: document.getElementById("ticksChartMeta"),
  ticksChartHoverCard: document.getElementById("ticksChartHoverCard"),
  ticksChartWrap: document.getElementById("ticksChartWrap"),
  ticksChart: document.getElementById("ticksChart"),
  ticksChartEmpty: document.getElementById("ticksChartEmpty"),
  ticksChartAxisScroll: document.getElementById("ticksChartAxisScroll"),
  ticksChartScrollBar: document.getElementById("ticksChartScrollBar"),
  peSeriesSelect: document.getElementById("peSeriesSelect"),
  peSeriesWrap: document.getElementById("peSeriesWrap"),
  peChartMeta: document.getElementById("peChartMeta"),
  peChartHoverCard: document.getElementById("peChartHoverCard"),
  peChartWrap: document.getElementById("peChartWrap"),
  peChart: document.getElementById("peChart"),
  peChartEmpty: document.getElementById("peChartEmpty"),
  peChartAxisScroll: document.getElementById("peChartAxisScroll"),
  peChartScrollBar: document.getElementById("peChartScrollBar"),
  turnoverChartMeta: document.getElementById("turnoverChartMeta"),
  turnoverChartHoverCard: document.getElementById("turnoverChartHoverCard"),
  turnoverChartWrap: document.getElementById("turnoverChartWrap"),
  turnoverChart: document.getElementById("turnoverChart"),
  turnoverChartEmpty: document.getElementById("turnoverChartEmpty"),
  turnoverChartAxisScroll: document.getElementById("turnoverChartAxisScroll"),
  turnoverChartScrollBar: document.getElementById("turnoverChartScrollBar"),
  refreshNewsBtn: document.getElementById("refreshNewsBtn"),
  panelNews: document.getElementById("panel-news"),
  newsSourceBar: document.getElementById("newsSourceBar"),
  refreshEmotionBtn: document.getElementById("refreshEmotionBtn"),
  companyMainTabs: document.getElementById("companyMainTabs"),
  exchangeForm: document.getElementById("exchangeForm"),
  exchangeTabs: document.getElementById("exchangeTabs"),
  exchangeTitle: document.getElementById("exchangeTitle"),
  exchangeCategory: document.getElementById("exchangeCategory"),
  exchangeDays: document.getElementById("exchangeDays"),
  exchangeStart: document.getElementById("exchangeStart"),
  exchangeEnd: document.getElementById("exchangeEnd"),
  exchangeStartWrap: document.getElementById("exchangeStartWrap"),
  exchangeEndWrap: document.getElementById("exchangeEndWrap"),
  exchangeKeyword: document.getElementById("exchangeKeyword"),
  exchangeQueryBtn: document.getElementById("exchangeQueryBtn"),
  exchangeMeta: document.getElementById("exchangeMeta"),
  exchangeHint: document.getElementById("exchangeHint"),
  exchangeBody: document.getElementById("exchangeBody"),
  exchangeList: document.getElementById("exchangeList"),
  pressForm: document.getElementById("pressForm"),
  pressTabs: document.getElementById("pressTabs"),
  pressTitle: document.getElementById("pressTitle"),
  pressExtraRow: document.getElementById("pressExtraRow"),
  pressDays: document.getElementById("pressDays"),
  pressStart: document.getElementById("pressStart"),
  pressEnd: document.getElementById("pressEnd"),
  pressStartWrap: document.getElementById("pressStartWrap"),
  pressEndWrap: document.getElementById("pressEndWrap"),
  pressKeyword: document.getElementById("pressKeyword"),
  pressQueryBtn: document.getElementById("pressQueryBtn"),
  pressMeta: document.getElementById("pressMeta"),
  pressHint: document.getElementById("pressHint"),
  pressBody: document.getElementById("pressBody"),
  pressList: document.getElementById("pressList"),
  cninfoForm: document.getElementById("cninfoForm"),
  cninfoTabs: document.getElementById("cninfoTabs"),
  cninfoCategory: document.getElementById("cninfoCategory"),
  cninfoDays: document.getElementById("cninfoDays"),
  cninfoStart: document.getElementById("cninfoStart"),
  cninfoEnd: document.getElementById("cninfoEnd"),
  cninfoStartWrap: document.getElementById("cninfoStartWrap"),
  cninfoEndWrap: document.getElementById("cninfoEndWrap"),
  cninfoKeyword: document.getElementById("cninfoKeyword"),
  cninfoQueryBtn: document.getElementById("cninfoQueryBtn"),
  cninfoMeta: document.getElementById("cninfoMeta"),
  cninfoHint: document.getElementById("cninfoHint"),
  cninfoBody: document.getElementById("cninfoBody"),
  cninfoList: document.getElementById("cninfoList"),
  emotionScoresMeta: document.getElementById("emotionScoresMeta"),
  emotionScoresTitle: document.getElementById("emotionScoresTitle"),
  emotionScoresHint: document.getElementById("emotionScoresHint"),
  emotionScoresBody: document.getElementById("emotionScoresBody"),
  emotionScoresContent: document.getElementById("emotionScoresContent"),
  emotionRankMeta: document.getElementById("emotionRankMeta"),
  emotionRankTitle: document.getElementById("emotionRankTitle"),
  emotionRankHint: document.getElementById("emotionRankHint"),
  emotionRankBody: document.getElementById("emotionRankBody"),
  emotionRankList: document.getElementById("emotionRankList"),
  emotionPostsForm: document.getElementById("emotionPostsForm"),
  emotionPostsKind: document.getElementById("emotionPostsKind"),
  emotionPostsSort: document.getElementById("emotionPostsSort"),
  emotionPostsSortThs: document.getElementById("emotionPostsSortThs"),
  emotionPostsDays: document.getElementById("emotionPostsDays"),
  emotionPostsPages: document.getElementById("emotionPostsPages"),
  emotionPostsReplies: document.getElementById("emotionPostsReplies"),
  emotionPostsQueryBtn: document.getElementById("emotionPostsQueryBtn"),
  emotionPostsMeta: document.getElementById("emotionPostsMeta"),
  emotionPostsTitle: document.getElementById("emotionPostsTitle"),
  emotionPostsHint: document.getElementById("emotionPostsHint"),
  emotionPostsBody: document.getElementById("emotionPostsBody"),
  emotionPostsList: document.getElementById("emotionPostsList"),
  emotionSearchForm: document.getElementById("emotionSearchForm"),
  emotionSearchKeyword: document.getElementById("emotionSearchKeyword"),
  emotionSearchSort: document.getElementById("emotionSearchSort"),
  emotionSearchSortThs: document.getElementById("emotionSearchSortThs"),
  emotionSearchDays: document.getElementById("emotionSearchDays"),
  emotionSearchPages: document.getElementById("emotionSearchPages"),
  emotionSearchQueryBtn: document.getElementById("emotionSearchQueryBtn"),
  emotionSearchMeta: document.getElementById("emotionSearchMeta"),
  emotionSearchTitle: document.getElementById("emotionSearchTitle"),
  emotionSearchHint: document.getElementById("emotionSearchHint"),
  emotionSearchBody: document.getElementById("emotionSearchBody"),
  emotionSearchList: document.getElementById("emotionSearchList"),
  emotionDetail: document.getElementById("emotionDetail"),
  emotionDetailTitle: document.getElementById("emotionDetailTitle"),
  emotionDetailMeta: document.getElementById("emotionDetailMeta"),
  emotionDetailContent: document.getElementById("emotionDetailContent"),
  emotionDetailLink: document.getElementById("emotionDetailLink"),
  emotionDetailClose: document.getElementById("emotionDetailClose"),
  emotionDetailReplies: document.getElementById("emotionDetailReplies"),
  emotionDetailRepliesTitle: document.getElementById("emotionDetailRepliesTitle"),
  emotionDetailRepliesList: document.getElementById("emotionDetailRepliesList"),
  emotionSourceBar: document.getElementById("emotionSourceBar"),
  panelEmotion: document.getElementById("panel-emotion"),
  errorBox: document.getElementById("errorBox"),
};

let activeMainPanel = "quotes";
let cninfoTab = "fulltext";
let exchangeTab = "bulletin";
let pressOutlet = "cs";
const cninfoState = {
  loading: false,
  items: [],
  count: 0,
  total: 0,
  seDate: "",
  category: "",
  keyword: "",
  tab: "fulltext",
  error: "",
  updatedAt: "",
};
const exchangeState = {
  loading: false,
  items: [],
  count: 0,
  total: 0,
  seDate: "",
  category: "",
  keyword: "",
  tab: "bulletin",
  market: "",
  marketLabel: "",
  error: "",
  updatedAt: "",
};
const pressState = {
  loading: false,
  items: [],
  count: 0,
  total: 0,
  seDate: "",
  outlet: "cs",
  keyword: "",
  error: "",
  updatedAt: "",
};
const platformTabs = { ths: "news", xueqiu: "news", eastmoney: "news" };
const platformState = {
  ths: { loading: false, items: [], count: 0, total: 0, seDate: "", tab: "news", keyword: "", error: "", updatedAt: "" },
  xueqiu: { loading: false, items: [], count: 0, total: 0, seDate: "", tab: "news", keyword: "", error: "", updatedAt: "" },
  eastmoney: { loading: false, items: [], count: 0, total: 0, seDate: "", tab: "news", keyword: "", error: "", updatedAt: "" },
};
const emotionState = {
  scores: { loading: false, data: null, error: "", updatedAt: "" },
  rank: { loading: false, data: null, items: [], count: 0, total: 0, error: "", updatedAt: "" },
  posts: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    kind: "all",
    sort: "time",
    days: EMOTION_DEFAULT_DAYS,
    withReplies: false,
    error: "",
    updatedAt: "",
  },
  search: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    keyword: "",
    sort: "time",
    days: 7,
    error: "",
    updatedAt: "",
  },
  detail: { loading: false, postId: "", pack: null, error: "" },
};
const thsEmotionState = {
  scores: { loading: false, data: null, error: "", updatedAt: "" },
  rank: { loading: false, data: null, items: [], count: 0, total: 0, error: "", updatedAt: "" },
  posts: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    sort: "hot",
    maxPages: 3,
    withReplies: false,
    error: "",
    updatedAt: "",
  },
  search: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    keyword: "",
    sort: "hot",
    maxPages: 3,
    error: "",
    updatedAt: "",
  },
  detail: { loading: false, postId: "", pack: null, error: "" },
};
const xqEmotionState = {
  scores: { loading: false, data: null, error: "", updatedAt: "" },
  rank: { loading: false, data: null, items: [], count: 0, total: 0, market: "cn", error: "", updatedAt: "" },
  posts: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    kind: "user",
    sort: "time",
    days: EMOTION_DEFAULT_DAYS,
    maxPages: 3,
    market: "cn",
    withReplies: false,
    error: "",
    updatedAt: "",
  },
  search: {
    loading: false,
    items: [],
    count: 0,
    total: 0,
    keyword: "",
    sort: "time",
    days: 7,
    maxPages: 3,
    error: "",
    updatedAt: "",
  },
  detail: { loading: false, postId: "", pack: null, error: "" },
};
let newsGroup = normalizeNewsGroup(params.get("news") || "");
let newsBootstrapped = { official: false, other: false };
let emotionBootstrapped = { eastmoney: false, tonghuashun: false, xueqiu: false };
const tabParamRaw = (params.get("tab") || "").trim().toLowerCase();
let emotionSource = normalizeEmotionSource(params.get("emotion") || "");
if (["ths-emotion", "ths", "circle"].includes(tabParamRaw)) {
  emotionSource = "tonghuashun";
} else if (["xueqiu", "xq", "snowball"].includes(tabParamRaw)) {
  emotionSource = "xueqiu";
}
let stockDisplayName = nameHint || code;

function normalizeEmotionSource(source) {
  const raw = String(source || "").trim().toLowerCase();
  if (raw === "tonghuashun" || raw === "ths" || raw === "10jqka" || raw === "circle") return "tonghuashun";
  if (raw === "xueqiu" || raw === "xq" || raw === "snowball") return "xueqiu";
  return "eastmoney";
}

function isThsEmotion(source = emotionSource) {
  return source === "tonghuashun";
}

function isXqEmotion(source = emotionSource) {
  return source === "xueqiu";
}

function activeEmotionState(source = emotionSource) {
  if (isXqEmotion(source)) return xqEmotionState;
  if (isThsEmotion(source)) return thsEmotionState;
  return emotionState;
}

function normalizeMainPanel(panelId) {
  if (panelId === "quotes" || panelId === "charts" || panelId === "overview") return "quotes";
  if (panelId === "news") return "news";
  if (panelId === "emotion" || panelId === "ths-emotion" || panelId === "ths" || panelId === "circle" || panelId === "xueqiu" || panelId === "xq") return "emotion";
  return "";
}

function normalizeNewsGroup(group) {
  const raw = String(group || "").trim().toLowerCase();
  if (raw === "other" || raw === "platform" || raw === "platforms" || raw === "media") return NEWS_GROUP_OTHER;
  return NEWS_GROUP_OFFICIAL;
}

function isOfficialNews(group = newsGroup) {
  return group === NEWS_GROUP_OFFICIAL;
}

function newsHubGroup(hub) {
  return hub?.dataset?.newsGroup || NEWS_GROUP_OFFICIAL;
}

function isNewsHubInGroup(hub, group = newsGroup) {
  return newsHubGroup(hub) === group;
}

function isQuotesPanel(panelId = activeMainPanel) {
  return panelId === "quotes";
}

/** @type {{ mode: string, adjust: 'qfq'|'hfq'|'none', loading: boolean, kind: 'kline', items: any[], allItems: any[], viewStart: number, viewSize: number, preClose: number|null, source: string, meta: string, hoverAbsIndex: number|null }} */
const chartState = {
  mode: "day",
  adjust: "qfq",
  loading: false,
  kind: "kline",
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: 90,
  preClose: null,
  source: "",
  meta: "",
  hoverAbsIndex: null,
};

/** @type {{ loading: boolean, liveFetching: boolean, liveFetchPending: boolean, liveFetchGen: number, items: any[], allItems: any[], viewStart: number, viewSize: number, preClose: number|null, source: string, live: boolean, phase: string, tradeDate: string, hoverTime: string|null }} */
const ticksState = {
  loading: false,
  liveFetching: false,
  liveFetchPending: false,
  liveFetchGen: 0,
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: 0,
  preClose: null,
  source: "",
  live: false,
  phase: "closed",
  tradeDate: "",
  hoverTime: null,
};

const livePollState = {
  profileFetching: false,
  profilePending: false,
};

const TICKS_LIVE_POS = -40;
const TICKS_DRAW_MAX = 1800;

const CHART_MODES = {
  "1m": { label: "1分", kind: "kline", period: "1m", limit: 720, viewSize: 240, adjust: "none" },
  "5m": { label: "5分", kind: "kline", period: "5m", limit: 480, viewSize: 96, adjust: "none" },
  "15m": { label: "15分", kind: "kline", period: "15m", limit: 360, viewSize: 80, adjust: "none" },
  "30m": { label: "30分", kind: "kline", period: "30m", limit: 360, viewSize: 80, adjust: "none" },
  "60m": { label: "60分", kind: "kline", period: "60m", limit: 240, viewSize: 72, adjust: "none" },
  day: { label: "日K", kind: "kline", period: "day", limit: 720, viewSize: 90, adjust: "qfq" },
  week: { label: "周K", kind: "kline", period: "week", limit: 360, viewSize: 80, adjust: "qfq" },
  month: { label: "月K", kind: "kline", period: "month", limit: 240, viewSize: 72, adjust: "qfq" },
};

const MINUTE_KLINE_MODES = new Set(["1m", "5m", "15m", "30m", "60m"]);
const ADJUSTABLE_KLINE_MODES = new Set(["day", "week", "month"]);

function isMinuteKline(mode) {
  return MINUTE_KLINE_MODES.has(mode);
}

function isAdjustableKline(mode) {
  return ADJUSTABLE_KLINE_MODES.has(mode);
}

function adjustLabel(adjust) {
  if (adjust === "none") return "不复权";
  if (adjust === "hfq") return "后复权";
  return "前复权";
}

function klineAdjustFor(mode) {
  if (isAdjustableKline(mode)) return chartState.adjust;
  const conf = CHART_MODES[mode];
  return conf?.adjust || "none";
}

function syncChartAdjustUi(mode = chartState.mode) {
  const show = isAdjustableKline(mode);
  if (els.chartAdjustWrap) els.chartAdjustWrap.classList.toggle("hidden", !show);
  if (!els.chartAdjustSelect) return;
  els.chartAdjustSelect.disabled = !show;
  els.chartAdjustSelect.value = klineAdjustFor(mode);
  syncComboLegend(mode);
}

function comboPanesEnabled(mode = chartState.mode) {
  return !isMinuteKline(mode);
}

function syncComboLegend(mode = chartState.mode) {
  const card = document.querySelector(".chart-card--kline");
  const combo = comboPanesEnabled(mode);
  if (card) card.classList.toggle("is-combo", combo);
  if (els.peSeriesWrap) els.peSeriesWrap.classList.toggle("hidden", !combo);
}

function syncChartModeSelect(mode = chartState.mode) {
  if (!els.chartModeSelect) return;
  if (els.chartModeSelect.value !== mode) els.chartModeSelect.value = mode;
}

/** K 均线：周期按当前 K 线根数（周K 的 MA5 = 5 周，1分的 MA5 = 5 分钟） */
const KLINE_MA_LINES = [
  { period: 5, key: "ma5", label: "MA5", color: "#f0b429" },
  { period: 10, key: "ma10", label: "MA10", color: "#5b9dff" },
  { period: 20, key: "ma20", label: "MA20", color: "#d48cff" },
];

function computeSmaSeries(closes, period) {
  const n = closes.length;
  const out = new Array(n).fill(null);
  if (period <= 0 || n < period) return out;
  for (let i = period - 1; i < n; i += 1) {
    let sum = 0;
    let ok = true;
    for (let j = i - period + 1; j <= i; j += 1) {
      const v = Number(closes[j]);
      if (!Number.isFinite(v)) {
        ok = false;
        break;
      }
      sum += v;
    }
    // 前 period-1 根及缺数窗口保持 null，绝不写 0
    if (ok) out[i] = sum / period;
  }
  return out;
}

function maPoint(vals, index) {
  if (!Array.isArray(vals) || index == null || index < 0 || index >= vals.length) {
    return null;
  }
  const raw = vals[index];
  if (raw == null || raw === "") return null;
  const v = Number(raw);
  return Number.isFinite(v) ? v : null;
}

function getKlineMaBundle() {
  const all = chartState.allItems || [];
  const closes = all.map((d) => Number(d.close));
  const full = {};
  for (const line of KLINE_MA_LINES) {
    full[line.key] = computeSmaSeries(closes, line.period);
  }
  const { start, size } = chartViewWindow();
  const visible = {};
  for (const line of KLINE_MA_LINES) {
    visible[line.key] = (full[line.key] || []).slice(start, start + size);
  }
  return { full, visible };
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const json = await res.json();
  if (!res.ok || !json.ok) {
    throw new Error(json.error || `请求失败 (${res.status})`);
  }
  return json;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function displayValue(v) {
  if (v == null || String(v).trim() === "") return "-";
  return String(v).trim();
}

function changeClass(v) {
  const text = displayValue(v);
  if (text === "-") return "";
  const num = parseFloat(String(text).replace(/%/g, "").replace(/,/g, ""));
  if (!Number.isFinite(num)) return "";
  if (num > 0) return "change-up";
  if (num < 0) return "change-down";
  return "";
}

function truncateText(text, max = 160) {
  const s = String(text || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

function setError(message) {
  if (!message) {
    els.errorBox.classList.add("hidden");
    els.errorBox.textContent = "";
    return;
  }
  els.errorBox.textContent = message;
  els.errorBox.classList.remove("hidden");
}

function daysLabel(days) {
  if (days <= DEFAULT_DAYS) return "最新";
  if (days >= 360) {
    const years = days / 365;
    const rounded = years >= 10 ? Math.round(years) : Math.round(years * 10) / 10;
    return `近约 ${rounded} 年`;
  }
  return `近 ${days} 天`;
}

/** 指标含义说明（点击展示，尽量白话） */
const METRIC_TIPS = {
  最新: "现在这只股票的最新成交价格。",
  涨幅: "今天比昨天收盘涨了还是跌了，用百分比表示。比如 +2% 就是比昨天贵了 2%。",
  涨跌: "今天比昨天收盘贵了或便宜了多少钱（元）。",
  市值: "按现在股价算，整家公司值多少钱：股价 × 全部股份。",
  换手: "今天卖掉又买走的股份，大概占能流通股份的多少。越高说明今天买卖越热闹。",
  今开: "今天开盘时的第一笔成交价。",
  昨收: "昨天收盘时的价格，用来对比今天涨跌。",
  最高: "今天到现在，成交过的最高价。",
  最低: "今天到现在，成交过的最低价。",
  均价: "把今天所有成交平均一下，大概多少钱一股买到的。",
  总手: "今天一共成交了多少手。1 手 = 100 股。",
  金额: "今天一共成交了多少钱。",
  "换手(实)": "只拿真正容易卖掉的股份来算活跃度，比普通换手更能看出“好卖的那部分”交易有多热。",
  现手: "刚刚那一笔买卖成交了多少手。",
  量比: "今天到现在平均每分钟成交量，和过去几天同时段比。大于 1 说明今天成交比平时更活跃。",
  振幅: "今天最高价和最低价差了多少，相对昨天收盘的比例。越大说明今天价格晃得越厉害。",
  实体涨幅: "从今天开盘价到现在的涨跌，主要看开盘以后实际走出的方向。",
  涨停: "今天按规定允许涨到的最高价。碰到它往往买不进或很难买。",
  跌停: "今天按规定允许跌到的最低价。碰到它往往卖不出或很难卖。",
  外盘: "主动按卖价买进去的成交量。多了，常被看作买的人更积极。",
  内盘: "主动按买价卖出来的成交量。多了，常被看作卖的人更积极。",
  委买: "现在排队等着买的委托量有多少。",
  委卖: "现在排队等着卖的委托量有多少。",
  委差: "想买的量减去想卖的量。正数说明买的人排队更多，负数相反。",
  委比: "买卖排队力量的对比。越接近 +100% 买盘越强，越接近 −100% 卖盘越强。",
  盘后委买: "收盘后那段固定价格交易里，还有多少人挂单想买。",
  盘后量: "收盘后那段时间成交了多少。",
  盘后额: "收盘后那段时间成交了多少钱。",
  近1日: "最近 1 个交易日涨了还是跌了多少。",
  "3日": "最近 3 个交易日累计涨跌多少。",
  近3日: "最近 3 个交易日累计涨跌多少。",
  "5日": "最近 5 个交易日累计涨跌多少。",
  "10日": "最近 10 个交易日累计涨跌多少。",
  "20日": "最近 20 个交易日累计涨跌多少（大约一个月）。",
  "60日": "最近 60 个交易日累计涨跌多少（大约三个月）。",
  近半年: "最近大约半年累计涨跌多少。",
  近1年: "最近大约一年累计涨跌多少。",
  今年: "从今年开年到现在，累计涨跌多少。",
  "52周最高": "过去一年里出现过的最高价（已按分红送股等做过前复权调整）。",
  "52周最低": "过去一年里出现过的最低价（已按分红送股等做过前复权调整）。",
  历史最高: "上市以来出现过的最高价（前复权后，方便和现在价格对比）。",
  历史最低: "上市以来出现过的最低价（前复权后，方便和现在价格对比）。",
  "市盈率(动)": "用现在市值去除以“预计今年能赚多少钱”。越低通常越便宜，但还要看行业和增长。",
  "市盈率(静)": "用现在市值去除以“去年已经赚到的钱”。看历史盈利贵不贵。",
  "市盈率(TTM)": "用现在市值去除以“最近四个季度一共赚了多少”。看最近一年盈利贵不贵。",
  市净率: "股价相对公司账面净资产贵不贵。数字越小，相对净资产越便宜。",
  "市销率(TTM)": "用现在市值去除以最近一年的销售收入。适合看还没稳定赚钱、但收入很重要的公司。",
  每股收益: "摊到每一股上，公司最近赚了多少钱。",
  每股净资产: "摊到每一股上，公司账面上有多少净资产。",
  净资产收益率: "公司用股东的钱，一年大概能赚回百分之几。越高通常说明赚钱能力越强。",
  "股息(TTM)": "最近一年，平均每股大概分了多少红（税前，仅供参考）。",
  股息率: "按现在股价算，分红收益率大概多少。比如 3%，相当于股价里约有 3% 来自分红。",
  净利增速: "净利润比去年同期增长了多少。正数是赚得更多，负数是赚得更少。",
  营收增速: "销售收入比去年同期增长了多少。",
  总股本: "公司一共发行了多少股。",
  流通股: "现在能在市场上买卖的股份有多少。",
  自由流通股: "去掉大股东等不太容易拿出来卖的股份后，真正好流通的股份大概有多少。",
  总市值: "按现价算，整家公司值多少钱。",
  流通市值: "按现价算，能流通的那部分股份值多少钱。",
  自由流通市值: "按现价算，真正好流通的那部分股份值多少钱。",
  发行股本: "发行或披露口径下的股本数量。",
  注册资本: "工商登记里写的注册资本。",
  纳入时间: "这只股票被放进当前这个申万行业分类的时间。",
  上市时间: "这只股票正式上市交易的日子。",
};

function metricTip(label) {
  return METRIC_TIPS[label] || "";
}

function metricCell([label, value, cls = ""]) {
  const tip = metricTip(label);
  const tipAttr = tip ? ` data-tip="${escapeHtml(tip)}"` : "";
  const tipClass = tip ? " has-tip" : "";
  const tipBtn = tip
    ? ` role="button" tabindex="0" aria-expanded="false" aria-label="${escapeHtml(label)}：查看指标说明"`
    : "";
  return `
    <div class="stat-cell${tipClass}"${tipAttr}${tipBtn}>
      <span class="detail-label">${escapeHtml(label)}</span>
      <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
    </div>`;
}

function metricTipLayer() {
  let el = document.getElementById("metricTipFloat");
  if (!el) {
    el = document.createElement("div");
    el.id = "metricTipFloat";
    el.className = "metric-tip-float hidden";
    el.setAttribute("role", "tooltip");
    document.body.appendChild(el);
  }
  return el;
}

function hideMetricTipLayer() {
  const el = document.getElementById("metricTipFloat");
  if (!el) return;
  el.classList.add("hidden");
  el.textContent = "";
}

function placeMetricTip(cell) {
  const text = cell?.getAttribute("data-tip") || "";
  if (!text) {
    hideMetricTipLayer();
    return;
  }
  const layer = metricTipLayer();
  layer.textContent = text;
  layer.classList.remove("hidden");
  layer.style.left = "0px";
  layer.style.top = "0px";
  const rect = cell.getBoundingClientRect();
  const tip = layer.getBoundingClientRect();
  const pad = 8;
  let left = rect.left;
  let top = rect.bottom + 6;
  if (left + tip.width > window.innerWidth - pad) {
    left = rect.right - tip.width;
  }
  left = Math.min(Math.max(pad, left), window.innerWidth - tip.width - pad);
  if (top + tip.height > window.innerHeight - pad) {
    top = rect.top - tip.height - 6;
  }
  top = Math.min(Math.max(pad, top), window.innerHeight - tip.height - pad);
  layer.style.left = `${Math.round(left)}px`;
  layer.style.top = `${Math.round(top)}px`;
}

function closeMetricTips(except = null) {
  document.querySelectorAll(".stat-cell.has-tip.is-tip-open").forEach((el) => {
    if (except && el === except) return;
    el.classList.remove("is-tip-open");
    el.setAttribute("aria-expanded", "false");
  });
  if (!except) hideMetricTipLayer();
}

function setupMetricTips() {
  const root = document.querySelector(".company-hero");
  if (!root || root.dataset.tipBound === "1") return;
  root.dataset.tipBound = "1";

  const syncOpenTip = () => {
    const open = root.querySelector(".stat-cell.has-tip.is-tip-open");
    if (open) placeMetricTip(open);
    else hideMetricTipLayer();
  };

  root.addEventListener("click", (event) => {
    const cell = event.target.closest(".stat-cell.has-tip");
    if (!cell || !root.contains(cell)) return;
    event.preventDefault();
    const opening = !cell.classList.contains("is-tip-open");
    closeMetricTips(opening ? cell : null);
    cell.classList.toggle("is-tip-open", opening);
    cell.setAttribute("aria-expanded", opening ? "true" : "false");
    if (opening) placeMetricTip(cell);
    else hideMetricTipLayer();
  });

  root.addEventListener("keydown", (event) => {
    const cell = event.target.closest(".stat-cell.has-tip");
    if (!cell || !root.contains(cell)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    cell.click();
  });

  root.addEventListener("scroll", syncOpenTip, { passive: true });
  window.addEventListener("resize", syncOpenTip);

  document.addEventListener("click", (event) => {
    if (event.target.closest(".stat-cell.has-tip")) return;
    if (event.target.closest(".metric-tip-float")) return;
    closeMetricTips();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMetricTips();
  });
}

function renderMetricSection(title, items, { gridClass = "" } = {}) {
  const cells = items.filter(([, v]) => displayValue(v) !== "-");
  if (!cells.length) return "";
  const gridCls = ["company-metrics", gridClass].filter(Boolean).join(" ");
  return `
    <section class="metrics-section">
      <h4 class="metrics-section-title">${escapeHtml(title)}</h4>
      <div class="${gridCls}">
        ${cells.map(metricCell).join("")}
      </div>
    </section>`;
}

function renderInlineMetricRows(title, rows, { highlightFirst = false, rowOpts = [] } = {}) {
  const parts = rows
    .map((items) => items.filter(([, v]) => displayValue(v) !== "-"))
    .filter((items) => items.length);
  if (!parts.length) return "";
  return `
    <section class="metrics-section">
      <h4 class="metrics-section-title">${escapeHtml(title)}</h4>
      ${parts
        .map((items, idx) => {
          const opts = rowOpts[idx] || {};
          const rowCls = [
            "company-metrics",
            opts.class || "metrics-inline-row",
            highlightFirst && idx === 0 ? "metrics-highlight-row" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const style = ` style="--metrics-cols:${opts.cols || items.length}"`;
          return `<div class="${rowCls}"${style}>${items.map(metricCell).join("")}</div>`;
        })
        .join("")}
    </section>`;
}

function renderMetrics(stock) {
  const panels = els.metricsPanels || els.metricsGrid;
  if (!panels) return;

  const mcap =
    stock.total_market_cap ||
    (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : "");

  const periodNear = [
    ["近3日", stock.change_3d, changeClass(stock.change_3d)],
    ["5日", stock.change_5d, changeClass(stock.change_5d)],
    ["10日", stock.change_10d, changeClass(stock.change_10d)],
    ["20日", stock.change_20d, changeClass(stock.change_20d)],
  ].filter(([, v]) => displayValue(v) !== "-");

  const periodFar = [
    ["60日", stock.change_60d, changeClass(stock.change_60d)],
    ["近半年", stock.change_half_year, changeClass(stock.change_half_year)],
    ["近1年", stock.change_1y, changeClass(stock.change_1y)],
    ["今年", stock.change_ytd, changeClass(stock.change_ytd)],
  ].filter(([, v]) => displayValue(v) !== "-");

  const weekRange = [
    ["52周最高", stock.high_52w],
    ["52周最低", stock.low_52w],
  ].filter(([, v]) => displayValue(v) !== "-");

  const allRange = [
    ["历史最高", stock.high_all],
    ["历史最低", stock.low_all],
  ].filter(([, v]) => displayValue(v) !== "-");

  const daySection = renderInlineMetricRows("当日行情", [
    [
      ["最新", stock.price],
      ["涨幅", stock.change_1d, changeClass(stock.change_1d)],
      ["涨跌", stock.change_amt, changeClass(stock.change_amt)],
    ],
    [
      ["今开", stock.open],
      ["昨收", stock.prev_close],
      ["均价", stock.avg_price],
    ],
    [
      ["最低", stock.low],
      ["最高", stock.high],
      ["振幅", stock.amplitude],
    ],
    [
      ["涨停", stock.limit_up],
      ["跌停", stock.limit_down],
      ["实体涨幅", stock.solid_change, changeClass(stock.solid_change)],
    ],
    [
      ["总手", stock.volume],
      ["金额", stock.amount],
      ["现手", stock.current_volume],
    ],
    [
      ["换手", stock.turnover],
      ["换手(实)", stock.turnover_real],
      ["量比", stock.volume_ratio],
    ],
    [
      ["外盘", stock.outer_vol],
      ["内盘", stock.inner_vol],
    ],
    [
      ["委买", stock.bid_vol],
      ["委卖", stock.ask_vol],
      ["委差", stock.bid_ask_diff, changeClass(stock.bid_ask_diff)],
      ["委比", stock.bid_ask_ratio, changeClass(stock.bid_ask_ratio)],
    ],
    [
      ["盘后委买", stock.after_bid],
      ["盘后量", stock.after_volume],
      ["盘后额", stock.after_amount],
    ],
  ], { highlightFirst: true });

  const periodSection = renderInlineMetricRows("区间涨幅", [
    periodNear,
    periodFar,
    weekRange,
    allRange,
  ]);

  const valuationSection = renderInlineMetricRows("估值与每股", [
    [
      ["市盈率(动)", stock.pe],
      ["市盈率(静)", stock.pe_static],
      ["市盈率(TTM)", stock.pe_ttm],
    ],
    [
      ["市净率", stock.pb],
      ["每股净资产", stock.bvps],
      ["净资产收益率", stock.roe],
    ],
    [
      ["市销率(TTM)", stock.ps_ttm],
    ],
    [
      ["股息(TTM)", stock.dividend_ttm],
      ["股息率", stock.dividend_yield],
      ["每股收益", stock.eps],
    ],
    [
      ["净利增速", stock.profit_growth || stock.profit_yoy],
      ["营收增速", stock.revenue_growth || stock.revenue_yoy],
    ],
  ]);

  const capitalSection = renderInlineMetricRows("股本与市值", [
    [
      ["上市时间", stock.list_date],
      ["注册资本", stock.registered_capital],
      ["发行股本", stock.issued_shares],
    ],
    [
      ["总股本", stock.total_shares],
      ["流通股", stock.float_shares],
      ["自由流通股", stock.free_float_shares],
    ],
    [
      ["总市值", mcap],
      ["流通市值", stock.float_market_cap],
      ["自由流通市值", stock.free_float_market_cap],
    ],
  ]);

  const html = [
    daySection,
    periodSection,
    valuationSection,
    capitalSection,
  ]
    .filter(Boolean)
    .join("");

  panels.innerHTML = html || `<p class="muted">暂无指标数据</p>`;
}

function applyStock(stock, industryMeta = {}) {
  const displayName = stock.name || nameHint || code;
  stockDisplayName = displayName;
  document.title = `${displayName} · 公司详情`;
  els.pageTitle.textContent = displayName;
  els.companyName.textContent = displayName;

  const codeText = stock.full_code || stock.code || code;
  if (els.companyCodeChip) {
    els.companyCodeChip.textContent = codeText || "";
    els.companyCodeChip.hidden = !codeText;
  }

  const breadcrumbParts = [
    industryMeta.l1_name,
    industryMeta.l2_name,
    industryMeta.name || industryMeta.l3_name,
  ].filter(Boolean);
  els.companyBreadcrumb.textContent = breadcrumbParts.length
    ? breadcrumbParts.join(" / ")
    : "公司详情";

  renderMetrics(stock);
}

function cninfoWhy(item) {
  const tab = String(item?.tab || cninfoTab || "fulltext");
  const tabLabel = CNINFO_TAB_LABELS[tab] || "公告";
  const why = String(item?.why || item?.category || "").trim();
  if (tab === "relation" || tab === "supervise") {
    if (!why || why === "公告") return tabLabel;
    if (why === tabLabel || why.startsWith(`${tabLabel} ·`) || why.startsWith(`${tabLabel}·`)) {
      return why;
    }
    return `${tabLabel} · ${why}`;
  }
  return why || tabLabel;
}

function renderCninfoList(items) {
  if (!items.length) {
    return renderNewsList(items, "暂无匹配的巨潮公告");
  }
  return renderNewsList(
    items.map((item) => {
      const why = cninfoWhy(item);
      const summary = String(item.summary || "").trim();
      return {
        ...item,
        why,
        summary: summary && summary !== why && summary !== "公告" ? summary : "",
      };
    }),
    "暂无匹配的巨潮公告"
  );
}

function detectExchangeMarket(stockCode = code) {
  const digits = String(stockCode || "").replace(/\D/g, "");
  if (!digits) return "";
  const c = digits.padStart(6, "0");
  if (/^(60|68|90)/.test(c)) return "sse";
  if (/^(00|30|20)/.test(c)) return "szse";
  if (/^[84]/.test(c) || c.startsWith("92")) return "bse";
  return "";
}

function exchangeTitleText(market = exchangeState.market) {
  return EXCHANGE_MARKET_TITLES[market] || EXCHANGE_MARKET_TITLES[detectExchangeMarket()] || "交易所公告";
}

function exchangeWhy(item) {
  return String(item?.why || item?.category || item?.heading || "").trim()
    || (exchangeTab === "inquiries" ? "问询函" : "公告");
}

function renderExchangeList(items) {
  if (!items.length) {
    return renderNewsList(items, "暂无匹配的交易所公告");
  }
  return renderNewsList(
    items.map((item) => {
      const why = exchangeWhy(item);
      const summary = String(item.summary || "").trim();
      return {
        ...item,
        why,
        summary: summary && summary !== why && summary !== "公告" ? summary : "",
      };
    }),
    "暂无匹配的交易所公告"
  );
}

function renderNewsList(items, emptyText) {
  if (!items.length) {
    return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map((item) => {
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      const extra =
        item.kind === "report" && item.rating
          ? `<span class="news-why">${escapeHtml(item.rating)}</span>`
          : item.why
            ? `<span class="news-why">${escapeHtml(item.why)}</span>`
            : "";
      return `
        <article class="news-item">
          <div class="news-item-meta">
            <time>${escapeHtml(item.published_at || "-")}</time>
            <span>${escapeHtml(item.source || "-")}</span>
            ${extra}
          </div>
          <h3>${titleHtml}</h3>
          <p>${escapeHtml(truncateText(item.summary || ""))}</p>
        </article>
      `;
    })
    .join("");
}

function setMetricsLoading(message = "正在加载指标…") {
  const panels = els.metricsPanels || els.metricsGrid;
  if (panels) {
    panels.innerHTML = `<p class="muted metrics-loading">${escapeHtml(message)}</p>`;
  }
}

function applyHeaderOnly(stock = {}, industryMeta = {}) {
  const displayName = stock.name || nameHint || code;
  stockDisplayName = displayName;
  document.title = `${displayName} · 公司详情`;
  els.pageTitle.textContent = displayName;
  els.companyName.textContent = displayName;

  const codeText = stock.full_code || stock.code || code;
  if (els.companyCodeChip) {
    els.companyCodeChip.textContent = codeText || "";
    els.companyCodeChip.hidden = !codeText;
  }

  const breadcrumbParts = [
    industryMeta.l1_name,
    industryMeta.l2_name,
    industryMeta.name || industryMeta.l3_name,
  ].filter(Boolean);
  els.companyBreadcrumb.textContent = breadcrumbParts.length
    ? breadcrumbParts.join(" / ")
    : "公司详情";
}

function isQuoteReady(stock) {
  // 盘口补全成功后通常至少有今开/昨收或完整涨跌幅字段
  if (!stock || typeof stock !== "object") return false;
  if (stock.quote_ready === true) return true;
  if (stock.quote_ready === false) return false;
  return Boolean(stock.open || stock.prev_close || stock.high || stock.low);
}

async function loadProfile({ silent = false, refresh = false, liveOnly = false } = {}) {
  if (!code) {
    setError("缺少公司代码");
    return null;
  }

  if (!silent) {
    applyHeaderOnly({ code, name: nameHint });
    setMetricsLoading();
  }

  try {
    const qs = new URLSearchParams({ code });
    if (industry) qs.set("industry", industry);
    if (nameHint) qs.set("name", nameHint);
    if (refresh) qs.set("refresh", "1");
    if (liveOnly) qs.set("live", "1");
    const json = await api(`/api/stocks/profile?${qs.toString()}`);
    const data = json.data || {};
    const stock = data.stock || {};
    if (!isQuoteReady(stock)) {
      if (!silent) {
        setMetricsLoading("盘口指标暂不可用，请稍后刷新");
        applyHeaderOnly(stock, data.industry || {});
      }
      return stock;
    }
    applyStock(stock, data.industry || {});
    if (!liveOnly) {
      try {
        sessionStorage.removeItem(`stock:${code}`);
      } catch {
        /* ignore */
      }
    }
    return stock;
  } catch (err) {
    if (!silent) {
      setError(err.message || String(err));
      setMetricsLoading("指标加载失败");
    }
    return null;
  }
}

async function loadOfficialNews() {
  await Promise.all([loadExchange(), loadCninfo(), loadPress()]);
}

async function loadOtherNews() {
  await Promise.all(PLATFORM_HUBS.map((hub) => loadPlatform(hub.id)));
}

async function loadNewsGroup(group = newsGroup, { refresh = false } = {}) {
  if (!code) return;
  if (refresh) newsBootstrapped[group] = true;
  if (group === NEWS_GROUP_OTHER) {
    await loadOtherNews();
  } else {
    await loadOfficialNews();
  }
}

function syncNewsGroupUi() {
  const group = newsGroup;
  if (els.panelNews) {
    els.panelNews.dataset.newsSource = group;
  }
  if (els.newsSourceBar) {
    els.newsSourceBar.querySelectorAll("[data-source]").forEach((btn) => {
      const active = btn.getAttribute("data-source") === group;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  syncNewsHubLayout();
}

function setNewsGroup(nextGroup, { reload = true } = {}) {
  const group = normalizeNewsGroup(nextGroup);
  if (group === newsGroup) return;
  newsGroup = group;
  syncNewsGroupUi();
  if (!reload || activeMainPanel !== "news") return;
  if (!newsBootstrapped[group]) {
    newsBootstrapped[group] = true;
    loadNewsGroup(group, { refresh: false });
  }
}

async function loadAllNews({ refresh = false, group = newsGroup } = {}) {
  if (!code) return;
  if (els.refreshNewsBtn) els.refreshNewsBtn.disabled = true;
  if (refresh) newsBootstrapped[group] = true;
  await loadNewsGroup(group, { refresh });
  if (els.refreshNewsBtn) els.refreshNewsBtn.disabled = false;
}

function emotionDaysParam(days) {
  const n = Number(days);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function emotionDaysLabel(days) {
  const n = emotionDaysParam(days);
  if (!n) return "不限日期";
  return daysLabel(n);
}

function emotionKindLabel(kind) {
  const map = {
    all: "全部",
    news: "新闻",
    reports: "研报",
    notices: "公告",
    margin: "融资融券",
    other: "其他",
    qa: "问董秘",
    meeting: "说明会",
    hot: "热门",
    search: "搜索",
  };
  return map[kind] || kind || "";
}

function emotionSortLabel(sort) {
  const map = { time: "发帖时间", reply: "最新回复", hot: "热门", default: "相关度" };
  return map[sort] || sort || "";
}

function emotionApiQuery(extra = {}) {
  const source = isXqEmotion() ? XQ_EMOTION_SOURCE : isThsEmotion() ? THS_EMOTION_SOURCE : EMOTION_SOURCE;
  const qs = new URLSearchParams({
    code,
    source,
    ...extra,
  });
  return qs;
}

function syncEmotionSourceUi() {
  const source = emotionSource;
  if (els.panelEmotion) {
    els.panelEmotion.dataset.emotionSource = source;
  }
  if (els.emotionSourceBar) {
    els.emotionSourceBar.querySelectorAll("[data-source]").forEach((btn) => {
      const active = btn.getAttribute("data-source") === source;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  if (els.emotionScoresTitle) {
    els.emotionScoresTitle.textContent = isXqEmotion(source)
      ? "社区快照"
      : isThsEmotion(source)
        ? "讨论热度"
        : "千股千评";
  }
  if (els.emotionRankTitle) {
    els.emotionRankTitle.textContent = isXqEmotion(source)
      ? "热股排名"
      : isThsEmotion(source)
        ? "热度排名"
        : "人气排名";
  }
  if (els.emotionPostsTitle) {
    els.emotionPostsTitle.textContent = isXqEmotion(source) ? "讨论帖" : isThsEmotion(source) ? "讨论帖" : "股吧帖子";
  }
  if (els.emotionSearchTitle) {
    els.emotionSearchTitle.textContent = isXqEmotion(source) ? "搜帖" : isThsEmotion(source) ? "讨论搜索" : "股吧搜索";
  }
  if (els.emotionSearchKeyword) {
    els.emotionSearchKeyword.placeholder = isXqEmotion(source)
      ? "关键词搜帖，默认可用公司名"
      : isThsEmotion(source)
        ? "股票名/代码，默认可用公司名"
        : "搜帖，默认可用公司名";
  }
  paintEmotionScores();
  paintEmotionRank();
  paintEmotionPosts();
  paintEmotionSearch();
}

function setEmotionSource(nextSource, { reload = true } = {}) {
  const source = normalizeEmotionSource(nextSource);
  if (source === emotionSource) return;
  closeEmotionDetail();
  emotionSource = source;
  syncEmotionSourceUi();
  syncEmotionHubLayout();
  if (!reload || activeMainPanel !== "emotion") return;
  if (!emotionBootstrapped[source]) {
    emotionBootstrapped[source] = true;
    loadAllEmotion({ refresh: false });
  } else {
    paintEmotionScores();
    paintEmotionRank();
    paintEmotionPosts();
    paintEmotionSearch();
  }
}

function renderEmotionPostList(items, emptyText) {
  if (!items.length) {
    return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map((item) => {
      const postId = String(item.post_id || item.article_id || "").trim();
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const bits = [
        item.published_at || "",
        item.author || item.media_name || "",
        item.comment_count ? `评 ${item.comment_count}` : "",
        item.click_count ? `阅 ${item.click_count}` : "",
        item.like_count ? `赞 ${item.like_count}` : "",
        emotionKindLabel(item.kind),
      ].filter(Boolean);
      const summary = escapeHtml(truncateText(item.summary || item.content || "", 180));
      const external = url
        ? `<a class="emotion-post-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="打开原文">↗</a>`
        : "";
      return `
        <article class="news-item emotion-post-item" data-post-id="${escapeHtml(postId)}" role="button" tabindex="0">
          <div class="news-item-meta">
            ${bits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}
            ${external}
          </div>
          <h3><button type="button" class="emotion-post-title" data-post-id="${escapeHtml(postId)}">${title}</button></h3>
          <p>${summary}</p>
        </article>
      `;
    })
    .join("");
}

function renderEmotionReplyList(items) {
  if (!items.length) {
    return `<p class="muted">暂无评论</p>`;
  }
  return items
    .map((item) => {
      const indent = item.is_child ? ' class="emotion-reply-child"' : "";
      return `
        <article class="news-item emotion-reply-item"${indent}>
          <div class="news-item-meta">
            <time>${escapeHtml(item.published_at || "-")}</time>
            <span>${escapeHtml(item.author || item.media_name || "-")}</span>
            ${item.like_count ? `<span>赞 ${escapeHtml(item.like_count)}</span>` : ""}
          </div>
          <p>${escapeHtml(item.content || item.summary || item.title || "")}</p>
        </article>
      `;
    })
    .join("");
}

function renderEmotionScores(data) {
  if (!data) return `<p class="muted">暂无千股千评数据</p>`;
  const item = Array.isArray(data.items) && data.items.length ? data.items[0] : data;
  const metrics = [
    ["综合得分", item.total_score],
    ["关注指数", item.focus],
    ["排名", item.rank],
    ["排名变化", item.rank_up],
    ["机构参与度", item.org_participate],
    ["收盘价", item.price],
    ["涨跌幅", item.change_rate != null ? `${item.change_rate}%` : ""],
    ["换手率", item.turnover_rate != null ? `${item.turnover_rate}%` : ""],
    ["市盈率", item.pe],
    ["主力成本", item.prime_cost],
    ["看多比例", item.ratio != null ? `${item.ratio}%` : ""],
    ["3日看多", item.ratio_3d != null ? `${item.ratio_3d}%` : ""],
    ["50日看多", item.ratio_50d != null ? `${item.ratio_50d}%` : ""],
  ].filter(([, value]) => value != null && value !== "" && value !== "-");
  if (!metrics.length) {
    return `<p class="muted">${escapeHtml(data.title || data.error || "暂无千股千评数据")}</p>`;
  }
  return `
    <div class="emotion-scores-grid">
      ${metrics
        .map(
          ([label, value]) => `
            <div class="emotion-score-metric">
              <span class="emotion-score-label">${escapeHtml(label)}</span>
              <strong class="emotion-score-value">${escapeHtml(displayValue(value))}</strong>
            </div>
          `
        )
        .join("")}
    </div>
    <p class="muted emotion-score-foot">${escapeHtml(item.published_at || data.trade_date || "")}</p>
  `;
}

function renderEmotionRankList(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    return `<p class="muted">${escapeHtml(data?.error || "暂无人气排名数据")}</p>`;
  }
  return items
    .map((item) => {
      const title = escapeHtml(item.title || `排名 ${item.rank || "-"}`);
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      return `
        <article class="news-item">
          <div class="news-item-meta">
            <time>${escapeHtml(item.published_at || "-")}</time>
            <span>人气</span>
          </div>
          <h3>${titleHtml}</h3>
        </article>
      `;
    })
    .join("");
}

function paintEmotionScores() {
  if (isXqEmotion()) return paintXqEmotionScores();
  if (isThsEmotion()) return paintThsEmotionScores();
  const st = emotionState.scores;
  if (els.emotionScoresMeta) {
    const bits = ["千股千评", st.data?.name || stockDisplayName || code, st.updatedAt || "-"].filter(Boolean);
    els.emotionScoresMeta.textContent = st.loading ? "正在加载千股千评…" : bits.join(" · ");
  }
  if (els.emotionScoresHint) {
    els.emotionScoresHint.textContent = st.loading
      ? "正在从东方财富拉取千股千评…"
      : st.error || (st.data ? st.data.title || "" : "暂无千股千评数据");
  }
  if (!els.emotionScoresContent) return;
  if (st.loading && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="muted">正在加载千股千评…</p>`;
    return;
  }
  if (st.error && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionScoresContent.innerHTML = renderEmotionScores(st.data);
}

function paintEmotionRank() {
  if (isXqEmotion()) return paintXqEmotionRank();
  if (isThsEmotion()) return paintThsEmotionRank();
  const st = emotionState.rank;
  const currentRank = st.data?.rank;
  if (els.emotionRankMeta) {
    const bits = [
      "股吧人气",
      currentRank ? `当前第 ${currentRank} 名` : "",
      st.count ? `${st.count} 条历史` : "",
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionRankMeta.textContent = st.loading ? "正在加载人气排名…" : bits.join(" · ");
  }
  if (els.emotionRankHint) {
    els.emotionRankHint.textContent = st.loading
      ? "正在从东方财富拉取人气排名…"
      : st.error || (st.items.length ? "近 30 个交易日排名" : "暂无人气排名数据");
  }
  if (!els.emotionRankList) return;
  if (st.loading && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="muted">正在加载人气排名…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionRankList.innerHTML = renderEmotionRankList(st.data || { items: st.items, error: st.error });
}

function paintEmotionPosts() {
  if (isXqEmotion()) return paintXqEmotionPosts();
  if (isThsEmotion()) return paintThsEmotionPosts();
  const st = emotionState.posts;
  if (els.emotionPostsMeta) {
    const bits = [
      emotionKindLabel(st.kind),
      emotionSortLabel(st.sort),
      emotionDaysLabel(st.days),
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionPostsMeta.textContent = st.loading ? "正在查询股吧帖子…" : bits.join(" · ");
  }
  if (els.emotionPostsHint) {
    if (st.loading) {
      els.emotionPostsHint.textContent = "正在从东方财富股吧拉取帖子…";
    } else if (st.error) {
      els.emotionPostsHint.textContent = st.error;
    } else if (!st.items.length) {
      els.emotionPostsHint.textContent = "暂无匹配帖子，可换分类、排序或拉长区间";
    } else if (st.total > st.count) {
      els.emotionPostsHint.textContent = `已显示 ${st.count} / 共 ${st.total} 条`;
    } else {
      els.emotionPostsHint.textContent = st.withReplies ? "已附带部分帖子评论" : "点击标题查看正文与评论";
    }
  }
  if (!els.emotionPostsList) return;
  if (st.loading && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="muted">正在查询股吧帖子…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionPostsList.innerHTML = renderEmotionPostList(st.items, "暂无匹配的股吧帖子");
}

function paintEmotionSearch() {
  if (isXqEmotion()) return paintXqEmotionSearch();
  if (isThsEmotion()) return paintThsEmotionSearch();
  const st = emotionState.search;
  if (els.emotionSearchMeta) {
    const bits = [
      st.keyword ? `「${st.keyword}」` : "股吧搜索",
      emotionSortLabel(st.sort),
      emotionDaysLabel(st.days),
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionSearchMeta.textContent = st.loading ? "正在搜索股吧帖…" : bits.join(" · ");
  }
  if (els.emotionSearchHint) {
    if (st.loading) {
      els.emotionSearchHint.textContent = "正在搜索东方财富股吧…";
    } else if (st.error) {
      els.emotionSearchHint.textContent = st.error;
    } else if (!st.keyword) {
      els.emotionSearchHint.textContent = "输入关键词搜索，留空时可用公司名";
    } else if (!st.items.length) {
      els.emotionSearchHint.textContent = "暂无匹配结果，可换关键词或拉长区间";
    } else {
      els.emotionSearchHint.textContent = `关键词「${st.keyword}」`;
    }
  }
  if (!els.emotionSearchList) return;
  if (st.loading && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">正在搜索股吧帖…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  if (!st.keyword && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">输入关键词搜索股吧帖</p>`;
    return;
  }
  els.emotionSearchList.innerHTML = renderEmotionPostList(st.items, "暂无匹配的股吧帖子");
}

function emotionPostsQueryParams() {
  if (isXqEmotion()) return xqEmotionPostsQueryParams();
  if (isThsEmotion()) return thsEmotionPostsQueryParams();
  const days = emotionDaysParam(els.emotionPostsDays?.value);
  return {
    kind: (els.emotionPostsKind?.value || "all").trim(),
    sort: (els.emotionPostsSort?.value || "time").trim(),
    days,
    withReplies: Boolean(els.emotionPostsReplies?.checked),
  };
}

function emotionSearchQueryParams() {
  if (isXqEmotion()) return xqEmotionSearchQueryParams();
  if (isThsEmotion()) return thsEmotionSearchQueryParams();
  const keyword = (els.emotionSearchKeyword?.value || "").trim();
  return {
    keyword: keyword || stockDisplayName || code,
    sort: (els.emotionSearchSort?.value || "time").trim(),
    days: emotionDaysParam(els.emotionSearchDays?.value),
  };
}

async function loadEmotionScores() {
  if (!code) return;
  if (isXqEmotion()) return loadXqEmotionScores();
  if (isThsEmotion()) return loadThsEmotionScores();
  if (emotionState.scores.loading) return;
  emotionState.scores.loading = true;
  emotionState.scores.error = "";
  paintEmotionScores();
  const qs = emotionApiQuery({ channel: "scores" });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    emotionState.scores.data = data;
    emotionState.scores.error = data.error || "";
    emotionState.scores.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionScoresBody) els.emotionScoresBody.scrollTop = 0;
  } catch (err) {
    emotionState.scores.data = null;
    emotionState.scores.error = err.message || String(err);
  } finally {
    emotionState.scores.loading = false;
    paintEmotionScores();
  }
}

async function loadEmotionRank() {
  if (!code) return;
  if (isXqEmotion()) return loadXqEmotionRank();
  if (isThsEmotion()) return loadThsEmotionRank();
  if (emotionState.rank.loading) return;
  emotionState.rank.loading = true;
  emotionState.rank.error = "";
  paintEmotionRank();
  const qs = emotionApiQuery({ channel: "rank" });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    emotionState.rank.data = data;
    emotionState.rank.items = Array.isArray(data.items) ? data.items : [];
    emotionState.rank.count = Number(data.count) || emotionState.rank.items.length;
    emotionState.rank.total = Number(data.total) || emotionState.rank.count;
    emotionState.rank.error = data.error || "";
    emotionState.rank.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionRankBody) els.emotionRankBody.scrollTop = 0;
  } catch (err) {
    emotionState.rank.data = null;
    emotionState.rank.items = [];
    emotionState.rank.count = 0;
    emotionState.rank.total = 0;
    emotionState.rank.error = err.message || String(err);
  } finally {
    emotionState.rank.loading = false;
    paintEmotionRank();
  }
}

async function loadEmotionPosts() {
  if (!code) return;
  if (isXqEmotion()) return loadXqEmotionPosts();
  if (isThsEmotion()) return loadThsEmotionPosts();
  if (emotionState.posts.loading) return;
  const query = emotionPostsQueryParams();
  emotionState.posts.loading = true;
  emotionState.posts.error = "";
  emotionState.posts.kind = query.kind;
  emotionState.posts.sort = query.sort;
  emotionState.posts.days = query.days;
  emotionState.posts.withReplies = query.withReplies;
  if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = true;
  paintEmotionPosts();
  const qs = emotionApiQuery({
    channel: "posts",
    kind: query.kind,
    sort: query.sort,
    max_pages: "3",
    replies: query.withReplies ? "1" : "0",
    days: String(query.days),
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    emotionState.posts.items = Array.isArray(data.items) ? data.items : [];
    emotionState.posts.count = Number(data.count) || emotionState.posts.items.length;
    emotionState.posts.total = Number(data.total) || emotionState.posts.count;
    emotionState.posts.error = data.error || "";
    emotionState.posts.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = 0;
  } catch (err) {
    emotionState.posts.items = [];
    emotionState.posts.count = 0;
    emotionState.posts.total = 0;
    emotionState.posts.error = err.message || String(err);
  } finally {
    emotionState.posts.loading = false;
    if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = false;
    paintEmotionPosts();
  }
}

async function loadEmotionSearch() {
  if (!code) return;
  if (isXqEmotion()) return loadXqEmotionSearch();
  if (isThsEmotion()) return loadThsEmotionSearch();
  if (emotionState.search.loading) return;
  const query = emotionSearchQueryParams();
  if (!query.keyword) {
    emotionState.search.error = "请输入搜索关键词";
    paintEmotionSearch();
    return;
  }
  emotionState.search.loading = true;
  emotionState.search.error = "";
  emotionState.search.keyword = query.keyword;
  emotionState.search.sort = query.sort;
  emotionState.search.days = query.days;
  if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = true;
  paintEmotionSearch();
  const qs = emotionApiQuery({
    channel: "search",
    q: query.keyword,
    sort: query.sort,
    max_pages: "3",
    days: String(query.days),
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    emotionState.search.items = Array.isArray(data.items) ? data.items : [];
    emotionState.search.count = Number(data.count) || emotionState.search.items.length;
    emotionState.search.total = Number(data.total) || emotionState.search.count;
    emotionState.search.error = data.error || "";
    emotionState.search.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionSearchBody) els.emotionSearchBody.scrollTop = 0;
  } catch (err) {
    emotionState.search.items = [];
    emotionState.search.count = 0;
    emotionState.search.total = 0;
    emotionState.search.error = err.message || String(err);
  } finally {
    emotionState.search.loading = false;
    if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = false;
    paintEmotionSearch();
  }
}

async function loadAllEmotion({ refresh = false } = {}) {
  if (!code) return;
  if (els.refreshEmotionBtn) els.refreshEmotionBtn.disabled = true;
  if (refresh) emotionBootstrapped[emotionSource] = true;
  if (isXqEmotion()) {
    await loadXqEmotionAll();
  } else if (isThsEmotion()) {
    await loadThsEmotionAll();
  } else {
    await Promise.all([loadEmotionScores(), loadEmotionRank(), loadEmotionPosts()]);
  }
  if (els.refreshEmotionBtn) els.refreshEmotionBtn.disabled = false;
}

function paintEmotionDetail() {
  if (isXqEmotion()) return paintXqEmotionDetail();
  if (isThsEmotion()) return paintThsEmotionDetail();
  const st = emotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  if (els.emotionDetailTitle) {
    els.emotionDetailTitle.textContent = pack.title || "帖子详情";
  }
  if (els.emotionDetailMeta) {
    const bits = [
      pack.published_at || "",
      pack.author || pack.media_name || "",
      pack.comment_count ? `评 ${pack.comment_count}` : "",
      pack.like_count ? `赞 ${pack.like_count}` : "",
      pack.ip || "",
    ].filter(Boolean);
    els.emotionDetailMeta.textContent = bits.join(" · ");
  }
  if (els.emotionDetailLink) {
    const url = String(pack.url || "").trim();
    if (url) {
      els.emotionDetailLink.href = url;
      els.emotionDetailLink.hidden = false;
    } else {
      els.emotionDetailLink.hidden = true;
    }
  }
  if (els.emotionDetailContent) {
    if (st.loading) {
      els.emotionDetailContent.innerHTML = `<p class="muted">正在加载正文…</p>`;
    } else if (st.error) {
      els.emotionDetailContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    } else {
      const text = String(pack.content || pack.summary || "").trim();
      els.emotionDetailContent.innerHTML = text
        ? `<div class="emotion-detail-text">${escapeHtml(text).replaceAll("\n", "<br>")}</div>`
        : `<p class="muted">暂无正文</p>`;
    }
  }
  const replies = Array.isArray(pack.replies) ? pack.replies : [];
  if (els.emotionDetailReplies) {
    els.emotionDetailReplies.hidden = !replies.length && !pack.replies_error;
  }
  if (els.emotionDetailRepliesTitle) {
    const total = Number(pack.reply_total || pack.reply_count || replies.length || 0);
    els.emotionDetailRepliesTitle.textContent = total ? `评论 (${replies.length}/${total})` : "评论";
  }
  if (els.emotionDetailRepliesList) {
    if (pack.replies_error) {
      els.emotionDetailRepliesList.innerHTML = `<p class="news-error">${escapeHtml(pack.replies_error)}</p>`;
    } else {
      els.emotionDetailRepliesList.innerHTML = renderEmotionReplyList(replies);
    }
  }
}

function setEmotionDetailOpen(open) {
  if (!els.emotionDetail) return;
  els.emotionDetail.classList.toggle("hidden", !open);
  els.emotionDetail.setAttribute("aria-hidden", open ? "false" : "true");
  document.body.classList.toggle("emotion-detail-open", open);
}

async function openEmotionDetail(postId) {
  if (isXqEmotion()) return openXqEmotionDetail(postId);
  if (isThsEmotion()) return openThsEmotionDetail(postId);
  const pid = String(postId || "").trim();
  if (!pid || !code) return;
  emotionState.detail.loading = true;
  emotionState.detail.postId = pid;
  emotionState.detail.pack = null;
  emotionState.detail.error = "";
  setEmotionDetailOpen(true);
  paintEmotionDetail();
  const qs = emotionApiQuery({
    channel: "article",
    post_id: pid,
    replies: "1",
    max_pages: "5",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    emotionState.detail.pack = data;
    emotionState.detail.error = data.error || "";
  } catch (err) {
    emotionState.detail.pack = null;
    emotionState.detail.error = err.message || String(err);
  } finally {
    emotionState.detail.loading = false;
    paintEmotionDetail();
  }
}

function closeEmotionDetail() {
  if (isXqEmotion()) return closeXqEmotionDetail();
  if (isThsEmotion()) return closeThsEmotionDetail();
  emotionState.detail.loading = false;
  emotionState.detail.postId = "";
  emotionState.detail.pack = null;
  emotionState.detail.error = "";
  setEmotionDetailOpen(false);
}

function emotionOpenEls() {
  return document.querySelector('.company-panel[data-panel="emotion"] .emotion-open');
}

function syncEmotionHubLayout() {
  const open = emotionOpenEls();
  if (!open) return;
  const hubs = [...open.querySelectorAll(":scope > .cninfo-hub")];
  const n = hubs.length;
  if (!n) {
    open.style.gridTemplateRows = "";
    return;
  }
  const cols = preferredNewsCols(n);
  const rows = Math.max(1, Math.ceil(n / cols));
  const units = 6;
  open.style.gridTemplateColumns = `repeat(${units}, minmax(0, 1fr))`;
  open.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  hubs.forEach((hub, i) => {
    const lastRowCount = n - cols * (rows - 1);
    const inLastRow = i >= cols * (rows - 1);
    const span = inLastRow && lastRowCount < cols ? units / lastRowCount : units / cols;
    hub.style.gridColumn = `span ${span}`;
  });
}

function setupEmotionBox() {
  if (!els.emotionPostsForm || els.emotionPostsForm.dataset.bound === "1") return;
  els.emotionPostsForm.dataset.bound = "1";

  els.emotionPostsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadEmotionPosts();
  });

  els.emotionSearchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadEmotionSearch();
  });

  const openDetailFromEvent = (event) => {
    const btn = event.target.closest("[data-post-id]");
    if (!btn) return;
    if (event.target.closest("a.emotion-post-link")) return;
    event.preventDefault();
    openEmotionDetail(btn.getAttribute("data-post-id") || "");
  };

  els.emotionPostsList?.addEventListener("click", openDetailFromEvent);
  els.emotionSearchList?.addEventListener("click", openDetailFromEvent);
  els.emotionPostsList?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const item = event.target.closest(".emotion-post-item[data-post-id], .ths-emotion-post-item[data-post-id], .xq-emotion-post-item[data-post-id]");
    if (!item) return;
    event.preventDefault();
    openEmotionDetail(item.getAttribute("data-post-id") || "");
  });
  els.emotionSearchList?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const item = event.target.closest(".emotion-post-item[data-post-id], .ths-emotion-post-item[data-post-id], .xq-emotion-post-item[data-post-id]");
    if (!item) return;
    event.preventDefault();
    openEmotionDetail(item.getAttribute("data-post-id") || "");
  });

  els.emotionDetailClose?.addEventListener("click", closeEmotionDetail);
  els.emotionSourceBar?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-source]");
    if (!btn || !els.emotionSourceBar.contains(btn)) return;
    setEmotionSource(btn.getAttribute("data-source") || "eastmoney");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.emotionDetail?.classList.contains("hidden")) {
      closeEmotionDetail();
    }
  });
}

function thsEmotionApiQuery(extra = {}) {
  return emotionApiQuery(extra);
}

function thsEmotionSortLabel(sort) {
  const map = { hot: "推荐", time: "最新", reply: "回复" };
  return map[sort] || sort || "";
}

function thsEmotionPagesParam(value, fallback = 3) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.min(20, Math.floor(n)) : fallback;
}

function renderThsEmotionScores(data) {
  if (!data) return `<p class="muted">暂无讨论热度数据</p>`;
  const item = Array.isArray(data.items) && data.items.length ? data.items[0] : data;
  const rank = item.rank ?? data.rank;
  const heat = item.heat ?? item.rank_amount ?? data.heat ?? data.rank_amount;
  const change = item.rank_change ?? data.rank_change;
  const metrics = [
    ["讨论排名", rank != null && rank !== "" ? `第 ${rank} 名` : ""],
    ["参与股票", heat != null && heat !== "" ? `${heat} 只` : ""],
    ["排名变动", change != null && change !== "" ? (Number(change) > 0 ? `+${change}` : String(change)) : ""],
    ["板块 ID", item.fid ?? data.fid],
  ].filter(([, value]) => value != null && value !== "" && value !== "-");
  if (!metrics.length) {
    return `<p class="muted">${escapeHtml(data.title || data.error || "暂无讨论热度数据")}</p>`;
  }
  return `
    <div class="emotion-scores-grid">
      ${metrics
        .map(
          ([label, value]) => `
            <div class="emotion-score-metric">
              <span class="emotion-score-label">${escapeHtml(label)}</span>
              <strong class="emotion-score-value">${escapeHtml(displayValue(value))}</strong>
            </div>
          `
        )
        .join("")}
    </div>
    <p class="muted emotion-score-foot">${escapeHtml(item.title || data.title || "")}</p>
  `;
}

function renderThsEmotionRankList(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    return `<p class="muted">${escapeHtml(data?.error || "暂无热度排名数据")}</p>`;
  }
  return items
    .map((item) => {
      const title = escapeHtml(item.title || `排名 ${item.rank || "-"}`);
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      const bits = [
        item.rank != null ? `第 ${item.rank} 名` : "",
        item.heat || item.rank_amount ? `共 ${item.heat || item.rank_amount} 只` : "",
        item.rank_change != null ? `变动 ${Number(item.rank_change) > 0 ? "+" : ""}${item.rank_change}` : "",
      ].filter(Boolean);
      return `
        <article class="news-item">
          <div class="news-item-meta">
            ${bits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}
          </div>
          <h3>${titleHtml}</h3>
        </article>
      `;
    })
    .join("");
}

function renderThsEmotionPostList(items, emptyText) {
  if (!items.length) {
    return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map((item) => {
      const postId = String(item.post_id || item.article_id || "").trim();
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const bits = [
        item.published_at || "",
        item.author || item.media_name || "",
        item.comment_count ? `评 ${item.comment_count}` : "",
        item.like_count ? `赞 ${item.like_count}` : "",
        item.forward_count ? `转 ${item.forward_count}` : "",
        Array.isArray(item.replies) && item.replies.length ? `预览 ${item.replies.length} 评` : "",
      ].filter(Boolean);
      const summary = escapeHtml(truncateText(item.summary || item.content || "", 180));
      const external = url
        ? `<a class="emotion-post-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="打开原文">↗</a>`
        : "";
      return `
        <article class="news-item emotion-post-item ths-emotion-post-item" data-post-id="${escapeHtml(postId)}" role="button" tabindex="0">
          <div class="news-item-meta">
            ${bits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}
            ${external}
          </div>
          <h3><button type="button" class="emotion-post-title" data-post-id="${escapeHtml(postId)}">${title}</button></h3>
          <p>${summary}</p>
        </article>
      `;
    })
    .join("");
}

function findThsEmotionPost(postId) {
  const pid = String(postId || "").trim();
  if (!pid) return null;
  const pools = [thsEmotionState.posts.items, thsEmotionState.search.items];
  for (const items of pools) {
    const hit = items.find((row) => String(row.post_id || row.article_id || "").trim() === pid);
    if (hit) return hit;
  }
  return null;
}

function paintThsEmotionScores() {
  const st = thsEmotionState.scores;
  if (els.emotionScoresMeta) {
    const bits = ["讨论热度", st.data?.name || stockDisplayName || code, st.updatedAt || "-"].filter(Boolean);
    els.emotionScoresMeta.textContent = st.loading ? "正在加载讨论热度…" : bits.join(" · ");
  }
  if (els.emotionScoresHint) {
    els.emotionScoresHint.textContent = st.loading
      ? "正在从同花顺圈子拉取讨论热度…"
      : st.error || (st.data ? st.data.title || "" : "暂无讨论热度数据");
  }
  if (!els.emotionScoresContent) return;
  if (st.loading && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="muted">正在加载讨论热度…</p>`;
    return;
  }
  if (st.error && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionScoresContent.innerHTML = renderThsEmotionScores(st.data);
}

function paintThsEmotionRank() {
  const st = thsEmotionState.rank;
  const currentRank = st.data?.rank;
  if (els.emotionRankMeta) {
    const bits = [
      "同花顺圈子",
      currentRank ? `当前第 ${currentRank} 名` : "",
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionRankMeta.textContent = st.loading ? "正在加载热度排名…" : bits.join(" · ");
  }
  if (els.emotionRankHint) {
    els.emotionRankHint.textContent = st.loading
      ? "正在从同花顺圈子拉取热度排名…"
      : st.error || (st.items.length ? "个股讨论热度快照" : "暂无热度排名数据");
  }
  if (!els.emotionRankList) return;
  if (st.loading && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="muted">正在加载热度排名…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionRankList.innerHTML = renderThsEmotionRankList(st.data || { items: st.items, error: st.error });
}

function paintThsEmotionPosts() {
  const st = thsEmotionState.posts;
  if (els.emotionPostsMeta) {
    const bits = [
      thsEmotionSortLabel(st.sort),
      `${st.maxPages} 页`,
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionPostsMeta.textContent = st.loading ? "正在查询讨论帖…" : bits.join(" · ");
  }
  if (els.emotionPostsHint) {
    if (st.loading) {
      els.emotionPostsHint.textContent = "正在从同花顺圈子拉取讨论帖…";
    } else if (st.error) {
      els.emotionPostsHint.textContent = st.error;
    } else if (!st.items.length) {
      els.emotionPostsHint.textContent = "暂无讨论帖，可换排序或增加页数";
    } else if (st.total > st.count) {
      els.emotionPostsHint.textContent = `已显示 ${st.count} / 共 ${st.total} 条`;
    } else {
      els.emotionPostsHint.textContent = st.withReplies
        ? "已附带部分帖子评论预览"
        : "点击标题查看详情；勾选评论可预览";
    }
  }
  if (!els.emotionPostsList) return;
  if (st.loading && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="muted">正在查询讨论帖…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionPostsList.innerHTML = renderThsEmotionPostList(st.items, "暂无匹配的讨论帖");
}

function paintThsEmotionSearch() {
  const st = thsEmotionState.search;
  if (els.emotionSearchMeta) {
    const bits = [
      st.keyword ? `「${st.keyword}」` : "讨论搜索",
      thsEmotionSortLabel(st.sort),
      `${st.maxPages} 页`,
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionSearchMeta.textContent = st.loading ? "正在搜索讨论帖…" : bits.join(" · ");
  }
  if (els.emotionSearchHint) {
    if (st.loading) {
      els.emotionSearchHint.textContent = "正在搜索同花顺圈子…";
    } else if (st.error) {
      els.emotionSearchHint.textContent = st.error;
    } else if (!st.keyword) {
      els.emotionSearchHint.textContent = "关键词可解析为股票后拉取该股讨论";
    } else if (!st.items.length) {
      els.emotionSearchHint.textContent = "暂无匹配结果，可换关键词";
    } else {
      els.emotionSearchHint.textContent = `关键词「${st.keyword}」`;
    }
  }
  if (!els.emotionSearchList) return;
  if (st.loading && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">正在搜索讨论帖…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  if (!st.keyword && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">输入关键词搜索讨论帖</p>`;
    return;
  }
  els.emotionSearchList.innerHTML = renderThsEmotionPostList(st.items, "暂无匹配的讨论帖");
}

function thsEmotionPostsQueryParams() {
  return {
    sort: (els.emotionPostsSortThs?.value || "hot").trim(),
    maxPages: thsEmotionPagesParam(els.emotionPostsPages?.value, 3),
    withReplies: Boolean(els.emotionPostsReplies?.checked),
  };
}

function thsEmotionSearchQueryParams() {
  const keyword = (els.emotionSearchKeyword?.value || "").trim();
  return {
    keyword: keyword || stockDisplayName || code,
    sort: (els.emotionSearchSortThs?.value || "hot").trim(),
    maxPages: thsEmotionPagesParam(els.emotionSearchPages?.value, 3),
  };
}

function applyThsEmotionPack(pack = {}) {
  const posts = pack.posts && typeof pack.posts === "object" ? pack.posts : pack;
  const scores = pack.scores && typeof pack.scores === "object" ? pack.scores : {};
  const rank = pack.rank && typeof pack.rank === "object" ? pack.rank : {};
  const updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });

  thsEmotionState.scores.data = scores;
  thsEmotionState.scores.error = scores.error || pack.error || "";
  thsEmotionState.scores.updatedAt = updatedAt;

  thsEmotionState.rank.data = rank;
  thsEmotionState.rank.items = Array.isArray(rank.items) ? rank.items : [];
  thsEmotionState.rank.count = Number(rank.count) || thsEmotionState.rank.items.length;
  thsEmotionState.rank.total = Number(rank.total) || thsEmotionState.rank.count;
  thsEmotionState.rank.error = rank.error || "";
  thsEmotionState.rank.updatedAt = updatedAt;

  thsEmotionState.posts.items = Array.isArray(posts.items) ? posts.items : [];
  thsEmotionState.posts.count = Number(posts.count) || thsEmotionState.posts.items.length;
  thsEmotionState.posts.total = Number(posts.total) || thsEmotionState.posts.count;
  thsEmotionState.posts.error = posts.error || "";
  thsEmotionState.posts.updatedAt = updatedAt;
  if (posts.sort) thsEmotionState.posts.sort = posts.sort;
}

async function loadThsEmotionScores() {
  if (!code || thsEmotionState.scores.loading) return;
  thsEmotionState.scores.loading = true;
  thsEmotionState.scores.error = "";
  paintThsEmotionScores();
  const qs = thsEmotionApiQuery({ channel: "scores" });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    thsEmotionState.scores.data = data;
    thsEmotionState.scores.error = data.error || "";
    thsEmotionState.scores.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionScoresBody) els.emotionScoresBody.scrollTop = 0;
  } catch (err) {
    thsEmotionState.scores.data = null;
    thsEmotionState.scores.error = err.message || String(err);
  } finally {
    thsEmotionState.scores.loading = false;
    paintThsEmotionScores();
  }
}

async function loadThsEmotionRank() {
  if (!code || thsEmotionState.rank.loading) return;
  thsEmotionState.rank.loading = true;
  thsEmotionState.rank.error = "";
  paintThsEmotionRank();
  const qs = thsEmotionApiQuery({ channel: "rank" });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    thsEmotionState.rank.data = data;
    thsEmotionState.rank.items = Array.isArray(data.items) ? data.items : [];
    thsEmotionState.rank.count = Number(data.count) || thsEmotionState.rank.items.length;
    thsEmotionState.rank.total = Number(data.total) || thsEmotionState.rank.count;
    thsEmotionState.rank.error = data.error || "";
    thsEmotionState.rank.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionRankBody) els.emotionRankBody.scrollTop = 0;
  } catch (err) {
    thsEmotionState.rank.data = null;
    thsEmotionState.rank.items = [];
    thsEmotionState.rank.count = 0;
    thsEmotionState.rank.total = 0;
    thsEmotionState.rank.error = err.message || String(err);
  } finally {
    thsEmotionState.rank.loading = false;
    paintThsEmotionRank();
  }
}

async function loadThsEmotionPosts() {
  if (!code || thsEmotionState.posts.loading) return;
  const query = thsEmotionPostsQueryParams();
  thsEmotionState.posts.loading = true;
  thsEmotionState.posts.error = "";
  thsEmotionState.posts.sort = query.sort;
  thsEmotionState.posts.maxPages = query.maxPages;
  thsEmotionState.posts.withReplies = query.withReplies;
  if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = true;
  paintThsEmotionPosts();
  const qs = thsEmotionApiQuery({
    channel: "posts",
    sort: query.sort,
    max_pages: String(query.maxPages),
    replies: query.withReplies ? "1" : "0",
    kind: "user",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    thsEmotionState.posts.items = Array.isArray(data.items) ? data.items : [];
    thsEmotionState.posts.count = Number(data.count) || thsEmotionState.posts.items.length;
    thsEmotionState.posts.total = Number(data.total) || thsEmotionState.posts.count;
    thsEmotionState.posts.error = data.error || "";
    thsEmotionState.posts.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = 0;
  } catch (err) {
    thsEmotionState.posts.items = [];
    thsEmotionState.posts.count = 0;
    thsEmotionState.posts.total = 0;
    thsEmotionState.posts.error = err.message || String(err);
  } finally {
    thsEmotionState.posts.loading = false;
    if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = false;
    paintThsEmotionPosts();
  }
}

async function loadThsEmotionSearch() {
  if (!code || thsEmotionState.search.loading) return;
  const query = thsEmotionSearchQueryParams();
  if (!query.keyword) {
    thsEmotionState.search.error = "请输入搜索关键词";
    paintThsEmotionSearch();
    return;
  }
  thsEmotionState.search.loading = true;
  thsEmotionState.search.error = "";
  thsEmotionState.search.keyword = query.keyword;
  thsEmotionState.search.sort = query.sort;
  thsEmotionState.search.maxPages = query.maxPages;
  if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = true;
  paintThsEmotionSearch();
  const qs = thsEmotionApiQuery({
    channel: "search",
    q: query.keyword,
    sort: query.sort,
    max_pages: String(query.maxPages),
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    thsEmotionState.search.items = Array.isArray(data.items) ? data.items : [];
    thsEmotionState.search.count = Number(data.count) || thsEmotionState.search.items.length;
    thsEmotionState.search.total = Number(data.total) || thsEmotionState.search.count;
    thsEmotionState.search.error = data.error || "";
    thsEmotionState.search.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionSearchBody) els.emotionSearchBody.scrollTop = 0;
  } catch (err) {
    thsEmotionState.search.items = [];
    thsEmotionState.search.count = 0;
    thsEmotionState.search.total = 0;
    thsEmotionState.search.error = err.message || String(err);
  } finally {
    thsEmotionState.search.loading = false;
    if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = false;
    paintThsEmotionSearch();
  }
}

async function loadThsEmotionAll() {
  if (!code) return;
  const query = thsEmotionPostsQueryParams();
  thsEmotionState.scores.loading = true;
  thsEmotionState.rank.loading = true;
  thsEmotionState.posts.loading = true;
  thsEmotionState.scores.error = "";
  thsEmotionState.rank.error = "";
  thsEmotionState.posts.error = "";
  thsEmotionState.posts.sort = query.sort;
  thsEmotionState.posts.maxPages = query.maxPages;
  thsEmotionState.posts.withReplies = query.withReplies;
  paintThsEmotionScores();
  paintThsEmotionRank();
  paintThsEmotionPosts();
  const qs = thsEmotionApiQuery({
    channel: "all",
    sort: query.sort,
    max_pages: String(query.maxPages),
    replies: query.withReplies ? "1" : "0",
    kind: "user",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    applyThsEmotionPack(json.data || {});
    if (els.emotionScoresBody) els.emotionScoresBody.scrollTop = 0;
    if (els.emotionRankBody) els.emotionRankBody.scrollTop = 0;
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = 0;
  } catch (err) {
    const message = err.message || String(err);
    thsEmotionState.scores.data = null;
    thsEmotionState.rank.data = null;
    thsEmotionState.posts.items = [];
    thsEmotionState.scores.error = message;
    thsEmotionState.rank.error = message;
    thsEmotionState.posts.error = message;
  } finally {
    thsEmotionState.scores.loading = false;
    thsEmotionState.rank.loading = false;
    thsEmotionState.posts.loading = false;
    paintThsEmotionScores();
    paintThsEmotionRank();
    paintThsEmotionPosts();
  }
}

function paintThsEmotionDetail() {
  const st = thsEmotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  if (els.emotionDetailTitle) {
    els.emotionDetailTitle.textContent = pack.title || "讨论帖详情";
  }
  if (els.emotionDetailMeta) {
    const bits = [
      pack.published_at || "",
      pack.author || pack.media_name || "",
      pack.comment_count ? `评 ${pack.comment_count}` : "",
      pack.like_count ? `赞 ${pack.like_count}` : "",
      pack.forward_count ? `转 ${pack.forward_count}` : "",
    ].filter(Boolean);
    els.emotionDetailMeta.textContent = bits.join(" · ");
  }
  if (els.emotionDetailLink) {
    const url = String(pack.url || "").trim();
    if (url) {
      els.emotionDetailLink.href = url;
      els.emotionDetailLink.hidden = false;
    } else {
      els.emotionDetailLink.hidden = true;
    }
  }
  if (els.emotionDetailContent) {
    if (st.loading) {
      els.emotionDetailContent.innerHTML = `<p class="muted">正在加载详情…</p>`;
    } else if (st.error) {
      els.emotionDetailContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    } else {
      const text = String(pack.content || pack.summary || "").trim();
      els.emotionDetailContent.innerHTML = text
        ? `<div class="emotion-detail-text">${escapeHtml(text).replaceAll("\n", "<br>")}</div>`
        : `<p class="muted">暂无正文</p>`;
    }
  }
  const replies = Array.isArray(pack.replies) ? pack.replies : [];
  if (els.emotionDetailReplies) {
    els.emotionDetailReplies.hidden = !replies.length;
  }
  if (els.emotionDetailRepliesTitle) {
    els.emotionDetailRepliesTitle.textContent = replies.length ? `评论预览 (${replies.length})` : "评论预览";
  }
  if (els.emotionDetailRepliesList) {
    els.emotionDetailRepliesList.innerHTML = renderEmotionReplyList(replies);
  }
}

async function openThsEmotionDetail(postId) {
  const pid = String(postId || "").trim();
  if (!pid || !code) return;
  thsEmotionState.detail.loading = true;
  thsEmotionState.detail.postId = pid;
  thsEmotionState.detail.pack = null;
  thsEmotionState.detail.error = "";
  setEmotionDetailOpen(true);
  paintThsEmotionDetail();

  const cached = findThsEmotionPost(pid);
  if (cached) {
    thsEmotionState.detail.pack = cached;
    thsEmotionState.detail.loading = false;
    paintThsEmotionDetail();
    return;
  }

  const query = thsEmotionPostsQueryParams();
  const qs = thsEmotionApiQuery({
    channel: "posts",
    sort: query.sort,
    max_pages: String(query.maxPages),
    replies: "1",
    kind: "user",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    const items = Array.isArray(data.items) ? data.items : [];
    const hit = items.find((row) => String(row.post_id || row.article_id || "").trim() === pid);
    if (hit) {
      thsEmotionState.detail.pack = hit;
    } else {
      thsEmotionState.detail.error = "未找到该讨论帖";
    }
  } catch (err) {
    thsEmotionState.detail.error = err.message || String(err);
  } finally {
    thsEmotionState.detail.loading = false;
    paintThsEmotionDetail();
  }
}

function closeThsEmotionDetail() {
  thsEmotionState.detail.loading = false;
  thsEmotionState.detail.postId = "";
  thsEmotionState.detail.pack = null;
  thsEmotionState.detail.error = "";
  setEmotionDetailOpen(false);
}

function xqEmotionSortLabel(sort) {
  const map = { time: "最新", alpha: "热门", reply: "评论" };
  return map[sort] || sort || "";
}

function xqEmotionKindLabel(kind) {
  const map = { user: "讨论", trans: "交易", all: "全部" };
  return map[kind] || kind || "";
}

function xqEmotionMarketLabel(market) {
  const map = { cn: "沪深", hk: "港股", us: "美股", global: "全球", follow: "关注" };
  return map[market] || market || "";
}

function xqEmotionPagesParam(value, fallback = 3) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.min(20, Math.floor(n)) : fallback;
}

function renderXqEmotionScores(data) {
  if (!data) return `<p class="muted">暂无社区快照</p>`;
  const item = Array.isArray(data.items) && data.items.length ? data.items[0] : data;
  const metrics = [
    ["关注人数", item.follower_count != null ? displayValue(item.follower_count) : ""],
    ["现价", item.price],
    ["涨跌幅", item.change_pct != null ? `${item.change_pct}%` : ""],
    ["换手率", item.turnover_rate != null ? `${item.turnover_rate}%` : ""],
    ["市值", item.market_capital],
    ["成交量", item.volume],
  ].filter(([, value]) => value != null && value !== "" && value !== "-");
  const hotUsers = Array.isArray(data.hot_users) ? data.hot_users : [];
  const popstocks = Array.isArray(data.popstocks) ? data.popstocks : [];
  let html = "";
  if (metrics.length) {
    html += `
      <div class="emotion-scores-grid">
        ${metrics
          .map(
            ([label, value]) => `
              <div class="emotion-score-metric">
                <span class="emotion-score-label">${escapeHtml(label)}</span>
                <strong class="emotion-score-value">${escapeHtml(displayValue(value))}</strong>
              </div>
            `
          )
          .join("")}
      </div>`;
  }
  if (hotUsers.length) {
    html += `<div class="emotion-xq-subsection"><h4 class="emotion-xq-subtitle">热门讨论用户</h4><ul class="emotion-xq-mini-list">`;
    html += hotUsers
      .slice(0, 6)
      .map((user) => {
        const name = escapeHtml(user.author || user.media_name || user.title || "-");
        const url = String(user.url || "").trim();
        const fans = user.followers_count ? ` · 粉丝 ${displayValue(user.followers_count)}` : "";
        return url
          ? `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${name}${escapeHtml(fans)}</a></li>`
          : `<li>${name}${escapeHtml(fans)}</li>`;
      })
      .join("");
    html += `</ul></div>`;
  }
  if (popstocks.length) {
    html += `<div class="emotion-xq-subsection"><h4 class="emotion-xq-subtitle">粉丝同时关注</h4><ul class="emotion-xq-mini-list">`;
    html += popstocks
      .slice(0, 6)
      .map((stock) => {
        const title = escapeHtml(stock.title || stock.name || stock.code || "-");
        const url = String(stock.url || "").trim();
        const change =
          stock.change_pct != null ? ` · ${Number(stock.change_pct) > 0 ? "+" : ""}${stock.change_pct}%` : "";
        return url
          ? `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}${escapeHtml(change)}</a></li>`
          : `<li>${title}${escapeHtml(change)}</li>`;
      })
      .join("");
    html += `</ul></div>`;
  }
  if (!html) {
    return `<p class="muted">${escapeHtml(data.title || data.error || "暂无社区快照")}</p>`;
  }
  html += `<p class="muted emotion-score-foot">${escapeHtml(item.published_at || data.trade_date || data.title || "")}</p>`;
  return html;
}

function renderXqEmotionRankList(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    const title = data?.title || data?.error || "暂无热股排名数据";
    return `<p class="muted">${escapeHtml(title)}</p>`;
  }
  return items
    .map((item) => {
      const title = escapeHtml(item.title || `排名 ${item.rank || "-"}`);
      const url = String(item.url || "").trim();
      const titleHtml = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : `<span>${title}</span>`;
      const bits = [
        item.rank != null ? `第 ${item.rank} 名` : "",
        item.value != null ? `热度 ${item.value}` : "",
        item.rank_change != null ? `变动 ${Number(item.rank_change) > 0 ? "+" : ""}${item.rank_change}` : "",
        item.change_pct != null ? `${Number(item.change_pct) > 0 ? "+" : ""}${item.change_pct}%` : "",
      ].filter(Boolean);
      return `
        <article class="news-item">
          <div class="news-item-meta">
            ${bits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}
          </div>
          <h3>${titleHtml}</h3>
        </article>
      `;
    })
    .join("");
}

function renderXqEmotionPostList(items, emptyText) {
  if (!items.length) {
    return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  }
  return items
    .map((item) => {
      const postId = String(item.post_id || item.article_id || "").trim();
      const title = escapeHtml(item.title || "无标题");
      const url = String(item.url || "").trim();
      const bits = [
        item.published_at || "",
        item.author || item.media_name || "",
        item.comment_count ? `评 ${item.comment_count}` : "",
        item.like_count ? `赞 ${item.like_count}` : "",
        item.retweet_count ? `转 ${item.retweet_count}` : "",
        Array.isArray(item.replies) && item.replies.length ? `预览 ${item.replies.length} 评` : "",
      ].filter(Boolean);
      const summary = escapeHtml(truncateText(item.summary || item.content || "", 180));
      const external = url
        ? `<a class="emotion-post-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="打开原文">↗</a>`
        : "";
      return `
        <article class="news-item emotion-post-item xq-emotion-post-item" data-post-id="${escapeHtml(postId)}" role="button" tabindex="0">
          <div class="news-item-meta">
            ${bits.map((bit) => `<span>${escapeHtml(bit)}</span>`).join("")}
            ${external}
          </div>
          <h3><button type="button" class="emotion-post-title" data-post-id="${escapeHtml(postId)}">${title}</button></h3>
          <p>${summary}</p>
        </article>
      `;
    })
    .join("");
}

function xqEmotionPostsQueryParams() {
  return {
    kind: (document.getElementById("emotionPostsKindXq")?.value || "user").trim(),
    sort: (document.getElementById("emotionPostsSortXq")?.value || "time").trim(),
    days: emotionDaysParam(document.getElementById("emotionPostsDaysXq")?.value),
    maxPages: xqEmotionPagesParam(document.getElementById("emotionPostsPagesXq")?.value, 3),
    market: (document.getElementById("emotionPostsMarketXq")?.value || "cn").trim(),
    withReplies: Boolean(els.emotionPostsReplies?.checked),
  };
}

function xqEmotionSearchQueryParams() {
  const keyword = (els.emotionSearchKeyword?.value || "").trim();
  return {
    keyword: keyword || stockDisplayName || code,
    sort: (document.getElementById("emotionSearchSortXq")?.value || "time").trim(),
    days: emotionDaysParam(document.getElementById("emotionSearchDaysXq")?.value),
    maxPages: xqEmotionPagesParam(document.getElementById("emotionSearchPagesXq")?.value, 3),
  };
}

function applyXqEmotionPack(pack = {}) {
  const posts = pack.posts && typeof pack.posts === "object" ? pack.posts : pack;
  const scores = pack.scores && typeof pack.scores === "object" ? pack.scores : {};
  const rank = pack.rank && typeof pack.rank === "object" ? pack.rank : {};
  const updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });

  xqEmotionState.scores.data = scores;
  xqEmotionState.scores.error = scores.error || pack.error || "";
  xqEmotionState.scores.updatedAt = updatedAt;

  xqEmotionState.rank.data = rank;
  xqEmotionState.rank.items = Array.isArray(rank.items) ? rank.items : rank.current ? [rank.current] : [];
  xqEmotionState.rank.count = Number(rank.count) || xqEmotionState.rank.items.length;
  xqEmotionState.rank.total = Number(rank.total) || xqEmotionState.rank.count;
  xqEmotionState.rank.error = rank.error || "";
  xqEmotionState.rank.market = rank.market || xqEmotionState.rank.market;
  xqEmotionState.rank.updatedAt = updatedAt;

  xqEmotionState.posts.items = Array.isArray(posts.items) ? posts.items : [];
  xqEmotionState.posts.count = Number(posts.count) || xqEmotionState.posts.items.length;
  xqEmotionState.posts.total = Number(posts.total) || xqEmotionState.posts.count;
  xqEmotionState.posts.error = posts.error || "";
  xqEmotionState.posts.updatedAt = updatedAt;
  if (posts.kind) xqEmotionState.posts.kind = posts.kind;
  if (posts.sort) xqEmotionState.posts.sort = posts.sort;
}

function paintXqEmotionScores() {
  const st = xqEmotionState.scores;
  if (els.emotionScoresMeta) {
    const bits = ["社区快照", st.data?.name || stockDisplayName || code, st.updatedAt || "-"].filter(Boolean);
    els.emotionScoresMeta.textContent = st.loading ? "正在加载社区快照…" : bits.join(" · ");
  }
  if (els.emotionScoresHint) {
    els.emotionScoresHint.textContent = st.loading
      ? "正在从雪球拉取社区快照…"
      : st.error || (st.data ? st.data.title || "" : "暂无社区快照");
  }
  if (!els.emotionScoresContent) return;
  if (st.loading && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="muted">正在加载社区快照…</p>`;
    return;
  }
  if (st.error && !st.data) {
    els.emotionScoresContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionScoresContent.innerHTML = renderXqEmotionScores(st.data);
}

function paintXqEmotionRank() {
  const st = xqEmotionState.rank;
  const currentRank = st.data?.rank;
  const marketLabel = xqEmotionMarketLabel(st.data?.market_label || st.market);
  if (els.emotionRankMeta) {
    const bits = [
      "雪球热股",
      marketLabel,
      currentRank ? `当前第 ${currentRank} 名` : "",
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionRankMeta.textContent = st.loading ? "正在加载热股排名…" : bits.join(" · ");
  }
  if (els.emotionRankHint) {
    els.emotionRankHint.textContent = st.loading
      ? "正在从雪球拉取热股排名…"
      : st.error || (st.data?.title || (st.items.length ? "个股热股榜名次" : "暂无热股排名数据"));
  }
  if (!els.emotionRankList) return;
  if (st.loading && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="muted">正在加载热股排名…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionRankList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionRankList.innerHTML = renderXqEmotionRankList(st.data || { items: st.items, error: st.error });
}

function paintXqEmotionPosts() {
  const st = xqEmotionState.posts;
  if (els.emotionPostsMeta) {
    const bits = [
      xqEmotionKindLabel(st.kind),
      xqEmotionSortLabel(st.sort),
      emotionDaysLabel(st.days),
      `${st.maxPages} 页`,
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionPostsMeta.textContent = st.loading ? "正在查询讨论帖…" : bits.join(" · ");
  }
  if (els.emotionPostsHint) {
    if (st.loading) {
      els.emotionPostsHint.textContent = "正在从雪球拉取讨论帖…";
    } else if (st.error) {
      els.emotionPostsHint.textContent = st.error;
    } else if (!st.items.length) {
      els.emotionPostsHint.textContent = "暂无讨论帖，可换来源、排序或拉长区间";
    } else if (st.total > st.count) {
      els.emotionPostsHint.textContent = `已显示 ${st.count} / 共 ${st.total} 条`;
    } else {
      els.emotionPostsHint.textContent = st.withReplies
        ? "已附带部分帖子评论"
        : "点击标题查看正文与评论";
    }
  }
  if (!els.emotionPostsList) return;
  if (st.loading && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="muted">正在查询讨论帖…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.emotionPostsList.innerHTML = renderXqEmotionPostList(st.items, "暂无匹配的雪球讨论帖");
}

function paintXqEmotionSearch() {
  const st = xqEmotionState.search;
  if (els.emotionSearchMeta) {
    const bits = [
      st.keyword ? `「${st.keyword}」` : "搜帖",
      xqEmotionSortLabel(st.sort),
      emotionDaysLabel(st.days),
      `${st.maxPages} 页`,
      st.total && st.total !== st.count ? `${st.count}/${st.total}` : `${st.count || st.items.length}`,
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionSearchMeta.textContent = st.loading ? "正在搜索帖子…" : bits.join(" · ");
  }
  if (els.emotionSearchHint) {
    if (st.loading) {
      els.emotionSearchHint.textContent = "正在搜索雪球帖子…";
    } else if (st.error) {
      els.emotionSearchHint.textContent = st.error;
    } else if (!st.keyword) {
      els.emotionSearchHint.textContent = "输入关键词搜索，留空时可用公司名";
    } else if (!st.items.length) {
      els.emotionSearchHint.textContent = "暂无匹配结果，可换关键词或拉长区间";
    } else {
      els.emotionSearchHint.textContent = `关键词「${st.keyword}」`;
    }
  }
  if (!els.emotionSearchList) return;
  if (st.loading && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">正在搜索帖子…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  if (!st.keyword && !st.items.length) {
    els.emotionSearchList.innerHTML = `<p class="muted">输入关键词搜索雪球帖</p>`;
    return;
  }
  els.emotionSearchList.innerHTML = renderXqEmotionPostList(st.items, "暂无匹配的雪球帖子");
}

async function loadXqEmotionScores() {
  if (!code || xqEmotionState.scores.loading) return;
  xqEmotionState.scores.loading = true;
  xqEmotionState.scores.error = "";
  paintXqEmotionScores();
  const qs = emotionApiQuery({ channel: "scores" });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    xqEmotionState.scores.data = data;
    xqEmotionState.scores.error = data.error || "";
    xqEmotionState.scores.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionScoresBody) els.emotionScoresBody.scrollTop = 0;
  } catch (err) {
    xqEmotionState.scores.data = null;
    xqEmotionState.scores.error = err.message || String(err);
  } finally {
    xqEmotionState.scores.loading = false;
    paintXqEmotionScores();
  }
}

async function loadXqEmotionRank() {
  if (!code || xqEmotionState.rank.loading) return;
  const query = xqEmotionPostsQueryParams();
  xqEmotionState.rank.loading = true;
  xqEmotionState.rank.error = "";
  xqEmotionState.rank.market = query.market;
  paintXqEmotionRank();
  const qs = emotionApiQuery({ channel: "rank", market: query.market });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    xqEmotionState.rank.data = data;
    xqEmotionState.rank.items = Array.isArray(data.items) ? data.items : data.current ? [data.current] : [];
    xqEmotionState.rank.count = Number(data.count) || xqEmotionState.rank.items.length;
    xqEmotionState.rank.total = Number(data.total) || xqEmotionState.rank.count;
    xqEmotionState.rank.error = data.error || "";
    xqEmotionState.rank.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionRankBody) els.emotionRankBody.scrollTop = 0;
  } catch (err) {
    xqEmotionState.rank.data = null;
    xqEmotionState.rank.items = [];
    xqEmotionState.rank.count = 0;
    xqEmotionState.rank.total = 0;
    xqEmotionState.rank.error = err.message || String(err);
  } finally {
    xqEmotionState.rank.loading = false;
    paintXqEmotionRank();
  }
}

async function loadXqEmotionPosts() {
  if (!code || xqEmotionState.posts.loading) return;
  const query = xqEmotionPostsQueryParams();
  xqEmotionState.posts.loading = true;
  xqEmotionState.posts.error = "";
  xqEmotionState.posts.kind = query.kind;
  xqEmotionState.posts.sort = query.sort;
  xqEmotionState.posts.days = query.days;
  xqEmotionState.posts.maxPages = query.maxPages;
  xqEmotionState.posts.market = query.market;
  xqEmotionState.posts.withReplies = query.withReplies;
  if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = true;
  paintXqEmotionPosts();
  const qs = emotionApiQuery({
    channel: "posts",
    kind: query.kind,
    sort: query.sort,
    max_pages: String(query.maxPages),
    replies: query.withReplies ? "1" : "0",
    days: String(query.days),
    market: query.market,
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    xqEmotionState.posts.items = Array.isArray(data.items) ? data.items : [];
    xqEmotionState.posts.count = Number(data.count) || xqEmotionState.posts.items.length;
    xqEmotionState.posts.total = Number(data.total) || xqEmotionState.posts.count;
    xqEmotionState.posts.error = data.error || "";
    xqEmotionState.posts.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = 0;
  } catch (err) {
    xqEmotionState.posts.items = [];
    xqEmotionState.posts.count = 0;
    xqEmotionState.posts.total = 0;
    xqEmotionState.posts.error = err.message || String(err);
  } finally {
    xqEmotionState.posts.loading = false;
    if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = false;
    paintXqEmotionPosts();
  }
}

async function loadXqEmotionSearch() {
  if (!code || xqEmotionState.search.loading) return;
  const query = xqEmotionSearchQueryParams();
  if (!query.keyword) {
    xqEmotionState.search.error = "请输入搜索关键词";
    paintXqEmotionSearch();
    return;
  }
  xqEmotionState.search.loading = true;
  xqEmotionState.search.error = "";
  xqEmotionState.search.keyword = query.keyword;
  xqEmotionState.search.sort = query.sort;
  xqEmotionState.search.days = query.days;
  xqEmotionState.search.maxPages = query.maxPages;
  if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = true;
  paintXqEmotionSearch();
  const qs = emotionApiQuery({
    channel: "search",
    q: query.keyword,
    sort: query.sort,
    max_pages: String(query.maxPages),
    days: String(query.days),
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    xqEmotionState.search.items = Array.isArray(data.items) ? data.items : [];
    xqEmotionState.search.count = Number(data.count) || xqEmotionState.search.items.length;
    xqEmotionState.search.total = Number(data.total) || xqEmotionState.search.count;
    xqEmotionState.search.error = data.error || "";
    xqEmotionState.search.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.emotionSearchBody) els.emotionSearchBody.scrollTop = 0;
  } catch (err) {
    xqEmotionState.search.items = [];
    xqEmotionState.search.count = 0;
    xqEmotionState.search.total = 0;
    xqEmotionState.search.error = err.message || String(err);
  } finally {
    xqEmotionState.search.loading = false;
    if (els.emotionSearchQueryBtn) els.emotionSearchQueryBtn.disabled = false;
    paintXqEmotionSearch();
  }
}

async function loadXqEmotionAll() {
  if (!code) return;
  const query = xqEmotionPostsQueryParams();
  xqEmotionState.scores.loading = true;
  xqEmotionState.rank.loading = true;
  xqEmotionState.posts.loading = true;
  xqEmotionState.scores.error = "";
  xqEmotionState.rank.error = "";
  xqEmotionState.posts.error = "";
  xqEmotionState.posts.kind = query.kind;
  xqEmotionState.posts.sort = query.sort;
  xqEmotionState.posts.days = query.days;
  xqEmotionState.posts.maxPages = query.maxPages;
  xqEmotionState.posts.market = query.market;
  xqEmotionState.posts.withReplies = query.withReplies;
  xqEmotionState.rank.market = query.market;
  paintXqEmotionScores();
  paintXqEmotionRank();
  paintXqEmotionPosts();
  const qs = emotionApiQuery({
    channel: "all",
    kind: query.kind,
    sort: query.sort,
    max_pages: String(query.maxPages),
    replies: query.withReplies ? "1" : "0",
    days: String(query.days),
    market: query.market,
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    applyXqEmotionPack(json.data || {});
    if (els.emotionScoresBody) els.emotionScoresBody.scrollTop = 0;
    if (els.emotionRankBody) els.emotionRankBody.scrollTop = 0;
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = 0;
  } catch (err) {
    const message = err.message || String(err);
    xqEmotionState.scores.data = null;
    xqEmotionState.rank.data = null;
    xqEmotionState.posts.items = [];
    xqEmotionState.scores.error = message;
    xqEmotionState.rank.error = message;
    xqEmotionState.posts.error = message;
  } finally {
    xqEmotionState.scores.loading = false;
    xqEmotionState.rank.loading = false;
    xqEmotionState.posts.loading = false;
    paintXqEmotionScores();
    paintXqEmotionRank();
    paintXqEmotionPosts();
  }
}

function paintXqEmotionDetail() {
  const st = xqEmotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  if (els.emotionDetailTitle) {
    els.emotionDetailTitle.textContent = pack.title || "帖子详情";
  }
  if (els.emotionDetailMeta) {
    const bits = [
      pack.published_at || "",
      pack.author || pack.media_name || "",
      pack.comment_count ? `评 ${pack.comment_count}` : "",
      pack.like_count ? `赞 ${pack.like_count}` : "",
      pack.retweet_count ? `转 ${pack.retweet_count}` : "",
      pack.ip || "",
    ].filter(Boolean);
    els.emotionDetailMeta.textContent = bits.join(" · ");
  }
  if (els.emotionDetailLink) {
    const url = String(pack.url || "").trim();
    if (url) {
      els.emotionDetailLink.href = url;
      els.emotionDetailLink.hidden = false;
    } else {
      els.emotionDetailLink.hidden = true;
    }
  }
  if (els.emotionDetailContent) {
    if (st.loading) {
      els.emotionDetailContent.innerHTML = `<p class="muted">正在加载正文…</p>`;
    } else if (st.error) {
      els.emotionDetailContent.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    } else {
      const text = String(pack.content || pack.summary || "").trim();
      els.emotionDetailContent.innerHTML = text
        ? `<div class="emotion-detail-text">${escapeHtml(text).replaceAll("\n", "<br>")}</div>`
        : `<p class="muted">暂无正文</p>`;
    }
  }
  const replies = Array.isArray(pack.replies) ? pack.replies : [];
  if (els.emotionDetailReplies) {
    els.emotionDetailReplies.hidden = !replies.length && !pack.replies_error;
  }
  if (els.emotionDetailRepliesTitle) {
    const total = Number(pack.reply_total || pack.reply_count || replies.length || 0);
    els.emotionDetailRepliesTitle.textContent = total ? `评论 (${replies.length}/${total})` : "评论";
  }
  if (els.emotionDetailRepliesList) {
    if (pack.replies_error) {
      els.emotionDetailRepliesList.innerHTML = `<p class="news-error">${escapeHtml(pack.replies_error)}</p>`;
    } else {
      els.emotionDetailRepliesList.innerHTML = renderEmotionReplyList(replies);
    }
  }
}

async function openXqEmotionDetail(postId) {
  const pid = String(postId || "").trim();
  if (!pid || !code) return;
  xqEmotionState.detail.loading = true;
  xqEmotionState.detail.postId = pid;
  xqEmotionState.detail.pack = null;
  xqEmotionState.detail.error = "";
  setEmotionDetailOpen(true);
  paintXqEmotionDetail();
  const qs = emotionApiQuery({
    channel: "article",
    post_id: pid,
    replies: "1",
    max_pages: "5",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    xqEmotionState.detail.pack = data;
    xqEmotionState.detail.error = data.error || "";
  } catch (err) {
    xqEmotionState.detail.pack = null;
    xqEmotionState.detail.error = err.message || String(err);
  } finally {
    xqEmotionState.detail.loading = false;
    paintXqEmotionDetail();
  }
}

function closeXqEmotionDetail() {
  xqEmotionState.detail.loading = false;
  xqEmotionState.detail.postId = "";
  xqEmotionState.detail.pack = null;
  xqEmotionState.detail.error = "";
  setEmotionDetailOpen(false);
}

function cninfoDaysMode() {
  return (els.cninfoDays?.value || String(CNINFO_DEFAULT_DAYS)).trim();
}

function isCninfoCustomRange() {
  return cninfoDaysMode() === "custom";
}

function isoDay(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function fillCustomDateInputs(startEl, endEl, days) {
  if (!startEl || !endEl) return;
  const today = new Date();
  if (!String(endEl.value || "").trim()) endEl.value = isoDay(today);
  if (!String(startEl.value || "").trim()) {
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    start.setDate(start.getDate() - Math.max(1, Number(days) || 365));
    startEl.value = isoDay(start);
  }
}

function syncCninfoDateFields() {
  const custom = isCninfoCustomRange();
  els.cninfoStartWrap?.classList.toggle("hidden", !custom);
  els.cninfoEndWrap?.classList.toggle("hidden", !custom);
  if (custom) fillCustomDateInputs(els.cninfoStart, els.cninfoEnd, CNINFO_DEFAULT_DAYS);
}

function syncCninfoCategoryEnabled() {
  const wrap = els.cninfoCategory?.closest(".cninfo-field");
  const locked = cninfoTab !== "fulltext";
  if (els.cninfoCategory) els.cninfoCategory.disabled = locked;
  wrap?.classList.toggle("is-disabled", locked);
}

function cninfoQueryParams() {
  const custom = isCninfoCustomRange();
  const daysRaw = Number(cninfoDaysMode());
  const days = custom ? CNINFO_DEFAULT_DAYS : daysRaw || CNINFO_DEFAULT_DAYS;
  const start = custom ? (els.cninfoStart?.value || "").trim() : "";
  const end = custom ? (els.cninfoEnd?.value || "").trim() : "";
  const category = cninfoTab === "fulltext" ? (els.cninfoCategory?.value || "").trim() : "";
  return {
    tab: cninfoTab || "fulltext",
    category,
    keyword: (els.cninfoKeyword?.value || "").trim(),
    days,
    start,
    end,
  };
}

function cninfoCategoryLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "全部分类";
  const opt = els.cninfoCategory
    ? Array.from(els.cninfoCategory.options).find((item) => item.value === raw)
    : null;
  return opt?.textContent?.trim() || raw;
}

function cninfoRangeLabel(query, seDate) {
  if (query.start || query.end) {
    return seDate || `${query.start || "?"} ~ ${query.end || "今天"}`;
  }
  return daysLabel(query.days);
}

function paintCninfo() {
  if (!els.cninfoList) return;
  const st = cninfoState;
  const query = cninfoQueryParams();
  const tabLabel = CNINFO_TAB_LABELS[st.tab] || CNINFO_TAB_LABELS[query.tab] || "公告";
  const showCategory = (st.tab || query.tab) === "fulltext";
  const catLabel = showCategory ? cninfoCategoryLabel(st.category || query.category) : "";
  const range = cninfoRangeLabel(query, st.seDate);
  const totalBit =
    st.total && st.total !== st.count ? `${st.count}/${st.total}` : String(st.count || st.items.length);
  if (els.cninfoMeta) {
    const bits = [tabLabel, catLabel || null, range, `${totalBit} 条`, st.updatedAt || "-"].filter(Boolean);
    els.cninfoMeta.textContent = st.loading ? `正在查询${tabLabel}…` : bits.join(" · ");
  }
  if (els.cninfoHint) {
    if (st.loading) {
      els.cninfoHint.textContent = "正在从巨潮拉取公告…";
    } else if (st.error) {
      els.cninfoHint.textContent = st.error;
    } else if (!st.items.length) {
      els.cninfoHint.textContent = "暂无匹配公告，可换分类、关键词或拉长区间";
    } else if (st.total > st.count) {
      els.cninfoHint.textContent = `已显示 ${st.count} / 共 ${st.total} 条，可缩小分类或缩短区间`;
    } else {
      els.cninfoHint.textContent = query.keyword ? `标题含「${query.keyword}」` : "";
    }
  }
  if (st.loading && !st.items.length) {
    els.cninfoList.innerHTML = `<p class="muted">正在查询巨潮${escapeHtml(tabLabel)}…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.cninfoList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.cninfoList.innerHTML = renderCninfoList(st.items);
}

async function loadCninfo() {
  if (!code || !els.cninfoList || cninfoState.loading) return;
  const query = cninfoQueryParams();
  if (isCninfoCustomRange() && !query.start && !query.end) {
    cninfoState.error = "自定义区间请填写开始或结束日期";
    paintCninfo();
    return;
  }

  cninfoState.loading = true;
  cninfoState.error = "";
  cninfoState.tab = query.tab;
  cninfoState.category = query.category;
  cninfoState.keyword = query.keyword;
  if (els.cninfoQueryBtn) els.cninfoQueryBtn.disabled = true;
  paintCninfo();

  const qs = new URLSearchParams({
    code,
    tab: query.tab,
    days: String(query.days),
  });
  if (query.category) qs.set("category", query.category);
  if (query.keyword) qs.set("keyword", query.keyword);
  if (query.start) qs.set("start", query.start);
  if (query.end) qs.set("end", query.end);

  try {
    const json = await api(`/api/stocks/cninfo?${qs.toString()}`);
    const data = json.data || {};
    cninfoState.items = Array.isArray(data.items) ? data.items : [];
    cninfoState.count = Number(data.count) || cninfoState.items.length;
    cninfoState.total = Number(data.total) || cninfoState.count;
    cninfoState.seDate = data.se_date || "";
    cninfoState.category = query.category;
    cninfoState.keyword = data.keyword || query.keyword;
    cninfoState.tab = data.tab || query.tab;
    cninfoState.error = data.error || "";
    cninfoState.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.cninfoBody) els.cninfoBody.scrollTop = 0;
    paintCninfo();
  } catch (err) {
    cninfoState.items = [];
    cninfoState.count = 0;
    cninfoState.total = 0;
    cninfoState.error = err.message || String(err);
    paintCninfo();
  } finally {
    cninfoState.loading = false;
    if (els.cninfoQueryBtn) els.cninfoQueryBtn.disabled = false;
    paintCninfo();
  }
}

function setCninfoTab(tab) {
  const next = CNINFO_TAB_LABELS[tab] ? tab : "fulltext";
  if (next === cninfoTab && els.cninfoTabs?.dataset.ready === "1") {
    return;
  }
  cninfoTab = next;
  if (els.cninfoTabs) {
    els.cninfoTabs.querySelectorAll("[data-tab]").forEach((btn) => {
      const active = btn.getAttribute("data-tab") === cninfoTab;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  syncCninfoCategoryEnabled();
}

function setupCninfoBox() {
  if (!els.cninfoForm || els.cninfoForm.dataset.bound === "1") return;
  els.cninfoForm.dataset.bound = "1";
  syncCninfoDateFields();
  syncCninfoCategoryEnabled();

  els.cninfoTabs?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (!btn || !els.cninfoTabs.contains(btn)) return;
    setCninfoTab(btn.getAttribute("data-tab") || "fulltext");
    loadCninfo();
  });
  els.cninfoTabs && (els.cninfoTabs.dataset.ready = "1");

  els.cninfoDays?.addEventListener("change", () => {
    syncCninfoDateFields();
    if (!isCninfoCustomRange()) loadCninfo();
  });
  els.cninfoCategory?.addEventListener("change", () => loadCninfo());
  els.cninfoForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadCninfo();
  });
}

function exchangeDaysMode() {
  return (els.exchangeDays?.value || String(EXCHANGE_DEFAULT_DAYS)).trim();
}

function isExchangeCustomRange() {
  return exchangeDaysMode() === "custom";
}

function syncExchangeDateFields() {
  const custom = isExchangeCustomRange();
  els.exchangeStartWrap?.classList.toggle("hidden", !custom);
  els.exchangeEndWrap?.classList.toggle("hidden", !custom);
  if (custom) fillCustomDateInputs(els.exchangeStart, els.exchangeEnd, EXCHANGE_DEFAULT_DAYS);
}

function syncExchangeCategoryEnabled() {
  const wrap = els.exchangeCategory?.closest(".cninfo-field");
  const locked = exchangeTab !== "bulletin";
  if (els.exchangeCategory) els.exchangeCategory.disabled = locked;
  wrap?.classList.toggle("is-disabled", locked);
}

function exchangeQueryParams() {
  const custom = isExchangeCustomRange();
  const daysRaw = Number(exchangeDaysMode());
  const days = custom ? EXCHANGE_DEFAULT_DAYS : daysRaw || EXCHANGE_DEFAULT_DAYS;
  const start = custom ? (els.exchangeStart?.value || "").trim() : "";
  const end = custom ? (els.exchangeEnd?.value || "").trim() : "";
  const category = exchangeTab === "bulletin" ? (els.exchangeCategory?.value || "").trim() : "";
  return {
    tab: exchangeTab || "bulletin",
    category,
    keyword: (els.exchangeKeyword?.value || "").trim(),
    days,
    start,
    end,
  };
}

function exchangeCategoryLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "全部分类";
  const opt = els.exchangeCategory
    ? Array.from(els.exchangeCategory.options).find((item) => item.value === raw)
    : null;
  return opt?.textContent?.trim() || raw;
}

function exchangeRangeLabel(query, seDate) {
  if (query.start || query.end) {
    return seDate || `${query.start || "?"} ~ ${query.end || "今天"}`;
  }
  return daysLabel(query.days);
}

function paintExchange() {
  if (!els.exchangeList) return;
  const st = exchangeState;
  const query = exchangeQueryParams();
  const tabLabel = EXCHANGE_TAB_LABELS[st.tab] || EXCHANGE_TAB_LABELS[query.tab] || "公告";
  const showCategory = (st.tab || query.tab) === "bulletin";
  const catLabel = showCategory ? exchangeCategoryLabel(st.category || query.category) : "";
  const range = exchangeRangeLabel(query, st.seDate);
  const totalBit =
    st.total && st.total !== st.count ? `${st.count}/${st.total}` : String(st.count || st.items.length);
  const title = exchangeTitleText(st.market);
  if (els.exchangeTitle) els.exchangeTitle.textContent = title;
  if (els.exchangeMeta) {
    const bits = [tabLabel, catLabel || null, range, `${totalBit} 条`, st.updatedAt || "-"].filter(Boolean);
    els.exchangeMeta.textContent = st.loading ? `正在查询${tabLabel}…` : bits.join(" · ");
  }
  if (els.exchangeHint) {
    if (st.loading) {
      const venue = title.replace(/公告$/, "") || "交易所";
      els.exchangeHint.textContent = `正在从${venue}拉取${tabLabel}…`;
    } else if (st.error) {
      els.exchangeHint.textContent = st.error;
    } else if (!st.items.length) {
      els.exchangeHint.textContent = "暂无匹配公告，可换分类、关键词或拉长区间";
    } else if (st.total > st.count) {
      els.exchangeHint.textContent = `已显示 ${st.count} / 共 ${st.total} 条，可缩小分类或缩短区间`;
    } else {
      els.exchangeHint.textContent = query.keyword ? `标题含「${query.keyword}」` : "";
    }
  }
  if (st.loading && !st.items.length) {
    els.exchangeList.innerHTML = `<p class="muted">正在查询${escapeHtml(title)} · ${escapeHtml(tabLabel)}…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.exchangeList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.exchangeList.innerHTML = renderExchangeList(st.items);
}

async function loadExchange() {
  if (!code || !els.exchangeList || exchangeState.loading) return;
  const query = exchangeQueryParams();
  if (isExchangeCustomRange() && !query.start && !query.end) {
    exchangeState.error = "自定义区间请填写开始或结束日期";
    paintExchange();
    return;
  }

  exchangeState.loading = true;
  exchangeState.error = "";
  exchangeState.tab = query.tab;
  exchangeState.category = query.category;
  exchangeState.keyword = query.keyword;
  exchangeState.market = detectExchangeMarket();
  if (els.exchangeQueryBtn) els.exchangeQueryBtn.disabled = true;
  paintExchange();

  const qs = new URLSearchParams({
    code,
    tab: query.tab,
    days: String(query.days),
  });
  if (query.category) qs.set("category", query.category);
  if (query.keyword) qs.set("keyword", query.keyword);
  if (query.start) qs.set("start", query.start);
  if (query.end) qs.set("end", query.end);

  try {
    const json = await api(`/api/stocks/exchange?${qs.toString()}`);
    const data = json.data || {};
    exchangeState.items = Array.isArray(data.items) ? data.items : [];
    exchangeState.count = Number(data.count) || exchangeState.items.length;
    exchangeState.total = Number(data.total) || exchangeState.count;
    exchangeState.seDate = data.se_date || "";
    exchangeState.category = query.category;
    exchangeState.keyword = data.keyword || query.keyword;
    exchangeState.tab = data.tab || query.tab;
    exchangeState.market = data.market || exchangeState.market;
    exchangeState.marketLabel = data.market_label || "";
    exchangeState.error = data.error || "";
    exchangeState.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.exchangeBody) els.exchangeBody.scrollTop = 0;
    paintExchange();
  } catch (err) {
    exchangeState.items = [];
    exchangeState.count = 0;
    exchangeState.total = 0;
    exchangeState.error = err.message || String(err);
    paintExchange();
  } finally {
    exchangeState.loading = false;
    if (els.exchangeQueryBtn) els.exchangeQueryBtn.disabled = false;
    paintExchange();
  }
}

function setExchangeTab(tab) {
  const next = EXCHANGE_TAB_LABELS[tab] ? tab : "bulletin";
  if (next === exchangeTab && els.exchangeTabs?.dataset.ready === "1") {
    return;
  }
  exchangeTab = next;
  if (els.exchangeTabs) {
    els.exchangeTabs.querySelectorAll("[data-tab]").forEach((btn) => {
      const active = btn.getAttribute("data-tab") === exchangeTab;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  syncExchangeCategoryEnabled();
}

function setupExchangeBox() {
  if (!els.exchangeForm || els.exchangeForm.dataset.bound === "1") return;
  els.exchangeForm.dataset.bound = "1";
  if (els.exchangeTitle) els.exchangeTitle.textContent = exchangeTitleText();
  syncExchangeDateFields();
  syncExchangeCategoryEnabled();

  els.exchangeTabs?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (!btn || !els.exchangeTabs.contains(btn)) return;
    setExchangeTab(btn.getAttribute("data-tab") || "bulletin");
    loadExchange();
  });
  els.exchangeTabs && (els.exchangeTabs.dataset.ready = "1");

  els.exchangeDays?.addEventListener("change", () => {
    syncExchangeDateFields();
    if (!isExchangeCustomRange()) loadExchange();
  });
  els.exchangeCategory?.addEventListener("change", () => loadExchange());
  els.exchangeForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadExchange();
  });
}

function pressOutletConf(id = pressOutlet) {
  return PRESS_OUTLETS.find((item) => item.id === id) || PRESS_OUTLETS[0];
}

function pressDaysMode() {
  return (els.pressDays?.value || String(PRESS_DEFAULT_DAYS)).trim();
}

function isPressCustomRange() {
  return pressDaysMode() === "custom";
}

function syncPressDateFields() {
  const custom = isPressCustomRange();
  els.pressStartWrap?.classList.toggle("hidden", !custom);
  els.pressEndWrap?.classList.toggle("hidden", !custom);
  if (custom) fillCustomDateInputs(els.pressStart, els.pressEnd, PRESS_DEFAULT_DAYS);
}

function renderPressExtraFilters() {
  const row = els.pressExtraRow;
  if (!row) return;
  const conf = pressOutletConf();
  const filters = conf.filters || [];
  row.innerHTML = filters
    .map((filter) => {
      const options = (filter.options || [])
        .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
        .join("");
      return `<label class="cninfo-field">
        <span>${escapeHtml(filter.label)}</span>
        <select class="chart-select cninfo-select" data-press-filter="${escapeHtml(filter.key)}" aria-label="${escapeHtml(filter.label)}">${options}</select>
      </label>`;
    })
    .join("");
  row.querySelectorAll("[data-press-filter]").forEach((select) => {
    select.addEventListener("change", () => loadPress());
  });
}

function pressExtraParams() {
  const params = {};
  els.pressExtraRow?.querySelectorAll("[data-press-filter]").forEach((select) => {
    const key = select.getAttribute("data-press-filter");
    const value = String(select.value || "").trim();
    if (key && value) params[key] = value;
  });
  return params;
}

function pressQueryParams() {
  const custom = isPressCustomRange();
  const daysRaw = Number(pressDaysMode());
  const days = custom ? PRESS_DEFAULT_DAYS : daysRaw || PRESS_DEFAULT_DAYS;
  return {
    outlet: pressOutlet || "cs",
    keyword: (els.pressKeyword?.value || "").trim(),
    days,
    start: custom ? (els.pressStart?.value || "").trim() : "",
    end: custom ? (els.pressEnd?.value || "").trim() : "",
    extra: pressExtraParams(),
  };
}

function pressRangeLabel(query, seDate) {
  if (query.start || query.end) {
    return seDate || `${query.start || "?"} ~ ${query.end || "今天"}`;
  }
  return daysLabel(query.days);
}

function extraFilterLabels(extra) {
  const conf = pressOutletConf();
  return (conf.filters || [])
    .map((filter) => {
      const value = extra[filter.key];
      if (!value) return "";
      const hit = (filter.options || []).find(([id]) => id === value);
      return hit ? hit[1] : value;
    })
    .filter(Boolean);
}

function renderPressList(items) {
  if (!items.length) {
    return renderNewsList(items, "暂无匹配的指定披露媒体新闻");
  }
  return renderNewsList(
    items.map((item) => {
      const why = String(item?.why || item?.paper || item?.source || "").trim();
      const summary = String(item.summary || "").trim();
      return {
        ...item,
        why,
        summary: summary && summary !== why ? summary : "",
      };
    }),
    "暂无匹配的指定披露媒体新闻"
  );
}

function paintPress() {
  if (!els.pressList) return;
  const st = pressState;
  const query = pressQueryParams();
  const conf = pressOutletConf(st.outlet || query.outlet);
  const range = pressRangeLabel(query, st.seDate);
  const extras = extraFilterLabels(query.extra);
  const totalBit =
    st.total && st.total !== st.count ? `${st.count}/${st.total}` : String(st.count || st.items.length);
  if (els.pressTitle) els.pressTitle.textContent = conf.paper ? `${conf.name}` : "七报七网";
  if (els.pressMeta) {
    const bits = [conf.name, ...extras, range, `${totalBit} 条`, st.updatedAt || "-"].filter(Boolean);
    els.pressMeta.textContent = st.loading ? `正在查询${conf.name}…` : bits.join(" · ");
  }
  if (els.pressHint) {
    if (st.loading) {
      els.pressHint.textContent = `正在从${conf.name}拉取新闻…`;
    } else if (st.error) {
      els.pressHint.textContent = st.error;
    } else if (!st.items.length) {
      els.pressHint.textContent = "暂无匹配新闻，可换类型、关键词或拉长区间";
    } else {
      els.pressHint.textContent = query.keyword ? `标题含「${query.keyword}」` : conf.paper || "";
    }
  }
  if (st.loading && !st.items.length) {
    els.pressList.innerHTML = `<p class="muted">正在查询${escapeHtml(conf.name)}…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    els.pressList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  els.pressList.innerHTML = renderPressList(st.items);
}

async function loadPress() {
  if (!code || !els.pressList || pressState.loading) return;
  const query = pressQueryParams();
  if (isPressCustomRange() && !query.start && !query.end) {
    pressState.error = "自定义区间请填写开始或结束日期";
    paintPress();
    return;
  }

  pressState.loading = true;
  pressState.error = "";
  pressState.outlet = query.outlet;
  pressState.keyword = query.keyword;
  if (els.pressQueryBtn) els.pressQueryBtn.disabled = true;
  paintPress();

  const qs = new URLSearchParams({
    code,
    outlet: query.outlet,
    days: String(query.days),
  });
  if (nameHint) qs.set("name", nameHint);
  if (query.keyword) qs.set("keyword", query.keyword);
  if (query.start) qs.set("start", query.start);
  if (query.end) qs.set("end", query.end);
  Object.entries(query.extra).forEach(([key, value]) => {
    if (value) qs.set(key, value);
  });

  try {
    const json = await api(`/api/stocks/press?${qs.toString()}`);
    const data = json.data || {};
    pressState.items = Array.isArray(data.items) ? data.items : [];
    pressState.count = Number(data.count) || pressState.items.length;
    pressState.total = Number(data.total) || pressState.count;
    pressState.seDate = data.se_date || "";
    pressState.outlet = data.outlet || query.outlet;
    pressState.keyword = data.keyword || query.keyword;
    pressState.error = data.error || "";
    pressState.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.pressBody) els.pressBody.scrollTop = 0;
    paintPress();
  } catch (err) {
    pressState.items = [];
    pressState.count = 0;
    pressState.total = 0;
    pressState.error = err.message || String(err);
    paintPress();
  } finally {
    pressState.loading = false;
    if (els.pressQueryBtn) els.pressQueryBtn.disabled = false;
    paintPress();
  }
}

function setPressOutlet(id) {
  const next = PRESS_OUTLETS.some((item) => item.id === id) ? id : "cs";
  const changed = next !== pressOutlet || els.pressTabs?.dataset.ready !== "1";
  pressOutlet = next;
  if (els.pressTabs) {
    els.pressTabs.querySelectorAll("[data-outlet]").forEach((btn) => {
      const active = btn.getAttribute("data-outlet") === pressOutlet;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  if (changed) renderPressExtraFilters();
  return changed;
}

function setupPressBox() {
  if (!els.pressForm || els.pressForm.dataset.bound === "1") return;
  els.pressForm.dataset.bound = "1";
  if (els.pressTabs && !els.pressTabs.children.length) {
    els.pressTabs.innerHTML = PRESS_OUTLETS.map(
      (item, index) =>
        `<button type="button" class="news-tab${index === 0 ? " is-active" : ""}" data-outlet="${item.id}" role="tab" aria-selected="${index === 0 ? "true" : "false"}">${item.name}</button>`
    ).join("");
  }
  setPressOutlet(pressOutlet);
  syncPressDateFields();

  els.pressTabs?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-outlet]");
    if (!btn || !els.pressTabs.contains(btn)) return;
    const changed = setPressOutlet(btn.getAttribute("data-outlet") || "cs");
    if (changed) loadPress();
  });
  els.pressTabs && (els.pressTabs.dataset.ready = "1");

  els.pressDays?.addEventListener("change", () => {
    syncPressDateFields();
    if (!isPressCustomRange()) loadPress();
  });
  els.pressForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadPress();
  });
}

function platformConf(source) {
  return PLATFORM_HUBS.find((item) => item.id === source) || PLATFORM_HUBS[0];
}

function platformEls(source) {
  const root = document.querySelector(`.platform-hub[data-source="${source}"]`);
  if (!root) return {};
  return {
    root,
    form: root.querySelector("[data-platform-form]"),
    tabs: root.querySelector("[data-platform-tabs]"),
    extra: root.querySelector("[data-platform-extra]"),
    days: root.querySelector("[data-platform-days]"),
    start: root.querySelector("[data-platform-start]"),
    end: root.querySelector("[data-platform-end]"),
    startWrap: root.querySelector("[data-platform-start-wrap]"),
    endWrap: root.querySelector("[data-platform-end-wrap]"),
    keyword: root.querySelector("[data-platform-keyword]"),
    btn: root.querySelector("[data-platform-query]"),
    meta: root.querySelector("[data-platform-meta]"),
    hint: root.querySelector("[data-platform-hint]"),
    body: root.querySelector("[data-platform-body]"),
    list: root.querySelector("[data-platform-list]"),
  };
}

function platformTabLabel(source, tab) {
  const hit = (platformConf(source).tabs || []).find((item) => item.id === tab);
  return hit?.label || tab || "";
}

function platformDaysMode(source) {
  const ui = platformEls(source);
  return (ui.days?.value || String(PLATFORM_DEFAULT_DAYS)).trim();
}

function isPlatformCustomRange(source) {
  return platformDaysMode(source) === "custom";
}

function syncPlatformDateFields(source) {
  const ui = platformEls(source);
  const custom = isPlatformCustomRange(source);
  ui.startWrap?.classList.toggle("hidden", !custom);
  ui.endWrap?.classList.toggle("hidden", !custom);
  if (custom) fillCustomDateInputs(ui.start, ui.end, PLATFORM_DEFAULT_DAYS);
}

function renderPlatformExtraFilters(source) {
  const ui = platformEls(source);
  const row = ui.extra;
  if (!row) return;
  const tab = platformTabs[source] || "news";
  const filters = (platformConf(source).extras || {})[tab] || [];
  if (!filters.length) {
    row.innerHTML = "";
    return;
  }
  row.innerHTML = filters
    .map((filter) => {
      const options = (filter.options || [])
        .map(([id, label], index) => `<option value="${escapeHtml(id)}"${index === 0 ? " selected" : ""}>${escapeHtml(label)}</option>`)
        .join("");
      return `<label class="cninfo-field">
        <span>${escapeHtml(filter.label)}</span>
        <select class="chart-select cninfo-select" data-platform-filter="${escapeHtml(filter.key)}" aria-label="${escapeHtml(filter.label)}">${options}</select>
      </label>`;
    })
    .join("");
  row.querySelectorAll("[data-platform-filter]").forEach((select) => {
    select.addEventListener("change", () => loadPlatform(source));
  });
}

function platformExtraParams(source) {
  const ui = platformEls(source);
  const params = {};
  ui.extra?.querySelectorAll("[data-platform-filter]").forEach((select) => {
    const key = select.getAttribute("data-platform-filter");
    const value = String(select.value || "").trim();
    if (key && value) params[key] = value;
  });
  return params;
}

function extraFilterValueLabels(source, extra) {
  const tab = platformTabs[source] || "news";
  const filters = (platformConf(source).extras || {})[tab] || [];
  return filters
    .map((filter) => {
      const value = extra[filter.key];
      if (!value) return "";
      const hit = (filter.options || []).find(([id]) => id === value);
      return hit ? hit[1] : value;
    })
    .filter(Boolean);
}

function platformQueryParams(source) {
  const ui = platformEls(source);
  const custom = isPlatformCustomRange(source);
  const daysRaw = Number(platformDaysMode(source));
  const days = custom ? PLATFORM_DEFAULT_DAYS : daysRaw || PLATFORM_DEFAULT_DAYS;
  return {
    source,
    tab: platformTabs[source] || "news",
    keyword: (ui.keyword?.value || "").trim(),
    days,
    start: custom ? (ui.start?.value || "").trim() : "",
    end: custom ? (ui.end?.value || "").trim() : "",
    extra: platformExtraParams(source),
  };
}

function platformRangeLabel(query, seDate) {
  if (query.start || query.end) {
    return seDate || `${query.start || "?"} ~ ${query.end || "今天"}`;
  }
  return daysLabel(query.days);
}

function paintPlatform(source) {
  const ui = platformEls(source);
  if (!ui.list) return;
  const conf = platformConf(source);
  const st = platformState[source];
  const query = platformQueryParams(source);
  const tabLabel = platformTabLabel(source, st.tab || query.tab);
  const range = platformRangeLabel(query, st.seDate);
  const extras = extraFilterValueLabels(source, query.extra);
  const totalBit =
    st.total && st.total !== st.count ? `${st.count}/${st.total}` : String(st.count || st.items.length);
  if (ui.meta) {
    const bits = [tabLabel, ...extras, range, `${totalBit} 条`, st.updatedAt || "-"].filter(Boolean);
    ui.meta.textContent = st.loading ? `正在查询${conf.name}${tabLabel}…` : bits.join(" · ");
  }
  if (ui.hint) {
    if (st.loading) {
      ui.hint.textContent = `正在从${conf.name}拉取${tabLabel}…`;
    } else if (st.error) {
      ui.hint.textContent = st.error;
    } else if (!st.items.length) {
      ui.hint.textContent = "暂无匹配内容，可换页签、关键词或拉长区间";
    } else {
      ui.hint.textContent = query.keyword ? `标题含「${query.keyword}」` : "";
    }
  }
  if (st.loading && !st.items.length) {
    ui.list.innerHTML = `<p class="muted">正在查询${escapeHtml(conf.name)}${escapeHtml(tabLabel)}…</p>`;
    return;
  }
  if (st.error && !st.items.length) {
    ui.list.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    return;
  }
  ui.list.innerHTML = renderNewsList(st.items, `暂无匹配的${conf.name}${tabLabel}`);
}

async function loadPlatform(source) {
  const ui = platformEls(source);
  const st = platformState[source];
  if (!code || !ui.list || !st || st.loading) return;
  const query = platformQueryParams(source);
  if (isPlatformCustomRange(source) && !query.start && !query.end) {
    st.error = "自定义区间请填写开始或结束日期";
    paintPlatform(source);
    return;
  }

  st.loading = true;
  st.error = "";
  st.tab = query.tab;
  st.keyword = query.keyword;
  if (ui.btn) ui.btn.disabled = true;
  paintPlatform(source);

  const qs = new URLSearchParams({
    code,
    source: query.source,
    tab: query.tab,
    days: String(query.days),
  });
  if (nameHint) qs.set("name", nameHint);
  if (query.keyword) qs.set("keyword", query.keyword);
  if (query.start) qs.set("start", query.start);
  if (query.end) qs.set("end", query.end);
  Object.entries(query.extra).forEach(([key, value]) => {
    if (value) qs.set(key, value);
  });

  try {
    const json = await api(`/api/stocks/platform?${qs.toString()}`);
    const data = json.data || {};
    st.items = Array.isArray(data.items) ? data.items : [];
    st.count = Number(data.count) || st.items.length;
    st.total = Number(data.total) || st.count;
    st.seDate = data.se_date || "";
    st.tab = data.tab || query.tab;
    st.keyword = data.keyword || query.keyword;
    st.error = data.error || "";
    st.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    if (ui.body) ui.body.scrollTop = 0;
    paintPlatform(source);
  } catch (err) {
    st.items = [];
    st.count = 0;
    st.total = 0;
    st.error = err.message || String(err);
    paintPlatform(source);
  } finally {
    st.loading = false;
    if (ui.btn) ui.btn.disabled = false;
    paintPlatform(source);
  }
}

function setPlatformTab(source, tab) {
  const conf = platformConf(source);
  const next = (conf.tabs || []).some((item) => item.id === tab) ? tab : conf.tabs?.[0]?.id || "news";
  const changed = next !== platformTabs[source];
  platformTabs[source] = next;
  const ui = platformEls(source);
  ui.tabs?.querySelectorAll("[data-tab]").forEach((btn) => {
    const active = btn.getAttribute("data-tab") === next;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (changed) renderPlatformExtraFilters(source);
  return changed;
}

function setupPlatformBox(source) {
  const ui = platformEls(source);
  if (!ui.form || ui.form.dataset.bound === "1") return;
  ui.form.dataset.bound = "1";
  const conf = platformConf(source);
  if (ui.tabs && !ui.tabs.children.length) {
    ui.tabs.innerHTML = (conf.tabs || [])
      .map(
        (item, index) =>
          `<button type="button" class="news-tab${index === 0 ? " is-active" : ""}" data-tab="${item.id}" role="tab" aria-selected="${index === 0 ? "true" : "false"}">${item.label}</button>`
      )
      .join("");
  }
  setPlatformTab(source, platformTabs[source]);
  renderPlatformExtraFilters(source);
  syncPlatformDateFields(source);

  ui.tabs?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (!btn || !ui.tabs.contains(btn)) return;
    const changed = setPlatformTab(source, btn.getAttribute("data-tab") || "news");
    if (changed) loadPlatform(source);
  });

  ui.days?.addEventListener("change", () => {
    syncPlatformDateFields(source);
    if (!isPlatformCustomRange(source)) loadPlatform(source);
  });
  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    loadPlatform(source);
  });
}

function setupPlatformBoxes() {
  PLATFORM_HUBS.forEach((hub) => setupPlatformBox(hub.id));
}

function newsFoldEls() {
  return {
    layout: document.querySelector('.company-panel[data-panel="news"] .news-layout'),
    folded: document.querySelector('.company-panel[data-panel="news"] .news-folded'),
    open: document.querySelector('.company-panel[data-panel="news"] .news-open'),
  };
}

function newsHubId(hub) {
  return hub?.dataset.fold || hub?.dataset.source || hub?.getAttribute("aria-label") || "";
}

const NEWS_HUB_ORDER = ["exchange", "cninfo", "press", "eastmoney", "ths", "xueqiu"];

function placeOpenHub(hub) {
  const { open } = newsFoldEls();
  if (!open || !hub) return;
  const rank = NEWS_HUB_ORDER.indexOf(newsHubId(hub));
  const next = [...open.querySelectorAll(":scope > .cninfo-hub")].find((item) => {
    if (item === hub) return false;
    const other = NEWS_HUB_ORDER.indexOf(newsHubId(item));
    return rank >= 0 && other > rank;
  });
  if (next) open.insertBefore(hub, next);
  else open.appendChild(hub);
}

function newsFoldStorageKey() {
  return `orbit-news-folded:${code || "default"}`;
}

function readFoldedHubs() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(newsFoldStorageKey()) || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function writeFoldedHubs() {
  const ids = [...document.querySelectorAll(".news-layout .cninfo-hub.is-collapsed")]
    .map(newsHubId)
    .filter(Boolean);
  try {
    sessionStorage.setItem(newsFoldStorageKey(), JSON.stringify(ids));
  } catch {
    /* ignore */
  }
}

function preferredNewsCols(n) {
  if (window.matchMedia("(max-width: 1100px)").matches) return 1;
  if (n <= 1) return 1;
  if (n === 2 || n === 4) return 2;
  return Math.min(3, Math.max(1, n));
}

function visibleNewsHubs(root) {
  return [...(root?.querySelectorAll(":scope > .cninfo-hub") || [])].filter((hub) =>
    isNewsHubInGroup(hub, newsGroup)
  );
}

function syncNewsHubLayout() {
  const { folded, open } = newsFoldEls();
  if (!open || !folded) return;
  [...open.querySelectorAll(":scope > .cninfo-hub"), ...folded.querySelectorAll(":scope > .cninfo-hub")].forEach((hub) => {
    hub.style.gridColumn = "";
    hub.style.gridRow = "";
  });
  const hubs = visibleNewsHubs(open);
  const foldedHubs = visibleNewsHubs(folded);
  folded.hidden = foldedHubs.length === 0;
  const n = hubs.length;
  if (!n) {
    open.style.gridTemplateRows = "";
    return;
  }
  const cols = preferredNewsCols(n);
  const rows = Math.max(1, Math.ceil(n / cols));
  const units = 6;
  open.style.gridTemplateColumns = `repeat(${units}, minmax(0, 1fr))`;
  open.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  hubs.forEach((hub, i) => {
    const lastRowCount = n - cols * (rows - 1);
    const inLastRow = i >= cols * (rows - 1);
    const span = inLastRow && lastRowCount < cols ? units / lastRowCount : units / cols;
    hub.style.gridColumn = `span ${span}`;
  });
}

function setNewsHubCollapsed(hub, collapsed) {
  const { folded, open } = newsFoldEls();
  if (!hub || !folded || !open) return;
  hub.classList.toggle("is-collapsed", collapsed);
  const btn = hub.querySelector(".news-fold-btn");
  if (btn) {
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.setAttribute("aria-label", collapsed ? "展开" : "折叠");
    btn.title = collapsed ? "展开" : "折叠";
    btn.textContent = collapsed ? "▸" : "▾";
  }
  if (collapsed && hub.parentElement !== folded) folded.appendChild(hub);
  else if (!collapsed) placeOpenHub(hub);
}

function toggleNewsHub(hub) {
  setNewsHubCollapsed(hub, !hub.classList.contains("is-collapsed"));
  writeFoldedHubs();
  syncNewsHubLayout();
}

function setupNewsFolding() {
  const { layout, open } = newsFoldEls();
  if (!layout || !open || layout.dataset.foldBound === "1") return;
  layout.dataset.foldBound = "1";
  const saved = new Set(readFoldedHubs());
  [...layout.querySelectorAll(".cninfo-hub")].forEach((hub) => {
    const head = hub.querySelector(".cninfo-hub-head");
    if (!head) return;
    if (!head.querySelector(".news-fold-btn")) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "news-fold-btn";
      head.appendChild(btn);
    }
    head.addEventListener("click", (event) => {
      if (event.target.closest("a, input, select, textarea, label")) return;
      event.preventDefault();
      toggleNewsHub(hub);
    });
    setNewsHubCollapsed(hub, saved.has(newsHubId(hub)));
  });
  els.newsSourceBar?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-source]");
    if (!btn || !els.newsSourceBar.contains(btn)) return;
    setNewsGroup(btn.getAttribute("data-source") || NEWS_GROUP_OFFICIAL);
  });
  syncNewsGroupUi();
}

function syncChartsViewportClass() {
  document.documentElement.classList.add("company-charts-on");
  document.body.classList.add("company-charts-on");
}

function fitChartsToViewport() {
  const panels = document.querySelector(".company-panels");
  const tabs = els.companyMainTabs;
  const rail = document.querySelector(".app-rail");
  if (!panels || !tabs) return;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const railBox = rail ? rail.getBoundingClientRect() : { width: 0, height: 0, top: 0, right: 0 };
  const tabsBox = tabs.getBoundingClientRect();
  const railIsSide = railBox.width > 0 && railBox.right < vw / 2;
  const railIsBottom = railBox.height > 0 && railBox.top > vh / 2;
  const left = `${railIsSide ? Math.round(railBox.right) : 0}px`;
  const top = `${Math.round(tabsBox.bottom)}px`;
  const right = "0px";
  const bottom = `${railIsBottom ? Math.max(0, Math.round(vh - railBox.top)) : 0}px`;
  if (
    panels.style.position === "fixed" &&
    panels.style.left === left &&
    panels.style.top === top &&
    panels.style.right === right &&
    panels.style.bottom === bottom
  ) {
    return;
  }
  const set = (prop, value) => panels.style.setProperty(prop, value, "important");
  set("position", "fixed");
  set("left", left);
  set("top", top);
  set("right", right);
  set("bottom", bottom);
  set("width", "auto");
  set("height", "auto");
  set("z-index", "4");
  set("overflow", "hidden");
}

function refreshChartsLayout() {
  const paint = () => {
    fitChartsToViewport();
    syncChartScrollBar();
    renderChart();
    syncTicksChartScrollBar();
    renderTicksChart();
  };
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(paint);
  });
}

function switchMainPanel(panelId) {
  const next = normalizeMainPanel(panelId);
  if (!next || next === activeMainPanel) return;
  activeMainPanel = next;

  if (els.companyMainTabs) {
    els.companyMainTabs.querySelectorAll("[data-panel]").forEach((tab) => {
      const active = tab.getAttribute("data-panel") === next;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  document.querySelectorAll(".company-panel[data-panel]").forEach((panel) => {
    const active = panel.getAttribute("data-panel") === next;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });

  if (els.refreshNewsBtn) {
    els.refreshNewsBtn.hidden = next !== "news";
  }
  if (els.refreshEmotionBtn) {
    els.refreshEmotionBtn.hidden = next !== "emotion";
  }

  if (isQuotesPanel(next)) {
    refreshChartsLayout();
  } else if (next === "news") {
    syncNewsGroupUi();
    if (!newsBootstrapped[newsGroup]) {
      newsBootstrapped[newsGroup] = true;
      loadNewsGroup(newsGroup, { refresh: false });
    }
  } else if (next === "emotion") {
    syncEmotionHubLayout();
    if (!emotionBootstrapped[emotionSource]) {
      emotionBootstrapped[emotionSource] = true;
      loadAllEmotion({ refresh: false });
    } else {
      syncEmotionSourceUi();
    }
  }
}

function setupMainTabs() {
  if (!els.companyMainTabs || els.companyMainTabs.dataset.bound === "1") return;
  els.companyMainTabs.dataset.bound = "1";

  els.companyMainTabs.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-panel]");
    if (!tab || !els.companyMainTabs.contains(tab)) return;
    switchMainPanel(tab.getAttribute("data-panel") || "");
  });

  if (els.refreshNewsBtn) {
    els.refreshNewsBtn.hidden = activeMainPanel !== "news";
  }
  if (els.refreshEmotionBtn) {
    els.refreshEmotionBtn.hidden = activeMainPanel !== "emotion";
  }
}

function setupBackLink() {
  if (industry) {
    els.backLink.href = `/?industry=${encodeURIComponent(industry)}`;
  } else {
    els.backLink.href = "/";
  }
}

/* ---------- 行情图表 ---------- */

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function fmtNum(n, digits = 2) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  return Number(n).toFixed(digits);
}

function fmtPct(n, digits = 2) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  return `${Number(n).toFixed(digits)}%`;
}

function fmtVol(n) {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  const v = Number(n);
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return String(Math.round(v));
}

function downsampleTicks(items, maxN) {
  if (!Array.isArray(items) || items.length <= maxN) return items;
  const last = Math.max(2, maxN) - 1;
  const step = (items.length - 1) / last;
  const out = [];
  for (let i = 0; i < last; i += 1) {
    out.push(items[Math.round(i * step)]);
  }
  out.push(items[items.length - 1]);
  return out;
}

function shortTimeLabel(t, mode) {
  const s = String(t || "");
  if (mode === "ticks") {
    if (s.length >= 16) return s.slice(11, 16);
    if (s.length >= 8 && s.includes(":")) {
      const hm = s.match(/(\d{1,2}:\d{2})/);
      if (hm) return hm[1].padStart(5, "0");
    }
    if (s.length >= 10) return s.slice(5, 10);
    return s;
  }
  // 分钟 K：2026-08-19 15:00 → 08-19 15:00
  if (isMinuteKline(mode)) {
    if (s.length >= 16) return `${s.slice(5, 10)} ${s.slice(11, 16)}`;
    if (s.length >= 10) return s.slice(5, 10);
    return s;
  }
  if (s.length >= 10) return s.slice(0, 10);
  return s;
}

function dayBreakIndices(items) {
  const breaks = [];
  for (let i = 0; i < items.length; i += 1) {
    if (i === 0) {
      breaks.push(i);
      continue;
    }
    const a = String(items[i - 1].time || "").slice(0, 10);
    const b = String(items[i].time || "").slice(0, 10);
    if (a && b && a !== b) breaks.push(i);
  }
  return breaks;
}

function setChartSource(text) {
  if (els.chartMeta) els.chartMeta.textContent = text || "";
}

function setChartStatus(message, { empty = false } = {}) {
  if (els.chartEmpty) {
    els.chartEmpty.textContent = empty ? message || "暂无走势数据" : "暂无走势数据";
    els.chartEmpty.classList.toggle("hidden", !empty);
  }
}

function chartViewWindow() {
  const all = chartState.allItems || [];
  const total = all.length;
  let size = Number(chartState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(chartState.viewStart) || 0), maxStart);
  return {
    all,
    total,
    size,
    maxStart,
    start,
    items: total ? all.slice(start, start + size) : [],
  };
}

function chartMinViewSize(total, { ticks = false } = {}) {
  if (total <= 1) return Math.max(1, total);
  if (ticks) return Math.min(total, 36);
  return Math.min(total, 20);
}

function refreshChartWindowStatus() {
  if (!(chartState.allItems || []).length) return;
  setChartSource(chartState.source || "");
}

function setChartViewStart(nextStart, { render = true, hoverIndex = null } = {}) {
  const { maxStart } = chartViewWindow();
  const start = Math.min(Math.max(0, Math.round(nextStart)), maxStart);
  if (start === chartState.viewStart && chartState.items.length) {
    syncChartScrollBar();
    if (render) renderChart(hoverIndex);
    return start;
  }
  chartState.viewStart = start;
  const win = chartViewWindow();
  chartState.items = win.items;
  syncChartScrollBar();
  if (render) renderChart(hoverIndex);
  propagateLinkedAxis("kline");
  return start;
}

/** 以横轴比例 anchorRatio(0~1) 为锚点缩放可视点数。factor>1 显示更多，factor<1 放大。 */
function zoomChartViewport(anchorRatio, factor, { render = true } = {}) {
  const total = (chartState.allItems || []).length;
  if (total <= 1) return false;
  const win = chartViewWindow();
  const minSize = chartMinViewSize(total, { ticks: false });
  const ratio = Math.min(1, Math.max(0, Number(anchorRatio) || 0.5));
  let nextSize = Math.round(win.size * factor);
  nextSize = Math.max(minSize, Math.min(total, nextSize));
  if (nextSize === win.size) return false;

  const anchorIndex = win.start + ratio * win.size;
  let nextStart = Math.round(anchorIndex - ratio * nextSize);
  nextStart = Math.max(0, Math.min(nextStart, total - nextSize));

  chartState.viewSize = nextSize;
  chartState.viewStart = nextStart;
  chartState.items = chartViewWindow().items;
  syncChartScrollBar();
  refreshChartWindowStatus();
  if (render) renderChart();
  propagateLinkedAxis("kline");
  return true;
}

function syncChartScrollBar() {
  const bar = els.chartScrollBar;
  const wrap = els.chartAxisScroll;
  if (!bar) return;
  const { maxStart, start, total, size } = chartViewWindow();
  const canScroll = total > size && maxStart > 0;
  if (wrap) wrap.classList.toggle("is-disabled", !canScroll);
  bar.disabled = !canScroll;
  bar.min = "0";
  bar.max = String(Math.max(0, maxStart));
  bar.value = String(start);
  // 滑块宽度随可视比例变化（WebKit）
  const ratio = total > 0 ? Math.min(1, size / total) : 1;
  const thumbPx = Math.max(28, Math.round(48 + ratio * 72));
  bar.style.setProperty("--thumb-w", `${thumbPx}px`);
}

function resetChartViewport(allItems, modeConf) {
  chartState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = chartState.allItems.length;
  let viewSize = Number(modeConf?.viewSize);
  if (!Number.isFinite(viewSize) || viewSize <= 0) {
    viewSize = total;
  }
  chartState.viewSize = viewSize;
  chartState.viewStart = Math.max(0, total - (viewSize > 0 && viewSize < total ? viewSize : total));
  chartState.items = chartViewWindow().items;
  syncChartScrollBar();
}

let linkedAxisLock = false;

function itemAxisDate(d) {
  const s = String(d?.time || "").trim();
  if (s.length >= 10) return s.slice(0, 10);
  return s;
}

function visibleAxisRange(items) {
  if (!Array.isArray(items) || !items.length) return null;
  const start = itemAxisDate(items[0]);
  const end = itemAxisDate(items[items.length - 1]);
  if (!start || !end) return null;
  return start <= end ? { start, end } : { start: end, end: start };
}

function viewportFromAxisRange(allItems, range) {
  if (!Array.isArray(allItems) || !allItems.length || !range) return null;
  const { start, end } = range;
  let lo = 0;
  let hi = allItems.length - 1;
  while (lo < allItems.length && itemAxisDate(allItems[lo]) < start) lo += 1;
  while (hi >= lo && itemAxisDate(allItems[hi]) > end) hi -= 1;
  if (hi < lo) return null;
  return { viewStart: lo, viewSize: hi - lo + 1 };
}

function klineJoinsLinkedAxis() {
  return !isMinuteKline(chartState.mode);
}

function applyLinkedRangeToKline(range) {
  const vp = viewportFromAxisRange(chartState.allItems, range);
  if (!vp) return;
  chartState.viewStart = vp.viewStart;
  chartState.viewSize = vp.viewSize;
  chartState.items = chartViewWindow().items;
  syncChartScrollBar();
  if (chartState.allItems.length) refreshChartWindowStatus();
  renderChart();
}

function applyLinkedRangeToPe(range) {
  const vp = viewportFromAxisRange(peState.allItems, range);
  if (!vp) return;
  peState.viewStart = vp.viewStart;
  peState.viewSize = vp.viewSize;
  peState.items = peViewWindow().items;
  syncPeScrollBar();
  hidePeHoverCard();
  if (!peState.allItems.length) {
    renderPeChart();
    return;
  }
  const hasValue = (peState.items || []).some((d) => peValue(d) != null);
  if (!hasValue) setPeStatus(peEmptyHint(), { empty: true });
  else {
    setPeStatus("");
    refreshPeWindowStatus();
  }
  renderPeChart();
}

function applyLinkedRangeToTurnover(range) {
  const vp = viewportFromAxisRange(turnoverState.allItems, range);
  if (!vp) return;
  turnoverState.viewStart = vp.viewStart;
  turnoverState.viewSize = vp.viewSize;
  turnoverState.items = turnoverViewWindow().items;
  syncTurnoverScrollBar();
  hideTurnoverHoverCard();
  if (!turnoverState.allItems.length) {
    renderTurnoverChart();
    return;
  }
  const hasValue = (turnoverState.items || []).some((d) => turnoverValue(d) != null);
  if (!hasValue) setTurnoverStatus("暂无换手率数据", { empty: true });
  else {
    setTurnoverStatus("");
    refreshTurnoverWindowStatus();
  }
  renderTurnoverChart();
}

function propagateLinkedAxis(source) {
  if (linkedAxisLock) return;
  if (source === "kline" && !klineJoinsLinkedAxis()) return;
  const items =
    source === "kline" ? chartState.items : source === "pe" ? peState.items : turnoverState.items;
  const range = visibleAxisRange(items);
  if (!range) return;
  linkedAxisLock = true;
  try {
    if (source !== "kline" && klineJoinsLinkedAxis()) applyLinkedRangeToKline(range);
    if (source !== "pe") applyLinkedRangeToPe(range);
    if (source !== "turnover") applyLinkedRangeToTurnover(range);
  } finally {
    linkedAxisLock = false;
  }
}

function chartLayout(w, h, { pctAxis = false, compact = false, combo = false } = {}) {
  const pad = {
    top: 8,
    right: pctAxis ? 52 : 8,
    bottom: compact ? 20 : 22,
    left: 52,
  };
  const innerW = Math.max(10, w - pad.left - pad.right);
  const innerH = Math.max(10, h - pad.top - pad.bottom);
  if (!combo) {
    const volH = Math.max(36, Math.floor(innerH * 0.16));
    const gap = 10;
    const priceH = Math.max(100, innerH - volH - gap);
    return {
      pad,
      price: { x: pad.left, y: pad.top, w: innerW, h: priceH },
      volume: {
        x: pad.left,
        y: pad.top + priceH + gap,
        w: innerW,
        h: volH,
      },
    };
  }
  const gap = 8;
  const volH = Math.max(32, Math.floor(innerH * 0.12));
  const peH = Math.max(72, Math.floor(innerH * 0.24));
  const priceH = Math.max(110, innerH - volH - peH - gap * 2);
  let y = pad.top;
  const price = { x: pad.left, y, w: innerW, h: priceH };
  y += priceH + gap;
  const volume = { x: pad.left, y, w: innerW, h: volH };
  y += volH + gap;
  const pe = { x: pad.left, y, w: innerW, h: peH };
  return { pad, price, volume, pe };
}

function alignMetricsToKline(klineItems, metricItems) {
  const map = new Map();
  for (const d of metricItems || []) {
    const key = itemAxisDate(d);
    if (key) map.set(key, d);
  }
  return (klineItems || []).map((d) => {
    const hit = map.get(itemAxisDate(d));
    return hit ? { ...hit, time: d.time } : { time: d.time };
  });
}

function metricValueAtTime(allItems, getValue, time) {
  const key = itemAxisDate({ time });
  if (!key || !Array.isArray(allItems)) return null;
  for (let i = allItems.length - 1; i >= 0; i -= 1) {
    if (itemAxisDate(allItems[i]) === key) return getValue(allItems[i]);
  }
  return null;
}

/** 取 1/2/5×10^n 漂亮步长 */
function niceNum(range, round) {
  const r = Math.abs(Number(range)) || 1;
  const exp = Math.floor(Math.log10(r));
  const frac = r / 10 ** exp;
  let nice;
  if (round) {
    if (frac < 1.5) nice = 1;
    else if (frac < 3) nice = 2;
    else if (frac < 7) nice = 5;
    else nice = 10;
  } else if (frac <= 1) nice = 1;
  else if (frac <= 2) nice = 2;
  else if (frac <= 5) nice = 5;
  else nice = 10;
  return nice * 10 ** exp;
}

function roundToStep(value, step) {
  if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) return value;
  const decimals = Math.min(8, Math.max(0, Math.ceil(-Math.log10(step) + 1)));
  const n = Math.round(value / step) * step;
  return Number(n.toFixed(decimals));
}

function fmtAxisPrice(value, step) {
  if (!Number.isFinite(value)) return "-";
  let digits = 2;
  if (Number.isFinite(step) && step > 0) {
    if (step >= 1) digits = Math.abs(step % 1) < 1e-8 ? 0 : 2;
    else if (step >= 0.1) digits = 2;
    else if (step >= 0.01) digits = 2;
    else if (step >= 0.001) digits = 3;
    else digits = 4;
  }
  return value.toFixed(digits);
}

/**
 * 价格纵轴：视窗贴合真实高低（少留白），刻度取落在视窗内的漂亮数。
 * 避免为对齐整数价把范围撑大，否则波动会被压扁。
 * center 有值时（分时昨收）仅做上下对称，仍尽量贴合实际波幅。
 */
function buildPriceScale(
  dataMin,
  dataMax,
  { tickCount = 5, padRatio = 0.02, center = null } = {}
) {
  let lo = Number(dataMin);
  let hi = Number(dataMax);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    return { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], step: 0.25 };
  }
  if (hi < lo) {
    const t = lo;
    lo = hi;
    hi = t;
  }

  if (Number.isFinite(center)) {
    // 只按实际偏离昨收的幅度对称，最小约 0.15% 防止完全横盘时高度为 0
    const raw = Math.max(hi - center, center - lo);
    const floor = Math.max(Math.abs(center) * 0.0015, 0.01);
    const span = Math.max(raw, floor);
    lo = center - span;
    hi = center + span;
  }

  if (hi <= lo) {
    const d = Math.max(Math.abs(hi) * 0.005, 0.02);
    lo -= d;
    hi += d;
  }

  // 少量边距即可，过大只会让 K 线/分时显得更「平」
  const pad = Math.max((hi - lo) * padRatio, 0.005);
  lo -= pad;
  hi += pad;

  const target = Math.max(4, Math.min(7, tickCount));
  // round=false：倾向更小步长，少把视窗撑开
  let step = niceNum((hi - lo) / Math.max(1, target - 1), false);
  if (step < 0.01) step = 0.01;

  const ticks = [];
  const startI = Math.ceil(lo / step - 1e-9);
  const endI = Math.floor(hi / step + 1e-9);
  for (let i = startI; i <= endI; i += 1) {
    const v = roundToStep(i * step, step);
    if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) ticks.push(v);
  }

  // 刻度过密则加大步长，但仍不扩张 min/max
  let guard = 0;
  while (ticks.length > 8 && guard < 6) {
    guard += 1;
    step = niceNum(step * 1.8, false);
    if (step < 0.01) step = 0.01;
    ticks.length = 0;
    const a = Math.ceil(lo / step - 1e-9);
    const b = Math.floor(hi / step + 1e-9);
    for (let i = a; i <= b; i += 1) {
      const v = roundToStep(i * step, step);
      if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) ticks.push(v);
    }
  }

  // 至少两端有可读刻度：不足时补视窗边界（按步长精度格式化）
  if (ticks.length === 0) {
    ticks.push(roundToStep(lo, step), roundToStep(hi, step));
  } else if (ticks.length === 1) {
    if (Math.abs(ticks[0] - lo) > Math.abs(ticks[0] - hi)) ticks.unshift(roundToStep(lo, step));
    else ticks.push(roundToStep(hi, step));
  }

  return {
    min: lo,
    max: hi,
    ticks,
    step,
  };
}

function priceScaleTickCount(priceH) {
  return Math.max(4, Math.min(7, Math.round(Number(priceH) / 42) || 5));
}

function drawGrid(ctx, rect, yTicks, xTicks, colors) {
  ctx.save();
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  for (const y of yTicks) {
    ctx.beginPath();
    ctx.moveTo(rect.x, y);
    ctx.lineTo(rect.x + rect.w, y);
    ctx.stroke();
  }
  for (const x of xTicks) {
    ctx.beginPath();
    ctx.moveTo(x, rect.y);
    ctx.lineTo(x, rect.y + rect.h);
    ctx.stroke();
  }
  ctx.restore();
}

/** A 股分时横轴：开盘竞价 09:15 → 盘后 15:30，午休压缩不占宽度。 */
const SESSION_SEGMENTS = [
  { start: 9 * 60 + 15, end: 9 * 60 + 25 },
  { start: 9 * 60 + 30, end: 11 * 60 + 30 },
  { start: 13 * 60, end: 15 * 60 },
  { start: 15 * 60 + 5, end: 15 * 60 + 30 },
];

const SESSION_X_LABELS = [
  { label: "09:15", minutes: 9 * 60 + 15, align: "left" },
  { label: "10:30", minutes: 10 * 60 + 30, align: "center" },
  { label: "11:30", minutes: 11 * 60 + 30, align: "center" },
  { label: "14:00", minutes: 14 * 60, align: "center" },
  { label: "15:00", minutes: 15 * 60, align: "center" },
  { label: "15:30", minutes: 15 * 60 + 30, align: "right" },
];

function sessionDuration() {
  return SESSION_SEGMENTS.reduce((sum, seg) => sum + (seg.end - seg.start), 0);
}

function parseClockMinutes(value) {
  const s = String(value || "");
  const m = s.match(/(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?/);
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]) + Number(m[3] || 0) / 60;
}

function sessionOffset(minutes) {
  if (!Number.isFinite(minutes)) return null;
  let acc = 0;
  for (const seg of SESSION_SEGMENTS) {
    if (minutes <= seg.start) return acc;
    if (minutes <= seg.end) return acc + (minutes - seg.start);
    acc += seg.end - seg.start;
  }
  return acc;
}

function sessionXAt(minutes, layout) {
  const off = sessionOffset(minutes);
  const total = sessionDuration() || 1;
  const ratio = off == null ? 0 : Math.min(1, Math.max(0, off / total));
  return layout.price.x + ratio * layout.price.w;
}

function cnNowParts(date = new Date()) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const map = {};
  for (const part of fmt.formatToParts(date)) {
    if (part.type !== "literal") map[part.type] = part.value;
  }
  const weekdayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const weekday = weekdayMap[map.weekday] ?? 0;
  const minutes = Number(map.hour) * 60 + Number(map.minute) + Number(map.second || 0) / 60;
  return {
    weekday,
    minutes,
    dateStr: `${map.year}-${map.month}-${map.day}`,
    clockStr: `${map.hour}:${map.minute}:${map.second || "00"}`,
  };
}

function cnMarketPhase() {
  const { weekday, minutes } = cnNowParts();
  if (weekday === 0 || weekday === 6) return "closed";
  if (
    (minutes >= 9 * 60 + 15 && minutes < 9 * 60 + 25) ||
    (minutes >= 9 * 60 + 30 && minutes < 11 * 60 + 30) ||
    (minutes >= 13 * 60 && minutes < 15 * 60) ||
    (minutes >= 15 * 60 + 5 && minutes < 15 * 60 + 31)
  ) {
    return "live";
  }
  if (minutes >= 11 * 60 + 30 && minutes < 13 * 60) return "lunch";
  return "closed";
}

function drawSessionTimeLabels(ctx, layout, colors) {
  const { volume } = layout;
  ctx.save();
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.fillStyle = colors.muted;
  ctx.textBaseline = "top";
  for (const item of SESSION_X_LABELS) {
    ctx.textAlign = item.align || "center";
    ctx.fillText(item.label, sessionXAt(item.minutes, layout), volume.y + volume.h + 6);
  }
  ctx.restore();
}

function drawAxesLabels(ctx, layout, priceScale, items, mode, colors, { preClose = null, yFormat = null, skipTimeLabels = false } = {}) {
  const { price, volume } = layout;
  const range = priceScale.max - priceScale.min || 1;
  const ticks = Array.isArray(priceScale.ticks) ? priceScale.ticks : [];
  const yOf = (val) => price.y + ((priceScale.max - val) / range) * price.h;

  ctx.save();
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (const val of ticks) {
    const y = yOf(val);
    if (y < price.y - 1 || y > price.y + price.h + 1) continue;
    if (Number.isFinite(preClose)) {
      if (val > preClose) ctx.fillStyle = colors.up;
      else if (val < preClose) ctx.fillStyle = colors.down;
      else ctx.fillStyle = colors.muted;
    } else {
      ctx.fillStyle = colors.muted;
    }
    ctx.fillText(yFormat ? yFormat(val, priceScale.step) : fmtAxisPrice(val, priceScale.step), price.x - 6, y);
  }

  // 分时：右侧涨跌幅刻度放在图外，避免挡住走势
  if (mode === "ticks" && Number.isFinite(preClose) && preClose) {
    ctx.textAlign = "left";
    for (const val of ticks) {
      const y = yOf(val);
      if (y < price.y - 1 || y > price.y + price.h + 1) continue;
      const pct = ((val - preClose) / preClose) * 100;
      if (pct > 0) ctx.fillStyle = colors.up;
      else if (pct < 0) ctx.fillStyle = colors.down;
      else ctx.fillStyle = colors.muted;
      const sign = pct > 0 ? "+" : "";
      ctx.fillText(`${sign}${pct.toFixed(2)}%`, price.x + price.w + 6, y);
    }
  }

  if (skipTimeLabels) {
    ctx.restore();
    return;
  }

  ctx.fillStyle = colors.muted;
  ctx.textBaseline = "top";
  const n = items.length;
  if (n > 0) {
    let idxs;
    if (isMinuteKline(mode)) {
      const breaks = dayBreakIndices(items);
      if (breaks.length >= 2) {
        idxs = breaks.length <= 5 ? breaks.slice() : [
          breaks[0],
          breaks[Math.floor(breaks.length / 2)],
          breaks[breaks.length - 1],
        ];
        if (idxs[idxs.length - 1] !== n - 1) idxs.push(n - 1);
      } else {
        idxs = [0, Math.floor((n - 1) / 2), n - 1];
      }
    } else {
      idxs = [0, Math.floor((n - 1) / 2), n - 1];
    }
    const seen = new Set();
    const plotLeft = price.x;
    const plotRight = price.x + price.w;
    for (const i of idxs) {
      if (seen.has(i)) continue;
      seen.add(i);
      const label = shortTimeLabel(items[i].time, mode);
      let x = plotLeft + ((i + 0.5) / n) * price.w;
      // 首尾标签贴边对齐，避免被 canvas 裁掉
      if (i === 0) {
        ctx.textAlign = "left";
        x = plotLeft;
      } else if (i === n - 1) {
        ctx.textAlign = "right";
        x = plotRight;
      } else {
        ctx.textAlign = "center";
        const approxHalf = Math.min(48, label.length * 3.4);
        x = Math.min(plotRight - approxHalf, Math.max(plotLeft + approxHalf, x));
      }
      ctx.fillText(label, x, volume.y + volume.h + 6);
    }
  }
  ctx.restore();
}

function paintChartFrame(ctx, w, h, colors) {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "rgba(4, 8, 14, 0.15)";
  ctx.fillRect(0, 0, w, h);
}

function sessionVolumeBuckets(items) {
  const buckets = [];
  const index = new Map();
  for (const d of items) {
    const mins = parseClockMinutes(d.time);
    if (mins == null) continue;
    const key = Math.floor(mins);
    let bucket = index.get(key);
    if (!bucket) {
      bucket = {
        minutes: key + 0.5,
        volume: 0,
        price: Number(d.price),
        prev: null,
      };
      index.set(key, bucket);
      buckets.push(bucket);
    }
    bucket.volume += Number(d.volume) || 0;
    bucket.prev = Number.isFinite(bucket.price) ? bucket.price : bucket.prev;
    bucket.price = Number(d.price);
  }
  return buckets;
}

function drawRealtimeChart(ctx, layout, items, preClose, mode, colors, hoverIndex, opts = {}) {
  const sessionAxis = Boolean(opts.sessionAxis);
  const nowMinutes = Number.isFinite(opts.nowMinutes) ? opts.nowMinutes : null;
  const n = items.length;
  if (!n && !sessionAxis) return;

  const prices = items.map((d) => Number(d.price)).filter(Number.isFinite);
  let minP = prices.length ? Math.min(...prices) : Number.isFinite(preClose) ? preClose : 0;
  let maxP = prices.length ? Math.max(...prices) : Number.isFinite(preClose) ? preClose : 1;
  if (Number.isFinite(preClose)) {
    minP = Math.min(minP, preClose);
    maxP = Math.max(maxP, preClose);
  }
  const { price, volume } = layout;
  const priceScale = buildPriceScale(minP, maxP, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.015,
    center: Number.isFinite(preClose) ? preClose : null,
  });

  const xAt = (i) => {
    if (!sessionAxis) return price.x + ((i + 0.5) / Math.max(1, n)) * price.w;
    const mins = parseClockMinutes(items[i]?.time);
    return mins == null ? price.x : sessionXAt(mins, layout);
  };
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

  const yTicks = (priceScale.ticks || []).map(yAt);
  const xTicks = sessionAxis
    ? SESSION_X_LABELS.map((item) => sessionXAt(item.minutes, layout))
    : [0, 0.5, 1].map((t) => price.x + price.w * t);
  drawGrid(ctx, price, yTicks, xTicks, colors);
  drawGrid(ctx, volume, [volume.y, volume.y + volume.h], xTicks, colors);

  if (Number.isFinite(preClose)) {
    const y = yAt(preClose);
    ctx.save();
    ctx.strokeStyle = colors.ref;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(price.x, y);
    ctx.lineTo(price.x + price.w, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  if (sessionAxis) {
    const buckets = sessionVolumeBuckets(items);
    const maxVol = buckets.reduce((m, b) => Math.max(m, b.volume || 0), 1);
    const barW = Math.max(1, (price.w / sessionDuration()) * 0.75);
    for (const bucket of buckets) {
      const h = (bucket.volume / maxVol) * volume.h;
      const x = sessionXAt(bucket.minutes, layout) - barW / 2;
      const up = Number.isFinite(bucket.prev) ? bucket.price >= bucket.prev : true;
      ctx.fillStyle = up ? colors.upSoft : colors.downSoft;
      ctx.fillRect(x, volume.y + volume.h - h, barW, h);
    }
  } else if (n) {
    const vols = items.map((d) => Number(d.volume) || 0);
    const maxVol = Math.max(...vols, 1);
    const barW = Math.max(1, (price.w / n) * 0.7);
    for (let i = 0; i < n; i += 1) {
      const v = vols[i];
      const h = (v / maxVol) * volume.h;
      const x = xAt(i) - barW / 2;
      const prev = i > 0 ? Number(items[i - 1].price) : preClose;
      const cur = Number(items[i].price);
      const up = Number.isFinite(prev) ? cur >= prev : true;
      ctx.fillStyle = up ? colors.upSoft : colors.downSoft;
      ctx.fillRect(x, volume.y + volume.h - h, barW, h);
    }
  }

  if (n) {
    ctx.beginPath();
    let startedAvg = false;
    for (let i = 0; i < n; i += 1) {
      const avg = Number(items[i].avg_price);
      if (!Number.isFinite(avg)) continue;
      const x = xAt(i);
      const y = yAt(avg);
      if (!startedAvg) {
        ctx.moveTo(x, y);
        startedAvg = true;
      } else ctx.lineTo(x, y);
    }
    if (startedAvg) {
      ctx.strokeStyle = colors.avg;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }

    ctx.beginPath();
    let startedPrice = false;
    let firstX = null;
    let lastX = null;
    for (let i = 0; i < n; i += 1) {
      const p = Number(items[i].price);
      if (!Number.isFinite(p)) continue;
      const x = xAt(i);
      const y = yAt(p);
      if (!startedPrice) {
        ctx.moveTo(x, y);
        startedPrice = true;
        firstX = x;
      } else ctx.lineTo(x, y);
      lastX = x;
    }
    if (startedPrice) {
      ctx.strokeStyle = colors.accent;
      ctx.lineWidth = 1.6;
      ctx.stroke();

      ctx.beginPath();
      startedPrice = false;
      for (let i = 0; i < n; i += 1) {
        const p = Number(items[i].price);
        if (!Number.isFinite(p)) continue;
        const x = xAt(i);
        const y = yAt(p);
        if (!startedPrice) {
          ctx.moveTo(x, y);
          startedPrice = true;
        } else ctx.lineTo(x, y);
      }
      ctx.lineTo(lastX, price.y + price.h);
      ctx.lineTo(firstX, price.y + price.h);
      ctx.closePath();
      const gradient = ctx.createLinearGradient(0, price.y, 0, price.y + price.h);
      gradient.addColorStop(0, "rgba(42, 212, 184, 0.18)");
      gradient.addColorStop(1, "rgba(42, 212, 184, 0)");
      ctx.fillStyle = gradient;
      ctx.fill();
    }
  }

  if (sessionAxis && nowMinutes != null) {
    const x = sessionXAt(nowMinutes, layout);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, volume.y + volume.h);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    const p = Number(items[hoverIndex].price);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, volume.y + volume.h);
    ctx.stroke();
    if (Number.isFinite(p)) {
      const y = yAt(p);
      ctx.beginPath();
      ctx.moveTo(price.x, y);
      ctx.lineTo(price.x + price.w, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = colors.accent;
      ctx.beginPath();
      ctx.arc(x, y, 3.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  drawAxesLabels(ctx, layout, priceScale, items, mode, colors, {
    preClose,
    skipTimeLabels: sessionAxis,
  });
  if (sessionAxis) drawSessionTimeLabels(ctx, layout, colors);
}

function drawMaLines(ctx, maVisible, yAt, xAt, n) {
  for (const line of KLINE_MA_LINES) {
    const vals = maVisible[line.key] || [];
    ctx.save();
    ctx.strokeStyle = line.color;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i += 1) {
      const v = maPoint(vals, i);
      if (v == null) {
        started = false;
        continue;
      }
      const x = xAt(i);
      const y = yAt(v);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    ctx.restore();
  }
}

function drawKlineChart(ctx, layout, items, mode, colors, hoverIndex) {
  const n = items.length;
  if (!n) return;

  const { visible: maVisible } = getKlineMaBundle();
  const highs = items.map((d) => Number(d.high)).filter(Number.isFinite);
  const lows = items.map((d) => Number(d.low)).filter(Number.isFinite);
  const maNums = [];
  for (const line of KLINE_MA_LINES) {
    const vals = maVisible[line.key] || [];
    for (let i = 0; i < vals.length; i += 1) {
      const v = maPoint(vals, i);
      if (v != null) maNums.push(v);
    }
  }
  const lo = Math.min(...lows, ...(maNums.length ? maNums : lows));
  const hi = Math.max(...highs, ...(maNums.length ? maNums : highs));
  const { price, volume } = layout;
  const priceScale = buildPriceScale(lo, hi, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.02,
  });
  const vols = items.map((d) => Number(d.volume) || 0);
  const maxVol = Math.max(...vols, 1);
  const slot = price.w / n;
  const bodyW = Math.max(2, Math.min(14, slot * 0.62));

  const xAt = (i) => price.x + (i + 0.5) * slot;
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

  const yTicks = (priceScale.ticks || []).map(yAt);
  let xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
  if (isMinuteKline(mode)) {
    const breaks = dayBreakIndices(items);
    if (breaks.length >= 2) {
      xTicks = breaks.map((i) => price.x + (i / Math.max(n, 1)) * price.w);
    }
  }
  drawGrid(ctx, price, yTicks, xTicks, colors);
  drawGrid(ctx, volume, [volume.y, volume.y + volume.h], xTicks, colors);

  for (let i = 0; i < n; i += 1) {
    const d = items[i];
    const o = Number(d.open);
    const c = Number(d.close);
    const h = Number(d.high);
    const l = Number(d.low);
    if (![o, c, h, l].every(Number.isFinite)) continue;
    const up = c >= o;
    const color = up ? colors.up : colors.down;
    const soft = up ? colors.upSoft : colors.downSoft;
    const x = xAt(i);

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, yAt(h));
    ctx.lineTo(x, yAt(l));
    ctx.stroke();

    const y1 = yAt(Math.max(o, c));
    const y2 = yAt(Math.min(o, c));
    const bh = Math.max(1, y2 - y1);
    if (up) {
      ctx.strokeRect(x - bodyW / 2, y1, bodyW, bh);
    } else {
      ctx.fillRect(x - bodyW / 2, y1, bodyW, bh);
    }

    const vh = (vols[i] / maxVol) * volume.h;
    ctx.fillStyle = soft;
    ctx.fillRect(x - bodyW / 2, volume.y + volume.h - vh, bodyW, vh);
  }

  drawMaLines(ctx, maVisible, yAt, xAt, n);

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    const crossBottom = layout.pe ? layout.pe.y + layout.pe.h : volume.y + volume.h;
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, crossBottom);
    ctx.stroke();
    ctx.restore();
  }

  drawAxesLabels(ctx, layout, priceScale, items, mode, colors, {
    skipTimeLabels: Boolean(layout.pe),
  });
}

function chartColors() {
  return {
    accent: cssVar("--accent", "#2ad4b8"),
    muted: cssVar("--muted", "#8494a8"),
    up: cssVar("--up", "#ff5d6c"),
    down: cssVar("--down", "#3dd68c"),
    upSoft: "rgba(255, 93, 108, 0.45)",
    downSoft: "rgba(61, 214, 140, 0.45)",
    avg: cssVar("--accent-hot", "#f0b429"),
    grid: "rgba(42, 212, 184, 0.08)",
    ref: "rgba(132, 148, 168, 0.55)",
    cross: "rgba(232, 238, 247, 0.35)",
  };
}

function renderChart(hoverIndex = null) {
  const canvas = els.priceChart;
  const wrap = els.chartWrap;
  if (!canvas || !wrap) return;

  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(320, wrap.clientWidth || 640);
  const cssH = Math.max(240, wrap.clientHeight || 320);
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const colors = chartColors();
  paintChartFrame(ctx, cssW, cssH, colors);
  const items = chartState.items || [];
  if (!items.length) return;

  const combo = comboPanesEnabled();
  const layout = chartLayout(cssW, cssH, { combo });
  drawKlineChart(ctx, layout, items, chartState.mode, colors, hoverIndex);
  if (!combo || !layout.pe) return;

  const peColors = {
    accent: cssVar("--accent", "#2ad4b8"),
    muted: colors.muted,
    up: colors.up,
    down: colors.down,
    grid: colors.grid,
    cross: colors.cross,
  };
  const peItems = alignMetricsToKline(items, peState.allItems);
  const pePane = {
    price: layout.pe,
    volume: { x: layout.pe.x, y: layout.pe.y + layout.pe.h, w: layout.pe.w, h: 0 },
  };
  if (peItems.some((d) => peValue(d) != null)) {
    drawMetricChart(ctx, pePane, peItems, peValue, peColors, hoverIndex, {
      formatLabel: fmtNum,
      mode: chartState.mode,
      skipHoverHair: true,
      compactRefs: true,
    });
  } else {
    drawPaneLabel(ctx, layout.pe, peState.loading ? "估值加载中…" : "暂无估值", peColors);
  }
}

function drawPaneLabel(ctx, rect, text, colors) {
  if (!rect || !text) return;
  ctx.save();
  ctx.fillStyle = colors.muted || "#8494a8";
  ctx.font = '10px "JetBrains Mono", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "top";
  ctx.fillText(text, rect.x - 6, rect.y + 4);
  ctx.restore();
}

function klineLatestAbsIndex() {
  const all = chartState.allItems || [];
  return all.length ? all.length - 1 : -1;
}

function klineQuoteAbsIndex() {
  const all = chartState.allItems || [];
  const hover = chartState.hoverAbsIndex;
  if (hover != null && hover >= 0 && hover < all.length) return hover;
  return klineLatestAbsIndex();
}

function fillKlineQuoteCard(absIndex) {
  if (!els.chartHoverCard) return;
  const all = chartState.allItems || [];
  if (absIndex == null || absIndex < 0 || absIndex >= all.length) {
    els.chartHoverCard.classList.add("hidden");
    els.chartHoverCard.setAttribute("aria-hidden", "true");
    els.chartHoverCard.innerHTML = "";
    return;
  }
  const d = all[absIndex];

  const row = (label, valueHtml, valueCls = "") =>
    `<span class="chart-hover-item"><span class="k">${escapeHtml(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;

  const pctText = (pct) => {
    if (pct == null || !Number.isFinite(Number(pct))) return null;
    const n = Number(pct);
    const cls = n > 0 ? "change-up" : n < 0 ? "change-down" : "";
    const sign = n > 0 ? "+" : "";
    return { text: `${sign}${n.toFixed(2)}%`, cls: `chart-hover-pct ${cls}` };
  };

  let pct = Number(d.pct_chg);
  if (!Number.isFinite(pct) && absIndex > 0) {
    const prevClose = Number(all[absIndex - 1].close);
    const close = Number(d.close);
    if (Number.isFinite(prevClose) && prevClose && Number.isFinite(close)) {
      pct = ((close - prevClose) / prevClose) * 100;
    }
  }
  const closeCls =
    Number.isFinite(pct) && pct > 0
      ? "change-up"
      : Number.isFinite(pct) && pct < 0
        ? "change-down"
        : "";
  const p = pctText(pct);
  const { full: maFull } = getKlineMaBundle();
  const maRows = KLINE_MA_LINES.map((line) => {
    const v = maPoint(maFull[line.key] || [], absIndex);
    if (v == null) return "";
    return row(
      line.label,
      `<span style="color:${line.color}">${escapeHtml(fmtNum(v))}</span>`
    );
  }).filter(Boolean);
  const rows = [
    row("开盘", escapeHtml(fmtNum(d.open))),
    row("最低", escapeHtml(fmtNum(d.low))),
    row("最高", escapeHtml(fmtNum(d.high))),
    row("收盘", escapeHtml(fmtNum(d.close)), closeCls),
    p ? row("涨跌幅", escapeHtml(p.text), p.cls) : "",
    ...maRows,
    row("成交量", escapeHtml(fmtVol(d.volume))),
  ].filter(Boolean);
  if (comboPanesEnabled()) {
    const pe = metricValueAtTime(peState.allItems, peValue, d.time);
    if (pe != null) {
      rows.push(
        row(
          peSeriesConf().label,
          `<span style="color:var(--accent)">${escapeHtml(fmtNum(pe))}</span>`
        )
      );
    }
  }

  els.chartHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${escapeHtml(d.time || "")}</span>${rows.join("")}</div>`;
  showHoverCard();
}

function refreshKlineQuoteCard() {
  fillKlineQuoteCard(klineQuoteAbsIndex());
}

function hideHoverCard() {
  chartState.hoverAbsIndex = null;
  refreshKlineQuoteCard();
}

function showHoverCard() {
  if (!els.chartHoverCard) return;
  els.chartHoverCard.classList.remove("hidden");
  els.chartHoverCard.setAttribute("aria-hidden", "false");
}

function updateHoverLabel(index, evt = null) {
  const items = chartState.items || [];
  if (index == null || index < 0 || index >= items.length) {
    hideHoverCard();
    return;
  }
  chartState.hoverAbsIndex = (Number(chartState.viewStart) || 0) + index;
  fillKlineQuoteCard(chartState.hoverAbsIndex);
}

function pointerIndex(evt) {
  const canvas = els.priceChart;
  const wrap = els.chartWrap;
  const items = chartState.items || [];
  if (!canvas || !wrap || !items.length) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const layout = chartLayout(rect.width, rect.height, { combo: comboPanesEnabled() });
  if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
  const t = (x - layout.price.x) / layout.price.w;
  const idx = Math.min(items.length - 1, Math.max(0, Math.floor(t * items.length)));
  return idx;
}

function panChartByPixels(dx, canvasWidth) {
  const { size, maxStart } = chartViewWindow();
  if (maxStart <= 0 || size <= 0) return false;
  const layout = chartLayout(canvasWidth, 300);
  const barW = layout.price.w / size;
  if (barW <= 0) return false;
  // 右拖看更早，左拖看更新
  const deltaBars = Math.round(-dx / barW);
  if (!deltaBars) return false;
  setChartViewStart(chartState.viewStart + deltaBars, { render: true });
  return true;
}

/* ---------- 实时分时图 ---------- */

function setTicksChartStatus(message, { empty = false } = {}) {
  if (els.ticksChartMeta) els.ticksChartMeta.textContent = message || "";
  if (els.ticksChartEmpty) {
    els.ticksChartEmpty.textContent = empty ? message || "暂无走势数据" : "暂无走势数据";
    els.ticksChartEmpty.classList.toggle("hidden", !empty);
  }
}

function formatTicksDay(raw) {
  const s = String(raw || "").trim();
  if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return "";
}

function inferTicksTradeDate(data, items) {
  const fromApi = formatTicksDay(data?.day);
  if (fromApi) return fromApi;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const day = formatTicksDay(items[i]?.time);
    if (day) return day;
  }
  const now = cnNowParts();
  const phase = cnMarketPhase();
  if (phase !== "closed") return now.dateStr;
  if (now.weekday >= 1 && now.weekday <= 5 && now.minutes >= 15 * 60 + 30) return now.dateStr;
  return "";
}

function withTickAvg(items) {
  let pv = 0;
  let volSum = 0;
  return items.map((d) => {
    const price = Number(d.price);
    const vol = Number(d.volume) || 0;
    if (Number.isFinite(price) && vol > 0) {
      pv += price * vol;
      volSum += vol;
    }
    const avg = Number(d.avg_price);
    return {
      ...d,
      avg_price: Number.isFinite(avg) ? avg : volSum ? pv / volSum : price,
    };
  });
}

function downsampleTicksByTime(items, maxN = TICKS_DRAW_MAX) {
  if (!Array.isArray(items) || items.length <= maxN) return items;
  const last = Math.max(2, maxN) - 1;
  const out = [];
  let prev = -1;
  for (let i = 0; i < last; i += 1) {
    const idx = Math.round((i * (items.length - 1)) / last);
    if (idx === prev) continue;
    out.push(items[idx]);
    prev = idx;
  }
  if (prev !== items.length - 1) out.push(items[items.length - 1]);
  return out;
}

function tickRowKey(d) {
  return `${d.time}|${d.price}|${d.volume}|${d.count ?? ""}|${d.seq ?? ""}`;
}

function mergeTickItems(current, incoming) {
  if (!incoming.length) return current;
  if (!current.length) return incoming;
  const lastKey = tickRowKey(current[current.length - 1]);
  let idx = -1;
  for (let i = incoming.length - 1; i >= 0; i -= 1) {
    if (tickRowKey(incoming[i]) === lastKey) {
      idx = i;
      break;
    }
  }
  if (idx >= 0) return current.concat(incoming.slice(idx + 1));
  const lastT = parseClockMinutes(current[current.length - 1].time);
  const firstT = parseClockMinutes(incoming[0].time);
  if (lastT != null && firstT != null && firstT >= lastT) return current.concat(incoming);
  return incoming;
}

function applyTicksItems(rawItems) {
  const decorated = withTickAvg(Array.isArray(rawItems) ? rawItems : []);
  ticksState.allItems = decorated;
  ticksState.items = downsampleTicksByTime(decorated);
  ticksState.viewSize = ticksState.items.length;
  ticksState.viewStart = 0;
  syncTicksChartScrollBar();
}

function minuteBarsToTicks(bars) {
  if (!Array.isArray(bars) || !bars.length) {
    return { items: [], preClose: null, day: "", source: "" };
  }
  const lastDay = formatTicksDay(bars[bars.length - 1]?.time);
  const dayBars = lastDay
    ? bars.filter((b) => formatTicksDay(b.time) === lastDay)
    : bars.slice();
  const prevBars = lastDay
    ? bars.filter((b) => formatTicksDay(b.time) && formatTicksDay(b.time) < lastDay)
    : [];
  const prevClose = prevBars.length ? Number(prevBars[prevBars.length - 1].close) : null;
  const useAmount = dayBars.some((b) => Number.isFinite(Number(b.amount)));
  let pv = 0;
  let shares = 0;
  const items = dayBars.map((b) => {
    const price = Number(b.close);
    const vol = Number(b.volume) || 0;
    const amt = Number(b.amount);
    if (useAmount && Number.isFinite(amt) && amt > 0) {
      pv += amt;
      shares += vol * 100;
    } else if (Number.isFinite(price) && vol > 0) {
      pv += price * vol;
      shares += vol;
    }
    const clock = String(b.time || "").slice(11, 16) || b.time;
    return {
      time: clock,
      price,
      volume: vol,
      avg_price: shares ? pv / shares : price,
    };
  });
  return { items, preClose: Number.isFinite(prevClose) ? prevClose : null, day: lastDay };
}

function ticksChartViewWindow() {
  const all = ticksState.items || [];
  const total = all.length;
  return {
    all,
    total,
    size: total,
    maxStart: 0,
    start: 0,
    items: all,
  };
}

function refreshTicksLiveStatus() {
  const src = ticksState.source ? ` · ${ticksState.source}` : "";
  const date = ticksState.tradeDate ? ` · ${ticksState.tradeDate}` : "";
  const axis = "09:15–15:30";
  const clock = cnNowParts().clockStr;
  if (ticksState.phase === "live") {
    setTicksChartStatus(`实时 · ${clock} · 每秒刷新${src}`);
    return;
  }
  if (ticksState.phase === "lunch") {
    setTicksChartStatus(`午间休市 · ${axis}${date}${src}`);
    return;
  }
  const today = cnNowParts().dateStr;
  if (ticksState.tradeDate && ticksState.tradeDate === today) {
    setTicksChartStatus(`已收盘${date} · ${axis}${src}`);
    return;
  }
  setTicksChartStatus(`上一交易日${date} · ${axis}${src}`);
}

function refreshTicksChartWindowStatus() {
  if (ticksState.phase === "live") {
    refreshTicksLiveStatus();
    return;
  }
  const count = (ticksState.items || []).length;
  if (!count && !ticksState.tradeDate) return;
  refreshTicksLiveStatus();
}

function syncTicksChartScrollBar() {
  const bar = els.ticksChartScrollBar;
  const wrap = els.ticksChartAxisScroll;
  if (wrap) wrap.classList.add("is-disabled");
  if (!bar) return;
  bar.disabled = true;
  bar.min = "0";
  bar.max = "0";
  bar.value = "0";
}

function setTicksChartViewStart() {
  return 0;
}

function zoomTicksChartViewport() {
  return false;
}

function panTicksChartByPixels() {
  return false;
}

function ticksHoverIndex() {
  const items = ticksState.items || [];
  const t = ticksState.hoverTime;
  if (!t || !items.length) return null;
  let best = null;
  for (let i = 0; i < items.length; i += 1) {
    if (String(items[i].time) === t) return i;
    if (String(items[i].time) <= t) best = i;
  }
  return best;
}

function renderTicksChart(hoverIndex = undefined) {
  const canvas = els.ticksChart;
  const wrap = els.ticksChartWrap;
  if (!canvas || !wrap) return;

  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(240, wrap.clientWidth || 320);
  const cssH = Math.max(200, wrap.clientHeight || 280);
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const colors = chartColors();
  paintChartFrame(ctx, cssW, cssH, colors);
  const items = ticksState.items || [];
  const idx = hoverIndex === undefined ? ticksHoverIndex() : hoverIndex;
  const showPctAxis = Number.isFinite(ticksState.preClose) && ticksState.preClose;
  const layout = chartLayout(cssW, cssH, { pctAxis: showPctAxis, compact: true });
  drawRealtimeChart(ctx, layout, items, ticksState.preClose, "ticks", colors, idx, {
    sessionAxis: true,
    nowMinutes: ticksState.phase === "live" ? cnNowParts().minutes : null,
  });
}

function ticksLatestItem() {
  const all = ticksState.allItems || [];
  if (all.length) return all[all.length - 1];
  const items = ticksState.items || [];
  return items.length ? items[items.length - 1] : null;
}

function hideTicksHoverCard() {
  ticksState.hoverTime = null;
  fillTicksQuoteCard(ticksLatestItem());
}

function showTicksHoverCard() {
  if (!els.ticksChartHoverCard) return;
  els.ticksChartHoverCard.classList.remove("hidden");
  els.ticksChartHoverCard.setAttribute("aria-hidden", "false");
}

function fillTicksQuoteCard(d) {
  if (!els.ticksChartHoverCard) return;
  if (!d) {
    els.ticksChartHoverCard.classList.add("hidden");
    els.ticksChartHoverCard.setAttribute("aria-hidden", "true");
    els.ticksChartHoverCard.innerHTML = "";
    return;
  }
  const row = (label, valueHtml, valueCls = "") =>
    `<span class="chart-hover-item"><span class="k">${escapeHtml(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;

  let pct = null;
  const price = Number(d.price);
  if (Number.isFinite(ticksState.preClose) && Number.isFinite(price) && ticksState.preClose) {
    pct = ((price - ticksState.preClose) / ticksState.preClose) * 100;
  }
  const priceCls = pct > 0 ? "change-up" : pct < 0 ? "change-down" : "";
  const pctText =
    pct == null || !Number.isFinite(Number(pct))
      ? null
      : {
          text: `${pct > 0 ? "+" : ""}${Number(pct).toFixed(2)}%`,
          cls: `chart-hover-pct ${priceCls}`,
        };
  const avg = Number(d.avg_price);
  const rows = [
    row("现价", escapeHtml(fmtNum(d.price)), priceCls),
    Number.isFinite(avg) ? row("均价", escapeHtml(fmtNum(avg))) : "",
    pctText ? row("涨跌幅", escapeHtml(pctText.text), pctText.cls) : "",
    row("成交量", escapeHtml(fmtVol(d.volume))),
  ].filter(Boolean);

  els.ticksChartHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${escapeHtml(d.time || "")}</span>${rows.join("")}</div>`;
  showTicksHoverCard();
}

function updateTicksHoverLabel(index) {
  const items = ticksState.items || [];
  if (index == null || index < 0 || index >= items.length) {
    hideTicksHoverCard();
    return;
  }
  const d = items[index];
  ticksState.hoverTime = d.time || null;
  fillTicksQuoteCard(d);
}

function refreshTicksQuoteCard() {
  const hover = ticksHoverIndex();
  if (hover != null) updateTicksHoverLabel(hover);
  else fillTicksQuoteCard(ticksLatestItem());
}

function ticksPointerIndex(evt) {
  const canvas = els.ticksChart;
  const wrap = els.ticksChartWrap;
  const items = ticksState.items || [];
  if (!canvas || !wrap || !items.length) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const showPctAxis = Number.isFinite(ticksState.preClose) && ticksState.preClose;
  const layout = chartLayout(rect.width, rect.height, { pctAxis: showPctAxis, compact: true });
  if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
  let best = 0;
  for (let i = 0; i < items.length; i += 1) {
    const mins = parseClockMinutes(items[i].time);
    const tx = mins == null ? layout.price.x : sessionXAt(mins, layout);
    if (tx <= x) best = i;
    else break;
  }
  return best;
}

async function loadPreviousSessionTicks() {
  const qs = new URLSearchParams({
    code,
    period: "1m",
    adjust: "none",
    limit: "500",
  });
  const json = await api(`/api/stocks/line?${qs.toString()}`);
  const data = json.data || {};
  const converted = minuteBarsToTicks(data.items || []);
  let preClose = converted.preClose;
  if (!Number.isFinite(preClose)) {
    const n = Number(data.pre_price);
    preClose = Number.isFinite(n) ? n : null;
  }
  return {
    items: converted.items,
    preClose,
    source: data.source ? `${data.source}·1m` : "1m",
    day: converted.day,
  };
}

async function bootstrapTicksFromMinuteKline() {
  if (ticksState.allItems.length) return;
  try {
    const fallback = await loadPreviousSessionTicks();
    if (!fallback.items.length) return;
    applyTicksItems(fallback.items);
    ticksState.preClose = fallback.preClose;
    ticksState.source = fallback.source;
    ticksState.tradeDate = fallback.day;
    if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
    refreshTicksLiveStatus();
    refreshTicksQuoteCard();
    renderTicksChart();
  } catch {
    /* 1m 兜底失败不影响后续全量逐笔 */
  }
}

async function loadTicksChart({ silent = false } = {}) {
  if (!code || !els.ticksChart) return;
  if (ticksState.loading) return;
  ticksState.loading = true;
  ticksState.phase = cnMarketPhase();
  ticksState.live = ticksState.phase === "live";
  if (!silent) {
    setTicksChartStatus("正在加载实时…");
    hideTicksHoverCard();
  }

  if (ticksState.phase === "live" && !ticksState.allItems.length) {
    void bootstrapTicksFromMinuteKline();
  }

  try {
    const qs = new URLSearchParams({ code });
    if (ticksState.phase === "live") {
      qs.set("refresh", "1");
    }
    const json = await api(`/api/stocks/ticks?${qs.toString()}`);
    const data = json.data || {};
    let rawItems = Array.isArray(data.items) ? data.items : [];
    let preClose = Number(data.pre_price);
    let source = data.source || "";
    let tradeDate = inferTicksTradeDate(data, rawItems);

    if (!rawItems.length && ticksState.phase !== "live") {
      const fallback = await loadPreviousSessionTicks();
      rawItems = fallback.items;
      if (Number.isFinite(fallback.preClose)) preClose = fallback.preClose;
      source = fallback.source || source;
      tradeDate = fallback.day || tradeDate;
    }

    applyTicksItems(rawItems);
    ticksState.preClose = Number.isFinite(preClose) ? preClose : null;
    ticksState.source = source;
    ticksState.tradeDate = tradeDate || inferTicksTradeDate(data, ticksState.allItems);

    const count = ticksState.items.length;
    if (!count) {
      if (!silent) setTicksChartStatus("暂无走势数据", { empty: true });
      else setTicksChartStatus(ticksState.phase === "live" ? "实时 · 09:15–15:30 · 等待成交" : "暂无走势数据", {
        empty: ticksState.phase !== "live",
      });
      fillTicksQuoteCard(null);
      renderTicksChart();
      return;
    }
    if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
    refreshTicksChartWindowStatus();
    refreshTicksQuoteCard();
    renderTicksChart();
  } catch (err) {
    applyTicksItems([]);
    setTicksChartStatus(err.message || "实时加载失败", { empty: true });
    fillTicksQuoteCard(null);
    renderTicksChart();
  } finally {
    ticksState.loading = false;
  }
}

async function pollTicksLive() {
  if (!code || !els.ticksChart || !ticksState.live) return;
  if (ticksState.liveFetching) {
    ticksState.liveFetchPending = true;
    return;
  }

  ticksState.liveFetching = true;
  const gen = ++ticksState.liveFetchGen;
  const incremental = Boolean(ticksState.allItems.length);

  try {
    const qs = new URLSearchParams({ code, refresh: "1" });
    if (incremental) {
      qs.set("pos", String(TICKS_LIVE_POS));
    } else if (ticksState.loading) {
      return;
    }
    const json = await api(`/api/stocks/ticks?${qs.toString()}`);
    if (gen !== ticksState.liveFetchGen) return;

    const data = json.data || {};
    let rawItems = Array.isArray(data.items) ? data.items : [];
    let preClose = Number(data.pre_price);
    let source = data.source || "";
    let tradeDate = inferTicksTradeDate(data, rawItems);

    if (incremental) {
      rawItems = mergeTickItems(ticksState.allItems, rawItems);
    }
    if (!rawItems.length) return;

    applyTicksItems(rawItems);
    if (Number.isFinite(preClose)) ticksState.preClose = preClose;
    if (source) ticksState.source = source;
    ticksState.tradeDate = tradeDate || inferTicksTradeDate(data, ticksState.allItems);
    if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
    refreshTicksQuoteCard();
    if (isQuotesPanel()) {
      renderTicksChart();
    }
  } catch {
    /* 盘中轮询失败不打断 UI */
  } finally {
    ticksState.liveFetching = false;
    if (ticksState.liveFetchPending && ticksState.live) {
      ticksState.liveFetchPending = false;
      void pollTicksLive();
    }
  }
}

async function pollProfileLive() {
  if (!code || cnMarketPhase() !== "live") return;
  if (livePollState.profileFetching) {
    livePollState.profilePending = true;
    return;
  }
  livePollState.profileFetching = true;
  try {
    await loadProfile({ silent: true, refresh: true, liveOnly: true });
  } catch {
    /* ignore */
  } finally {
    livePollState.profileFetching = false;
    if (livePollState.profilePending && cnMarketPhase() === "live") {
      livePollState.profilePending = false;
      void pollProfileLive();
    }
  }
}

function onTicksMarketClock() {
  if (document.hidden || !code) return;
  const phase = cnMarketPhase();
  const wasLive = ticksState.live;
  ticksState.phase = phase;
  ticksState.live = phase === "live";

  if (phase === "live") {
    refreshTicksLiveStatus();
    if (isQuotesPanel() && els.ticksChart) {
      renderTicksChart();
    }
    void pollTicksLive();
    void pollProfileLive();
    return;
  }

  if (wasLive) {
    ticksState.liveFetchPending = false;
    livePollState.profilePending = false;
    if (els.ticksChart) {
      loadTicksChart({ silent: true });
    }
  }
}

function bindChartPaneInteractions({
  canvas,
  wrap,
  scrollBar,
  hideHover,
  updateHover,
  render,
  pointerIndexAt,
  panByPixels,
  viewWindow,
  setViewStart,
  zoomViewport,
  syncScrollBar,
  layoutPctAxis = () => false,
  layoutCompact = false,
  enablePanZoom = true,
}) {
  if (!canvas) return;

  if (scrollBar) {
    scrollBar.addEventListener("input", () => {
      hideHover();
      setViewStart(Number(scrollBar.value) || 0, { render: true });
    });
  }

  let hoverIdx = null;
  let pan = null;

  const onMove = (evt) => {
    if (pan) {
      const dx = evt.clientX - pan.lastX;
      if (Math.abs(evt.clientX - pan.originX) > 4) pan.moved = true;
      if (pan.moved && Math.abs(dx) >= 1) {
        hideHover();
        hoverIdx = null;
        panByPixels(dx, pan.width);
        pan.lastX = evt.clientX;
      }
      return;
    }
    const idx = pointerIndexAt(evt);
    if (idx === hoverIdx) return;
    hoverIdx = idx;
    updateHover(idx, evt);
    render(idx);
  };

  const onLeave = () => {
    if (pan) return;
    hoverIdx = null;
    hideHover();
    render();
  };

  const onDown = (evt) => {
    if (!enablePanZoom) return;
    if (evt.button != null && evt.button !== 0) return;
    const rect = canvas.getBoundingClientRect();
    pan = {
      originX: evt.clientX,
      lastX: evt.clientX,
      width: rect.width,
      moved: false,
    };
    wrap?.classList.add("is-panning");
    try {
      canvas.setPointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onUp = (evt) => {
    if (!pan) return;
    const wasPan = pan.moved;
    pan = null;
    wrap?.classList.remove("is-panning");
    try {
      canvas.releasePointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
    if (!wasPan) {
      const idx = pointerIndexAt(evt);
      hoverIdx = idx;
      updateHover(idx, evt);
      render(idx);
    } else {
      hideHover();
      hoverIdx = null;
      render();
    }
  };

  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointercancel", onUp);
  canvas.addEventListener("pointerleave", onLeave);

  canvas.addEventListener(
    "wheel",
    (evt) => {
      if (!enablePanZoom) return;
      const win = viewWindow();
      if (!win.total) return;
      evt.preventDefault();
      hideHover();
      hoverIdx = null;

      const rect = canvas.getBoundingClientRect();
      const layout = chartLayout(rect.width, rect.height, {
        pctAxis: layoutPctAxis(),
        compact: layoutCompact,
      });
      const x = evt.clientX - rect.left;
      let anchorRatio = 0.5;
      if (x >= layout.price.x && x <= layout.price.x + layout.price.w) {
        anchorRatio = (x - layout.price.x) / layout.price.w;
      }

      if (Math.abs(evt.deltaX) > Math.abs(evt.deltaY) * 1.15) {
        const { maxStart } = viewWindow();
        if (maxStart <= 0) return;
        const step = Math.max(1, Math.round(Math.abs(evt.deltaX) / 40));
        setViewStart(win.start + (evt.deltaX > 0 ? step : -step), { render: true });
        return;
      }

      const steps = Math.max(1, Math.min(5, Math.round(Math.abs(evt.deltaY) / 72) || 1));
      const base = evt.deltaY > 0 ? 1.14 : 1 / 1.14;
      zoomViewport(anchorRatio, base ** steps, { render: true });
    },
    { passive: false }
  );

  if (typeof ResizeObserver !== "undefined" && wrap) {
    let timer = 0;
    const ro = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        syncScrollBar?.();
        render(hoverIdx);
      }, 60);
    });
    ro.observe(wrap);
  } else {
    window.addEventListener("resize", () => {
      syncScrollBar?.();
      render(hoverIdx);
    });
  }
}

async function loadChart(mode = chartState.mode) {
  if (!code || !els.priceChart) return;
  const conf = CHART_MODES[mode] || CHART_MODES.day;
  chartState.mode = mode;
  chartState.kind = "kline";
  chartState.loading = true;
  syncChartModeSelect(mode);
  syncChartAdjustUi(mode);
  setChartSource("加载中…");
  setChartStatus(`正在加载${conf.label}…`);
  hideHoverCard();

  try {
    const qs = new URLSearchParams({
      code,
      period: conf.period,
      adjust: klineAdjustFor(mode),
      limit: String(conf.limit || 180),
    });
    const json = await api(`/api/stocks/line?${qs.toString()}`);
    const data = json.data || {};
    resetChartViewport(data.items || [], conf);
    chartState.preClose = null;
    chartState.source = data.source || "";

    const count = chartState.allItems.length;
    if (!count) {
      setChartSource("");
      setChartStatus("暂无走势数据", { empty: true });
      hideHoverCard();
      renderChart();
      return;
    }
    refreshChartWindowStatus();
    hideHoverCard();
    renderChart();
    propagateLinkedAxis("kline");
  } catch (err) {
    resetChartViewport([], conf);
    chartState.source = "";
    setChartSource("");
    setChartStatus(err.message || "走势加载失败", { empty: true });
    hideHoverCard();
    renderChart();
  } finally {
    chartState.loading = false;
  }
}

function setupChart() {
  if (!els.chartModeSelect || !els.priceChart) return;

  els.chartModeSelect.addEventListener("change", () => {
    const mode = els.chartModeSelect.value;
    if (!mode || mode === chartState.mode) return;
    loadChart(mode);
  });

  els.chartAdjustSelect?.addEventListener("change", () => {
    if (!isAdjustableKline(chartState.mode)) return;
    const adjust = els.chartAdjustSelect.value;
    if (!adjust || adjust === chartState.adjust) return;
    if (!["none", "qfq", "hfq"].includes(adjust)) return;
    chartState.adjust = adjust;
    syncChartAdjustUi();
    loadChart(chartState.mode);
  });

  syncChartModeSelect();
  syncChartAdjustUi();

  bindChartPaneInteractions({
    canvas: els.priceChart,
    wrap: els.chartWrap,
    scrollBar: els.chartScrollBar,
    hideHover: hideHoverCard,
    updateHover: updateHoverLabel,
    render: renderChart,
    pointerIndexAt: pointerIndex,
    panByPixels: panChartByPixels,
    viewWindow: chartViewWindow,
    setViewStart: setChartViewStart,
    zoomViewport: zoomChartViewport,
    syncScrollBar: syncChartScrollBar,
  });
}

function setupTicksChart() {
  if (!els.ticksChart) return;

  bindChartPaneInteractions({
    canvas: els.ticksChart,
    wrap: els.ticksChartWrap,
    scrollBar: els.ticksChartScrollBar,
    hideHover: hideTicksHoverCard,
    updateHover: updateTicksHoverLabel,
    render: renderTicksChart,
    pointerIndexAt: ticksPointerIndex,
    panByPixels: panTicksChartByPixels,
    viewWindow: ticksChartViewWindow,
    setViewStart: setTicksChartViewStart,
    zoomViewport: zoomTicksChartViewport,
    syncScrollBar: syncTicksChartScrollBar,
    layoutPctAxis: () => Number.isFinite(ticksState.preClose) && ticksState.preClose,
    layoutCompact: true,
    enablePanZoom: false,
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    if (cnMarketPhase() === "live") {
      void pollTicksLive();
      void pollProfileLive();
    }
  });
  window.setInterval(onTicksMarketClock, 1000);
  onTicksMarketClock();
}

/* ---------- 市盈率曲线 ---------- */

const PE_SERIES = {
  dyn: { key: "pe_dyn", label: "市盈率动" },
  ttm: { key: "pe_ttm", label: "市盈率TTM" },
  static: { key: "pe_static", label: "市盈率静" },
  pb: { key: "pb", label: "市净率" },
};

/** 未跟行情联动时（如分时 K 线）的默认窗口，接近日 K 默认 90 根。 */
const METRIC_FALLBACK_VIEW_SIZE = 90;

const peState = {
  series: "ttm",
  loading: false,
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: METRIC_FALLBACK_VIEW_SIZE,
  source: "",
};

function peSeriesConf() {
  return PE_SERIES[peState.series] || PE_SERIES.ttm;
}

function peValue(d) {
  const key = peSeriesConf().key;
  const n = Number(d?.[key]);
  return Number.isFinite(n) ? n : null;
}

function quantile(values, q) {
  if (!values.length) return null;
  const s = values.slice().sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const i = Math.floor(pos);
  const f = pos - i;
  const a = s[i];
  const b = s[Math.min(i + 1, s.length - 1)];
  return a + (b - a) * f;
}

function percentileRank(values, x) {
  if (!values.length || !Number.isFinite(x)) return null;
  let n = 0;
  for (const v of values) {
    if (v <= x) n += 1;
  }
  return (n / values.length) * 100;
}

function peEmptyHint() {
  if (peState.series === "pb") return "暂无市净率数据";
  if (peState.series === "dyn") return "暂无动态市盈率（可能长期亏损）";
  if ((peState.allItems || []).length) return "该口径暂无有效市盈率（可能长期亏损）";
  return "暂无估值数据";
}

function setPeStatus(message, { empty = false } = {}) {
  if (els.peChartMeta) els.peChartMeta.textContent = message || "";
  if (els.peChartEmpty) {
    els.peChartEmpty.textContent = empty ? message || peEmptyHint() : "暂无估值数据";
    els.peChartEmpty.classList.toggle("hidden", !empty);
  }
}

function peViewWindow() {
  const all = peState.allItems || [];
  const total = all.length;
  let size = Number(peState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(peState.viewStart) || 0), maxStart);
  return { total, size, start, maxStart, items: total ? all.slice(start, start + size) : [] };
}

function peMinViewSize(total) {
  if (total <= 1) return Math.max(1, total);
  return Math.min(total, 40);
}

function syncPeScrollBar() {
  const bar = els.peChartScrollBar;
  const wrap = els.peChartAxisScroll;
  if (!bar || !wrap) return;
  const { maxStart, start, total, size } = peViewWindow();
  const disabled = maxStart <= 0;
  wrap.classList.toggle("is-disabled", disabled);
  bar.disabled = disabled;
  bar.min = "0";
  bar.max = String(maxStart);
  bar.value = String(start);
  const ratio = total > 0 ? Math.min(1, size / total) : 1;
  bar.style.setProperty("--thumb-w", `${Math.max(28, Math.round(ratio * 220))}px`);
}

function resetPeViewport(allItems, { preferLinked = true } = {}) {
  peState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = peState.allItems.length;
  const linked = preferLinked && klineJoinsLinkedAxis() ? visibleAxisRange(chartState.items) : null;
  const vp = linked ? viewportFromAxisRange(peState.allItems, linked) : null;
  if (vp) {
    peState.viewStart = vp.viewStart;
    peState.viewSize = vp.viewSize;
  } else {
    let viewSize = METRIC_FALLBACK_VIEW_SIZE;
    if (viewSize <= 0 || viewSize >= total) viewSize = total;
    peState.viewSize = viewSize;
    peState.viewStart = Math.max(0, total - viewSize);
  }
  peState.items = peViewWindow().items;
  syncPeScrollBar();
}

function setPeViewStart(nextStart, { render = true, hoverIndex = null } = {}) {
  const { maxStart } = peViewWindow();
  const start = Math.min(Math.max(0, Math.round(nextStart)), maxStart);
  if (start === peState.viewStart && peState.items.length) {
    syncPeScrollBar();
    if (render) renderPeChart(hoverIndex);
    return start;
  }
  peState.viewStart = start;
  peState.items = peViewWindow().items;
  syncPeScrollBar();
  if (render) {
    refreshPeWindowStatus();
    renderPeChart(hoverIndex);
  }
  propagateLinkedAxis("pe");
  return start;
}

function zoomPeViewport(anchorRatio, factor, { render = true } = {}) {
  const total = (peState.allItems || []).length;
  if (total <= 1) return;
  const win = peViewWindow();
  const minSize = peMinViewSize(total);
  const nextSize = Math.min(total, Math.max(minSize, Math.round(win.size * factor)));
  const anchorIndex = win.start + Math.round(win.size * Math.min(1, Math.max(0, anchorRatio)));
  const nextStart = Math.round(anchorIndex - nextSize * Math.min(1, Math.max(0, anchorRatio)));
  peState.viewSize = nextSize;
  peState.viewStart = nextStart;
  peState.items = peViewWindow().items;
  syncPeScrollBar();
  if (render) {
    refreshPeWindowStatus();
    renderPeChart();
  }
  propagateLinkedAxis("pe");
}

function refreshPeWindowStatus() {
  const { total, size, items } = peViewWindow();
  if (!total) return;
  const series = peSeriesConf();
  const values = items.map(peValue).filter((v) => v != null);
  const last = values.length ? values[values.length - 1] : null;
  const mid = quantile(values, 0.5);
  const lo = values.length ? Math.min(...values) : null;
  const hi = values.length ? Math.max(...values) : null;
  const rank = percentileRank(values, last);
  const src = peState.source ? ` · ${peState.source}` : "";
  const tip =
    size < total
      ? ` · 显示 ${size}/${total}，滚轮缩放 · 拖动/滑动平移`
      : ` · ${total} 日，滚轮可放大`;
  const stats = [
    last != null ? `当前 ${fmtNum(last)}` : "",
    rank != null ? `${Math.round(rank)}%分位` : "",
    mid != null ? `中位 ${fmtNum(mid)}` : "",
    lo != null && hi != null ? `区间 ${fmtNum(lo)}–${fmtNum(hi)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  setPeStatus(`${series.label}${stats ? ` · ${stats}` : ""}${tip}${src}`);
}

function peChartLayout(w, h) {
  const pad = { top: 8, right: 8, bottom: 22, left: 8 };
  const innerW = Math.max(10, w - pad.left - pad.right);
  const innerH = Math.max(10, h - pad.top - pad.bottom);
  return {
    pad,
    price: { x: pad.left, y: pad.top, w: innerW, h: innerH },
    volume: { x: pad.left, y: pad.top + innerH, w: innerW, h: 0 },
  };
}

function hidePeHoverCard() {
  if (!els.peChartHoverCard) return;
  els.peChartHoverCard.classList.add("hidden");
  els.peChartHoverCard.setAttribute("aria-hidden", "true");
  els.peChartHoverCard.innerHTML = "";
}

function showPeHoverCard() {
  if (!els.peChartHoverCard) return;
  els.peChartHoverCard.classList.remove("hidden");
  els.peChartHoverCard.setAttribute("aria-hidden", "false");
}

function updatePeHoverLabel(index) {
  if (!els.peChartHoverCard) return;
  const items = peState.items || [];
  if (index == null || index < 0 || index >= items.length) {
    hidePeHoverCard();
    return;
  }
  const d = items[index];
  const series = peSeriesConf();
  const pe = peValue(d);
  const values = items.map(peValue).filter((v) => v != null);
  const rank = percentileRank(values, pe);
  const row = (label, valueHtml, valueCls = "") =>
    `<span class="chart-hover-item"><span class="k">${escapeHtml(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;
  const extra =
    peState.series === "dyn" || peState.series === "pb"
      ? Number.isFinite(Number(d.pe_ttm))
        ? row("市盈率(TTM)", escapeHtml(fmtNum(d.pe_ttm)))
        : ""
      : Number.isFinite(Number(d.pe_dyn))
        ? row("市盈率(动)", escapeHtml(fmtNum(d.pe_dyn)))
        : Number.isFinite(Number(d.pb))
          ? row("市净率", escapeHtml(fmtNum(d.pb)))
          : "";
  const rows = [
    row(series.label, escapeHtml(fmtNum(pe))),
    Number.isFinite(Number(d.close)) ? row("收盘", escapeHtml(fmtNum(d.close))) : "",
    rank != null ? row("窗口分位", escapeHtml(`${Math.round(rank)}%`)) : "",
    extra,
  ].filter(Boolean);
  els.peChartHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${escapeHtml(d.time || "")}</span>${rows.join("")}</div>`;
  showPeHoverCard();
}

function pePointerIndex(evt) {
  const canvas = els.peChart;
  const wrap = els.peChartWrap;
  const items = peState.items || [];
  if (!canvas || !wrap || !items.length) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const layout = peChartLayout(rect.width, rect.height);
  if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
  const t = (x - layout.price.x) / layout.price.w;
  return Math.min(items.length - 1, Math.max(0, Math.floor(t * items.length)));
}

function panPeByPixels(dx, canvasWidth) {
  const { size, maxStart } = peViewWindow();
  if (maxStart <= 0 || size <= 0) return false;
  const layout = peChartLayout(canvasWidth, 300);
  const barW = layout.price.w / size;
  if (barW <= 0) return false;
  const deltaBars = Math.round(-dx / barW);
  if (!deltaBars) return false;
  setPeViewStart(peState.viewStart + deltaBars, { render: true });
  return true;
}

function drawPeRefLine(ctx, price, y, text, color, align = "right") {
  if (!Number.isFinite(y)) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(price.x, y);
  ctx.lineTo(price.x + price.w, y);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.font = '10px "JetBrains Mono", Consolas, monospace';
  ctx.textBaseline = "middle";
  if (align === "right") {
    ctx.textAlign = "right";
    ctx.fillText(text, price.x + price.w - 6, y);
  } else {
    ctx.textAlign = "left";
    ctx.fillText(text, price.x + 6, y + 8);
  }
  ctx.restore();
}

function drawMetricChart(ctx, layout, items, getValue, colors, hoverIndex, { formatLabel = fmtNum, yFormat = null, mode = "day", skipTimeLabels = false, skipHoverHair = false, paneLabel = "", compactRefs = false } = {}) {
  const n = items.length;
  if (!n) return;
  const values = items.map(getValue).filter((v) => v != null);
  if (!values.length) return;

  const { price } = layout;
  const q25 = quantile(values, 0.25);
  const q50 = quantile(values, 0.5);
  const q75 = quantile(values, 0.75);
  let minP = Math.min(...values);
  let maxP = Math.max(...values);
  if (q25 != null) minP = Math.min(minP, q25);
  if (q75 != null) maxP = Math.max(maxP, q75);
  const priceScale = buildPriceScale(minP, maxP, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.04,
  });
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;
  const xAt = (i) => price.x + ((i + 0.5) / n) * price.w;

  const yTicks = (priceScale.ticks || []).map(yAt);
  const xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
  drawGrid(ctx, price, yTicks, xTicks, colors);

  ctx.save();
  ctx.beginPath();
  ctx.rect(price.x, price.y, price.w, price.h);
  ctx.clip();

  if (q25 != null && q75 != null) {
    const yA = yAt(q25);
    const yB = yAt(q75);
    ctx.fillStyle = "rgba(42, 212, 184, 0.08)";
    ctx.fillRect(price.x, Math.min(yA, yB), price.w, Math.abs(yB - yA));
  }

  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i += 1) {
    const v = getValue(items[i]);
    if (v == null) {
      started = false;
      continue;
    }
    const x = xAt(i);
    const y = yAt(v);
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 1.7;
  ctx.stroke();
  ctx.restore();

  if (q50 != null) {
    drawPeRefLine(ctx, price, yAt(q50), `中 ${formatLabel(q50)}`, "rgba(132, 148, 168, 0.85)");
  }
  if (!compactRefs) {
    if (q25 != null) {
      drawPeRefLine(ctx, price, yAt(q25), `25% ${formatLabel(q25)}`, "rgba(61, 214, 140, 0.7)");
    }
    if (q75 != null) {
      drawPeRefLine(ctx, price, yAt(q75), `75% ${formatLabel(q75)}`, "rgba(255, 93, 108, 0.7)");
    }
  }

  const lastIdx = [...items].map(getValue).reduce((acc, v, i) => (v != null ? i : acc), -1);
  if (lastIdx >= 0) {
    const last = getValue(items[lastIdx]);
    ctx.fillStyle = colors.accent;
    ctx.beginPath();
    ctx.arc(xAt(lastIdx), yAt(last), 3.2, 0, Math.PI * 2);
    ctx.fill();
  }

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    const v = getValue(items[hoverIndex]);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    if (!skipHoverHair) {
      ctx.beginPath();
      ctx.moveTo(x, price.y);
      ctx.lineTo(x, price.y + price.h);
      ctx.stroke();
    }
    if (v != null) {
      const y = yAt(v);
      ctx.beginPath();
      ctx.moveTo(price.x, y);
      ctx.lineTo(price.x + price.w, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = colors.accent;
      ctx.beginPath();
      ctx.arc(x, y, 3.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  if (paneLabel) drawPaneLabel(ctx, price, paneLabel, colors);
  drawAxesLabels(ctx, layout, priceScale, items, mode, colors, { yFormat, skipTimeLabels });
}

function drawPeChart(ctx, layout, items, colors, hoverIndex) {
  drawMetricChart(ctx, layout, items, peValue, colors, hoverIndex, { formatLabel: fmtNum, mode: "day" });
}

function renderPeChart(hoverIndex = null) {
  if (els.priceChart) renderChart(hoverIndex);
}

function syncPeSeriesSelect(series = peState.series) {
  if (!els.peSeriesSelect) return;
  if (els.peSeriesSelect.value !== series) els.peSeriesSelect.value = series;
}

function setupPeChart() {
  if (!els.peSeriesSelect) return;
  els.peSeriesSelect.addEventListener("change", () => {
    applyPeSeries(els.peSeriesSelect.value);
  });
  syncPeSeriesSelect();
}

function applyPeSeries(series) {
  if (!PE_SERIES[series] || series === peState.series) return;
  peState.series = series;
  syncPeSeriesSelect(series);
  hidePeHoverCard();
  const hasValue = (peState.items || []).some((d) => peValue(d) != null);
  if (!hasValue) {
    setPeStatus(peEmptyHint(), { empty: true });
    renderPeChart();
    refreshKlineQuoteCard();
    return;
  }
  setPeStatus("");
  refreshPeWindowStatus();
  renderPeChart();
  refreshKlineQuoteCard();
}

async function loadPeChart() {
  if (!code) return;
  peState.loading = true;
  setPeStatus("正在加载估值…");
  hidePeHoverCard();
  try {
    const qs = new URLSearchParams({ code, limit: "2500" });
    const json = await api(`/api/stocks/pe?${qs.toString()}`);
    const data = json.data || {};
    peState.source = data.source || "";
    resetPeViewport(data.items || []);
    const hasValue = (peState.items || []).some((d) => peValue(d) != null);
    if (!peState.allItems.length || !hasValue) {
      setPeStatus(peEmptyHint(), { empty: true });
      renderPeChart();
      refreshKlineQuoteCard();
      return;
    }
    setPeStatus("");
    refreshPeWindowStatus();
    renderPeChart();
    refreshKlineQuoteCard();
  } catch (err) {
    resetPeViewport([]);
    setPeStatus(err.message || "估值加载失败", { empty: true });
    renderPeChart();
  } finally {
    peState.loading = false;
  }
}

const turnoverState = {
  loading: false,
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: METRIC_FALLBACK_VIEW_SIZE,
  source: "",
};

function turnoverValue(d) {
  const n = Number(d?.turnover);
  return Number.isFinite(n) ? n : null;
}

function setTurnoverStatus(message, { empty = false } = {}) {
  if (els.turnoverChartMeta) els.turnoverChartMeta.textContent = message || "";
  if (els.turnoverChartEmpty) {
    els.turnoverChartEmpty.textContent = empty ? message || "暂无换手率数据" : "暂无换手率数据";
    els.turnoverChartEmpty.classList.toggle("hidden", !empty);
  }
}

function turnoverViewWindow() {
  const all = turnoverState.allItems || [];
  const total = all.length;
  let size = Number(turnoverState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(turnoverState.viewStart) || 0), maxStart);
  return { total, size, start, maxStart, items: total ? all.slice(start, start + size) : [] };
}

function syncTurnoverScrollBar() {
  const bar = els.turnoverChartScrollBar;
  const wrap = els.turnoverChartAxisScroll;
  if (!bar || !wrap) return;
  const { maxStart, start, total, size } = turnoverViewWindow();
  const disabled = maxStart <= 0;
  wrap.classList.toggle("is-disabled", disabled);
  bar.disabled = disabled;
  bar.min = "0";
  bar.max = String(maxStart);
  bar.value = String(start);
  const ratio = total > 0 ? Math.min(1, size / total) : 1;
  bar.style.setProperty("--thumb-w", `${Math.max(28, Math.round(ratio * 220))}px`);
}

function resetTurnoverViewport(allItems, { preferLinked = true } = {}) {
  turnoverState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = turnoverState.allItems.length;
  const linked = preferLinked && klineJoinsLinkedAxis() ? visibleAxisRange(chartState.items) : null;
  const vp = linked ? viewportFromAxisRange(turnoverState.allItems, linked) : null;
  if (vp) {
    turnoverState.viewStart = vp.viewStart;
    turnoverState.viewSize = vp.viewSize;
  } else {
    let viewSize = METRIC_FALLBACK_VIEW_SIZE;
    if (viewSize <= 0 || viewSize >= total) viewSize = total;
    turnoverState.viewSize = viewSize;
    turnoverState.viewStart = Math.max(0, total - viewSize);
  }
  turnoverState.items = turnoverViewWindow().items;
  syncTurnoverScrollBar();
}

function setTurnoverViewStart(nextStart, { render = true, hoverIndex = null } = {}) {
  const { maxStart } = turnoverViewWindow();
  const start = Math.min(Math.max(0, Math.round(nextStart)), maxStart);
  if (start === turnoverState.viewStart && turnoverState.items.length) {
    syncTurnoverScrollBar();
    if (render) renderTurnoverChart(hoverIndex);
    return start;
  }
  turnoverState.viewStart = start;
  turnoverState.items = turnoverViewWindow().items;
  syncTurnoverScrollBar();
  if (render) {
    refreshTurnoverWindowStatus();
    renderTurnoverChart(hoverIndex);
  }
  propagateLinkedAxis("turnover");
  return start;
}

function zoomTurnoverViewport(anchorRatio, factor, { render = true } = {}) {
  const total = (turnoverState.allItems || []).length;
  if (total <= 1) return;
  const win = turnoverViewWindow();
  const minSize = peMinViewSize(total);
  const nextSize = Math.min(total, Math.max(minSize, Math.round(win.size * factor)));
  const anchorIndex = win.start + Math.round(win.size * Math.min(1, Math.max(0, anchorRatio)));
  const nextStart = Math.round(anchorIndex - nextSize * Math.min(1, Math.max(0, anchorRatio)));
  turnoverState.viewSize = nextSize;
  turnoverState.viewStart = nextStart;
  turnoverState.items = turnoverViewWindow().items;
  syncTurnoverScrollBar();
  if (render) {
    refreshTurnoverWindowStatus();
    renderTurnoverChart();
  }
  propagateLinkedAxis("turnover");
}

function refreshTurnoverWindowStatus() {
  const { total, size, items } = turnoverViewWindow();
  if (!total) return;
  const values = items.map(turnoverValue).filter((v) => v != null);
  const last = values.length ? values[values.length - 1] : null;
  const mid = quantile(values, 0.5);
  const lo = values.length ? Math.min(...values) : null;
  const hi = values.length ? Math.max(...values) : null;
  const rank = percentileRank(values, last);
  const src = turnoverState.source ? ` · ${turnoverState.source}` : "";
  const tip =
    size < total
      ? ` · 显示 ${size}/${total}，滚轮缩放 · 拖动/滑动平移`
      : ` · ${total} 日，滚轮可放大`;
  const stats = [
    last != null ? `当前 ${fmtPct(last)}` : "",
    rank != null ? `${Math.round(rank)}%分位` : "",
    mid != null ? `中位 ${fmtPct(mid)}` : "",
    lo != null && hi != null ? `区间 ${fmtPct(lo)}–${fmtPct(hi)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  setTurnoverStatus(`换手率${stats ? ` · ${stats}` : ""}${tip}${src}`);
}

function hideTurnoverHoverCard() {
  if (!els.turnoverChartHoverCard) return;
  els.turnoverChartHoverCard.classList.add("hidden");
  els.turnoverChartHoverCard.setAttribute("aria-hidden", "true");
  els.turnoverChartHoverCard.innerHTML = "";
}

function showTurnoverHoverCard() {
  if (!els.turnoverChartHoverCard) return;
  els.turnoverChartHoverCard.classList.remove("hidden");
  els.turnoverChartHoverCard.setAttribute("aria-hidden", "false");
}

function updateTurnoverHoverLabel(index) {
  if (!els.turnoverChartHoverCard) return;
  const items = turnoverState.items || [];
  if (index == null || index < 0 || index >= items.length) {
    hideTurnoverHoverCard();
    return;
  }
  const d = items[index];
  const to = turnoverValue(d);
  const values = items.map(turnoverValue).filter((v) => v != null);
  const rank = percentileRank(values, to);
  const row = (label, valueHtml, valueCls = "") =>
    `<span class="chart-hover-item"><span class="k">${escapeHtml(label)}</span><span class="v ${valueCls}">${valueHtml}</span></span>`;
  const rows = [
    row("换手率", escapeHtml(fmtPct(to))),
    Number.isFinite(Number(d.close)) ? row("收盘", escapeHtml(fmtNum(d.close))) : "",
    rank != null ? row("窗口分位", escapeHtml(`${Math.round(rank)}%`)) : "",
  ].filter(Boolean);
  els.turnoverChartHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${escapeHtml(d.time || "")}</span>${rows.join("")}</div>`;
  showTurnoverHoverCard();
}

function turnoverPointerIndex(evt) {
  const canvas = els.turnoverChart;
  const wrap = els.turnoverChartWrap;
  const items = turnoverState.items || [];
  if (!canvas || !wrap || !items.length) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const layout = peChartLayout(rect.width, rect.height);
  if (x < layout.price.x || x > layout.price.x + layout.price.w) return null;
  const t = (x - layout.price.x) / layout.price.w;
  return Math.min(items.length - 1, Math.max(0, Math.floor(t * items.length)));
}

function panTurnoverByPixels(dx, canvasWidth) {
  const { size, maxStart } = turnoverViewWindow();
  if (maxStart <= 0 || size <= 0) return false;
  const layout = peChartLayout(canvasWidth, 300);
  const barW = layout.price.w / size;
  if (barW <= 0) return false;
  const deltaBars = Math.round(-dx / barW);
  if (!deltaBars) return false;
  setTurnoverViewStart(turnoverState.viewStart + deltaBars, { render: true });
  return true;
}

function drawTurnoverChart(ctx, layout, items, colors, hoverIndex) {
  drawMetricChart(ctx, layout, items, turnoverValue, colors, hoverIndex, {
    formatLabel: fmtPct,
    yFormat: (val) => fmtPct(val),
    mode: "day",
  });
}

function renderTurnoverChart(hoverIndex = null) {
  if (els.priceChart) renderChart(hoverIndex);
}

async function loadTurnoverChart({ refresh = false } = {}) {
  if (!code) return;
  turnoverState.loading = true;
  setTurnoverStatus("正在加载换手率…");
  hideTurnoverHoverCard();
  try {
    const qs = new URLSearchParams({ code, limit: "1500" });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/turnover?${qs.toString()}`);
    const data = json.data || {};
    turnoverState.source = data.source || "";
    resetTurnoverViewport(data.items || []);
    const hasValue = (turnoverState.items || []).some((d) => turnoverValue(d) != null);
    if (!turnoverState.allItems.length || !hasValue) {
      setTurnoverStatus("暂无换手率数据", { empty: true });
      renderTurnoverChart();
      return;
    }
    setTurnoverStatus("");
    refreshTurnoverWindowStatus();
    renderTurnoverChart();
  } catch (err) {
    resetTurnoverViewport([]);
    setTurnoverStatus(err.message || "换手率加载失败", { empty: true });
    renderTurnoverChart();
  } finally {
    turnoverState.loading = false;
  }
}

function setupTurnoverChart() {
  if (!els.turnoverChart) return;

  if (els.turnoverChartScrollBar) {
    els.turnoverChartScrollBar.addEventListener("input", () => {
      hideTurnoverHoverCard();
      setTurnoverViewStart(Number(els.turnoverChartScrollBar.value) || 0, { render: true });
    });
  }

  let hoverIdx = null;
  let pan = null;

  const onMove = (evt) => {
    if (pan) {
      const dx = evt.clientX - pan.lastX;
      if (Math.abs(evt.clientX - pan.originX) > 4) pan.moved = true;
      if (pan.moved && Math.abs(dx) >= 1) {
        hideTurnoverHoverCard();
        hoverIdx = null;
        panTurnoverByPixels(dx, pan.width);
        pan.lastX = evt.clientX;
      }
      return;
    }
    const idx = turnoverPointerIndex(evt);
    if (idx === hoverIdx) return;
    hoverIdx = idx;
    updateTurnoverHoverLabel(idx);
    renderTurnoverChart(idx);
  };

  const onLeave = () => {
    if (pan) return;
    hoverIdx = null;
    hideTurnoverHoverCard();
    renderTurnoverChart();
  };

  const onDown = (evt) => {
    if (evt.button != null && evt.button !== 0) return;
    const rect = els.turnoverChart.getBoundingClientRect();
    pan = { originX: evt.clientX, lastX: evt.clientX, width: rect.width, moved: false };
    els.turnoverChartWrap?.classList.add("is-panning");
    try {
      els.turnoverChart.setPointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onUp = (evt) => {
    if (!pan) return;
    const wasPan = pan.moved;
    pan = null;
    els.turnoverChartWrap?.classList.remove("is-panning");
    try {
      els.turnoverChart.releasePointerCapture(evt.pointerId);
    } catch {
      /* ignore */
    }
    if (!wasPan) {
      const idx = turnoverPointerIndex(evt);
      hoverIdx = idx;
      updateTurnoverHoverLabel(idx);
      renderTurnoverChart(idx);
    } else {
      hideTurnoverHoverCard();
      hoverIdx = null;
      renderTurnoverChart();
    }
  };

  els.turnoverChart.addEventListener("pointerdown", onDown);
  els.turnoverChart.addEventListener("pointermove", onMove);
  els.turnoverChart.addEventListener("pointerup", onUp);
  els.turnoverChart.addEventListener("pointercancel", onUp);
  els.turnoverChart.addEventListener("pointerleave", onLeave);

  els.turnoverChart.addEventListener(
    "wheel",
    (evt) => {
      const total = (turnoverState.allItems || []).length;
      if (!total) return;
      evt.preventDefault();
      hideTurnoverHoverCard();
      hoverIdx = null;
      const rect = els.turnoverChart.getBoundingClientRect();
      const layout = peChartLayout(rect.width, rect.height);
      const x = evt.clientX - rect.left;
      let anchorRatio = 0.5;
      if (x >= layout.price.x && x <= layout.price.x + layout.price.w) {
        anchorRatio = (x - layout.price.x) / layout.price.w;
      }
      if (Math.abs(evt.deltaX) > Math.abs(evt.deltaY) * 1.15) {
        const { maxStart } = turnoverViewWindow();
        if (maxStart <= 0) return;
        const step = Math.max(1, Math.round(Math.abs(evt.deltaX) / 40));
        setTurnoverViewStart(turnoverState.viewStart + (evt.deltaX > 0 ? step : -step), { render: true });
        return;
      }
      const steps = Math.max(1, Math.min(5, Math.round(Math.abs(evt.deltaY) / 72) || 1));
      const base = evt.deltaY > 0 ? 1.14 : 1 / 1.14;
      zoomTurnoverViewport(anchorRatio, base ** steps, { render: true });
    },
    { passive: false }
  );

  if (typeof ResizeObserver !== "undefined" && els.turnoverChartWrap) {
    let timer = 0;
    const ro = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        syncTurnoverScrollBar();
        renderTurnoverChart(hoverIdx);
      }, 60);
    });
    ro.observe(els.turnoverChartWrap);
  } else {
    window.addEventListener("resize", () => {
      syncTurnoverScrollBar();
      renderTurnoverChart(hoverIdx);
    });
  }
}

els.refreshNewsBtn.addEventListener("click", () =>
  loadAllNews({ refresh: true })
);
if (els.refreshEmotionBtn) {
  els.refreshEmotionBtn.addEventListener("click", () =>
    loadAllEmotion({ refresh: true })
  );
}
function setupChartsViewport() {
  const relayout = () => {
    fitChartsToViewport();
    syncNewsHubLayout();
    syncEmotionHubLayout();
  };
  window.addEventListener("resize", relayout);
  if (typeof ResizeObserver !== "undefined") {
    const stage = document.querySelector(".app-stage");
    if (stage) new ResizeObserver(relayout).observe(stage);
  }
  syncChartsViewportClass();
  syncNewsGroupUi();
  syncEmotionSourceUi();
  const tab = normalizeMainPanel((params.get("tab") || "").trim());
  if (tab) switchMainPanel(tab);
  fitChartsToViewport();
}

setupBackLink();
setupExchangeBox();
setupPressBox();
setupPlatformBoxes();
setupCninfoBox();
setupEmotionBox();
setupNewsFolding();
setupMainTabs();
setupChartsViewport();
setupMetricTips();
setupChart();
setupTicksChart();
setupPeChart();
setupTurnoverChart();
(async () => {
  await loadProfile();
  await Promise.all([
    loadChart("day"),
    loadTicksChart(),
    loadPeChart(),
    loadNewsGroup(newsGroup, { refresh: false }),
  ]);
  propagateLinkedAxis("kline");
  if (isQuotesPanel()) refreshChartsLayout();
})();
