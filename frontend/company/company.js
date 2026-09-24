const params = new URLSearchParams(window.location.search);
const code = (params.get("code") || "").trim();
const nameHint = (params.get("name") || "").trim();
const industry = (params.get("industry") || "").trim();
const fromPage = (params.get("from") || "").trim();
const fromCat = (params.get("cat") || "").trim();

const DEFAULT_DAYS = 3;
const CNINFO_DEFAULT_DAYS = 365;
const EXCHANGE_DEFAULT_DAYS = 365;
const PRESS_DEFAULT_DAYS = 30;
const PLATFORM_DEFAULT_DAYS = 30;
const NEWS_GROUP_OFFICIAL = "official";
const NEWS_GROUP_FINANCIALS = "financials";
const NEWS_GROUP_OTHER = "other";
const NEWS_GROUP_LABELS = {
  official: "官方",
  financials: "财报",
  other: "其他",
};
const NEWS_FINANCIALS_ALIASES = new Set(["reports", "financials", "financial", "financial-report", "caibao"]);
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

let metricsStock = {};
const BIG_DEAL_MIN_KEY = "orbit-big-deal-min-amount";
const BIG_DEAL_MAX_KEY = "orbit-big-deal-max-amount";
const FUNDAMENTALS_FOLD_KEY = "orbit-fundamentals-folded";
const BIG_DEAL_DEFAULT_YUAN = 1_000_000;
let bigDealRangeReloadTimer = 0;
const bigDealState = {
  loading: false,
  rawItems: [],
  items: [],
  note: "",
  error: "",
  cached: false,
  sessionDay: "",
  minAmount: BIG_DEAL_DEFAULT_YUAN,
  maxAmount: null,
  rangeHydrated: false,
  total: 0,
};

const BIG_DEAL_BAR_TYPES = {
  active_buy: { label: "主动买", color: "#ff5d6c" },
  active_sell: { label: "主动卖", color: "#3dd68c" },
  passive_buy: { label: "被动买", color: "rgba(255, 93, 108, 0.52)" },
  passive_sell: { label: "被动卖", color: "rgba(61, 214, 140, 0.52)" },
};

const BIG_DEAL_COLUMNS = ["active_buy", "passive_buy", "active_sell", "passive_sell"];

const bigDealChartState = {
  loading: false,
  rawItems: [],
  items: [],
  barSlots: [],
  yMax: 1,
  note: "",
  error: "",
  cached: false,
  sessionDay: "",
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
  fundamentalsPanel: document.getElementById("fundamentalsPanel"),
  fundamentalsBody: document.getElementById("fundamentalsBody"),
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
  comboMetricSelect: document.getElementById("comboMetricSelect"),
  comboMetricWrap: document.getElementById("comboMetricWrap"),
  peLegendWrap: document.getElementById("peLegendWrap"),
  fundflowLegendWrap: document.getElementById("fundflowLegendWrap"),
  marginLegendWrap: document.getElementById("marginLegendWrap"),
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
  companyTabStack: document.getElementById("companyTabStack"),
  panelJudgment: document.getElementById("panel-judgment"),
  judgmentSourceBar: document.getElementById("judgmentSourceBar"),
  earningsSourceBar: document.getElementById("earningsSourceBar"),
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
  emotionThsVote: document.getElementById("emotionThsVote"),
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
  emotionPostsDaysThs: document.getElementById("emotionPostsDaysThs"),
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
  emotionSearchDays: document.getElementById("emotionSearchDays"),
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
  refreshListBtn: document.getElementById("refreshListBtn"),
  companyListTitle: document.getElementById("companyListTitle"),
  companyListMeta: document.getElementById("companyListMeta"),
  companyListSortSeg: document.getElementById("companyListSortSeg"),
  companyListBody: document.getElementById("companyListBody"),
  companyListDetailHead: document.getElementById("companyListDetailHead"),
  companyListDetailBody: document.getElementById("companyListDetailBody"),
  panelOthers: document.getElementById("panel-others"),
  othersSourceBar: document.getElementById("othersSourceBar"),
  refreshHoldersBtn: document.getElementById("refreshHoldersBtn"),
  holdersTitle: document.getElementById("holdersTitle"),
  holdersMeta: document.getElementById("holdersMeta"),
  holdersHint: document.getElementById("holdersHint"),
  holdersDate: document.getElementById("holdersDate"),
  holdersBody: document.getElementById("holdersBody"),
  holdersBodyRows: document.getElementById("holdersBodyRows"),
  holderNumMeta: document.getElementById("holderNumMeta"),
  holderNumHoverCard: document.getElementById("holderNumHoverCard"),
  holderNumChartWrap: document.getElementById("holderNumChartWrap"),
  holderNumChart: document.getElementById("holderNumChart"),
  holderNumChartEmpty: document.getElementById("holderNumChartEmpty"),
  holdingsStatsMeta: document.getElementById("holdingsStatsMeta"),
  holdingsStatsBar: document.getElementById("holdingsStatsBar"),
  holdingsStatsChartEmpty: document.getElementById("holdingsStatsChartEmpty"),
  holdingsStatsLegend: document.getElementById("holdingsStatsLegend"),
  fundHoldersTitle: document.getElementById("fundHoldersTitle"),
  fundHoldersMeta: document.getElementById("fundHoldersMeta"),
  fundHoldersHint: document.getElementById("fundHoldersHint"),
  fundHoldersDate: document.getElementById("fundHoldersDate"),
  fundHoldersBody: document.getElementById("fundHoldersBody"),
  fundHoldersBodyRows: document.getElementById("fundHoldersBodyRows"),
  refreshFinancialsBtn: document.getElementById("refreshFinancialsBtn"),
  financialsTitle: document.getElementById("financialsTitle"),
  financialsMeta: document.getElementById("financialsMeta"),
  financialsHint: document.getElementById("financialsHint"),
  financialsSheetSeg: document.getElementById("financialsSheetSeg"),
  financialsFilterSeg: document.getElementById("financialsFilterSeg"),
  financialsRangeSeg: document.getElementById("financialsRangeSeg"),
  financialsRangeShortBtn: document.getElementById("financialsRangeShortBtn"),
  financialsReadSeg: document.getElementById("financialsReadSeg"),
  financialsUnitSeg: document.getElementById("financialsUnitSeg"),
  financialsDensitySeg: document.getElementById("financialsDensitySeg"),
  financialsKpis: document.getElementById("financialsKpis"),
  financialsBody: document.getElementById("financialsBody"),
  financialsHead: document.getElementById("financialsHead"),
  financialsBodyRows: document.getElementById("financialsBodyRows"),
  errorBox: document.getElementById("errorBox"),
};

let activeMainPanel = "quotes";
let companyListBootstrapped = false;
const companyListState = {
  loading: false,
  items: [],
  count: 0,
  name: "",
  selected: "",
  sort: "date",
  updatedAt: "",
  error: "",
};
let holdersBootstrapped = false;
const holdersState = {
  loading: false,
  items: [],
  count: 0,
  reportDate: "",
  reportDates: [],
  totalShares: null,
  totalSharesFmt: "",
  updatedAt: "",
  error: "",
};
const holderNumState = {
  loading: false,
  items: [],
  latest: null,
  source: "",
  updatedAt: "",
  error: "",
  hoverIndex: null,
};
let fundHoldersBootstrapped = false;
const fundHoldersState = {
  loading: false,
  items: [],
  count: 0,
  reportDate: "",
  updatedAt: "",
  error: "",
  sortKey: "shares",
  sortDir: "desc",
};
let financialsBootstrapped = false;
const financialsState = {
  loading: false,
  sheet: "balance",
  items: [],
  income: [],
  balance: [],
  cashflow: [],
  lines: { income: [], balance: [], cashflow: [] },
  count: 0,
  cadence: "quarterly",
  range: "short",
  read: "yoy",
  unit: "yi",
  density: "focus",
  collapsed: {},
  updatedAt: "",
  error: "",
};
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
    days: 0,
    maxPages: 1,
    hasMore: true,
    loadingMore: false,
    withReplies: true,
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
    loadingMore: false,
    items: [],
    count: 0,
    total: 0,
    kind: "user",
    sort: "time",
    days: EMOTION_DEFAULT_DAYS,
    maxPages: 1,
    hasMore: true,
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
let newsBootstrapped = { official: false, financials: false, other: false };
let emotionBootstrapped = { eastmoney: false, tonghuashun: false, xueqiu: false };
const ANALYSIS_PANELS = new Set(["business", "bazhang", "buffett", "buffett-rules", "competition", "chain", "risk", "sentiment", "trend"]);
const EARNINGS_VIEWS = new Set(["bazhang", "buffett", "buffett-rules"]);
const EARNINGS_FAMILY = new Set(["earnings", "财报简述", ...EARNINGS_VIEWS]);
let lastEarningsView = "bazhang";
const tabParamRaw = (params.get("tab") || "").trim().toLowerCase();
let emotionSource = normalizeEmotionSource(params.get("emotion") || "");
if (["ths-emotion", "ths", "circle"].includes(tabParamRaw)) {
  emotionSource = "tonghuashun";
} else if (["xueqiu", "xq", "snowball"].includes(tabParamRaw)) {
  emotionSource = "xueqiu";
}
let othersSubTab = normalizeOthersSubTab(params.get("others") || "");
if (["list", "lhb", "longhu"].includes(tabParamRaw)) {
  othersSubTab = "lhb";
} else if (["holders", "owner", "shareholders", "top10", "sdgd", "fund-holders", "funds", "fund", "holdings"].includes(tabParamRaw)) {
  othersSubTab = "holders";
}
if (
  NEWS_FINANCIALS_ALIASES.has(tabParamRaw)
  || NEWS_FINANCIALS_ALIASES.has(String(params.get("others") || "").trim().toLowerCase())
) {
  newsGroup = NEWS_GROUP_FINANCIALS;
}
let judgmentSubTab = normalizeJudgmentSubTab(params.get("judgment") || "");
if (isAnalysisPanel(tabParamRaw) || tabParamRaw === "analysis") {
  judgmentSubTab = normalizeJudgmentSubTab(tabParamRaw === "analysis" ? "business" : tabParamRaw);
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

function isEmEmotion(source = emotionSource) {
  return normalizeEmotionSource(source) === "eastmoney";
}

function activeEmotionState(source = emotionSource) {
  if (isXqEmotion(source)) return xqEmotionState;
  if (isThsEmotion(source)) return thsEmotionState;
  return emotionState;
}

function isAnalysisPanel(panelId = "") {
  const raw = String(panelId || "").trim().toLowerCase();
  if (EARNINGS_FAMILY.has(raw)) return true;
  const aliases = window.AI_MODE_ALIASES || {};
  const mapped = aliases[raw] || raw;
  return ANALYSIS_PANELS.has(mapped);
}

function notifyAnalysisIdentity(stock = {}, { ready = false } = {}) {
  window.CompanyAnalysis?.syncIdentity?.({
    code: stock.code || code,
    name: stock.name || nameHint || "",
    ready,
  });
}

function normalizeMainPanel(panelId) {
  if (panelId === "quotes" || panelId === "charts" || panelId === "overview") return "quotes";
  if (
    panelId === "news"
    || panelId === "reports"
    || panelId === "financials"
    || panelId === "financial"
    || panelId === "financial-report"
    || panelId === "caibao"
  ) {
    return "news";
  }
  if (panelId === "emotion" || panelId === "ths-emotion" || panelId === "ths" || panelId === "circle" || panelId === "xueqiu" || panelId === "xq") return "emotion";
  if (
    panelId === "others" ||
    panelId === "list" ||
    panelId === "lhb" ||
    panelId === "longhu" ||
    panelId === "holders" ||
    panelId === "owner" ||
    panelId === "shareholders" ||
    panelId === "top10" ||
    panelId === "sdgd" ||
    panelId === "fund-holders" ||
    panelId === "funds" ||
    panelId === "fund"
  ) {
    return "others";
  }
  if (panelId === "judgment" || panelId === "analysis" || isAnalysisPanel(panelId)) return "judgment";
  return "";
}

function normalizeJudgmentSubTab(view) {
  const raw = String(view || "").trim().toLowerCase();
  if (raw === "earnings" || raw === "财报简述") {
    return EARNINGS_VIEWS.has(lastEarningsView) ? lastEarningsView : "bazhang";
  }
  const aliases = window.AI_MODE_ALIASES || {};
  const mapped = aliases[raw] || raw;
  if (ANALYSIS_PANELS.has(mapped)) {
    if (EARNINGS_VIEWS.has(mapped)) lastEarningsView = mapped;
    return mapped;
  }
  return "business";
}

function normalizeOthersSubTab(view) {
  const raw = String(view || "").trim().toLowerCase();
  if (
    raw === "holders" ||
    raw === "owner" ||
    raw === "shareholders" ||
    raw === "top10" ||
    raw === "sdgd" ||
    raw === "fund-holders" ||
    raw === "funds" ||
    raw === "fund" ||
    raw === "holdings" ||
    raw === "cgxx"
  ) {
    return "holders";
  }
  return "lhb";
}

function normalizeNewsGroup(group) {
  const raw = String(group || "").trim().toLowerCase();
  if (raw === "other" || raw === "platform" || raw === "platforms" || raw === "media") return NEWS_GROUP_OTHER;
  if (NEWS_FINANCIALS_ALIASES.has(raw)) return NEWS_GROUP_FINANCIALS;
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

/** 走势 combo 底部指标：pe 估值 | fundflow 资金流 | margin 融资融券 */
let comboMetricState = "fundflow";

/** @type {{ loading: boolean, liveFetching: boolean, liveFetchPending: boolean, liveFetchGen: number, items: any[], allItems: any[], viewStart: number, viewSize: number, preClose: number|null, source: string, cached: boolean, live: boolean, phase: string, tradeDate: string, hoverTime: string|null }} */
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
  cached: false,
  live: false,
  phase: "closed",
  tradeDate: "",
  hoverTime: null,
  hoverSecond: null,
  hoverRange: null,
  hoverTickIndexes: [],
  hoverLinkKey: "",
  hoverOrigin: "",
  listHover: false,
  chartHovering: false,
  linkPin: null,
  hoverBigDeal: null,
  hoverDealPreferred: null,
  hoverDealPaintId: "",
  sessionView: null,
  viewDay: "",
  loadGen: 0,
};

const livePollState = {
  profileFetching: false,
  profilePending: false,
};

const TICKS_LIVE_POS = -40;
const TICKS_DRAW_MAX = 1800;
/** 会话轴最小可视跨度（15 秒，单位为 session offset 分钟）。 */
const TICKS_SESSION_MIN_SPAN = 15 / 60;

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
  const metric = comboMetricState;
  if (card) card.classList.toggle("is-combo", combo);
  if (els.comboMetricWrap) els.comboMetricWrap.classList.toggle("hidden", !combo);
  if (els.peLegendWrap) els.peLegendWrap.classList.toggle("hidden", !combo || metric !== "pe");
  if (els.fundflowLegendWrap) els.fundflowLegendWrap.classList.toggle("hidden", !combo || metric !== "fundflow");
  if (els.marginLegendWrap) els.marginLegendWrap.classList.toggle("hidden", !combo || metric !== "margin");
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
  if (window.OrbitHttp) return OrbitHttp.get(path, options);
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

function metricCell([label, value, cls = "", note = ""]) {
  const tip = metricTip(label);
  const tipAttr = tip ? ` data-tip="${escapeHtml(tip)}"` : "";
  const tipClass = tip ? " has-tip" : "";
  const tipBtn = tip
    ? ` role="button" tabindex="0" aria-expanded="false" aria-label="${escapeHtml(label)}：查看指标说明"`
    : "";
  const noteHtml = note
    ? `<span class="detail-note">${escapeHtml(note).replace(/\n/g, "<br>")}</span>`
    : "";
  return `
    <div class="stat-cell${tipClass}"${tipAttr}${tipBtn}>
      <span class="detail-label">${escapeHtml(label)}</span>
      <span class="detail-value ${cls}">${escapeHtml(displayValue(value))}</span>
      ${noteHtml}
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
  const root = document.querySelector(".quotes-layout") || document.querySelector(".company-hero");
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

function yuanFromWan(wan) {
  const n = Number(wan);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 10000);
}

function wanFromYuan(yuan) {
  const n = Number(yuan);
  if (!Number.isFinite(n) || n < 0) return 0;
  const wan = n / 10000;
  return Number.isInteger(wan) ? wan : Math.round(wan * 100) / 100;
}

function formatWanInput(yuan) {
  if (yuan == null || !Number.isFinite(Number(yuan))) return "";
  return String(wanFromYuan(yuan));
}

function parseWanInputValue(value) {
  const raw = String(value || "")
    .trim()
    .replace(/,/g, "")
    .replace(/万/g, "");
  if (!raw || raw === ".") return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

function bigDealMinAmount() {
  const stored = Number(bigDealState.minAmount);
  if (Number.isFinite(stored) && stored >= 0) return stored;
  return BIG_DEAL_DEFAULT_YUAN;
}

function bigDealMaxAmount() {
  const stored = Number(bigDealState.maxAmount);
  if (Number.isFinite(stored) && stored > 0) return stored;
  return null;
}

function bigDealRangeLabel() {
  const minWan = wanFromYuan(bigDealMinAmount());
  const maxYuan = bigDealMaxAmount();
  if (maxYuan == null) return `${minWan}万以上`;
  return `${minWan}–${wanFromYuan(maxYuan)}万`;
}

function readStoredBigDealMinAmount() {
  try {
    const raw = Number(localStorage.getItem(BIG_DEAL_MIN_KEY));
    if (Number.isFinite(raw) && raw >= 0) return raw;
  } catch {
    /* ignore */
  }
  return BIG_DEAL_DEFAULT_YUAN;
}

function readStoredBigDealMaxAmount() {
  try {
    const raw = localStorage.getItem(BIG_DEAL_MAX_KEY);
    if (raw == null || raw === "" || raw === "none") return null;
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) return n;
  } catch {
    /* ignore */
  }
  return null;
}

function persistBigDealRange(minYuan, maxYuan) {
  const min = Number.isFinite(Number(minYuan)) && Number(minYuan) >= 0 ? Number(minYuan) : BIG_DEAL_DEFAULT_YUAN;
  const max = Number.isFinite(Number(maxYuan)) && Number(maxYuan) > 0 ? Number(maxYuan) : null;
  bigDealState.minAmount = min;
  bigDealState.maxAmount = max;
  try {
    localStorage.setItem(BIG_DEAL_MIN_KEY, String(min));
    if (max == null) localStorage.removeItem(BIG_DEAL_MAX_KEY);
    else localStorage.setItem(BIG_DEAL_MAX_KEY, String(max));
  } catch {
    /* ignore */
  }
}

function hydrateBigDealRange() {
  if (bigDealState.rangeHydrated) return;
  persistBigDealRange(readStoredBigDealMinAmount(), readStoredBigDealMaxAmount());
  bigDealState.rangeHydrated = true;
}

function filterBigDealsByRange(items) {
  const min = bigDealMinAmount();
  const max = bigDealMaxAmount();
  return (items || []).filter((row) => {
    const amount = Number(row?.amount);
    if (!Number.isFinite(amount)) return false;
    if (amount < min) return false;
    if (max != null && amount > max) return false;
    return true;
  });
}

function applyBigDealRangeFilter() {
  bigDealState.items = filterBigDealsByRange(bigDealState.rawItems);
  bigDealState.total = bigDealState.items.length;
  bigDealChartState.items = filterBigDealsByRange(bigDealChartState.rawItems);
  refreshBigDealList();
  if (isQuotesPanel() && els.ticksChart) renderTicksChart();
}

function syncBigDealRangeInputs() {
  const minEl = document.getElementById("bigDealMinWan");
  const maxEl = document.getElementById("bigDealMaxWan");
  if (minEl && document.activeElement !== minEl) minEl.value = formatWanInput(bigDealMinAmount());
  if (maxEl && document.activeElement !== maxEl) maxEl.value = formatWanInput(bigDealMaxAmount());
}

function commitBigDealRange({ swap = true } = {}) {
  const minEl = document.getElementById("bigDealMinWan");
  const maxEl = document.getElementById("bigDealMaxWan");
  const minWan = parseWanInputValue(minEl?.value);
  const maxWan = parseWanInputValue(maxEl?.value);
  let minYuan = minWan == null ? bigDealMinAmount() : yuanFromWan(minWan);
  let maxYuan = maxWan == null ? null : yuanFromWan(maxWan);
  if (minYuan == null) minYuan = BIG_DEAL_DEFAULT_YUAN;
  if (swap && maxYuan != null && maxYuan < minYuan) {
    const tmp = minYuan;
    minYuan = maxYuan;
    maxYuan = tmp;
  }
  const minChanged = minYuan !== Number(bigDealState.minAmount);
  const prevMax = bigDealMaxAmount();
  const maxChanged = maxYuan !== prevMax;
  persistBigDealRange(minYuan, maxYuan);
  if (swap) syncBigDealRangeInputs();
  if (!minChanged && !maxChanged) return;
  window.clearTimeout(bigDealRangeReloadTimer);
  bigDealRangeReloadTimer = window.setTimeout(() => {
    if (minChanged) {
      void loadBigDeals({ keep: true });
      void loadBigDealChart({ refresh: true });
      return;
    }
    applyBigDealRangeFilter();
  }, 180);
}

function bindBigDealRange() {
  const root = els.metricsPanels || els.metricsGrid;
  if (!root || root.dataset.bigDealRangeBound === "1") return;
  root.dataset.bigDealRangeBound = "1";
  const isRangeInput = (el) => el && (el.id === "bigDealMinWan" || el.id === "bigDealMaxWan");
  root.addEventListener("input", (event) => {
    if (!isRangeInput(event.target)) return;
    event.stopPropagation();
    window.clearTimeout(bigDealRangeReloadTimer);
    bigDealRangeReloadTimer = window.setTimeout(() => commitBigDealRange({ swap: false }), 480);
  });
  root.addEventListener("change", (event) => {
    if (!isRangeInput(event.target)) return;
    event.stopPropagation();
    commitBigDealRange({ swap: true });
  });
  root.addEventListener("blur", (event) => {
    if (!isRangeInput(event.target)) return;
    commitBigDealRange({ swap: true });
  }, true);
  root.addEventListener("keydown", (event) => {
    if (!isRangeInput(event.target)) return;
    event.stopPropagation();
    if (event.key !== "Enter") return;
    event.preventDefault();
    commitBigDealRange({ swap: true });
  });
  syncBigDealRangeInputs();
}

function shiftIsoDate(iso, days) {
  const [y, m, d] = String(iso || "").split("-").map(Number);
  if (!y || !m || !d) return "";
  const dt = new Date(Date.UTC(y, m - 1, d + Number(days || 0)));
  return dt.toISOString().slice(0, 10);
}

function cnSessionDay() {
  const now = cnNowParts();
  const open = 9 * 60 + 15;
  if (now.weekday === 0) return shiftIsoDate(now.dateStr, -2);
  if (now.weekday === 6) return shiftIsoDate(now.dateStr, -1);
  if (now.minutes < open) return shiftIsoDate(now.dateStr, now.weekday === 1 ? -3 : -1);
  return now.dateStr;
}

function ticksViewDay() {
  return String(ticksState.viewDay || cnSessionDay()).slice(0, 10);
}

function isTicksHistoryView() {
  return ticksViewDay() !== cnSessionDay();
}

function syncTicksDayInput() {
  const el = document.getElementById("ticksTapeDay");
  if (!el) return;
  if (document.activeElement === el) return;
  el.value = ticksViewDay();
  el.max = cnNowParts().dateStr;
}

function bindTicksDayPicker() {
  const el = document.getElementById("ticksTapeDay");
  if (!el || el.dataset.bound === "1") return;
  el.dataset.bound = "1";
  el.addEventListener("change", () => {
    void applyTicksViewDay(el.value);
  });
}

async function applyTicksViewDay(iso) {
  const session = cnSessionDay();
  const today = cnNowParts().dateStr;
  let next = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(next)) next = session;
  if (next > today) next = today;
  const prev = ticksViewDay();
  ticksState.viewDay = next === session ? "" : next;
  if (ticksViewDay() === prev && document.getElementById("ticksTapeDay")?.value === ticksViewDay()) {
    syncTicksDayInput();
    return;
  }
  ticksState.liveFetchGen += 1;
  ticksState.loadGen += 1;
  ticksState.liveFetchPending = false;
  ticksState.linkPin = null;
  ticksState.hoverRange = null;
  ticksState.hoverSecond = null;
  ticksState.hoverTickIndexes = [];
  ticksState.hoverLinkKey = "";
  ticksState.listHover = false;
  ticksState.sessionView = null;
  hideTicksHoverCard();
  applyTicksItems([], { resetViewport: true });
  bigDealState.rawItems = [];
  bigDealState.items = [];
  bigDealState.total = 0;
  bigDealState.error = "";
  bigDealChartState.rawItems = [];
  bigDealChartState.items = [];
  bigDealChartState.error = "";
  syncTicksDayInput();
  refreshBigDealList();
  refreshTicksTapeList();
  const history = isTicksHistoryView();
  if (history) {
    ticksState.live = false;
    ticksState.phase = "closed";
    setTicksChartStatus("");
    if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
    renderTicksChart();
    void loadTicksChart({ silent: true });
    void loadBigDeals();
    void loadBigDealChart();
    return;
  }
  ticksState.phase = cnMarketPhase();
  ticksState.live = ticksState.phase === "live";
  void loadTicksChart({ silent: false, refresh: ticksState.live });
  void loadBigDeals({ refresh: ticksState.live });
  void loadBigDealChart({ refresh: ticksState.live });
  if (ticksState.live) void pollTicksLive();
}

const tapeScrollRaf = new WeakMap();

function tapeIsPinnedToLatest(scroller) {
  if (!scroller) return true;
  const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
  if (maxTop <= 4) return true;
  return scroller.scrollTop >= maxTop - 48;
}

function restoreTapeScroll(scroller, prevTop, prevHeight, followLatest = false) {
  if (!scroller) return;
  const pin = followLatest || !prevHeight;
  const apply = () => {
    if (!scroller.isConnected) return;
    const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    scroller.scrollTop = pin ? maxTop : Math.min(prevTop, maxTop);
  };
  apply();
  const prev = tapeScrollRaf.get(scroller);
  if (prev != null) window.cancelAnimationFrame(prev);
  const id = window.requestAnimationFrame(() => {
    apply();
    const id2 = window.requestAnimationFrame(() => {
      apply();
      tapeScrollRaf.delete(scroller);
    });
    tapeScrollRaf.set(scroller, id2);
  });
  tapeScrollRaf.set(scroller, id);
}

function tapeTimeKey(row) {
  return String(row?.time || "");
}

function sortTapeByTimeAsc(items) {
  return (items || [])
    .slice()
    .sort((a, b) => tapeTimeKey(a).localeCompare(tapeTimeKey(b)) || String(a?.event_id || "").localeCompare(String(b?.event_id || "")));
}

function tapeTickItems() {
  return sortTapeByTimeAsc(ticksState.allItems || []);
}

function timeToSec(value) {
  const minutes = parseClockMinutes(value);
  if (minutes == null) return null;
  return minutes * 60;
}

function tickLinkInterval(items, index) {
  if (index < 0 || index >= items.length) return null;
  const to = timeToSec(items[index]?.time);
  if (to == null) return null;
  if (index === 0) return { from: -Infinity, to, indexes: [index] };
  const from = timeToSec(items[index - 1]?.time);
  return { from: from == null ? -Infinity : from, to, indexes: [index] };
}

function tickLinkRangeForClock(clock) {
  const items = tapeTickItems();
  const key = tickClockSecond(clock);
  const sec = timeToSec(clock);
  if (sec == null) return null;
  if (!items.length) return { from: -Infinity, to: sec, indexes: [] };

  const atKey = [];
  for (let i = 0; i < items.length; i += 1) {
    if (tickClockSecond(items[i].time) === key) atKey.push(i);
  }
  if (atKey.length) {
    const first = atKey[0];
    const last = atKey[atKey.length - 1];
    const from = first > 0 ? timeToSec(items[first - 1].time) : -Infinity;
    const to = timeToSec(items[last].time);
    return { from: from == null ? -Infinity : from, to: to ?? sec, indexes: atKey };
  }

  let succ = -1;
  for (let i = 0; i < items.length; i += 1) {
    const stamp = timeToSec(items[i].time);
    if (stamp != null && stamp >= sec) {
      succ = i;
      break;
    }
  }
  if (succ >= 0) return tickLinkInterval(items, succ);
  const lastTo = timeToSec(items[items.length - 1]?.time);
  return { from: lastTo == null ? -Infinity : lastTo, to: sec, indexes: [] };
}

function linkedTickClock(range) {
  const items = tapeTickItems();
  const indexes = range?.indexes || [];
  if (!indexes.length) return "";
  return tickClockSecond(items[indexes[indexes.length - 1]]?.time);
}

function quoteClockForEvent(clock) {
  const key = tickClockSecond(clock);
  if (!key) return "";
  return linkedTickClock(tickLinkRangeForClock(clock)) || key;
}

function dealInHoverRange(clock, range = ticksState.hoverRange) {
  if (!range) return false;
  const sec = timeToSec(clock);
  return sec != null && sec > range.from && sec <= range.to;
}

function tapeLinkOriginOfRow(row) {
  if (!row) return "list";
  if (row.closest("#bigDealBody")) return "deals";
  if (row.closest("#ticksTapeBody")) return "ticks";
  return "list";
}

function scrollTapeRowsToCenter(root, rows) {
  const scroller = root?.querySelector(".big-deal-scroll, .ticks-tape-scroll");
  if (!scroller || !rows?.length) return;
  const first = rows[0];
  const last = rows[rows.length - 1];
  if (!first.isConnected || !last.isConnected) return;
  const scrollerRect = scroller.getBoundingClientRect();
  const top = first.getBoundingClientRect().top;
  const bottom = last.getBoundingClientRect().bottom;
  const groupCenter = (top + bottom) / 2;
  const viewCenter = scrollerRect.top + scroller.clientHeight / 2;
  const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
  scroller.scrollTop = Math.max(0, Math.min(maxTop, scroller.scrollTop + (groupCenter - viewCenter)));
}

function syncTapeLinkHighlight({ scroll = false, origin = "" } = {}) {
  const range = ticksState.hoverRange;
  const tickSet = new Set((ticksState.hoverTickIndexes || []).map(String));
  const prefId = String(ticksState.hoverDealPreferred?.event_id || "");
  const targets = [
    { root: document.getElementById("ticksTapeBody"), skip: origin === "ticks", kind: "ticks" },
    { root: document.getElementById("bigDealBody"), skip: origin === "deals", kind: "deals" },
  ];
  for (const { root, skip, kind } of targets) {
    if (!root) continue;
    const linked = [];
    let primary = null;
    root.querySelectorAll("tbody tr[data-clock]").forEach((tr) => {
      const on =
        kind === "ticks"
          ? tickSet.has(String(tr.dataset.tickIndex || ""))
          : dealInHoverRange(tr.dataset.time || tr.dataset.clock, range);
      const isPrimary = on && prefId && tr.dataset.eventId === prefId;
      tr.classList.toggle("is-linked", on);
      tr.classList.toggle("is-linked-primary", Boolean(isPrimary));
      if (on) linked.push(tr);
      if (isPrimary) primary = tr;
    });
    if (scroll && !skip && linked.length) {
      const focusRows = primary ? [primary] : linked;
      window.requestAnimationFrame(() => scrollTapeRowsToCenter(root, focusRows));
    }
  }
}

function ensureTicksSecondVisible(clock) {
  const off = sessionOffset(parseClockMinutes(clock));
  if (off == null) return false;
  const range = ticksEffectiveSessionRange();
  if (!range) return false;
  if (off >= range.start - 1e-6 && off <= range.end + 1e-6) return false;
  const span = Math.max(TICKS_SESSION_MIN_SPAN, range.end - range.start);
  const full = sessionDuration();
  let start = off - span / 2;
  let end = start + span;
  if (start < 0) {
    start = 0;
    end = Math.min(full, span);
  }
  if (end > full) {
    end = full;
    start = Math.max(0, full - span);
  }
  ticksState.sessionView = start <= 1e-6 && end >= full - 1e-6 ? null : { start, end };
  syncTicksChartScrollBar();
  refreshTicksChartWindowStatus();
  return true;
}

function pinTicksChartLink(clock, { preferred, scrollLists = true } = {}) {
  applyTicksLinkHover(clock, { origin: "chart", preferred, scrollLists });
  if (!ticksState.hoverSecond || !ticksState.hoverRange) {
    ticksState.linkPin = null;
    return "";
  }
  ticksState.linkPin = {
    clock: ticksState.hoverSecond,
    range: ticksState.hoverRange,
    indexes: (ticksState.hoverTickIndexes || []).slice(),
    preferred: ticksState.hoverDealPreferred,
  };
  return ticksState.hoverSecond;
}

function restoreTicksLinkPin() {
  const pin = ticksState.linkPin;
  if (!pin?.clock) return false;
  const range = tickLinkRangeForClock(pin.preferred?.time || pin.clock);
  ticksState.linkPin = {
    ...pin,
    range,
    indexes: range?.indexes || [],
  };
  ticksState.hoverSecond = pin.clock;
  ticksState.hoverRange = range;
  ticksState.hoverTickIndexes = range?.indexes || [];
  ticksState.hoverLinkKey = range
    ? `chart:${range.from}:${range.to}:${(range.indexes || []).join(",")}:${String(pin.preferred?.event_id || "")}`
    : "";
  ticksState.hoverOrigin = "chart";
  ticksState.hoverDealPreferred = pin.preferred || null;
  syncTapeLinkHighlight();
  return true;
}

function applyTicksLinkHover(clock, { origin = "chart", preferred, tickIndex, scrollLists = true } = {}) {
  const key = tickClockSecond(clock);
  if (preferred !== undefined) ticksState.hoverDealPreferred = preferred;
  const prefId = String(ticksState.hoverDealPreferred?.event_id || "");
  let range = null;
  const idx = Number(tickIndex);
  if (origin === "ticks" && tickIndex != null && String(tickIndex) !== "" && Number.isFinite(idx)) {
    range = tickLinkInterval(tapeTickItems(), idx);
  } else if (key) {
    range = tickLinkRangeForClock(preferred?.time || key);
  }
  const nextKey = range
    ? `${origin}:${range.from}:${range.to}:${(range.indexes || []).join(",")}:${prefId}`
    : "";
  const changed = nextKey !== ticksState.hoverLinkKey;
  ticksState.hoverSecond = key || null;
  ticksState.hoverRange = range;
  ticksState.hoverTickIndexes = range?.indexes || [];
  ticksState.hoverLinkKey = nextKey;
  ticksState.hoverOrigin = key ? origin : "";
  if (origin === "list" || origin === "ticks" || origin === "deals") {
    ticksState.listHover = Boolean(key);
  } else if (origin === "chart") {
    ticksState.listHover = false;
  }
  if (!key) {
    ticksState.hoverRange = null;
    ticksState.hoverTickIndexes = [];
    ticksState.hoverLinkKey = "";
    syncTapeLinkHighlight();
    return "";
  }
  if (origin !== "chart") ensureTicksSecondVisible(key);
  fillTicksQuoteCardFromSecond(linkedTickClock(range) || key);
  if (changed) {
    syncTapeLinkHighlight({ scroll: Boolean(scrollLists), origin });
    if (origin !== "chart") renderTicksChart();
  } else if (scrollLists && origin !== "chart") {
    syncTapeLinkHighlight({ scroll: true, origin });
  }
  return key;
}

function bindTapeChartLink() {
  const root = els.metricsPanels;
  if (!root || root.dataset.tapeLinkBound === "1") return;
  root.dataset.tapeLinkBound = "1";
  root.addEventListener("pointerover", (event) => {
    const row = event.target.closest("tr[data-clock]");
    if (!row || !root.contains(row)) return;
    const from = event.relatedTarget instanceof Element ? event.relatedTarget.closest("tr[data-clock]") : null;
    if (from === row) return;
    applyTicksLinkHover(row.dataset.time || row.dataset.clock, {
      origin: tapeLinkOriginOfRow(row),
      tickIndex: row.dataset.tickIndex,
      preferred: row.dataset.eventId
        ? { event_id: row.dataset.eventId, time: row.dataset.time || row.dataset.clock }
        : null,
      scrollLists: true,
    });
  });
  root.addEventListener("pointerout", (event) => {
    const row = event.target.closest("tr[data-clock]");
    if (!row) return;
    const next = event.relatedTarget instanceof Element ? event.relatedTarget.closest("tr[data-clock]") : null;
    if (next && root.contains(next)) return;
    ticksState.listHover = false;
    hideTicksHoverCard();
    renderTicksChart();
  });
}

function renderBigDealListHtml() {
  if (bigDealState.loading && !bigDealState.items.length) {
    return `<p class="muted metrics-loading">正在加载大单…</p>`;
  }
  if (bigDealState.error && !bigDealState.items.length) {
    return `<p class="muted">${escapeHtml(bigDealState.error)}</p>`;
  }
  if (!bigDealState.items.length) {
    if (isTicksHistoryView() && !bigDealState.loading) return "";
    return `<p class="muted">暂无 ${escapeHtml(bigDealRangeLabel())} 的大单</p>`;
  }
  const rows = sortTapeByTimeAsc(bigDealState.items)
    .map((row) => {
      const side = String(row.side || "");
      const tone = side === "buy" ? "change-up" : side === "sell" ? "change-down" : "";
      const tag = displayValue(row.aggressor_label);
      const lots = Number(row.volume_lots);
      const lotsText = Number.isFinite(lots) ? `${Math.round(lots)}手` : "-";
      return `<tr class="${tone}" data-clock="${escapeHtml(tickClockSecond(row.time))}" data-time="${escapeHtml(String(row.time || ""))}" data-event-id="${escapeHtml(String(row.event_id || ""))}">
          <td>${escapeHtml(displayValue(row.time))}</td>
          <td><span class="big-deal-tag">${escapeHtml(tag)}</span></td>
          <td>${escapeHtml(fmtWan(row.amount))}</td>
          <td>${escapeHtml(lotsText)}</td>
          <td>${escapeHtml(fmtNum(row.price))}</td>
        </tr>`;
    })
    .join("");
  const total = Number(bigDealState.total) || bigDealState.items.length;
  const metaBits = [
    bigDealState.sessionDay || "",
    bigDealState.cached ? "盘后缓存" : "",
    `共${total}笔`,
    bigDealRangeLabel(),
  ].filter(Boolean);
  return `
      <div class="big-deal-scroll">
        <table class="big-deal-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>主/被</th>
              <th>金额</th>
              <th>手数</th>
              <th>均价</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${metaBits.length ? `<p class="big-deal-meta muted">${escapeHtml(metaBits.join(" · "))}</p>` : ""}`;
}

function refreshBigDealList() {
  const body = document.getElementById("bigDealBody");
  if (!body) {
    if (els.metricsPanels || els.metricsGrid) renderMetrics(metricsStock);
    return;
  }
  const items = sortTapeByTimeAsc(bigDealState.items);
  const newest = items[items.length - 1];
  const paintKey = [
    bigDealState.loading ? "1" : "0",
    items.length,
    newest?.time || "",
    newest?.amount ?? "",
    newest?.event_id || "",
    bigDealRangeLabel(),
    bigDealState.error || "",
  ].join(":");
  const scroller = body.querySelector(".big-deal-scroll");
  if (paintKey === body.dataset.paintKey && scroller) {
    if (tapeIsPinnedToLatest(scroller)) restoreTapeScroll(scroller, scroller.scrollTop, scroller.scrollHeight, true);
    return;
  }
  const followLatest = tapeIsPinnedToLatest(scroller);
  const prevTop = scroller?.scrollTop || 0;
  const prevHeight = scroller?.scrollHeight || 0;
  body.dataset.paintKey = paintKey;
  body.innerHTML = renderBigDealListHtml();
  restoreTapeScroll(body.querySelector(".big-deal-scroll"), prevTop, prevHeight, followLatest);
  if (ticksState.linkPin && !ticksState.listHover) restoreTicksLinkPin();
  else syncTapeLinkHighlight();
}

function renderBigDealSection() {
  hydrateBigDealRange();
  return `
    <section class="metrics-section big-deal-section">
      <div class="big-deal-head">
        <h4 class="metrics-section-title">资金动向</h4>
        <div class="big-deal-range" aria-label="资金范围（万）">
          <input id="bigDealMinWan" class="big-deal-range-input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="最低金额（万）" placeholder="最低" value="${escapeHtml(formatWanInput(bigDealMinAmount()))}" />
          <span class="big-deal-range-sep">–</span>
          <input id="bigDealMaxWan" class="big-deal-range-input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" aria-label="最高金额（万）" placeholder="不限" value="${escapeHtml(formatWanInput(bigDealMaxAmount()))}" />
          <span class="big-deal-range-unit">万</span>
        </div>
      </div>
      <div id="bigDealBody" class="big-deal-body">${renderBigDealListHtml()}</div>
    </section>`;
}

function renderTicksTapeSection() {
  return `
    <section class="metrics-section ticks-tape-section" id="ticksTapeSection">
      <div class="ticks-tape-head">
        <h4 class="metrics-section-title">分时成交</h4>
        <p id="ticksTapeMeta" class="ticks-tape-meta muted"></p>
      </div>
      <div id="ticksTapeBody" class="ticks-tape-body"></div>
    </section>`;
}

function tickTradeCount(row) {
  const n = Number(row?.count);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 1;
}

function refreshTicksTapeList() {
  const body = document.getElementById("ticksTapeBody");
  const meta = document.getElementById("ticksTapeMeta");
  if (!body) return;
  const all = ticksState.allItems || [];
  const total = all.length;
  const items = total ? sortTapeByTimeAsc(all) : [];
  const tradeTotal = items.reduce((sum, row) => sum + tickTradeCount(row), 0);
  const metaText = [
    ticksState.tradeDate || "",
    ticksState.cached ? "盘后缓存" : "",
    ticksState.source || "",
    total ? `${total}次分时成交` : "",
    tradeTotal ? `共${tradeTotal}笔交易` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  if (meta) meta.textContent = metaText;

  const newest = items[items.length - 1];
  const paintKey = [
    "tick-count-total",
    ticksState.loading ? "1" : "0",
    total,
    tradeTotal,
    newest?.time || "",
    newest?.price ?? "",
    newest?.volume ?? "",
    newest?.count ?? "",
  ].join(":");
  if (paintKey === body.dataset.paintKey && body.querySelector("tbody")) return;
  body.dataset.paintKey = paintKey;

  let html;
  if (ticksState.loading && !total) {
    html = `<p class="muted metrics-loading">正在加载成交明细…</p>`;
  } else if (!total) {
    html = isTicksHistoryView() ? "" : `<p class="muted">${ticksState.phase === "live" ? "等待成交" : "暂无成交明细"}</p>`;
  } else {
    const rows = items
      .map((row, index) => {
        const side = tickSideMeta(row);
        const tone = side.cls;
        const clock = tickClockSecond(row.time) || displayValue(row.time);
        const lots = Number(row.volume);
        const lotsText = Number.isFinite(lots) ? fmtVolLots(lots) : "-";
        const count = Number(row.count);
        const countText = Number.isFinite(count) && count > 1 ? `/${Math.round(count)}笔` : "";
        return `<tr class="${tone}" data-clock="${escapeHtml(clock)}" data-time="${escapeHtml(String(row.time || ""))}" data-tick-index="${index}">
          <td>${escapeHtml(clock)}</td>
          <td>${escapeHtml(fmtNum(row.price))}</td>
          <td>${escapeHtml(lotsText)}${escapeHtml(countText)}</td>
          <td><span class="big-deal-tag">${escapeHtml(side.text || "-")}</span></td>
        </tr>`;
      })
      .join("");
    html = `
      <div class="big-deal-scroll ticks-tape-scroll">
        <table class="big-deal-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>成交价</th>
              <th>手数</th>
              <th>方向</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }
  const scroller = body.querySelector(".ticks-tape-scroll");
  const followLatest = tapeIsPinnedToLatest(scroller);
  const prevTop = scroller?.scrollTop || 0;
  const prevHeight = scroller?.scrollHeight || 0;
  body.innerHTML = html;
  restoreTapeScroll(body.querySelector(".ticks-tape-scroll"), prevTop, prevHeight, followLatest);
  if (ticksState.linkPin && !ticksState.listHover) restoreTicksLinkPin();
  else syncTapeLinkHighlight();
}

function flattenMetricRows(rows) {
  return (rows || []).flatMap((items) => items.filter(([, v]) => displayValue(v) !== "-"));
}

const VALUATION_HISTORY_FIELDS = {
  "市盈率(动)": "pe_dyn",
  "市盈率(静)": "pe_static",
  "市盈率(TTM)": "pe_ttm",
  市净率: "pb",
  "市销率(TTM)": "ps_ttm",
};

function valuationSeriesStats(items, key) {
  const vals = [];
  for (const item of items || []) {
    const n = Number(item?.[key]);
    if (Number.isFinite(n) && n > 0) vals.push(n);
  }
  if (!vals.length) return null;
  let high = vals[0];
  let low = vals[0];
  for (const v of vals) {
    if (v > high) high = v;
    if (v < low) low = v;
  }
  return { high, low, median: quantile(vals, 0.5) };
}

function valuationHistoryNote(label) {
  const key = VALUATION_HISTORY_FIELDS[label];
  if (!key) return "";
  const stats = valuationSeriesStats(peState.allItems, key);
  if (!stats) return "";
  return `历史最高 ${fmtNum(stats.high)}\n历史最低 ${fmtNum(stats.low)}\n中位数 ${fmtNum(stats.median)}`;
}

function renderFundamentalsRow(items) {
  if (!items.length) return "";
  return `<div class="fundamentals-row">
    <div class="company-metrics metrics-inline-row">${items.map(metricCell).join("")}</div>
  </div>`;
}

function readFundamentalsFolded() {
  try {
    return localStorage.getItem(FUNDAMENTALS_FOLD_KEY) === "1";
  } catch {
    return false;
  }
}

function persistFundamentalsFolded(folded) {
  try {
    localStorage.setItem(FUNDAMENTALS_FOLD_KEY, folded ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function applyFundamentalsFold(folded) {
  const panel = els.fundamentalsPanel;
  if (!panel) return;
  panel.classList.toggle("is-collapsed", folded);
  const btn = document.getElementById("fundamentalsFoldBtn");
  if (!btn) return;
  btn.setAttribute("aria-expanded", folded ? "false" : "true");
  btn.setAttribute("aria-label", folded ? "展开基本信息" : "折叠基本信息");
  btn.title = folded ? "展开" : "折叠";
  btn.textContent = folded ? "▸" : "▾";
}

function bindFundamentalsFold() {
  const head = document.querySelector("#fundamentalsPanel .fundamentals-head");
  if (!head || head.dataset.bound === "1") return;
  head.dataset.bound = "1";
  head.addEventListener("click", (event) => {
    if (event.target.closest(".stat-cell")) return;
    const panel = els.fundamentalsPanel;
    if (!panel || panel.classList.contains("hidden")) return;
    const next = !panel.classList.contains("is-collapsed");
    applyFundamentalsFold(next);
    persistFundamentalsFolded(next);
  });
  applyFundamentalsFold(readFundamentalsFolded());
}

function renderFundamentals(stock = metricsStock) {
  const panel = els.fundamentalsPanel;
  const body = els.fundamentalsBody;
  if (!panel || !body) return;

  const mcap =
    stock.total_market_cap ||
    (stock.market_cap ? `${displayValue(stock.market_cap)}亿` : "");
  const valuation = flattenMetricRows([
    [
      ["市盈率(动)", stock.pe],
      ["市盈率(静)", stock.pe_static],
      ["市盈率(TTM)", stock.pe_ttm],
      ["市净率", stock.pb],
      ["市销率(TTM)", stock.ps_ttm],
      ["每股净资产", stock.bvps],
    ],
  ]);
  const capital = flattenMetricRows([
    [
      ["上市时间", stock.list_date],
      ["注册资本", stock.registered_capital],
      ["发行股本", stock.issued_shares],
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
    renderFundamentalsRow(valuation.map((item) => [...item, "", valuationHistoryNote(item[0])])),
    renderFundamentalsRow(capital),
  ]
    .filter(Boolean)
    .join("");
  body.innerHTML = html;
  panel.classList.toggle("hidden", !html);
  applyFundamentalsFold(readFundamentalsFolded());
}

function renderMetrics(stock = metricsStock) {
  const panels = els.metricsPanels || els.metricsGrid;
  if (!panels) return;
  metricsStock = stock && typeof stock === "object" ? stock : metricsStock;
  renderFundamentals(metricsStock);

  const mounted = document.getElementById("bigDealBody") && document.getElementById("ticksTapeBody");
  if (mounted) {
    bindBigDealRange();
    bindTapeChartLink();
    bindTicksDayPicker();
    syncTicksDayInput();
    return;
  }

  const html = [renderTicksTapeSection(), renderBigDealSection()].filter(Boolean).join("");
  panels.innerHTML = html || `<p class="muted">暂无指标数据</p>`;
  bindBigDealRange();
  syncBigDealRangeInputs();
  bindTapeChartLink();
  bindTicksDayPicker();
  syncTicksDayInput();
  refreshTicksTapeList();
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
  notifyAnalysisIdentity(stock, { ready: true });
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

async function loadBigDeals({ refresh = false, keep = false } = {}) {
  if (!code) return;
  hydrateBigDealRange();
  if (!keep || !bigDealState.items.length) {
    bigDealState.loading = !bigDealState.items.length;
    refreshBigDealList();
  }
  try {
    const qs = new URLSearchParams({
      code,
      scope: "big_deal",
      source: "tonghuashun",
      limit: "0",
      order: "asc",
      min_amount: String(bigDealMinAmount()),
    });
    if (refresh && !isTicksHistoryView()) qs.set("refresh", "1");
    qs.set("day", ticksViewDay());
    const json = await api(`/api/stocks/fund-flow?${qs.toString()}`);
    const data = json.data || {};
    bigDealState.rawItems = Array.isArray(data.items) ? data.items : [];
    bigDealState.items = filterBigDealsByRange(bigDealState.rawItems);
    bigDealState.note = String(data.note || "");
    bigDealState.cached = Boolean(data.cached);
    bigDealState.sessionDay = String(data.session_day || "");
    bigDealState.total = bigDealState.items.length;
    bigDealState.error = "";
  } catch (err) {
    bigDealState.error = err.message || String(err);
    if (!bigDealState.items.length) {
      bigDealState.rawItems = [];
      bigDealState.items = [];
    }
  } finally {
    bigDealState.loading = false;
    refreshBigDealList();
  }
}

async function loadBigDealChart({ refresh = false } = {}) {
  if (!code) return;
  hydrateBigDealRange();
  bigDealChartState.loading = !bigDealChartState.items.length;
  try {
    const qs = new URLSearchParams({
      code,
      scope: "big_deal",
      source: "tonghuashun",
      limit: "0",
      min_amount: String(bigDealMinAmount()),
    });
    if (refresh && !isTicksHistoryView()) qs.set("refresh", "1");
    qs.set("day", ticksViewDay());
    const json = await api(`/api/stocks/fund-flow?${qs.toString()}`);
    const data = json.data || {};
    bigDealChartState.rawItems = Array.isArray(data.items) ? data.items : [];
    bigDealChartState.items = filterBigDealsByRange(bigDealChartState.rawItems);
    bigDealChartState.note = String(data.note || "");
    bigDealChartState.cached = Boolean(data.cached);
    bigDealChartState.sessionDay = String(data.session_day || "");
    bigDealChartState.error = "";
  } catch (err) {
    bigDealChartState.error = err.message || String(err);
    if (!bigDealChartState.items.length) {
      bigDealChartState.rawItems = [];
      bigDealChartState.items = [];
    }
  } finally {
    bigDealChartState.loading = false;
    if (isQuotesPanel() && els.ticksChart) renderTicksChart();
  }
}

async function loadProfile({ silent = false, refresh = false, liveOnly = false } = {}) {
  if (!code) {
    setError("缺少公司代码");
    return null;
  }

  if (!silent) {
    applyHeaderOnly({ code, name: nameHint });
    bigDealState.loading = !bigDealState.items.length;
    renderMetrics(metricsStock);
    void loadBigDeals({ refresh });
    void loadBigDealChart({ refresh });
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
    applyStock(stock, data.industry || {});
    if (liveOnly && !isTicksHistoryView()) {
      const live = cnMarketPhase() === "live";
      void loadBigDeals({ refresh: live });
      void loadBigDealChart({ refresh: live });
    }
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
    }
    return null;
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
  notifyAnalysisIdentity(stock, { ready: false });
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
  if (group === NEWS_GROUP_FINANCIALS) {
    await loadFinancials({ refresh });
    return;
  }
  if (group === NEWS_GROUP_OTHER) {
    await loadOtherNews();
  } else {
    await loadOfficialNews();
  }
}

function syncNewsRefreshButtons() {
  const onNews = activeMainPanel === "news";
  const onFinancials = newsGroup === NEWS_GROUP_FINANCIALS;
  if (els.refreshNewsBtn) {
    els.refreshNewsBtn.hidden = !onNews || onFinancials;
  }
  if (els.refreshFinancialsBtn) {
    els.refreshFinancialsBtn.hidden = !onNews || !onFinancials;
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
  syncNewsRefreshButtons();
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

function syncOthersRefreshButtons() {
  const onOthers = activeMainPanel === "others";
  if (els.refreshListBtn) {
    els.refreshListBtn.hidden = !onOthers || othersSubTab !== "lhb";
  }
  if (els.refreshHoldersBtn) {
    els.refreshHoldersBtn.hidden = !onOthers || othersSubTab !== "holders";
  }
}

function syncOthersSubTabUi() {
  const view = othersSubTab;
  if (els.panelOthers) {
    els.panelOthers.dataset.othersView = view;
  }
  if (els.othersSourceBar) {
    els.othersSourceBar.querySelectorAll("[data-source]").forEach((btn) => {
      const active = btn.getAttribute("data-source") === view;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  syncOthersRefreshButtons();
}

function bootstrapOthersSubTab(view = othersSubTab) {
  if (view === "lhb") {
    if (!companyListBootstrapped) {
      companyListBootstrapped = true;
      loadCompanyList({ refresh: false });
    }
  } else if (view === "holders") {
    if (!holdersBootstrapped) {
      holdersBootstrapped = true;
      fundHoldersBootstrapped = true;
      loadHolders({ refresh: false });
      loadHolderNum({ refresh: false });
      loadFundHolders({ refresh: false });
    }
  }
}

function setOthersSubTab(nextView, { reload = true } = {}) {
  const view = normalizeOthersSubTab(nextView);
  if (view === othersSubTab) return;
  othersSubTab = view;
  syncOthersSubTabUi();
  if (!reload || activeMainPanel !== "others") return;
  bootstrapOthersSubTab(view);
}

function syncJudgmentSubTabUi() {
  const view = judgmentSubTab;
  const family = EARNINGS_VIEWS.has(view) ? "earnings" : view;
  if (els.panelJudgment) {
    els.panelJudgment.dataset.judgmentView = view;
    els.panelJudgment.dataset.judgmentFamily = family;
  }
  if (els.judgmentSourceBar) {
    els.judgmentSourceBar.querySelectorAll("[data-source]").forEach((btn) => {
      const active = btn.getAttribute("data-source") === family;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  if (els.earningsSourceBar) {
    els.earningsSourceBar.hidden = family !== "earnings";
    els.earningsSourceBar.querySelectorAll("[data-source]").forEach((btn) => {
      const active = btn.getAttribute("data-source") === view;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
}

function bootstrapJudgmentSubTab(view = judgmentSubTab) {
  window.CompanyAnalysis?.onPanel?.(view);
}

function setJudgmentSubTab(nextView, { reload = true } = {}) {
  const view = normalizeJudgmentSubTab(nextView);
  if (view === judgmentSubTab) return;
  judgmentSubTab = view;
  syncJudgmentSubTabUi();
  if (!reload || activeMainPanel !== "judgment") return;
  bootstrapJudgmentSubTab(view);
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
    els.emotionSearchTitle.textContent = isXqEmotion(source) ? "搜帖" : "股吧搜索";
  }
  if (els.emotionSearchKeyword) {
    els.emotionSearchKeyword.placeholder = isXqEmotion(source)
      ? "关键词搜帖，默认可用公司名"
      : "搜帖，默认可用公司名";
  }
  paintEmotionScores();
  paintEmotionRank();
  paintEmotionPosts();
  paintEmotionSearch();
  if (isThsEmotion(source)) {
    setEmotionDetailOpen(Boolean(thsEmotionState.detail.postId));
    paintThsEmotionDetail();
  } else if (isXqEmotion(source)) {
    setEmotionDetailOpen(Boolean(xqEmotionState.detail?.postId));
    paintXqEmotionDetail();
  } else {
    setEmotionDetailOpen(Boolean(emotionState.detail?.postId));
    paintEmotionDetail();
  }
  syncEmotionHubLayout();
}

function setEmotionSource(nextSource, { reload = true } = {}) {
  const source = normalizeEmotionSource(nextSource);
  if (source === emotionSource) return;
  closeEmotionDetail();
  emotionSource = source;
  syncEmotionSourceUi();
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
            ${item.user_tag && String(item.user_tag).toLowerCase() !== "ordinary" ? `<span>${escapeHtml(thsIdentityLabel(item.user_tag) || "认证")}</span>` : ""}
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
  const currentRank = data?.rank;
  const hero = currentRank
    ? `<div class="em-rank-now">
         <span>当前人气</span>
         <strong>${escapeHtml(String(currentRank))}</strong>
         <em>名</em>
       </div>`
    : "";
  if (!items.length) {
    return `${hero}<p class="muted">${escapeHtml(data?.error || "暂无人气排名数据")}</p>`;
  }
  const rows = [...items]
    .reverse()
    .map((item) => {
      const rnk = item.rank != null && item.rank !== "" ? String(item.rank) : "-";
      const day = String(item.published_at || "").slice(0, 10);
      const url = String(item.url || "").trim();
      const place = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(rnk)}</a>`
        : escapeHtml(rnk);
      return `
        <article class="em-rank-row">
          <time>${escapeHtml(day || "-")}</time>
          <span class="em-rank-place">${place}</span>
        </article>
      `;
    })
    .join("");
  return `${hero}<div class="em-rank-rows">${rows}</div>`;
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
  if (isThsEmotion()) return;
  if (isXqEmotion()) return paintXqEmotionRank();
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
  if (!isThsEmotion()) paintThsVoteSlot("");
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
  syncEmPostSelection();
}

function paintEmotionSearch() {
  if (isThsEmotion()) return;
  if (isXqEmotion()) return paintXqEmotionSearch();
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
  if (isThsEmotion()) return { keyword: "", sort: "hot", maxPages: 3 };
  if (isXqEmotion()) return xqEmotionSearchQueryParams();
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
  if (isThsEmotion()) return;
  if (isXqEmotion()) return loadXqEmotionRank();
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
  if (isThsEmotion()) return;
  if (isXqEmotion()) return loadXqEmotionSearch();
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

const FUND_HOLDERS_REPORT_DATES = [
  "2025-06-30",
  "2025-03-31",
  "2024-12-31",
  "2024-09-30",
  "2024-06-30",
  "2024-03-31",
  "2023-12-31",
  "2023-09-30",
];

function syncFundHoldersDateOptions() {
  if (!els.fundHoldersDate) return;
  const current = els.fundHoldersDate.value || "";
  const dates = [...FUND_HOLDERS_REPORT_DATES];
  const loaded = fundHoldersState.reportDate;
  if (loaded && !dates.includes(loaded)) {
    dates.unshift(loaded);
  }
  const options = ['<option value="">最新</option>'];
  for (const date of dates) {
    options.push(
      `<option value="${escapeHtml(date)}"${current === date ? " selected" : ""}>${escapeHtml(date)}</option>`
    );
  }
  els.fundHoldersDate.innerHTML = options.join("");
}

function fundHolderSortValue(item, key = fundHoldersState.sortKey) {
  if (key === "shares") return Number(item?.shares);
  if (key === "free") return Number(item?.free_float_ratio_raw);
  if (key === "mv") return Number(item?.market_value_raw);
  return Number(item?.weight_raw);
}

function sortedFundHolders(items = fundHoldersState.items) {
  const list = Array.isArray(items) ? [...items] : [];
  const key = fundHoldersState.sortKey || "shares";
  const dir = fundHoldersState.sortDir === "asc" ? 1 : -1;
  list.sort((a, b) => {
    const av = fundHolderSortValue(a, key);
    const bv = fundHolderSortValue(b, key);
    const aOk = Number.isFinite(av);
    const bOk = Number.isFinite(bv);
    if (!aOk && !bOk) return 0;
    if (!aOk) return 1;
    if (!bOk) return -1;
    if (av === bv) return 0;
    return av > bv ? dir : -dir;
  });
  return list;
}

function syncFundHoldersSortButtons() {
  const root = els.fundHoldersBody;
  if (!root) return;
  root.querySelectorAll("[data-fund-sort]").forEach((btn) => {
    const key = btn.getAttribute("data-fund-sort") || "";
    const active = key === fundHoldersState.sortKey;
    btn.classList.toggle("is-active", active);
    btn.classList.toggle("is-asc", active && fundHoldersState.sortDir === "asc");
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function paintFundHolders() {
  const st = fundHoldersState;
  const sortLabels = {
    shares: "持股数量",
    weight: "占净值比",
    free: "占流通股",
    mv: "持股市值",
  };
  const sortLabel = sortLabels[st.sortKey] || "持股数量";
  const sortDirLabel = st.sortDir === "asc" ? "升序" : "降序";
  if (els.fundHoldersMeta) {
    const bits = [];
    if (st.reportDate) bits.push(`报告期 ${st.reportDate}`);
    if (st.count) bits.push(`${st.count} 只基金`);
    if (st.updatedAt) bits.push(`更新 ${st.updatedAt}`);
    els.fundHoldersMeta.textContent = st.loading
      ? "正在加载基金持股…"
      : bits.join(" · ");
  }
  if (els.fundHoldersHint) {
    els.fundHoldersHint.textContent = st.loading
      ? "正在拉取基金持股…"
      : st.error
        ? st.error
        : `按${sortLabel}${sortDirLabel} · 点击表头切换 · 基金季报披露`;
  }
  syncFundHoldersSortButtons();
  if (!els.fundHoldersBodyRows) return;
  if (st.loading) {
    els.fundHoldersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">正在加载…</td></tr>`;
    return;
  }
  if (st.error) {
    els.fundHoldersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">${escapeHtml(st.error)}</td></tr>`;
    return;
  }
  if (!st.items.length) {
    els.fundHoldersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">暂无基金持股数据</td></tr>`;
    return;
  }
  els.fundHoldersBodyRows.innerHTML = sortedFundHolders(st.items)
    .map((item, idx) => {
      const fundCode = escapeHtml(item.code || "");
      const fundName = escapeHtml(item.name || "-");
      const shares = escapeHtml(displayValue(item.shares_fmt || fmtVol(item.shares)));
      const weight = escapeHtml(displayValue(item.weight));
      const freeRatio = escapeHtml(displayValue(item.free_float_ratio));
      const marketValue = escapeHtml(displayValue(item.market_value));
      return `<tr class="is-row">
        <td>${idx + 1}</td>
        <td class="mono">${fundCode}</td>
        <td>${fundName}</td>
        <td class="num">${shares}</td>
        <td class="num">${weight}</td>
        <td class="num">${freeRatio}</td>
        <td class="num">${marketValue}</td>
      </tr>`;
    })
    .join("");
}

async function loadFundHolders({ refresh = false } = {}) {
  if (!code || fundHoldersState.loading) return;
  const reportDate = (els.fundHoldersDate?.value || "").trim();
  fundHoldersState.loading = true;
  fundHoldersState.error = "";
  paintFundHolders();
  paintHoldingsStats();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;
  if (els.fundHoldersDate) {
    els.fundHoldersDate.disabled = true;
    els.fundHoldersDate.value = reportDate;
  }
  try {
    const qs = new URLSearchParams({ code });
    if (reportDate) qs.set("date", reportDate);
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/fund-holders?${qs.toString()}`);
    const data = json.data || {};
    fundHoldersState.items = Array.isArray(data.items) ? data.items : [];
    fundHoldersState.count = Number(data.count) || fundHoldersState.items.length;
    fundHoldersState.reportDate = data.report_date || reportDate || "";
    fundHoldersState.updatedAt = data.updated_at || new Date().toLocaleString("zh-CN", { hour12: false });
    syncFundHoldersDateOptions();
    if (els.fundHoldersBody) els.fundHoldersBody.scrollTop = 0;
  } catch (err) {
    fundHoldersState.items = [];
    fundHoldersState.count = 0;
    fundHoldersState.error = err.message || String(err);
  } finally {
    fundHoldersState.loading = false;
    if (els.refreshHoldersBtn) {
      els.refreshHoldersBtn.disabled = holdersState.loading || holderNumState.loading;
    }
    if (els.fundHoldersDate) {
      els.fundHoldersDate.disabled = false;
      els.fundHoldersDate.value = reportDate;
    }
    paintFundHolders();
    paintHoldingsStats();
  }
}

function setupFundHoldersBox() {
  syncFundHoldersDateOptions();
  if (els.fundHoldersDate && els.fundHoldersDate.dataset.bound !== "1") {
    els.fundHoldersDate.dataset.bound = "1";
    els.fundHoldersDate.addEventListener("change", () => {
      loadFundHolders({ refresh: false });
    });
  }
  if (els.fundHoldersBody && els.fundHoldersBody.dataset.sortBound !== "1") {
    els.fundHoldersBody.dataset.sortBound = "1";
    els.fundHoldersBody.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-fund-sort]");
      if (!btn || !els.fundHoldersBody.contains(btn)) return;
      const key = btn.getAttribute("data-fund-sort") || "shares";
      if (fundHoldersState.sortKey === key) {
        fundHoldersState.sortDir = fundHoldersState.sortDir === "desc" ? "asc" : "desc";
      } else {
        fundHoldersState.sortKey = key;
        fundHoldersState.sortDir = "desc";
      }
      paintFundHolders();
    });
  }
  setupHoldingsStatsChart();
}

function normalizeHoldingsName(value) {
  return String(value || "")
    .replace(/[\s　]+/g, "")
    .replace(/[（(].*?[）)]/g, "")
    .toLowerCase();
}

function fundRatioPct(item, totalShares) {
  const direct = Number(item?.total_share_ratio_raw);
  if (Number.isFinite(direct)) return direct;
  const shares = Number(item?.shares);
  if (Number.isFinite(shares) && Number.isFinite(totalShares) && totalShares > 0) {
    return (shares / totalShares) * 100;
  }
  return null;
}

function computeHoldingsStats() {
  const holders = Array.isArray(holdersState.items) ? holdersState.items : [];
  const funds = Array.isArray(fundHoldersState.items) ? fundHoldersState.items : [];
  const totalShares = holdersState.totalShares;
  const topKeys = new Set();
  let majorPct = 0;
  let majorShares = 0;
  let majorCount = 0;
  for (const item of holders) {
    const nameKey = normalizeHoldingsName(item?.name);
    if (nameKey) topKeys.add(nameKey);
    const code = String(item?.holder_code || "").trim();
    if (code) topKeys.add(code.toLowerCase());
    majorCount += 1;
    const ratio = Number(item?.ratio);
    if (Number.isFinite(ratio)) majorPct += ratio;
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) majorShares += shares;
  }

  let fundPct = 0;
  let fundShares = 0;
  let fundCount = 0;
  let deduped = 0;
  const seenFunds = new Set();
  for (const item of funds) {
    const code = String(item?.code || "").trim().toLowerCase();
    const nameKey = normalizeHoldingsName(item?.name);
    const dedupeKey = code || nameKey;
    if (dedupeKey && seenFunds.has(dedupeKey)) {
      deduped += 1;
      continue;
    }
    if (dedupeKey) seenFunds.add(dedupeKey);
    const inTop =
      (code && topKeys.has(code)) || (nameKey && topKeys.has(nameKey));
    if (inTop) {
      deduped += 1;
      continue;
    }
    fundCount += 1;
    const ratio = fundRatioPct(item, totalShares);
    if (Number.isFinite(ratio)) fundPct += ratio;
    const shares = Number(item?.shares);
    if (Number.isFinite(shares)) fundShares += shares;
  }

  if ((!Number.isFinite(majorPct) || majorPct <= 0) && majorShares > 0 && totalShares > 0) {
    majorPct = (majorShares / totalShares) * 100;
  }
  if ((!Number.isFinite(fundPct) || fundPct <= 0) && fundShares > 0 && totalShares > 0) {
    fundPct = (fundShares / totalShares) * 100;
  }

  majorPct = Math.max(0, Number.isFinite(majorPct) ? majorPct : 0);
  fundPct = Math.max(0, Number.isFinite(fundPct) ? fundPct : 0);
  const used = majorPct + fundPct;
  const otherPct = used > 0 ? Math.max(0, 100 - used) : 0;
  return {
    ready: holders.length > 0 || funds.length > 0,
    loading: holdersState.loading || fundHoldersState.loading,
    error: holdersState.error || fundHoldersState.error || "",
    majorPct,
    fundPct,
    otherPct,
    majorShares,
    fundShares,
    majorCount,
    fundCount,
    deduped,
    holdersDate: holdersState.reportDate || "",
    fundsDate: fundHoldersState.reportDate || "",
  };
}

function paintHoldingsStats() {
  const stats = computeHoldingsStats();
  if (els.holdingsStatsMeta) {
    if (stats.loading) {
      els.holdingsStatsMeta.textContent = "正在汇总持股结构…";
    } else if (!stats.ready) {
      els.holdingsStatsMeta.textContent = stats.error || "暂无持股统计";
    } else {
      const bits = [];
      if (stats.holdersDate || stats.fundsDate) {
        bits.push(
          stats.holdersDate && stats.fundsDate && stats.holdersDate !== stats.fundsDate
            ? `股东 ${stats.holdersDate} / 基金 ${stats.fundsDate}`
            : `报告期 ${stats.holdersDate || stats.fundsDate}`
        );
      }
      if (stats.deduped) bits.push(`去重 ${stats.deduped}`);
      els.holdingsStatsMeta.textContent = bits.join(" · ") || "持股结构";
    }
  }

  const empty = !stats.loading && !stats.ready;
  if (els.holdingsStatsChartEmpty) {
    els.holdingsStatsChartEmpty.classList.toggle("hidden", !empty);
    els.holdingsStatsChartEmpty.textContent = stats.error || "暂无持股统计";
  }
  if (els.holdingsStatsBar) {
    if (!stats.ready) {
      els.holdingsStatsBar.hidden = true;
      els.holdingsStatsBar.innerHTML = "";
      els.holdingsStatsBar.removeAttribute("aria-label");
    } else {
      const segs = [
        ["major", stats.majorPct],
        ["fund", stats.fundPct],
        ["other", stats.otherPct],
      ].filter(([, pct]) => Number.isFinite(pct) && pct > 0.0001);
      els.holdingsStatsBar.hidden = false;
      els.holdingsStatsBar.setAttribute(
        "aria-label",
        `大股东 ${stats.majorPct.toFixed(2)}%，基金 ${stats.fundPct.toFixed(2)}%，其他 ${stats.otherPct.toFixed(2)}%`
      );
      els.holdingsStatsBar.innerHTML = segs
        .map(
          ([key, pct]) =>
            `<span class="holdings-stats-seg holdings-stats-seg--${key}" style="flex:${pct.toFixed(3)} 0 0"></span>`
        )
        .join("");
    }
  }

  if (!els.holdingsStatsLegend) return;
  if (!stats.ready) {
    els.holdingsStatsLegend.innerHTML = "";
    return;
  }

  const rows = [
    {
      key: "major",
      label: "大股东",
      value: `${stats.majorPct.toFixed(2)}%`,
      detail: [
        stats.majorCount ? `${stats.majorCount} 户` : "",
        stats.majorShares > 0 ? `${fmtVol(stats.majorShares)}股` : "",
      ]
        .filter(Boolean)
        .join(" · ") || "前十大股东",
    },
    {
      key: "fund",
      label: "基金",
      value: `${stats.fundPct.toFixed(2)}%`,
      detail: stats.fundCount
        ? `${stats.fundCount} 只${stats.fundShares > 0 ? ` · ${fmtVol(stats.fundShares)}股` : ""}`
        : stats.deduped
          ? "已计入大股东"
          : "基金季报",
    },
    {
      key: "other",
      label: "其他",
      value: `${stats.otherPct.toFixed(2)}%`,
      detail: "剩余股本",
    },
  ];

  els.holdingsStatsLegend.innerHTML = rows
    .map(
      (row) => `<li class="holdings-stats-metric holdings-stats-metric--${row.key}">
        <span class="holdings-stats-metric-label">${escapeHtml(row.label)}</span>
        <span class="holdings-stats-metric-value">${escapeHtml(row.value)}</span>
        <span class="holdings-stats-metric-detail">${escapeHtml(row.detail)}</span>
      </li>`
    )
    .join("");
}

function setupHoldingsStatsChart() {
  // no-op placeholder kept for existing setupFundHoldersBox() call
}

function holderChangeClass(item) {
  const n = Number(item?.change);
  if (Number.isFinite(n) && n !== 0) return n > 0 ? "change-up" : "change-down";
  const text = `${item?.status || ""} ${item?.change_fmt || ""}`;
  if (/增持|新进/.test(text)) return "change-up";
  if (/减持|减仓|退出/.test(text)) return "change-down";
  return "";
}

function mergeHolderReportDates(incoming) {
  const dates = [];
  const seen = new Set();
  for (const date of [...(incoming || []), ...(holdersState.reportDates || [])]) {
    const day = String(date || "").trim();
    if (!day || seen.has(day)) continue;
    seen.add(day);
    dates.push(day);
  }
  dates.sort((a, b) => b.localeCompare(a));
  return dates;
}

function syncHoldersDateOptions() {
  if (!els.holdersDate) return;
  const select = els.holdersDate;
  const current = select.value || "";
  const dates = mergeHolderReportDates([holdersState.reportDate]);
  holdersState.reportDates = dates;
  const nextValues = ["", ...dates];
  const prevValues = [...select.options].map((opt) => opt.value);
  const same =
    prevValues.length === nextValues.length &&
    prevValues.every((value, idx) => value === nextValues[idx]);
  if (!same) {
    select.innerHTML = [
      '<option value="">最新</option>',
      ...dates.map((date) => `<option value="${escapeHtml(date)}">${escapeHtml(date)}</option>`),
    ].join("");
  }
  if (current && dates.includes(current)) select.value = current;
  else if (!current) select.value = "";
}

function paintHolders() {
  const st = holdersState;
  if (els.holdersMeta) {
    const bits = [];
    if (st.reportDate) bits.push(`报告期 ${st.reportDate}`);
    if (st.count) bits.push(`${st.count} 人`);
    if (st.totalSharesFmt) bits.push(`总股本 ${st.totalSharesFmt}`);
    if (st.updatedAt) bits.push(`更新 ${st.updatedAt}`);
    els.holdersMeta.textContent = st.loading
      ? "正在加载前十大股东…"
      : bits.join(" · ");
  }
  if (els.holdersHint) {
    els.holdersHint.textContent = st.loading
      ? "正在拉取前十大股东…"
      : st.error
        ? st.error
        : "按持股数量排名 · 定期报告披露";
  }
  if (!els.holdersBodyRows) return;
  if (st.loading) {
    els.holdersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">正在加载…</td></tr>`;
    return;
  }
  if (st.error) {
    els.holdersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">${escapeHtml(st.error)}</td></tr>`;
    return;
  }
  if (!st.items.length) {
    els.holdersBodyRows.innerHTML = `<tr class="is-empty"><td colspan="7">暂无十大股东数据</td></tr>`;
    return;
  }
  els.holdersBodyRows.innerHTML = st.items
    .map((item) => {
      const rank = escapeHtml(item.rank || "");
      const name = escapeHtml(item.name || "-");
      const shares = escapeHtml(displayValue(item.shares_fmt));
      const ratio = escapeHtml(displayValue(item.ratio_fmt));
      const change = escapeHtml(displayValue(item.change_fmt));
      const kind = escapeHtml(displayValue(item.shares_type || item.holder_type));
      const marketValue = escapeHtml(displayValue(item.market_value_fmt));
      const changeCls = holderChangeClass(item);
      return `<tr class="is-row">
        <td>${rank}</td>
        <td>${name}</td>
        <td class="num">${shares}</td>
        <td class="num">${ratio}</td>
        <td class="num ${changeCls}">${change}</td>
        <td>${kind}</td>
        <td class="num">${marketValue}</td>
      </tr>`;
    })
    .join("");
}

async function loadHolders({ refresh = false } = {}) {
  if (!code || holdersState.loading) return;
  const reportDate = (els.holdersDate?.value || "").trim();
  holdersState.loading = true;
  holdersState.error = "";
  paintHolders();
  paintHoldingsStats();
  if (els.refreshHoldersBtn) els.refreshHoldersBtn.disabled = true;
  if (els.holdersDate) {
    els.holdersDate.disabled = true;
    els.holdersDate.value = reportDate;
  }
  try {
    const qs = new URLSearchParams({ code });
    if (reportDate) qs.set("date", reportDate);
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/holders?${qs.toString()}`);
    const data = json.data || {};
    holdersState.items = Array.isArray(data.items) ? data.items : [];
    holdersState.count = Number(data.count) || holdersState.items.length;
    holdersState.reportDate = data.report_date || reportDate || "";
    holdersState.reportDates = mergeHolderReportDates(data.report_dates);
    holdersState.totalShares = Number(data.total_shares);
    if (!Number.isFinite(holdersState.totalShares)) holdersState.totalShares = null;
    holdersState.totalSharesFmt = data.total_shares_fmt || "";
    holdersState.updatedAt = data.updated_at || new Date().toLocaleString("zh-CN", { hour12: false });
    syncHoldersDateOptions();
    if (els.holdersBody) els.holdersBody.scrollTop = 0;
  } catch (err) {
    holdersState.items = [];
    holdersState.count = 0;
    holdersState.totalShares = null;
    holdersState.error = err.message || String(err);
  } finally {
    holdersState.loading = false;
    if (els.refreshHoldersBtn) {
      els.refreshHoldersBtn.disabled =
        fundHoldersState.loading || holderNumState.loading;
    }
    if (els.holdersDate) {
      els.holdersDate.disabled = false;
      if (reportDate && (holdersState.reportDates || []).includes(reportDate)) {
        els.holdersDate.value = reportDate;
      } else if (!reportDate) {
        els.holdersDate.value = "";
      }
    }
    paintHolders();
    paintHoldingsStats();
  }
}

function setupHoldersBox() {
  syncHoldersDateOptions();
  if (els.holdersDate && els.holdersDate.dataset.bound !== "1") {
    els.holdersDate.dataset.bound = "1";
    els.holdersDate.addEventListener("change", () => {
      loadHolders({ refresh: false });
    });
  }
  setupHolderNumChart();
}

function setHolderNumStatus(message, { empty = false } = {}) {
  if (els.holderNumMeta) els.holderNumMeta.textContent = message || "";
  if (els.holderNumChartEmpty) {
    els.holderNumChartEmpty.textContent = empty ? message || "暂无股东户数" : "暂无股东户数";
    els.holderNumChartEmpty.classList.toggle("hidden", !empty);
  }
}

function hideHolderNumHoverCard() {
  if (!els.holderNumHoverCard) return;
  els.holderNumHoverCard.classList.add("hidden");
  els.holderNumHoverCard.setAttribute("aria-hidden", "true");
  els.holderNumHoverCard.innerHTML = "";
}

function showHolderNumHoverCard() {
  if (!els.holderNumHoverCard) return;
  els.holderNumHoverCard.classList.remove("hidden");
  els.holderNumHoverCard.setAttribute("aria-hidden", "false");
}

function paintHolderNumHover(item) {
  if (!els.holderNumHoverCard || !item) return;
  const changeTone =
    Number(item.change) > 0 ? "up" : Number(item.change) < 0 ? "down" : "";
  const rows = [
    ["户数", item.holder_num_fmt || fmtVol(item.holder_num)],
    ["变动", item.change_fmt || "—", changeTone],
    ["环比", item.change_ratio_fmt || "—", changeTone],
    ["户均持股", item.avg_hold_num_fmt || fmtVol(item.avg_hold_num)],
  ]
    .map(([label, value, tone]) => {
      const cls = tone ? ` chart-hover-card-value--${tone}` : "";
      return `<span class="chart-hover-card-row"><span class="chart-hover-card-label">${escapeHtml(label)}</span><span class="chart-hover-card-value${cls}">${escapeHtml(displayValue(value))}</span></span>`;
    })
    .join("");
  els.holderNumHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline"><span class="chart-hover-card-time">${escapeHtml(item.time || "")}</span>${rows}</div>`;
  showHolderNumHoverCard();
}

function holderNumLayout(w, h) {
  const padL = 54;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  return {
    w,
    h,
    padL,
    padR,
    padT,
    padB,
    plotW: Math.max(1, w - padL - padR),
    plotH: Math.max(1, h - padT - padB),
  };
}

function fitHolderNumCanvas() {
  const canvas = els.holderNumChart;
  const wrap = els.holderNumChartWrap;
  if (!canvas || !wrap) return null;
  const rect = wrap.getBoundingClientRect();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(1, Math.floor(rect.height || 168));
  const nextW = Math.floor(width * dpr);
  const nextH = Math.floor(height * dpr);
  const resized = canvas.width !== nextW || canvas.height !== nextH;
  if (resized) {
    canvas.width = nextW;
    canvas.height = nextH;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height, layout: holderNumLayout(width, height), resized };
}

function renderHolderNumChart(hoverIndex = holderNumState.hoverIndex) {
  const pack = fitHolderNumCanvas();
  if (!pack) return;
  const { ctx, layout } = pack;
  const items = holderNumState.items || [];
  const colors = chartColors();
  ctx.clearRect(0, 0, layout.w, layout.h);

  if (!items.length) {
    hideHolderNumHoverCard();
    return;
  }

  const values = items
    .map((d) => Number(d.holder_num))
    .filter((n) => Number.isFinite(n));
  if (!values.length) {
    setHolderNumStatus("暂无股东户数", { empty: true });
    return;
  }

  let vmin = Math.min(...values);
  let vmax = Math.max(...values);
  if (vmin === vmax) {
    vmin -= Math.abs(vmin) * 0.05 || 1;
    vmax += Math.abs(vmax) * 0.05 || 1;
  }
  const pad = (vmax - vmin) * 0.08;
  vmin -= pad;
  vmax += pad;

  const n = items.length;
  const xAt = (i) => layout.padL + (n <= 1 ? layout.plotW / 2 : (i / (n - 1)) * layout.plotW);
  const yAt = (v) => layout.padT + ((vmax - v) / (vmax - vmin)) * layout.plotH;

  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i += 1) {
    const y = layout.padT + (layout.plotH * i) / 3;
    ctx.beginPath();
    ctx.moveTo(layout.padL, y);
    ctx.lineTo(layout.padL + layout.plotW, y);
    ctx.stroke();
  }

  ctx.fillStyle = colors.muted;
  ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 3; i += 1) {
    const v = vmax - ((vmax - vmin) * i) / 3;
    const y = layout.padT + (layout.plotH * i) / 3;
    ctx.fillText(fmtVol(v), layout.padL - 8, y);
  }

  ctx.beginPath();
  items.forEach((d, i) => {
    const v = Number(d.holder_num);
    if (!Number.isFinite(v)) return;
    const x = xAt(i);
    const y = yAt(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 2;
  ctx.stroke();

  const last = items[items.length - 1];
  if (last && Number.isFinite(Number(last.holder_num))) {
    const x = xAt(items.length - 1);
    const y = yAt(Number(last.holder_num));
    ctx.fillStyle = colors.accent;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = colors.muted;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const labelIdx = [0, Math.floor((n - 1) / 2), n - 1].filter((v, i, arr) => arr.indexOf(v) === i);
  for (const i of labelIdx) {
    const d = items[i];
    if (!d) continue;
    ctx.fillText(String(d.time || "").slice(0, 7), xAt(i), layout.padT + layout.plotH + 8);
  }

  const hi = hoverIndex == null ? null : Math.max(0, Math.min(n - 1, hoverIndex));
  if (hi != null && items[hi]) {
    const d = items[hi];
    const v = Number(d.holder_num);
    const x = xAt(hi);
    const y = Number.isFinite(v) ? yAt(v) : layout.padT + layout.plotH / 2;
    ctx.strokeStyle = colors.cross;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, layout.padT);
    ctx.lineTo(x, layout.padT + layout.plotH);
    ctx.stroke();
    if (Number.isFinite(v)) {
      ctx.fillStyle = colors.accent;
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
    paintHolderNumHover(d);
  } else {
    hideHolderNumHoverCard();
  }
}

function refreshHolderNumMeta() {
  const st = holderNumState;
  if (st.loading) {
    setHolderNumStatus("正在加载股东户数…");
    return;
  }
  if (st.error) {
    setHolderNumStatus(st.error, { empty: true });
    return;
  }
  const items = st.items || [];
  if (!items.length) {
    setHolderNumStatus("暂无股东户数", { empty: true });
    return;
  }
  const latest = st.latest || items[items.length - 1] || {};
  const bits = [];
  if (latest.time) bits.push(latest.time);
  if (latest.holder_num_fmt || latest.holder_num != null) {
    bits.push(`户数 ${latest.holder_num_fmt || fmtVol(latest.holder_num)}`);
  }
  if (latest.change_fmt) bits.push(`变动 ${latest.change_fmt}`);
  if (latest.change_ratio_fmt) bits.push(latest.change_ratio_fmt);
  if (latest.avg_hold_num_fmt) bits.push(`户均 ${latest.avg_hold_num_fmt}`);
  bits.push(`${items.length} 期`);
  setHolderNumStatus(bits.join(" · "));
}

async function loadHolderNum({ refresh = false } = {}) {
  if (!code || holderNumState.loading) return;
  holderNumState.loading = true;
  holderNumState.error = "";
  refreshHolderNumMeta();
  hideHolderNumHoverCard();
  try {
    const qs = new URLSearchParams({ code, limit: "120" });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/holder-num?${qs.toString()}`);
    const data = json.data || {};
    holderNumState.items = Array.isArray(data.items) ? data.items : [];
    holderNumState.latest = data.latest || holderNumState.items[holderNumState.items.length - 1] || null;
    holderNumState.source = data.source || "";
    holderNumState.updatedAt = data.updated_at || "";
    holderNumState.hoverIndex = null;
    refreshHolderNumMeta();
    renderHolderNumChart();
  } catch (err) {
    holderNumState.items = [];
    holderNumState.latest = null;
    holderNumState.error = err.message || String(err);
    refreshHolderNumMeta();
    renderHolderNumChart();
  } finally {
    holderNumState.loading = false;
    if (els.refreshHoldersBtn) {
      els.refreshHoldersBtn.disabled = holdersState.loading || fundHoldersState.loading;
    }
  }
}

function setupHolderNumChart() {
  if (!els.holderNumChart || els.holderNumChart.dataset.bound === "1") return;
  els.holderNumChart.dataset.bound = "1";

  const indexFromEvent = (evt) => {
    const rect = els.holderNumChart.getBoundingClientRect();
    const layout = holderNumLayout(rect.width, rect.height);
    const items = holderNumState.items || [];
    if (!items.length) return null;
    const x = evt.clientX - rect.left;
    const t = (x - layout.padL) / Math.max(1, layout.plotW);
    const idx = Math.round(t * (items.length - 1));
    if (!Number.isFinite(idx)) return null;
    return Math.max(0, Math.min(items.length - 1, idx));
  };

  els.holderNumChart.addEventListener("pointermove", (evt) => {
    const idx = indexFromEvent(evt);
    if (idx == null) return;
    if (holderNumState.hoverIndex === idx) return;
    holderNumState.hoverIndex = idx;
    renderHolderNumChart(idx);
  });
  els.holderNumChart.addEventListener("pointerleave", () => {
    if (holderNumState.hoverIndex == null) return;
    holderNumState.hoverIndex = null;
    renderHolderNumChart(null);
  });

  if (typeof ResizeObserver !== "undefined" && els.holderNumChartWrap) {
    let raf = 0;
    const ro = new ResizeObserver(() => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        raf = 0;
        renderHolderNumChart();
      });
    });
    ro.observe(els.holderNumChartWrap);
  }
}

function lhbTone(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}

function lhbFmtPct(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function lhbFmtYi(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}万`;
  return `${sign}${abs.toFixed(0)}`;
}

function financialsPick(row, ...keys) {
  for (const key of keys) {
    if (!row || !Object.prototype.hasOwnProperty.call(row, key)) continue;
    const value = row[key];
    if (value != null && value !== "" && value !== "-" && value !== "--") return value;
  }
  return null;
}

function financialsDate(row) {
  return String(row?.REPORT_DATE || row?.REPORTDATE || "").slice(0, 10);
}

function financialsIsAnnual(row) {
  const day = financialsDate(row);
  return day.length >= 7 && day.slice(5, 7) === "12";
}

function financialsPeriodLabel(row) {
  const day = financialsDate(row);
  if (day.length < 7) {
    const name = String(row?.PERIOD_LABEL || row?.REPORT_DATE_NAME || "").trim();
    return name || day || "—";
  }
  const year = day.slice(0, 4);
  const month = day.slice(5, 7);
  if (financialsState.cadence === "annual") return year;
  const mapping = { "03": "一季", "06": "中报", "09": "三季", "12": "年报" };
  return `${year}${mapping[month] || ""}`;
}

const FINANCIALS_SHEETS = {
  income: {
    title: "利润表",
    hint: "精读藏空行，完整显示全部科目。",
    mixKeys: ["OPERATE_INCOME", "TOTAL_OPERATE_INCOME", "TOTALOPERATEREVE", "OPERATE_INCOME_PK"],
    lines: [],
  },
  balance: {
    title: "资产负债表",
    hint: "期末时点数。精读藏空行，完整显示全部科目。同比为去年同期；占比分母为资产总计。",
    mixKeys: ["TOTAL_ASSETS", "TOTAL_ASSETS_PK"],
    lines: [],
  },
  cashflow: {
    title: "现金流量表",
    hint: "直接法三段：经营 / 投资 / 筹资净额 ± 汇率 = 现金净增加。精读藏空行，补充资料默认收起。",
    mixKeys: ["SALES_SERVICES"],
    lines: [],
  },
};

const FINANCIALS_KPIS = [
  {
    label: "营业收入",
    keys: ["OPERATE_INCOME", "TOTAL_OPERATE_INCOME", "TOTALOPERATEREVE", "OPERATE_INCOME_PK"],
    kind: "money",
  },
  {
    label: "归母净利润",
    keys: ["PARENT_NETPROFIT", "PARENTNETPROFIT"],
    kind: "money",
  },
  {
    label: "经营现金流",
    keys: ["NETCASH_OPERATE", "NETCASH_OPERATE_PK"],
    kind: "money",
  },
  {
    label: "ROE",
    keys: ["ROEJQ", "WEIGHTAVG_ROE"],
    kind: "pct",
  },
];

function financialsNormalizeSheet(sheet) {
  const raw = String(sheet || "").trim().toLowerCase();
  if (raw === "income" || raw === "cashflow") return raw;
  return "balance";
}

function financialsSheetHasDensity(sheet) {
  return Boolean(financialsNormalizeSheet(sheet));
}

function financialsNormalizeCadence(value) {
  return value === "annual" ? "annual" : "quarterly";
}

function financialsNormalizeRange(value) {
  return value === "all" ? "all" : "short";
}

function financialsNormalizeRead(value) {
  if (value === "amount" || value === "mix") return value;
  return "yoy";
}

function financialsNormalizeDensity(value) {
  return value === "full" ? "full" : "focus";
}

function financialsNormalizeUnit(value) {
  return value === "wan" ? "wan" : "yi";
}

function financialsUnitLabel(unit = financialsState.unit) {
  return financialsNormalizeUnit(unit) === "wan" ? "万元" : "亿元";
}

function financialsSheetLines(sheet) {
  const key = financialsNormalizeSheet(sheet);
  const fromApi = financialsState.lines?.[key];
  if (Array.isArray(fromApi) && fromApi.length) return fromApi;
  return FINANCIALS_SHEETS[key]?.lines || [];
}

function financialsSheetRows(sheet = financialsState.sheet) {
  const key = financialsNormalizeSheet(sheet);
  if (key === "income") return financialsState.income;
  if (key === "balance") return financialsState.balance;
  if (key === "cashflow") return financialsState.cashflow;
  return financialsState.items;
}

function financialsCadenceItems(rows = financialsSheetRows()) {
  const list = Array.isArray(rows) ? rows : [];
  if (financialsState.cadence === "annual") return list.filter(financialsIsAnnual);
  return list;
}

function financialsVisibleItems(rows = financialsSheetRows()) {
  const list = financialsCadenceItems(rows);
  if (financialsState.range === "all") return list;
  const limit = financialsState.cadence === "annual" ? 5 : 8;
  return list.slice(0, limit);
}

function financialsPeriodIndex(rows) {
  const map = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const day = financialsDate(row);
    if (day.length >= 7) map.set(day.slice(0, 7), row);
  }
  return map;
}

function financialsPriorRow(row, index) {
  const day = financialsDate(row);
  if (day.length < 7) return null;
  const year = Number(day.slice(0, 4));
  if (!Number.isFinite(year)) return null;
  return index.get(`${year - 1}-${day.slice(5, 7)}`) || null;
}

function financialsIsAppendixGroup(label) {
  return /补充资料|不能重分类|能重分类/.test(String(label || ""));
}

function financialsIsSkipGroup(line) {
  return financialsIsGroupRow(line) && /审计意见/.test(String(line.label || ""));
}

function financialsIsCaptionGroup(line) {
  if (!financialsIsGroupRow(line)) return false;
  if (line.caption) return true;
  return /按经营持续性|按所有权归属/.test(String(line.label || ""));
}

function financialsIndentDepth(line) {
  const raw = line?.indent;
  if (raw === true) return 1;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function financialsLineNoise(line) {
  return /平衡项目|其他项目/.test(String(line?.label || ""));
}

function financialsEnsureCollapsed(sheet) {
  const key = financialsNormalizeSheet(sheet);
  if (!financialsState.collapsed[key]) {
    const pack = {};
    for (const line of financialsSheetLines(key)) {
      if (line.group && financialsIsAppendixGroup(line.label)) pack[line.label] = true;
    }
    financialsState.collapsed[key] = pack;
  }
  return financialsState.collapsed[key];
}

function financialsNum(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function financialsFmtMoney(n, unit = financialsState.unit) {
  if (n == null || !Number.isFinite(n)) return "—";
  const x = n / (financialsNormalizeUnit(unit) === "wan" ? 1e4 : 1e8);
  const sign = x < 0 ? "-" : "";
  const abs = Math.abs(x);
  return `${sign}${abs >= 100 ? abs.toFixed(1) : abs.toFixed(2)}`;
}

function financialsFmtLevel(n, kind = "money", unit = financialsState.unit) {
  if (n == null || !Number.isFinite(n)) return "—";
  if (kind === "pct" || kind === "ratio") return `${n.toFixed(2)}%`;
  if (kind === "x") {
    const x = n > 50 ? n / 100 : n;
    return `${x.toFixed(2)}x`;
  }
  if (kind === "eps") return n.toFixed(3);
  return financialsFmtMoney(n, unit);
}

function financialsYoyPack(curr, prev, kind = "money") {
  if (curr == null || prev == null || !Number.isFinite(curr) || !Number.isFinite(prev)) return null;
  if (kind === "pct" || kind === "ratio" || kind === "x") {
    const delta = curr - prev;
    if (!Number.isFinite(delta)) return null;
    const suffix = kind === "x" ? "x" : "";
    return { text: `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${suffix}`, tone: lhbTone(delta) };
  }
  if (prev === 0) return null;
  const yoy = ((curr - prev) / Math.abs(prev)) * 100;
  return { text: `${yoy > 0 ? "+" : ""}${yoy.toFixed(1)}%`, tone: lhbTone(yoy) };
}

function syncFinancialsToolbar() {
  const st = financialsState;
  st.sheet = financialsNormalizeSheet(st.sheet);
  st.cadence = financialsNormalizeCadence(st.cadence);
  st.range = financialsNormalizeRange(st.range);
  st.read = financialsNormalizeRead(st.read);
  st.unit = financialsNormalizeUnit(st.unit);
  st.density = financialsNormalizeDensity(st.density);
  if (els.financialsSheetSeg) {
    els.financialsSheetSeg.querySelectorAll("[data-sheet]").forEach((btn) => {
      const active = btn.getAttribute("data-sheet") === st.sheet;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  if (els.financialsFilterSeg) {
    els.financialsFilterSeg.querySelectorAll("[data-cadence]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-cadence") === st.cadence);
    });
  }
  if (els.financialsRangeSeg) {
    els.financialsRangeSeg.querySelectorAll("[data-range]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-range") === st.range);
    });
  }
  if (els.financialsRangeShortBtn) {
    els.financialsRangeShortBtn.textContent = st.cadence === "annual" ? "近5年" : "近8期";
  }
  if (els.financialsReadSeg) {
    els.financialsReadSeg.querySelectorAll("[data-read]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-read") === st.read);
    });
  }
  if (els.financialsUnitSeg) {
    els.financialsUnitSeg.querySelectorAll("[data-unit]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-unit") === st.unit);
    });
  }
  if (els.financialsDensitySeg) {
    els.financialsDensitySeg.hidden = !financialsSheetHasDensity(st.sheet);
    els.financialsDensitySeg.querySelectorAll("[data-density]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-density") === st.density);
    });
  }
}

function financialsEmptyRow(colspan, text) {
  return `<tr class="is-empty"><td colspan="${colspan}">${escapeHtml(text)}</td></tr>`;
}

function paintFinancialsKpis(rows) {
  if (!els.financialsKpis) return;
  const latest = rows[0];
  if (!latest) {
    els.financialsKpis.hidden = true;
    els.financialsKpis.innerHTML = "";
    return;
  }
  const day = financialsDate(latest);
  const merged = (Array.isArray(financialsState.items) ? financialsState.items : []).find(
    (row) => financialsDate(row) === day,
  ) || latest;
  const index = financialsPeriodIndex(financialsState.items.length ? financialsState.items : rows);
  const prior = financialsPriorRow(merged, index);
  const unit = financialsState.unit;
  els.financialsKpis.hidden = false;
  els.financialsKpis.innerHTML = FINANCIALS_KPIS.map((kpi) => {
    const curr = financialsNum(financialsPick(merged, ...(kpi.keys || [])));
    const prev = prior ? financialsNum(financialsPick(prior, ...(kpi.keys || []))) : null;
    const yoy = financialsYoyPack(curr, prev, kpi.kind);
    const value = kpi.kind === "money" && curr != null
      ? `${financialsFmtMoney(curr, unit)} ${unit === "wan" ? "万" : "亿"}`
      : financialsFmtLevel(curr, kpi.kind, unit);
    const chg = yoy
      ? `<span class="financials-kpi-chg" data-tone="${yoy.tone}">${escapeHtml(yoy.text)}</span>`
      : `<span class="financials-kpi-chg">—</span>`;
    return `<div class="financials-kpi">
      <div class="financials-kpi-label">${escapeHtml(kpi.label)}</div>
      <div class="financials-kpi-row">
        <span class="financials-kpi-value">${escapeHtml(value)}</span>
        ${chg}
      </div>
    </div>`;
  }).join("");
}

function financialsLineEmpty(line, periods) {
  const keys = line?.keys || [];
  if (!keys.length) return false;
  return periods.every((period) => {
    const value = financialsPick(period.row, ...keys);
    if (value == null) return true;
    return Boolean(line.sparse) && financialsNum(value) === 0;
  });
}

function financialsIsGroupRow(line) {
  return Boolean(line?.group) && !(line.keys || []).length;
}

function financialsLineCore(label) {
  return String(label || "")
    .replace(/^[一二三四五六七八]、\s*/, "")
    .replace(/^其中[:：]\s*/, "")
    .replace(/^[加减][:：]\s*/, "");
}

function financialsTotalKind(line) {
  if (!line || line.group) return "";
  if (line.role === "result") return "grand";
  if (line.role === "lead" || line.role === "stage") return "sub";
  const label = String(line.label || "");
  const core = financialsLineCore(label);
  if (/总计$|负债合计$|股东权益合计$|所有者权益合计$/.test(label)) return "grand";
  if (/现金及现金等价物净增加额$|期末现金及现金等价物余额$/.test(label)) return "grand";
  if (/^(营业利润|利润总额|净利润|综合收益总额)$/.test(core)) return "grand";
  if (!line.strong || financialsIndentDepth(line)) return "";
  if (/合计$|小计$|现金流量净额$/.test(label)) return "sub";
  if (line.strong) return "sub";
  return "";
}

function financialsLineRedundant(line, lines, periods) {
  const label = String(line?.label || "");
  if (line?.combined) {
    const splits = /应付/.test(label) ? ["应付票据", "应付账款"] : ["应收票据", "应收账款"];
    const splitLines = (lines || []).filter((item) => splits.includes(item.label));
    if (!splitLines.length) return false;
    return periods.some((period) =>
      splitLines.some((item) => financialsNum(financialsPick(period.row, ...(item.keys || []))) != null),
    );
  }
  if (label !== "营业收入" && label !== "其中：营业收入") return false;
  const parent = (lines || []).find((item) => item.label === "营业总收入" || item.label === "一、营业总收入");
  if (!parent) return false;
  return periods.every((period) => {
    const curr = financialsNum(financialsPick(period.row, ...(line.keys || [])));
    const base = financialsNum(financialsPick(period.row, ...(parent.keys || [])));
    return curr == null || base == null || curr === base;
  });
}

function financialsVisibleLines(lines, periods, collapsed, { keepEmpty = false } = {}) {
  const list = Array.isArray(lines) ? lines : [];
  const out = [];
  let hiding = false;
  let hideDepth = 0;
  for (let i = 0; i < list.length; i += 1) {
    const line = list[i];
    const depth = financialsIndentDepth(line);
    const isGroup = financialsIsGroupRow(line);
    if (hiding && !(isGroup && depth <= hideDepth)) continue;
    hiding = false;
    if (isGroup) {
      if (financialsIsSkipGroup(line) || financialsLineNoise(line)) continue;
      const section = Boolean(line.section);
      let hasChild = false;
      for (let j = i + 1; j < list.length; j += 1) {
        const next = list[j];
        const nextDepth = financialsIndentDepth(next);
        if (financialsIsGroupRow(next) && nextDepth <= depth) break;
        if (!section && !nextDepth && !financialsIsGroupRow(next)) break;
        if (financialsIsSkipGroup(next) || financialsIsCaptionGroup(next) || financialsIsGroupRow(next)) continue;
        if (financialsLineNoise(next) || (!keepEmpty && financialsLineRedundant(next, list, periods))) continue;
        if (keepEmpty || !financialsLineEmpty(next, periods)) {
          hasChild = true;
          break;
        }
      }
      if (!hasChild) continue;
      out.push(line);
      if (collapsed?.[line.label]) {
        hiding = true;
        hideDepth = depth;
      }
      continue;
    }
    if (financialsLineNoise(line)) continue;
    if (!keepEmpty && financialsLineRedundant(line, list, periods)) continue;
    if (line.role === "stage") {
      let hasChild = false;
      for (let j = i + 1; j < list.length; j += 1) {
        const next = list[j];
        if (!financialsIndentDepth(next)) break;
        if (financialsLineNoise(next)) continue;
        if (!keepEmpty && financialsLineEmpty(next, periods)) continue;
        hasChild = true;
        break;
      }
      if (keepEmpty || hasChild) {
        out.push(line);
      }
      continue;
    }
    if (keepEmpty || !financialsLineEmpty(line, periods)) out.push(line);
  }
  return out;
}

function financialsAmtCell({ value, kind, yoy, mix, latest, read }) {
  const latestClass = latest ? " financials-latest" : "";
  const n = financialsNum(value);
  if (n == null) {
    return `<td class="num${latestClass}">—</td>`;
  }
  const main = financialsFmtLevel(n, kind, financialsState.unit);
  const neg = kind !== "pct" && kind !== "ratio" && kind !== "x" && n < 0 ? " is-neg" : "";
  let sub = "";
  if (read === "yoy") {
    sub = `<span class="financials-amt-sub"${yoy ? ` data-tone="${yoy.tone}"` : ""}">${yoy ? escapeHtml(yoy.text) : ""}</span>`;
  } else if (read === "mix" && kind === "money") {
    sub = `<span class="financials-amt-sub">${mix == null ? "" : escapeHtml(`${mix.toFixed(1)}%`)}</span>`;
  }
  return `<td class="num financials-amt${latestClass}${neg}">
    <span class="financials-amt-wrap">${sub}<span class="financials-amt-main">${escapeHtml(main)}</span></span>
  </td>`;
}

function paintFinancialsStatement(sheet, rows) {
  const spec = FINANCIALS_SHEETS[sheet] || FINANCIALS_SHEETS.income;
  const periods = rows.map((row) => ({
    label: financialsPeriodLabel(row),
    day: financialsDate(row) || "—",
    row,
  }));
  const collapsed = financialsEnsureCollapsed(sheet);
  const keepEmpty = financialsSheetHasDensity(sheet) && financialsState.density === "full";
  const lines = financialsVisibleLines(financialsSheetLines(sheet), periods, collapsed, {
    keepEmpty,
  });
  const index = financialsPeriodIndex(financialsCadenceItems(financialsSheetRows(sheet)));
  const read = financialsState.read;
  const mixKeys = spec.mixKeys || [];
  if (els.financialsHead) {
    els.financialsHead.innerHTML = `<tr>
      <th scope="col">科目</th>
      ${periods
        .map(
          (period, col) => `<th scope="col" class="num${col === 0 ? " financials-latest" : ""}" title="${escapeHtml(period.day)}">${escapeHtml(period.label)}</th>`,
        )
        .join("")}
    </tr>`;
  }
  els.financialsBodyRows.innerHTML = lines
    .map((line) => {
      const isGroup = financialsIsGroupRow(line);
      if (isGroup) {
        if (financialsIsCaptionGroup(line)) {
          const depth = financialsIndentDepth(line);
          const capClass = ["financials-line-caption"];
          if (depth >= 1) capClass.push("financials-line-indent");
          if (depth >= 2) capClass.push("is-note");
          return `<tr class="financials-caption-row">
            <td colspan="${periods.length + 1}" class="${capClass.join(" ")}">${escapeHtml(line.label)}</td>
          </tr>`;
        }
        const closed = Boolean(collapsed[line.label]);
        return `<tr class="financials-group-row" data-group="${escapeHtml(line.label)}" aria-expanded="${closed ? "false" : "true"}">
          <td colspan="${periods.length + 1}" class="financials-line-group"><span class="financials-group-toggle" aria-hidden="true">${closed ? "▸" : "▾"}</span>${escapeHtml(line.label)}</td>
        </tr>`;
      }
      const totalKind = financialsTotalKind(line);
      const depth = financialsIndentDepth(line);
      const classes = ["financials-line"];
      if (depth >= 1 && !totalKind) classes.push("financials-line-indent");
      if (depth >= 2 && !totalKind) classes.push("is-note");
      if (totalKind) classes.push("financials-line-strong");
      const kind = line.kind || "money";
      const keys = line.keys || [];
      const cells = periods
        .map((period, col) => {
          if (!keys.length) {
            return `<td class="num${col === 0 ? " financials-latest" : ""}"></td>`;
          }
          const curr = financialsPick(period.row, ...keys);
          const priorRow = financialsPriorRow(period.row, index);
          const prev = priorRow ? financialsNum(financialsPick(priorRow, ...keys)) : null;
          const yoy = financialsYoyPack(financialsNum(curr), prev, kind);
          const base = financialsNum(financialsPick(period.row, ...mixKeys));
          const n = financialsNum(curr);
          const mix = n == null || base == null || base === 0 ? null : (n / Math.abs(base)) * 100;
          return financialsAmtCell({
            value: curr,
            kind,
            yoy,
            mix,
            latest: col === 0,
            read,
          });
        })
        .join("");
      const rowKind = totalKind === "grand" ? " financials-grand-row" : totalKind === "sub" ? " financials-subtotal-row" : "";
      return `<tr class="is-row${rowKind}">
        <td class="${classes.join(" ")}" title="${escapeHtml(line.label)}">${escapeHtml(line.label)}</td>
        ${cells}
      </tr>`;
    })
    .join("");
}

function paintFinancials() {
  const st = financialsState;
  const sheet = financialsNormalizeSheet(st.sheet);
  st.sheet = sheet;
  const spec = FINANCIALS_SHEETS[sheet] || FINANCIALS_SHEETS.income;
  const rows = financialsVisibleItems();
  const colspan = Math.max(1, rows.length + 1);
  const cadenceLabel = st.cadence === "annual" ? "年报" : "季报";
  const readLabel = st.read === "mix" ? "占比" : st.read === "yoy" ? "同比" : "金额";
  if (els.financialsMeta) {
    const bits = [];
    if (rows.length) bits.push(`${rows.length}期`);
    bits.push(cadenceLabel);
    bits.push(financialsUnitLabel());
    bits.push(readLabel);
    if (financialsSheetHasDensity(sheet)) bits.push(st.density === "full" ? "完整" : "精读");
    els.financialsMeta.textContent = st.loading
      ? "加载中…"
      : st.error
        ? st.error
        : bits.join(" · ");
  }
  if (!els.financialsBodyRows) return;
  if (st.loading || st.error || !rows.length) {
    if (els.financialsKpis) {
      els.financialsKpis.hidden = true;
      els.financialsKpis.innerHTML = "";
    }
    if (els.financialsHead) els.financialsHead.innerHTML = "";
    const text = st.loading ? "正在加载…" : st.error || `暂无${spec.title}数据`;
    els.financialsBodyRows.innerHTML = financialsEmptyRow(colspan, text);
    return;
  }
  paintFinancialsKpis(rows);
  paintFinancialsStatement(sheet, rows);
}

async function loadFinancials({ refresh = false } = {}) {
  if (!code || financialsState.loading) return;
  financialsState.loading = true;
  financialsState.error = "";
  paintFinancials();
  if (els.refreshFinancialsBtn) els.refreshFinancialsBtn.disabled = true;
  try {
    const qs = new URLSearchParams({ code, scope: "all", limit: "24" });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/stocks/financial-report?${qs.toString()}`);
    const data = json.data || {};
    const statements = data.statements || {};
    financialsState.items = Array.isArray(data.merged)
      ? data.merged
      : Array.isArray(data.items)
        ? data.items
        : [];
    financialsState.income = Array.isArray(statements.income) ? statements.income : [];
    financialsState.balance = Array.isArray(statements.balance) ? statements.balance : [];
    financialsState.cashflow = Array.isArray(statements.cashflow) ? statements.cashflow : [];
    const sheets = data.sheets || {};
    financialsState.lines = {
      income: Array.isArray(sheets.income?.lines) ? sheets.income.lines : [],
      balance: Array.isArray(sheets.balance?.lines) ? sheets.balance.lines : [],
      cashflow: Array.isArray(sheets.cashflow?.lines) ? sheets.cashflow.lines : [],
    };
    financialsState.collapsed = {};
    financialsState.count = Number(data.count) || financialsState.items.length;
    financialsState.updatedAt = data.updated_at || new Date().toLocaleString("zh-CN", { hour12: false });
    if (els.financialsBody) els.financialsBody.scrollTop = 0;
  } catch (err) {
    financialsState.items = [];
    financialsState.income = [];
    financialsState.balance = [];
    financialsState.cashflow = [];
    financialsState.lines = { income: [], balance: [], cashflow: [] };
    financialsState.collapsed = {};
    financialsState.count = 0;
    financialsState.error = err.message || String(err);
  } finally {
    financialsState.loading = false;
    if (els.refreshFinancialsBtn) els.refreshFinancialsBtn.disabled = false;
    paintFinancials();
  }
}

function financialsBindSeg(el, attr, apply) {
  if (!el || el.dataset.bound === "1") return;
  el.dataset.bound = "1";
  el.addEventListener("click", (event) => {
    const btn = event.target.closest(`[${attr}]`);
    if (!btn || !el.contains(btn)) return;
    if (!apply(btn.getAttribute(attr))) return;
    syncFinancialsToolbar();
    paintFinancials();
    if (els.financialsBody) els.financialsBody.scrollTop = 0;
  });
}

function setupFinancialsBox() {
  syncFinancialsToolbar();
  financialsBindSeg(els.financialsSheetSeg, "data-sheet", (value) => {
    const next = financialsNormalizeSheet(value);
    if (next === financialsState.sheet) return false;
    financialsState.sheet = next;
    return true;
  });
  financialsBindSeg(els.financialsFilterSeg, "data-cadence", (value) => {
    const next = financialsNormalizeCadence(value);
    if (next === financialsState.cadence) return false;
    financialsState.cadence = next;
    return true;
  });
  financialsBindSeg(els.financialsRangeSeg, "data-range", (value) => {
    const next = financialsNormalizeRange(value);
    if (next === financialsState.range) return false;
    financialsState.range = next;
    return true;
  });
  financialsBindSeg(els.financialsReadSeg, "data-read", (value) => {
    const next = financialsNormalizeRead(value);
    if (next === financialsState.read) return false;
    financialsState.read = next;
    return true;
  });
  financialsBindSeg(els.financialsUnitSeg, "data-unit", (value) => {
    const next = financialsNormalizeUnit(value);
    if (next === financialsState.unit) return false;
    financialsState.unit = next;
    return true;
  });
  financialsBindSeg(els.financialsDensitySeg, "data-density", (value) => {
    const next = financialsNormalizeDensity(value);
    if (next === financialsState.density) return false;
    financialsState.density = next;
    return true;
  });
  if (els.financialsBodyRows && els.financialsBodyRows.dataset.groupBound !== "1") {
    els.financialsBodyRows.dataset.groupBound = "1";
    els.financialsBodyRows.addEventListener("click", (event) => {
      const row = event.target.closest("[data-group]");
      if (!row || !els.financialsBodyRows.contains(row)) return;
      const label = row.getAttribute("data-group");
      if (!label) return;
      const pack = financialsEnsureCollapsed(financialsState.sheet);
      pack[label] = !pack[label];
      paintFinancials();
    });
  }
}

function lhbRowKey(row) {
  return `${row.code || code}:${row.date || ""}`;
}

function companyListSortedItems() {
  const rows = companyListState.items.slice();
  const sort = companyListState.sort;
  if (sort === "date") {
    rows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
    return rows;
  }
  const field = sort === "change" ? "change_pct" : sort === "turnover" ? "turnover" : "net_amt";
  rows.sort((a, b) => {
    const va = Number(a[field]);
    const vb = Number(b[field]);
    const aOk = Number.isFinite(va);
    const bOk = Number.isFinite(vb);
    if (!aOk && !bOk) return 0;
    if (!aOk) return 1;
    if (!bOk) return -1;
    return vb - va;
  });
  return rows;
}

function companyListSelectedRow(rows = companyListSortedItems()) {
  return rows.find((row) => lhbRowKey(row) === companyListState.selected) || null;
}

function paintCompanyListSeats(title, seats) {
  const rows = Array.isArray(seats) ? seats : [];
  if (!rows.length) {
    return `<div class="lhb-seats"><h4>${escapeHtml(title)}</h4><p class="muted">无席位数据</p></div>`;
  }
  const body = rows
    .map((seat) => {
      return `<tr>
        <td class="num">${seat.rank ?? ""}</td>
        <td><span class="lhb-dept-type" data-type="${escapeHtml(seat.dept_type)}">${escapeHtml(seat.dept_type)}</span>${escapeHtml(seat.dept)}</td>
        <td class="num" data-tone="${lhbTone(seat.buy)}">${lhbFmtYi(seat.buy)}</td>
        <td class="num" data-tone="${lhbTone(seat.sell)}">${lhbFmtYi(seat.sell)}</td>
        <td class="num" data-tone="${lhbTone(seat.net)}">${lhbFmtYi(seat.net)}</td>
        <td class="num">${seat.buy_ratio == null ? "—" : `${Number(seat.buy_ratio).toFixed(2)}%`}</td>
      </tr>`;
    })
    .join("");
  return `
    <div class="lhb-seats">
      <h4>${escapeHtml(title)}</h4>
      <table class="market-table lhb-seat-table">
        <thead>
          <tr>
            <th class="num">#</th>
            <th>席位</th>
            <th class="num">买入</th>
            <th class="num">卖出</th>
            <th class="num">净额</th>
            <th class="num">买入占比</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function paintCompanyListDetail(row) {
  const head = els.companyListDetailHead;
  const body = els.companyListDetailBody;
  if (!head || !body) return;
  if (!row) {
    head.innerHTML = `<h2>买卖席位</h2><p class="muted">点左侧一行查看买入 / 卖出营业部</p>`;
    body.innerHTML = `<div class="lhb-detail-empty muted">${
      companyListState.loading
        ? "正在加载…"
        : companyListState.error
          ? escapeHtml(companyListState.error)
          : "暂无选中记录"
    }</div>`;
    return;
  }
  const sw = [row.l1_name, row.l2_name, row.l3_name].filter(Boolean).join(" / ");
  head.innerHTML = `
    <div class="lhb-detail-identity">
      <h2>${escapeHtml(row.date || "买卖席位")}</h2>
      <p class="muted">${escapeHtml(row.name || companyListState.name || code)}${
        sw ? ` · ${escapeHtml(sw)}` : ""
      }</p>
    </div>`;
  const metrics = `
    <div class="lhb-metrics">
      <span>收盘 <b>${row.close == null ? "—" : Number(row.close).toFixed(2)}</b></span>
      <span data-tone="${lhbTone(row.change_pct)}">涨跌 <b>${lhbFmtPct(row.change_pct)}</b></span>
      <span>换手 <b>${row.turnover == null ? "—" : `${Number(row.turnover).toFixed(2)}%`}</b></span>
      <span data-tone="${lhbTone(row.net_amt)}">净买 <b>${lhbFmtYi(row.net_amt)}</b></span>
      <span>买入 <b>${lhbFmtYi(row.buy_amt)}</b></span>
      <span>卖出 <b>${lhbFmtYi(row.sell_amt)}</b></span>
    </div>`;
  const listings = (row.listings || [])
    .map((listing) => {
      return `
        <article class="lhb-listing">
          <div class="lhb-reason-head">
            <strong>${escapeHtml(listing.reason || "上榜")}</strong>
            <span class="muted">${escapeHtml(listing.explain || "")}</span>
            <span class="muted">成交占比 ${
              listing.deal_ratio == null ? "—" : `${Number(listing.deal_ratio).toFixed(2)}%`
            }</span>
          </div>
          <div class="lhb-seat-grid">
            ${paintCompanyListSeats("买入前五", listing.buyers || [])}
            ${paintCompanyListSeats("卖出前五", listing.sellers || [])}
          </div>
        </article>`;
    })
    .join("");
  body.innerHTML = `${metrics}${listings || '<p class="muted">暂无席位</p>'}`;
}

function paintCompanyList() {
  const st = companyListState;
  const rows = companyListSortedItems();
  if (els.companyListTitle) {
    els.companyListTitle.textContent = "历史上榜";
  }
  if (els.companyListMeta) {
    els.companyListMeta.textContent = st.loading
      ? "正在加载历史上榜…"
      : st.error
        ? st.error
        : st.count
          ? `${st.name || code} · ${st.count} 次`
          : "暂无上榜记录";
  }
  if (els.companyListSortSeg) {
    els.companyListSortSeg.querySelectorAll("button[data-sort]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.sort === st.sort);
    });
  }
  if (!els.companyListBody) return;
  if (st.loading) {
    els.companyListBody.innerHTML = `<tr class="is-empty"><td colspan="3">正在加载…</td></tr>`;
    paintCompanyListDetail(null);
    return;
  }
  if (st.error) {
    els.companyListBody.innerHTML = `<tr class="is-empty"><td colspan="3">${escapeHtml(st.error)}</td></tr>`;
    paintCompanyListDetail(null);
    return;
  }
  if (!rows.length) {
    els.companyListBody.innerHTML = `<tr class="is-empty"><td colspan="3">该公司暂无龙虎榜记录</td></tr>`;
    paintCompanyListDetail(null);
    return;
  }
  if (!rows.some((row) => lhbRowKey(row) === st.selected)) {
    st.selected = lhbRowKey(rows[0]);
  }
  els.companyListBody.innerHTML = rows
    .map((row) => {
      const key = lhbRowKey(row);
      const reasons = (row.reasons || []).filter(Boolean).join(" / ");
      return `<tr class="is-row${st.selected === key ? " is-active" : ""}" data-key="${escapeHtml(key)}">
        <td>
          <span class="lhb-date">${escapeHtml(row.date || "")}</span>
          ${reasons ? `<span class="lhb-reason-line" title="${escapeHtml(reasons)}">${escapeHtml(reasons)}</span>` : ""}
        </td>
        <td class="num" data-tone="${lhbTone(row.change_pct)}">${lhbFmtPct(row.change_pct)}</td>
        <td class="num" data-tone="${lhbTone(row.net_amt)}">${lhbFmtYi(row.net_amt)}</td>
      </tr>`;
    })
    .join("");
  paintCompanyListDetail(companyListSelectedRow(rows));
}

async function loadCompanyList({ refresh = false } = {}) {
  if (!code || companyListState.loading) return;
  companyListState.loading = true;
  companyListState.error = "";
  paintCompanyList();
  if (els.refreshListBtn) els.refreshListBtn.disabled = true;
  try {
    const qs = new URLSearchParams({ code });
    if (refresh) qs.set("refresh", "1");
    const json = await api(`/api/list/stock?${qs.toString()}`);
    const data = json.data || {};
    companyListState.items = Array.isArray(data.items) ? data.items : [];
    companyListState.count = Number(data.count) || companyListState.items.length;
    companyListState.name = data.name || nameHint || "";
    companyListState.updatedAt = data.updated_at || "";
    companyListState.selected = "";
  } catch (err) {
    companyListState.items = [];
    companyListState.count = 0;
    companyListState.error = err.message || String(err);
  } finally {
    companyListState.loading = false;
    if (els.refreshListBtn) els.refreshListBtn.disabled = false;
    paintCompanyList();
  }
}

function setupCompanyListBox() {
  if (els.companyListSortSeg && els.companyListSortSeg.dataset.bound !== "1") {
    els.companyListSortSeg.dataset.bound = "1";
    els.companyListSortSeg.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-sort]");
      if (!btn || !els.companyListSortSeg.contains(btn)) return;
      companyListState.sort = btn.dataset.sort || "date";
      paintCompanyList();
    });
  }
  if (els.companyListBody && els.companyListBody.dataset.bound !== "1") {
    els.companyListBody.dataset.bound = "1";
    els.companyListBody.addEventListener("click", (event) => {
      const tr = event.target.closest("tr.is-row");
      if (!tr || !els.companyListBody.contains(tr)) return;
      companyListState.selected = tr.dataset.key || "";
      paintCompanyList();
    });
  }
}

function syncEmPostSelection() {
  const pid = String(emotionState.detail.postId || "").trim();
  els.emotionPostsList?.querySelectorAll(".emotion-post-item[data-post-id]").forEach((el) => {
    el.classList.toggle("is-active", Boolean(pid) && el.getAttribute("data-post-id") === pid);
  });
}

function paintEmotionDetail() {
  if (isXqEmotion()) return paintXqEmotionDetail();
  if (isThsEmotion()) return paintThsEmotionDetail();
  const st = emotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  const empty = !st.postId && !st.loading;
  els.emotionDetail.classList.toggle("is-empty", empty);
  if (empty) {
    if (els.emotionDetailTitle) els.emotionDetailTitle.textContent = "帖子详情";
    if (els.emotionDetailMeta) els.emotionDetailMeta.textContent = "点击股吧帖子查看正文和评论";
    if (els.emotionDetailLink) els.emotionDetailLink.hidden = true;
    if (els.emotionDetailContent) {
      els.emotionDetailContent.innerHTML = `<p class="muted">从中间点开一条帖子，这里会显示全文和评论。</p>`;
    }
    if (els.emotionDetailReplies) els.emotionDetailReplies.hidden = true;
    if (els.emotionDetailRepliesList) els.emotionDetailRepliesList.innerHTML = "";
    syncEmPostSelection();
    return;
  }
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
  syncEmPostSelection();
}

function setEmotionDetailOpen(open) {
  if (!els.emotionDetail) return;
  if (isThsEmotion() || isEmEmotion() || isXqEmotion()) {
    els.emotionDetail.classList.remove("hidden");
    els.emotionDetail.classList.toggle("is-empty", !open);
    els.emotionDetail.setAttribute("aria-hidden", "false");
    document.body.classList.remove("emotion-detail-open");
    if (isThsEmotion()) syncThsPostSelection();
    else if (isEmEmotion()) syncEmPostSelection();
    else syncXqPostSelection();
    return;
  }
  els.emotionDetail.classList.remove("is-empty");
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
  paintEmotionDetail();
}

function emotionOpenEls() {
  return document.querySelector('.company-panel[data-panel="emotion"] .emotion-open');
}

function syncEmotionHubLayout() {
  const open = emotionOpenEls();
  if (!open) return;
  const allHubs = [...open.querySelectorAll(":scope > .cninfo-hub")];
  allHubs.forEach((hub) => {
    hub.style.gridColumn = "";
    hub.style.gridRow = "";
  });
  if (els.emotionDetail) {
    els.emotionDetail.style.gridColumn = "";
    els.emotionDetail.style.gridRow = "";
  }
  const hubs = allHubs.filter((hub) => window.getComputedStyle(hub).display !== "none");
  const n = hubs.length;
  if (!n) {
    open.style.gridTemplateRows = "";
    open.style.gridTemplateColumns = "";
    return;
  }
  if (isEmEmotion() && n === 2) {
    const stacked = window.matchMedia("(max-width: 1100px)").matches;
    const rank = hubs.find((hub) => hub.getAttribute("data-emotion") === "rank") || hubs[0];
    const posts = hubs.find((hub) => hub.getAttribute("data-emotion") === "posts") || hubs[1];
    if (stacked) {
      open.style.gridTemplateColumns = "minmax(0, 1fr)";
      open.style.gridTemplateRows = "minmax(220px, 0.42fr) minmax(280px, 1fr) minmax(280px, 1fr)";
      if (rank) {
        rank.style.gridColumn = "1";
        rank.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "1";
        posts.style.gridRow = "2";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "1";
        els.emotionDetail.style.gridRow = "3";
      }
    } else {
      open.style.gridTemplateColumns = "minmax(220px, 280px) minmax(0, 1.2fr) minmax(320px, 1fr)";
      open.style.gridTemplateRows = "minmax(0, 1fr)";
      if (rank) {
        rank.style.gridColumn = "1";
        rank.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "2";
        posts.style.gridRow = "1";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "3";
        els.emotionDetail.style.gridRow = "1";
      }
    }
    return;
  }
  if (isThsEmotion() && n === 2) {
    const stacked = window.matchMedia("(max-width: 1100px)").matches;
    const scores = hubs[0];
    const posts = hubs[1];
    if (stacked) {
      open.style.gridTemplateColumns = "minmax(0, 1fr)";
      open.style.gridTemplateRows = "auto minmax(240px, 1fr) minmax(280px, 1fr)";
      if (scores) {
        scores.style.gridColumn = "1";
        scores.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "1";
        posts.style.gridRow = "2";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "1";
        els.emotionDetail.style.gridRow = "3";
      }
    } else {
      open.style.gridTemplateColumns = "minmax(0, 1.05fr) minmax(360px, 1fr)";
      open.style.gridTemplateRows = "auto minmax(0, 1fr)";
      if (scores) {
        scores.style.gridColumn = "1 / -1";
        scores.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "1";
        posts.style.gridRow = "2";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "2";
        els.emotionDetail.style.gridRow = "2";
      }
    }
    return;
  }
  if (isXqEmotion() && n === 2) {
    const stacked = window.matchMedia("(max-width: 1100px)").matches;
    const scores = hubs.find((hub) => hub.getAttribute("data-emotion") === "scores") || hubs[0];
    const posts = hubs.find((hub) => hub.getAttribute("data-emotion") === "posts") || hubs[1];
    if (stacked) {
      open.style.gridTemplateColumns = "minmax(0, 1fr)";
      open.style.gridTemplateRows = "minmax(220px, 0.42fr) minmax(280px, 1fr) minmax(280px, 1fr)";
      if (scores) {
        scores.style.gridColumn = "1";
        scores.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "1";
        posts.style.gridRow = "2";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "1";
        els.emotionDetail.style.gridRow = "3";
      }
    } else {
      open.style.gridTemplateColumns = "minmax(240px, 300px) minmax(0, 1.15fr) minmax(340px, 1fr)";
      open.style.gridTemplateRows = "minmax(0, 1fr)";
      if (scores) {
        scores.style.gridColumn = "1";
        scores.style.gridRow = "1";
      }
      if (posts) {
        posts.style.gridColumn = "2";
        posts.style.gridRow = "1";
      }
      if (els.emotionDetail) {
        els.emotionDetail.style.gridColumn = "3";
        els.emotionDetail.style.gridRow = "1";
      }
    }
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
  els.emotionPostsBody?.addEventListener(
    "scroll",
    () => {
      if (isThsEmotion()) maybeLoadThsEmotionMore();
      if (isXqEmotion()) maybeLoadXqEmotionMore();
    },
    { passive: true }
  );
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
  const map = { hot: "推荐", time: "最新发布", reply: "最新回复" };
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
  const fid = item.fid ?? data.fid;
  const present = (value) => value != null && value !== "" && value !== "-";
  const hasRank = present(rank);
  const hasHeat = present(heat);
  const hasChange = present(change);
  const hasFid = present(fid);
  if (!hasRank && !hasHeat && !hasChange && !hasFid) {
    return `<p class="muted">${escapeHtml(data.title || data.error || "暂无讨论热度数据")}</p>`;
  }
  const rankNum = Number(rank);
  const heatNum = Number(heat);
  const barPct =
    Number.isFinite(rankNum) && Number.isFinite(heatNum) && heatNum > 0
      ? Math.max(2, Math.min(100, Math.round((1 - (Math.max(1, rankNum) - 1) / heatNum) * 100)))
      : 0;
  const changeText = hasChange ? (Number(change) > 0 ? `+${change}` : String(change)) : "";
  const sideMetrics = [
    hasHeat ? ["参与股票", `${heat} 只`] : null,
    hasFid ? ["板块 ID", fid] : null,
  ].filter(Boolean);
  return `
    <div class="ths-heat-board">
      ${
        hasRank || hasChange
          ? `<div class="ths-heat-hero">
              <span class="ths-heat-kicker">讨论排名</span>
              <div class="ths-heat-hero-row">
                <strong class="ths-heat-rank">${hasRank ? escapeHtml(`第 ${rank} 名`) : "—"}</strong>
                ${hasChange ? `<span class="ths-heat-change ${changeClass(change)}">${escapeHtml(changeText)}</span>` : ""}
              </div>
              ${barPct ? `<div class="ths-heat-bar" aria-hidden="true"><i style="width:${barPct}%"></i></div>` : ""}
            </div>`
          : ""
      }
      ${
        sideMetrics.length
          ? `<div class="ths-heat-metrics">
              ${sideMetrics
                .map(
                  ([label, value]) => `
                    <div class="emotion-score-metric">
                      <span class="emotion-score-label">${escapeHtml(label)}</span>
                      <strong class="emotion-score-value">${escapeHtml(displayValue(value))}</strong>
                    </div>`
                )
                .join("")}
            </div>`
          : ""
      }
      <p class="muted emotion-score-foot">${escapeHtml(item.title || data.title || "")}</p>
    </div>
  `;
}

function thsIdentityLabel(tag) {
  const key = String(tag || "").trim().toLowerCase();
  if (!key) return "";
  const map = { bluev: "蓝V", yellowv: "黄V", orangev: "橙V" };
  return map[key] || "认证";
}

function thsIdentityClass(tag) {
  const key = String(tag || "").trim().toLowerCase().replace(/[^a-z0-9-]/g, "");
  return key ? `ths-id-tag ths-id-tag--${key}` : "ths-id-tag";
}

function paintThsVoteSlot(html) {
  if (!els.emotionThsVote) return;
  const content = String(html || "").trim();
  els.emotionThsVote.innerHTML = content;
  els.emotionThsVote.hidden = !content;
}

function renderThsVoteCard(vote) {
  if (!vote || !vote.title) return "";
  const total = Number(vote.total) || 0;
  const options = (Array.isArray(vote.options) ? vote.options : []).map((opt) => {
    const count = Number(opt.count) || 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    return `
      <div class="ths-vote-option">
        <span>${escapeHtml(opt.text || "")}</span>
        <b>${count}${total > 0 ? ` · ${pct}%` : ""}</b>
        <i style="width:${pct}%"></i>
      </div>`;
  }).join("");
  return `
    <article class="news-item ths-vote-card">
      <div class="ths-vote-head"><span>投票</span><span>${total} 人参与</span></div>
      <h3>${escapeHtml(vote.title)}</h3>
      ${options}
    </article>`;
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
      const identity = thsIdentityLabel(item.identity_tag);
      const summary = escapeHtml(truncateText(item.summary || item.content || "", 180));
      const external = url
        ? `<a class="emotion-post-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="打开原文">↗</a>`
        : "";
      const metaBits = [
        item.published_at ? `<time>${escapeHtml(item.published_at)}</time>` : "",
        item.author || item.media_name
          ? `<span>${escapeHtml(item.author || item.media_name)}</span>`
          : "",
        identity ? `<span class="${thsIdentityClass(item.identity_tag)}">${escapeHtml(identity)}</span>` : "",
        item.comment_count ? `<span>评 ${escapeHtml(item.comment_count)}</span>` : "",
        item.like_count ? `<span>赞 ${escapeHtml(item.like_count)}</span>` : "",
        item.forward_count ? `<span>转 ${escapeHtml(item.forward_count)}</span>` : "",
        Array.isArray(item.replies) && item.replies.length
          ? `<span>预览 ${escapeHtml(item.replies.length)} 评</span>`
          : "",
      ].filter(Boolean);
      const selected = String(thsEmotionState.detail.postId || "").trim() === postId;
      return `
        <article class="news-item emotion-post-item ths-emotion-post-item${selected ? " is-active" : ""}" data-post-id="${escapeHtml(postId)}" role="button" tabindex="0">
          <div class="ths-post-head">
            <h3><button type="button" class="emotion-post-title" data-post-id="${escapeHtml(postId)}">${title}</button></h3>
            ${external}
          </div>
          ${summary ? `<p class="ths-post-summary">${summary}</p>` : ""}
          <div class="news-item-meta ths-post-meta">
            ${metaBits.join("")}
          </div>
        </article>
      `;
    })
    .join("");
}

function findThsEmotionPost(postId) {
  const pid = String(postId || "").trim();
  if (!pid) return null;
  return thsEmotionState.posts.items.find((row) => String(row.post_id || row.article_id || "").trim() === pid) || null;
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

function paintThsEmotionPosts() {
  const st = thsEmotionState.posts;
  if (els.emotionPostsMeta) {
    const bits = [
      thsEmotionSortLabel(st.sort),
      emotionDaysLabel(st.days),
      `${st.count || st.items.length} 条`,
      st.hasMore ? "滚动加载" : st.items.length ? "已全部加载" : "",
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionPostsMeta.textContent = st.loading && !st.items.length ? "正在查询讨论帖…" : bits.join(" · ");
  }
  if (els.emotionPostsHint) {
    if (st.loading && !st.items.length) {
      els.emotionPostsHint.textContent = "正在从同花顺圈子拉取讨论帖…";
    } else if (st.error && !st.items.length) {
      els.emotionPostsHint.textContent = st.error;
    } else if (!st.items.length) {
      els.emotionPostsHint.textContent = "暂无讨论帖，可换排序后再试";
    } else if (st.loadingMore) {
      els.emotionPostsHint.textContent = "正在加载更多讨论帖…";
    } else if (st.hasMore) {
      els.emotionPostsHint.textContent = "向下滚动自动加载更多；点击左侧查看详情和评论";
    } else {
      els.emotionPostsHint.textContent = `已加载 ${st.count || st.items.length} 条，点击左侧查看详情和评论`;
    }
  }
  if (!els.emotionPostsList) return;
  if (st.loading && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="muted">正在查询讨论帖…</p>`;
    paintThsVoteSlot("");
    return;
  }
  if (st.error && !st.items.length) {
    els.emotionPostsList.innerHTML = `<p class="news-error">${escapeHtml(st.error)}</p>`;
    paintThsVoteSlot("");
    return;
  }
  const vote = st.sort === "hot" ? null : st.vote;
  paintThsVoteSlot(renderThsVoteCard(vote));
  const foot = st.loadingMore
    ? `<p class="muted ths-load-more">正在加载更多…</p>`
    : st.hasMore
      ? `<p class="muted ths-load-more">滚动加载更多</p>`
      : st.items.length
        ? `<p class="muted ths-load-more">已加载全部</p>`
        : "";
  els.emotionPostsList.innerHTML = `${renderThsEmotionPostList(st.items, "暂无匹配的讨论帖")}${foot}`;
  syncThsPostSelection();
}

function thsEmotionPostsQueryParams() {
  return {
    sort: (els.emotionPostsSortThs?.value || "hot").trim(),
    days: emotionDaysParam(els.emotionPostsDaysThs?.value),
    maxPages: thsEmotionState.posts.maxPages || 1,
    withReplies: true,
  };
}

function applyThsEmotionPack(pack = {}) {
  const posts = pack.posts && typeof pack.posts === "object" ? pack.posts : pack;
  const scores = pack.scores && typeof pack.scores === "object" ? pack.scores : {};
  const updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });

  thsEmotionState.scores.data = scores;
  thsEmotionState.scores.error = scores.error || pack.error || "";
  thsEmotionState.scores.updatedAt = updatedAt;

  thsEmotionState.posts.items = Array.isArray(posts.items) ? posts.items : [];
  thsEmotionState.posts.count = Number(posts.count) || thsEmotionState.posts.items.length;
  thsEmotionState.posts.total = Number(posts.total) || thsEmotionState.posts.count;
  thsEmotionState.posts.error = posts.error || "";
  thsEmotionState.posts.vote = posts.vote && typeof posts.vote === "object" ? posts.vote : null;
  thsEmotionState.posts.updatedAt = updatedAt;
  thsEmotionState.posts.hasMore = thsEmotionState.posts.items.length > 0 && thsEmotionState.posts.maxPages < 20;
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

async function loadThsEmotionPosts({ more = false } = {}) {
  if (!code) return;
  const st = thsEmotionState.posts;
  if (more) {
    if (st.loading || st.loadingMore || !st.hasMore) return;
  } else if (st.loading) {
    return;
  }
  if (!more) {
    st.maxPages = 1;
    st.hasMore = true;
  } else {
    st.maxPages = Math.min(20, (Number(st.maxPages) || 1) + 1);
  }
  const query = thsEmotionPostsQueryParams();
  query.maxPages = st.maxPages;
  if (more) st.loadingMore = true;
  else st.loading = true;
  st.error = "";
  st.sort = query.sort;
  st.days = query.days;
  st.withReplies = true;
  if (!more && els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = true;
  paintThsEmotionPosts();
  const prevCount = more ? st.items.length : 0;
  const prevTop = els.emotionPostsBody?.scrollTop || 0;
  const qs = thsEmotionApiQuery({
    channel: "posts",
    sort: query.sort,
    days: String(query.days || 0),
    max_pages: String(query.maxPages),
    replies: "1",
    kind: "user",
  });
  try {
    const json = await api(`/api/stocks/emotion?${qs.toString()}`);
    const data = json.data || {};
    const items = Array.isArray(data.items) ? data.items : [];
    st.items = items;
    st.count = Number(data.count) || items.length;
    st.total = Number(data.total) || st.count;
    st.error = data.error || "";
    st.vote = data.vote && typeof data.vote === "object" ? data.vote : null;
    st.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    st.hasMore = items.length > prevCount && st.maxPages < 20;
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = more ? prevTop : 0;
  } catch (err) {
    if (!more) {
      st.items = [];
      st.count = 0;
      st.total = 0;
      st.vote = null;
    }
    st.hasMore = false;
    st.error = err.message || String(err);
  } finally {
    st.loading = false;
    st.loadingMore = false;
    if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = false;
    paintThsEmotionPosts();
    if (more && els.emotionPostsBody) els.emotionPostsBody.scrollTop = prevTop;
    window.requestAnimationFrame(() => maybeLoadThsEmotionMore());
  }
}

function maybeLoadThsEmotionMore() {
  if (!isThsEmotion()) return;
  const st = thsEmotionState.posts;
  const body = els.emotionPostsBody;
  if (!body || st.loading || st.loadingMore || !st.hasMore || !st.items.length) return;
  if (!body.clientHeight) return;
  const remain = body.scrollHeight - body.scrollTop - body.clientHeight;
  if (remain > 160) return;
  loadThsEmotionPosts({ more: true });
}

async function loadThsEmotionAll() {
  if (!code) return;
  thsEmotionState.posts.maxPages = 1;
  thsEmotionState.posts.hasMore = true;
  await Promise.all([loadThsEmotionScores(), loadThsEmotionPosts()]);
}

function syncThsPostSelection() {
  const pid = String(thsEmotionState.detail.postId || "").trim();
  els.emotionPostsList?.querySelectorAll(".ths-emotion-post-item[data-post-id]").forEach((el) => {
    el.classList.toggle("is-active", Boolean(pid) && el.getAttribute("data-post-id") === pid);
  });
}

function paintThsEmotionDetail() {
  const st = thsEmotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  const empty = !st.postId && !st.loading;
  els.emotionDetail.classList.toggle("is-empty", empty);
  if (empty) {
    if (els.emotionDetailTitle) els.emotionDetailTitle.textContent = "帖子详情";
    if (els.emotionDetailMeta) els.emotionDetailMeta.textContent = "点击左侧讨论帖查看正文和评论";
    if (els.emotionDetailLink) els.emotionDetailLink.hidden = true;
    if (els.emotionDetailContent) {
      els.emotionDetailContent.innerHTML = `<p class="muted">从左侧点开一条讨论帖，这里会显示全文和评论。</p>`;
    }
    if (els.emotionDetailReplies) els.emotionDetailReplies.hidden = true;
    if (els.emotionDetailRepliesList) els.emotionDetailRepliesList.innerHTML = "";
    syncThsPostSelection();
    return;
  }
  if (els.emotionDetailTitle) {
    els.emotionDetailTitle.textContent = pack.title || (st.loading ? "正在加载详情…" : "讨论帖详情");
  }
  if (els.emotionDetailMeta) {
    const bits = [
      pack.published_at || "",
      pack.author || pack.media_name || "",
      thsIdentityLabel(pack.identity_tag),
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
    if (st.loading && !pack.title) {
      els.emotionDetailContent.innerHTML = `<p class="muted">正在加载详情…</p>`;
    } else if (st.error && !pack.title) {
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
  if (els.emotionDetailContent) els.emotionDetailContent.scrollTop = 0;
  if (els.emotionDetailRepliesList) els.emotionDetailRepliesList.scrollTop = 0;
  syncThsPostSelection();
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
  thsEmotionState.detail.loading = false;
  thsEmotionState.detail.error = "未找到该讨论帖";
  paintThsEmotionDetail();
}

function closeThsEmotionDetail() {
  thsEmotionState.detail.loading = false;
  thsEmotionState.detail.postId = "";
  thsEmotionState.detail.pack = null;
  thsEmotionState.detail.error = "";
  setEmotionDetailOpen(false);
  paintThsEmotionDetail();
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
  const followers = item.follower_count != null ? item.follower_count : data.follower_count;
  const followerText = followers != null && followers !== "" ? displayValue(followers) : "";
  const hotUsers = Array.isArray(data.hot_users) ? data.hot_users : [];
  const pageUrl = String(item.url || data.page || "").trim();
  const stockName = escapeHtml(data.name || item.name || stockDisplayName || code || "");
  let html = `<div class="xq-snap">`;
  if (followerText) {
    html += `
      <div class="xq-snap-hero">
        <span class="xq-snap-kicker">关注人数</span>
        <strong class="xq-snap-count">${escapeHtml(followerText)}</strong>
        <p class="xq-snap-name">${stockName}</p>
        ${
          pageUrl
            ? `<a class="xq-snap-link" href="${escapeHtml(pageUrl)}" target="_blank" rel="noopener noreferrer">打开雪球</a>`
            : ""
        }
      </div>`;
  }
  if (hotUsers.length) {
    html += `<div class="xq-snap-users"><h4 class="xq-snap-subtitle">热门讨论用户</h4><ul class="xq-snap-user-list">`;
    html += hotUsers
      .map((user) => {
        const name = escapeHtml(user.author || user.media_name || user.title || "-");
        const url = String(user.url || "").trim();
        const fans = user.followers_count != null && user.followers_count !== ""
          ? `粉丝 ${displayValue(user.followers_count)}`
          : "";
        const intro = escapeHtml(truncateText(user.summary || user.content || "", 72));
        const verified = user.verified
          ? `<span class="xq-snap-verified" title="认证">V</span>`
          : "";
        const inner = `
          <span class="xq-snap-user-head">
            <span class="xq-snap-user-name">${name}${verified}</span>
            ${fans ? `<span class="xq-snap-user-fans">${escapeHtml(fans)}</span>` : ""}
          </span>
          ${intro ? `<p class="xq-snap-user-intro">${intro}</p>` : ""}`;
        return url
          ? `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${inner}</a></li>`
          : `<li>${inner}</li>`;
      })
      .join("");
    html += `</ul></div>`;
  }
  html += `</div>`;
  if (!followerText && !hotUsers.length) {
    return `<p class="muted">${escapeHtml(data.title || data.error || "暂无社区快照")}</p>`;
  }
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
    maxPages: xqEmotionState.posts.maxPages || 1,
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
  xqEmotionState.posts.hasMore = xqEmotionState.posts.items.length > 0 && xqEmotionState.posts.maxPages < 20;
  if (posts.kind) xqEmotionState.posts.kind = posts.kind;
  if (posts.sort) xqEmotionState.posts.sort = posts.sort;
}

function paintXqEmotionScores() {
  const st = xqEmotionState.scores;
  if (els.emotionScoresMeta) {
    const bits = [st.data?.name || stockDisplayName || code, st.updatedAt || "-"].filter(Boolean);
    els.emotionScoresMeta.textContent = st.loading ? "正在加载…" : bits.join(" · ");
  }
  if (els.emotionScoresHint) {
    els.emotionScoresHint.textContent = st.loading ? "正在从雪球拉取社区快照…" : st.error || "";
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
      `${st.count || st.items.length} 条`,
      st.hasMore ? "滚动加载" : st.items.length ? "已全部加载" : "",
      st.updatedAt || "-",
    ].filter(Boolean);
    els.emotionPostsMeta.textContent = st.loading && !st.items.length ? "正在查询讨论帖…" : bits.join(" · ");
  }
  if (els.emotionPostsHint) {
    if (st.loading && !st.items.length) {
      els.emotionPostsHint.textContent = "正在从雪球拉取讨论帖…";
    } else if (st.error && !st.items.length) {
      els.emotionPostsHint.textContent = st.error;
    } else if (!st.items.length) {
      els.emotionPostsHint.textContent = "暂无讨论帖，可换来源、排序或拉长区间";
    } else if (st.loadingMore) {
      els.emotionPostsHint.textContent = "正在加载更多讨论帖…";
    } else if (st.hasMore) {
      els.emotionPostsHint.textContent = "向下滚动自动加载更多；点击标题查看正文与评论";
    } else {
      els.emotionPostsHint.textContent = `已加载 ${st.count || st.items.length} 条，点击标题查看正文与评论`;
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
  const foot = st.loadingMore
    ? `<p class="muted xq-load-more">正在加载更多…</p>`
    : st.hasMore
      ? `<p class="muted xq-load-more">滚动加载更多</p>`
      : st.items.length
        ? `<p class="muted xq-load-more">已加载全部</p>`
        : "";
  els.emotionPostsList.innerHTML = `${renderXqEmotionPostList(st.items, "暂无匹配的雪球讨论帖")}${foot}`;
  syncXqPostSelection();
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

async function loadXqEmotionPosts({ more = false } = {}) {
  if (!code) return;
  const st = xqEmotionState.posts;
  if (more) {
    if (st.loading || st.loadingMore || !st.hasMore) return;
  } else if (st.loading) {
    return;
  }
  if (!more) {
    st.maxPages = 1;
    st.hasMore = true;
  } else {
    st.maxPages = Math.min(20, (Number(st.maxPages) || 1) + 1);
  }
  const query = xqEmotionPostsQueryParams();
  query.maxPages = st.maxPages;
  if (more) st.loadingMore = true;
  else st.loading = true;
  st.error = "";
  st.kind = query.kind;
  st.sort = query.sort;
  st.days = query.days;
  st.market = query.market;
  st.withReplies = query.withReplies;
  if (!more && els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = true;
  paintXqEmotionPosts();
  const prevCount = more ? st.items.length : 0;
  const prevTop = els.emotionPostsBody?.scrollTop || 0;
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
    const items = Array.isArray(data.items) ? data.items : [];
    st.items = items;
    st.count = Number(data.count) || items.length;
    st.total = Number(data.total) || st.count;
    st.error = data.error || "";
    st.updatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    st.hasMore = items.length > prevCount && st.maxPages < 20;
    if (els.emotionPostsBody) els.emotionPostsBody.scrollTop = more ? prevTop : 0;
  } catch (err) {
    if (!more) {
      st.items = [];
      st.count = 0;
      st.total = 0;
    }
    st.hasMore = false;
    st.error = err.message || String(err);
  } finally {
    st.loading = false;
    st.loadingMore = false;
    if (els.emotionPostsQueryBtn) els.emotionPostsQueryBtn.disabled = false;
    paintXqEmotionPosts();
    if (more && els.emotionPostsBody) els.emotionPostsBody.scrollTop = prevTop;
    window.requestAnimationFrame(() => maybeLoadXqEmotionMore());
  }
}

function maybeLoadXqEmotionMore() {
  if (!isXqEmotion()) return;
  const st = xqEmotionState.posts;
  const body = els.emotionPostsBody;
  if (!body || st.loading || st.loadingMore || !st.hasMore || !st.items.length) return;
  if (!body.clientHeight) return;
  const remain = body.scrollHeight - body.scrollTop - body.clientHeight;
  if (remain > 160) return;
  loadXqEmotionPosts({ more: true });
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
  xqEmotionState.posts.maxPages = 1;
  xqEmotionState.posts.hasMore = true;
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
    window.requestAnimationFrame(() => maybeLoadXqEmotionMore());
  }
}

function syncXqPostSelection() {
  const pid = String(xqEmotionState.detail.postId || "").trim();
  els.emotionPostsList?.querySelectorAll(".xq-emotion-post-item[data-post-id]").forEach((el) => {
    el.classList.toggle("is-active", Boolean(pid) && el.getAttribute("data-post-id") === pid);
  });
}

function paintXqEmotionDetail() {
  const st = xqEmotionState.detail;
  const pack = st.pack || {};
  if (!els.emotionDetail) return;
  const empty = !st.postId && !st.loading;
  els.emotionDetail.classList.toggle("is-empty", empty);
  if (empty) {
    if (els.emotionDetailTitle) els.emotionDetailTitle.textContent = "帖子详情";
    if (els.emotionDetailMeta) els.emotionDetailMeta.textContent = "点击讨论帖查看正文和评论";
    if (els.emotionDetailLink) els.emotionDetailLink.hidden = true;
    if (els.emotionDetailContent) {
      els.emotionDetailContent.innerHTML = `<p class="muted">从中间点开一条讨论帖，这里会显示全文和评论。</p>`;
    }
    if (els.emotionDetailReplies) els.emotionDetailReplies.hidden = true;
    if (els.emotionDetailRepliesList) els.emotionDetailRepliesList.innerHTML = "";
    syncXqPostSelection();
    return;
  }
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
  syncXqPostSelection();
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

function setupOthersSubTabs() {
  if (!els.othersSourceBar || els.othersSourceBar.dataset.bound === "1") return;
  els.othersSourceBar.dataset.bound = "1";
  els.othersSourceBar.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-source]");
    if (!btn || !els.othersSourceBar.contains(btn)) return;
    setOthersSubTab(btn.getAttribute("data-source") || "lhb");
  });
  syncOthersSubTabUi();
}

function setupJudgmentSubTabs() {
  if (els.judgmentSourceBar && els.judgmentSourceBar.dataset.bound !== "1") {
    els.judgmentSourceBar.dataset.bound = "1";
    els.judgmentSourceBar.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-source]");
      if (!btn || !els.judgmentSourceBar.contains(btn)) return;
      const source = btn.getAttribute("data-source") || "business";
      if (source === "earnings") {
        setJudgmentSubTab(lastEarningsView || "bazhang");
        return;
      }
      setJudgmentSubTab(source);
    });
  }
  if (els.earningsSourceBar && els.earningsSourceBar.dataset.bound !== "1") {
    els.earningsSourceBar.dataset.bound = "1";
    els.earningsSourceBar.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-source]");
      if (!btn || !els.earningsSourceBar.contains(btn)) return;
      setJudgmentSubTab(btn.getAttribute("data-source") || lastEarningsView || "bazhang");
    });
  }
  syncJudgmentSubTabUi();
}

function syncChartsViewportClass() {
  document.documentElement.classList.add("company-charts-on");
  document.body.classList.add("company-charts-on");
}

function fitChartsToViewport() {
  const panels = document.querySelector(".company-panels");
  const tabs = els.companyTabStack || els.companyMainTabs;
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
  const rawPanel = String(panelId || "").trim().toLowerCase();
  const next = normalizeMainPanel(panelId);
  if (!next) return;
  if (next === activeMainPanel) {
    if (next === "judgment" && isAnalysisPanel(rawPanel)) {
      setJudgmentSubTab(rawPanel);
    }
    return;
  }
  activeMainPanel = next;

  document.querySelectorAll(".company-main-tab[data-panel]").forEach((tab) => {
    const active = tab.getAttribute("data-panel") === next;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });

  document.querySelectorAll(".company-panel[data-panel]").forEach((panel) => {
    const active = panel.getAttribute("data-panel") === next;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });

  if (els.refreshEmotionBtn) {
    els.refreshEmotionBtn.hidden = next !== "emotion";
  }
  syncNewsRefreshButtons();
  syncOthersRefreshButtons();

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
  } else if (next === "others") {
    syncOthersSubTabUi();
    bootstrapOthersSubTab();
  } else if (next === "judgment") {
    syncJudgmentSubTabUi();
    bootstrapJudgmentSubTab();
  }
}

function setupMainTabs() {
  const stack = els.companyTabStack || els.companyMainTabs;
  if (!stack || stack.dataset.bound === "1") return;
  stack.dataset.bound = "1";

  stack.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-panel]");
    if (!tab || !stack.contains(tab)) return;
    switchMainPanel(tab.getAttribute("data-panel") || "");
  });
  stack.addEventListener("pointerover", (event) => {
    const tab = event.target.closest("[data-panel]");
    if (!tab || !stack.contains(tab)) return;
    window.OrbitPrefetch?.prefetchTab(tab.getAttribute("data-panel") || "");
  });

  if (els.refreshEmotionBtn) {
    els.refreshEmotionBtn.hidden = activeMainPanel !== "emotion";
  }
  syncNewsRefreshButtons();
  syncOthersRefreshButtons();
}

function setupBackLink() {
  if (!els.backLink) return;
  const cname = (params.get("cname") || "").trim();
  const ccode = (params.get("ccode") || "").trim();
  const industryHref = industry
    ? `/industry?industry=${encodeURIComponent(industry)}`
    : "/industry";
  const searchQs = new URLSearchParams();
  if (cname) searchQs.set("cname", cname);
  if (ccode) searchQs.set("ccode", ccode);
  const searchSuffix = searchQs.toString();

  const targets = {
    market: { href: "/market", label: "返回行业行情" },
    shares: { href: "/shares", label: "返回个股行情" },
    steep: { href: "/steep", label: "返回涨跌停" },
    industry: { href: industryHref, label: "返回行业树" },
    search: {
      href: searchSuffix ? `/industry?${searchSuffix}` : "/industry",
      label: "返回行业树",
    },
    fund: {
      href: fromCat ? `/fund?cat=${encodeURIComponent(fromCat)}` : "/fund",
      label: "返回基金",
    },
    "otc-fund": {
      href: `/fund?cat=${encodeURIComponent(fromCat || "gp")}`,
      label: "返回基金",
    },
    screen: { href: "/analysis?view=limit", label: "返回研判" },
    analysis: { href: "/analysis", label: "返回研判" },
  };
  const fallback = industry
    ? { href: industryHref, label: "返回行业树" }
    : { href: "/market", label: "返回市场" };
  const target = targets[fromPage] || fallback;
  els.backLink.href = target.href;
  els.backLink.textContent = target.label;
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

function fmtWan(n) {
  const value = Number(n);
  if (!Number.isFinite(value)) return "-";
  return `${Math.round(value / 10000)}万`;
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

function fmtVolLots(n) {
  const text = fmtVol(n);
  return text === "-" ? text : `${text}手`;
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
  const hasValue = hasPeSeriesData(peState.items);
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

function applyLinkedRangeToFundflow(range) {
  const vp = viewportFromAxisRange(fundflowState.allItems, range);
  if (!vp) return;
  fundflowState.viewStart = vp.viewStart;
  fundflowState.viewSize = vp.viewSize;
  fundflowState.items = fundflowViewWindow().items;
}

function applyLinkedRangeToMargin(range) {
  const vp = viewportFromAxisRange(marginState.allItems, range);
  if (!vp) return;
  marginState.viewStart = vp.viewStart;
  marginState.viewSize = vp.viewSize;
  marginState.items = marginViewWindow().items;
}

function propagateLinkedAxis(source) {
  if (linkedAxisLock) return;
  if (source === "kline" && !klineJoinsLinkedAxis()) return;
  const items =
    source === "kline"
      ? chartState.items
      : source === "pe"
        ? peState.items
        : source === "fundflow"
          ? fundflowState.items
          : source === "margin"
            ? marginState.items
            : turnoverState.items;
  const range = visibleAxisRange(items);
  if (!range) return;
  linkedAxisLock = true;
  try {
    if (source !== "kline" && klineJoinsLinkedAxis()) applyLinkedRangeToKline(range);
    if (source !== "pe") applyLinkedRangeToPe(range);
    if (source !== "fundflow") applyLinkedRangeToFundflow(range);
    if (source !== "margin") applyLinkedRangeToMargin(range);
    if (source !== "turnover") applyLinkedRangeToTurnover(range);
  } finally {
    linkedAxisLock = false;
  }
}

function chartLayout(
  w,
  h,
  { pctAxis = false, compact = false, combo = false, fundflow = false, ticksCombo = false } = {},
) {
  const pad = {
    top: 8,
    right: pctAxis ? 52 : 8,
    bottom: compact ? 20 : 22,
    left: 52,
  };
  const innerW = Math.max(10, w - pad.left - pad.right);
  const innerH = Math.max(10, h - pad.top - pad.bottom);
  if (ticksCombo) {
    const gap = 8;
    const volH = Math.max(28, Math.floor(innerH * 0.12));
    const bdH = Math.max(64, Math.floor(innerH * 0.22));
    const priceH = Math.max(90, innerH - volH - bdH - gap * 2);
    let y = pad.top;
    const price = { x: pad.left, y, w: innerW, h: priceH };
    y += priceH + gap;
    const volume = { x: pad.left, y, w: innerW, h: volH };
    y += volH + gap;
    const bigDeal = { x: pad.left, y, w: innerW, h: bdH };
    return { pad, price, volume, bigDeal };
  }
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
  const peH = fundflow
    ? Math.max(80, Math.floor(innerH * 0.3))
    : Math.max(72, Math.floor(innerH * 0.24));
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

const FUND_FLOW_AGG_FIELDS = ["main_net", "small_net", "mid_net", "big_net", "super_net"];

function parseAxisDate(str) {
  const key = itemAxisDate({ time: str });
  if (!key || key.length < 10) return null;
  const [y, m, d] = key.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function formatAxisDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function weekStartFromEnd(endStr) {
  const end = parseAxisDate(endStr);
  if (!end) return endStr;
  const day = end.getDay();
  const monday = new Date(end);
  monday.setDate(end.getDate() - (day === 0 ? 6 : day - 1));
  return formatAxisDate(monday);
}

function sumFundflowRows(rows) {
  const out = {};
  for (const field of FUND_FLOW_AGG_FIELDS) {
    let sum = 0;
    let has = false;
    for (const row of rows) {
      const v = Number(row?.[field]);
      if (Number.isFinite(v)) {
        sum += v;
        has = true;
      }
    }
    out[field] = has ? sum : null;
  }
  return out;
}

function alignFundflowToKline(klineItems, flowItems, mode = chartState.mode) {
  const flows = Array.isArray(flowItems) ? flowItems : [];
  const items = Array.isArray(klineItems) ? klineItems : [];
  if (!items.length) return [];
  if (!flows.length) return items.map((d) => ({ time: d.time }));
  if (mode === "day") return alignMetricsToKline(items, flows);

  if (mode === "week") {
    return items.map((k) => {
      const end = itemAxisDate(k);
      if (!end) return { time: k.time };
      const start = weekStartFromEnd(end);
      const bucket = flows.filter((f) => {
        const fd = itemAxisDate(f);
        return fd && fd >= start && fd <= end;
      });
      if (!bucket.length) return { time: k.time };
      return { time: k.time, ...sumFundflowRows(bucket) };
    });
  }

  if (mode === "month") {
    return items.map((k) => {
      const ym = itemAxisDate(k)?.slice(0, 7);
      if (!ym) return { time: k.time };
      const bucket = flows.filter((f) => itemAxisDate(f)?.slice(0, 7) === ym);
      if (!bucket.length) return { time: k.time };
      return { time: k.time, ...sumFundflowRows(bucket) };
    });
  }

  return alignMetricsToKline(items, flows);
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

/** 竞价 | 连续交易 | 盘后 */
const SESSION_PHASE_BREAKS = [9 * 60 + 30, 15 * 60];

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

function sessionOffsetAtX(x, layout, sessionRange = null) {
  const start = sessionRange?.start ?? 0;
  const end = sessionRange?.end ?? sessionDuration();
  const span = Math.max(TICKS_SESSION_MIN_SPAN, end - start);
  const t = (x - layout.price.x) / Math.max(1e-9, layout.price.w);
  return start + Math.min(1, Math.max(0, t)) * span;
}

function snapOffsetToSecond(off, sessionRange = null) {
  const start = sessionRange?.start ?? 0;
  const end = sessionRange?.end ?? sessionDuration();
  const sec = 1 / 60;
  let snapped = Math.floor(off / sec + 1e-6) * sec;
  if (snapped < start) snapped = start;
  if (snapped > end) snapped = Math.max(start, Math.floor(end / sec + 1e-6) * sec);
  return snapped;
}

function clockSecondAtX(x, layout, sessionRange = null) {
  const off = snapOffsetToSecond(sessionOffsetAtX(x, layout, sessionRange), sessionRange);
  return formatClockMinutes(sessionOffsetToClock(off));
}

const ticksEventSecCache = { key: "", secs: [] };

function ticksOrDealEventSeconds() {
  const ticks = ticksState.allItems || [];
  const deals = bigDealChartState.items || [];
  const lastTick = ticks[ticks.length - 1];
  const lastDeal = deals[deals.length - 1];
  const key = [
    ticks.length,
    lastTick?.time || "",
    lastTick?.price ?? "",
    deals.length,
    lastDeal?.time || "",
    lastDeal?.event_id || "",
  ].join(":");
  if (key === ticksEventSecCache.key) return ticksEventSecCache.secs;
  const seen = new Set();
  const secs = [];
  const add = (time) => {
    const sec = timeToSec(time);
    if (sec == null) return;
    const stamp = Math.round(sec * 1000) / 1000;
    if (seen.has(stamp)) return;
    seen.add(stamp);
    secs.push(stamp);
  };
  for (const row of ticks) add(row.time);
  for (const row of deals) add(row.time);
  secs.sort((a, b) => a - b);
  ticksEventSecCache.key = key;
  ticksEventSecCache.secs = secs;
  return secs;
}

function nearestEventSec(targetSec, events) {
  if (!events.length) return null;
  let lo = 0;
  let hi = events.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (events[mid] < targetSec) lo = mid + 1;
    else hi = mid;
  }
  let best = lo;
  if (lo > 0 && Math.abs(events[lo - 1] - targetSec) <= Math.abs(events[lo] - targetSec)) best = lo - 1;
  return events[best];
}

function eventClockAtX(x, layout, sessionRange = null) {
  const raw = clockSecondAtX(x, layout, sessionRange);
  const events = ticksOrDealEventSeconds();
  const target = timeToSec(raw);
  if (target == null || !events.length) return raw;
  const nearest = nearestEventSec(target, events);
  if (nearest == null) return raw;
  return formatClockMinutes(nearest / 60);
}

function sessionSecondKey(clock) {
  const mins = parseClockMinutes(clock);
  if (mins == null) return null;
  return Math.round(mins * 60);
}

function sessionXAt(minutes, layout) {
  const off = sessionOffset(minutes);
  const total = sessionDuration() || 1;
  const ratio = off == null ? 0 : Math.min(1, Math.max(0, off / total));
  return layout.price.x + ratio * layout.price.w;
}

function sessionXAtInRange(minutes, layout, sessionRange = null) {
  if (!sessionRange) return sessionXAt(minutes, layout);
  const off = sessionOffset(minutes);
  if (off == null) return layout.price.x;
  return sessionXFromOffset(off, layout, sessionRange);
}

function sessionXFromOffset(off, layout, sessionRange = null) {
  const start = sessionRange?.start ?? 0;
  const end = sessionRange?.end ?? sessionDuration();
  const len = Math.max(TICKS_SESSION_MIN_SPAN, end - start);
  const ratio = (off - start) / len;
  return layout.price.x + Math.min(1, Math.max(0, ratio)) * layout.price.w;
}

function drawSessionPhaseDividers(ctx, layout, colors, sessionRange) {
  const top = layout.price.y;
  const bottom = ticksChartBottomY(layout);
  if (bottom <= top || layout.price.w <= 0) return;
  const visStart = sessionRange?.start ?? 0;
  const visEnd = sessionRange?.end ?? sessionDuration();
  ctx.save();
  ctx.strokeStyle = colors.ref || "rgba(132, 148, 168, 0.7)";
  ctx.lineWidth = 1;
  for (const minutes of SESSION_PHASE_BREAKS) {
    const off = sessionOffset(minutes);
    if (off == null || off <= visStart + 1e-6 || off >= visEnd - 1e-6) continue;
    const x = Math.round(sessionXFromOffset(off, layout, sessionRange)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
  }
  ctx.restore();
}

function sessionOffsetToClock(sessionOff) {
  if (!Number.isFinite(sessionOff)) return null;
  let acc = 0;
  for (const seg of SESSION_SEGMENTS) {
    const len = seg.end - seg.start;
    if (acc + len >= sessionOff - 1e-9) {
      return seg.start + (sessionOff - acc);
    }
    acc += len;
  }
  return SESSION_SEGMENTS[SESSION_SEGMENTS.length - 1].end;
}

function formatClockMinutes(minutes) {
  if (!Number.isFinite(minutes)) return "";
  const totalSec = Math.max(0, Math.round(minutes * 60));
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function snapSessionAxisStep(rawMinutes) {
  const rawSec = Math.max(TICKS_SESSION_MIN_SPAN * 60, rawMinutes * 60);
  const secSteps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  for (const sec of secSteps) {
    if (sec >= rawSec - 1e-9) return sec / 60;
  }
  return rawMinutes;
}

function buildSessionAxisTicks(sessionRange, plotWidthPx) {
  const full = sessionDuration();
  const start = sessionRange?.start ?? 0;
  const end = sessionRange?.end ?? full;
  const span = Math.max(TICKS_SESSION_MIN_SPAN, end - start);
  const maxLabels = Math.max(2, Math.floor(Math.max(120, plotWidthPx) / 54));
  const step = snapSessionAxisStep(span / maxLabels);
  const ticks = [];
  let off = Math.ceil(start / step - 1e-9) * step;
  for (let guard = 0; off <= end + step * 0.001 && guard < 512; off += step, guard += 1) {
    const clock = sessionOffsetToClock(off);
    if (clock == null) continue;
    ticks.push({
      minutes: clock,
      sessionOff: off,
      label: formatClockMinutes(clock),
      align: off <= start + step * 0.51 ? "left" : off >= end - step * 0.51 ? "right" : "center",
    });
  }
  if (!ticks.length) {
    ticks.push({
      minutes: sessionOffsetToClock(start),
      sessionOff: start,
      label: formatClockMinutes(sessionOffsetToClock(start)),
      align: "left",
    });
  }
  return ticks;
}

function sessionAxisXTicks(layout, sessionRange) {
  return buildSessionAxisTicks(sessionRange, layout.price.w).map((tick) =>
    sessionXAtInRange(tick.minutes, layout, sessionRange),
  );
}

function drawSessionAxisTicks(ctx, layout, colors, sessionRange, targetPane) {
  const pane = targetPane || layout.volume;
  if (!pane) return;
  const ticks = buildSessionAxisTicks(sessionRange, layout.price.w);
  ctx.save();
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.fillStyle = colors.muted;
  ctx.textBaseline = "top";
  for (const tick of ticks) {
    ctx.textAlign = tick.align || "center";
    ctx.fillText(
      tick.label,
      sessionXAtInRange(tick.minutes, layout, sessionRange),
      pane.y + pane.h + 6,
    );
  }
  ctx.restore();
}

function filterItemsBySessionRange(items, sessionRange) {
  if (!sessionRange) return items || [];
  return (items || []).filter((item) => {
    const off = sessionOffset(parseClockMinutes(item?.time));
    return off != null && off >= sessionRange.start - 1e-9 && off <= sessionRange.end + 1e-9;
  });
}

function ticksEffectiveSessionRange() {
  if (ticksState.sessionView) {
    const start = Math.max(0, Number(ticksState.sessionView.start) || 0);
    const end = Math.min(sessionDuration(), Number(ticksState.sessionView.end) || sessionDuration());
    if (end - start >= TICKS_SESSION_MIN_SPAN) return { start, end };
  }
  return null;
}

function ticksSessionViewWindow() {
  const full = sessionDuration();
  const range = ticksEffectiveSessionRange();
  const span = range ? Math.max(TICKS_SESSION_MIN_SPAN, range.end - range.start) : full;
  const maxStart = Math.max(0, full - span);
  const start = range ? Math.min(Math.max(0, range.start), maxStart) : 0;
  return {
    full,
    span,
    maxStart,
    start,
    end: start + span,
    zoomed: Boolean(range),
  };
}

function ticksPlotItems() {
  const all = ticksState.allItems || [];
  const range = ticksEffectiveSessionRange();
  if (!range) return all;
  return filterItemsBySessionRange(all, range);
}

function zoomTicksSessionView(anchorRatio, factor, { render = true } = {}) {
  const full = sessionDuration();
  const cur = ticksEffectiveSessionRange() || { start: 0, end: full };
  const span = Math.max(TICKS_SESSION_MIN_SPAN, cur.end - cur.start);
  const ratio = Math.min(1, Math.max(0, Number(anchorRatio) || 0.5));
  const anchor = cur.start + span * ratio;
  // 与 K 线/滚轮约定一致：factor>1 显示更多（缩小），factor<1 放大；用 span*factor，勿对 factor 做 max(1.05, …)
  const f = Math.min(6, Math.max(0.18, Number(factor) || 1));
  let nextSpan = span * f;
  nextSpan = Math.max(TICKS_SESSION_MIN_SPAN, Math.min(full, nextSpan));
  let start = anchor - ratio * nextSpan;
  let end = start + nextSpan;
  if (start < 0) {
    start = 0;
    end = nextSpan;
  }
  if (end > full) {
    end = full;
    start = Math.max(0, full - nextSpan);
  }
  const atFull = start <= 1e-6 && end >= full - 1e-6;
  if (
    !atFull &&
    Math.abs(start - cur.start) < 1e-6 &&
    Math.abs(end - cur.end) < 1e-6 &&
    Math.abs(nextSpan - span) < 1e-6
  ) {
    return false;
  }
  ticksState.sessionView = atFull ? null : { start, end };
  syncTicksChartScrollBar();
  refreshTicksChartWindowStatus();
  if (render) renderTicksChart();
  return true;
}

function panTicksSessionByPixels(dx, canvasWidth) {
  const win = ticksSessionViewWindow();
  if (win.maxStart <= 0 && !win.zoomed) return false;
  const layout = chartLayout(canvasWidth, 300, ticksLayoutOptions({ pctAxis: false }));
  const span = win.span;
  const pxPerUnit = layout.price.w / Math.max(TICKS_SESSION_MIN_SPAN, span);
  if (pxPerUnit <= 0) return false;
  const delta = -dx / pxPerUnit;
  if (!Number.isFinite(delta) || Math.abs(delta) < 1e-6) return false;
  let start = win.start + delta;
  let end = start + span;
  if (start < 0) {
    start = 0;
    end = span;
  }
  if (end > win.full) {
    end = win.full;
    start = Math.max(0, win.full - span);
  }
  ticksState.sessionView = start <= 1e-6 && end >= win.full - 1e-6 ? null : { start, end };
  syncTicksChartScrollBar();
  refreshTicksChartWindowStatus();
  renderTicksChart();
  return true;
}

function setTicksChartSessionStart(nextStart, { render = true, hoverIndex = null } = {}) {
  const win = ticksSessionViewWindow();
  const start = Math.min(Math.max(0, Number(nextStart) || 0), win.maxStart);
  const end = start + win.span;
  const prev = ticksEffectiveSessionRange() || { start: 0, end: win.full };
  if (Math.abs(start - prev.start) < 1e-6) {
    syncTicksChartScrollBar();
    if (render) renderTicksChart(hoverIndex);
    return start;
  }
  ticksState.sessionView = start <= 1e-6 && end >= win.full - 1e-6 ? null : { start, end };
  syncTicksChartScrollBar();
  refreshTicksChartWindowStatus();
  if (render) renderTicksChart(hoverIndex);
  return start;
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

function drawSessionTimeLabels(ctx, layout, colors, sessionRange = null, targetPane = null) {
  const pane = targetPane || layout.volume;
  if (!pane) return;
  ctx.save();
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.fillStyle = colors.muted;
  ctx.textBaseline = "top";
  const labels = sessionRange
    ? SESSION_X_LABELS.filter((item) => {
        const off = sessionOffset(item.minutes);
        return off != null && off >= sessionRange.start && off <= sessionRange.end;
      })
    : SESSION_X_LABELS;
  for (const item of labels) {
    ctx.textAlign = item.align || "center";
    ctx.fillText(item.label, sessionXAtInRange(item.minutes, layout, sessionRange), pane.y + pane.h + 6);
  }
  ctx.restore();
}

function ticksChartBottomY(layout) {
  if (layout?.bigDeal) return layout.bigDeal.y + layout.bigDeal.h;
  return layout.volume.y + layout.volume.h;
}

function ticksLayoutOptions(extra = {}) {
  return {
    pctAxis: Number.isFinite(ticksState.preClose) && ticksState.preClose,
    compact: true,
    ticksCombo: true,
    ...extra,
  };
}

function bigDealEventType(row) {
  const side = String(row?.side || "").toLowerCase();
  let agg = String(row?.aggressor || "").toLowerCase();
  if (!agg) {
    const label = String(row?.aggressor_label || "");
    if (label.includes("主")) agg = "active";
    else if (label.includes("被")) agg = "passive";
  }
  if (agg === "active" && side === "buy") return "active_buy";
  if (agg === "active" && side === "sell") return "active_sell";
  if (agg === "passive" && side === "buy") return "passive_buy";
  if (agg === "passive" && side === "sell") return "passive_sell";
  const name = String(row?.event_name || "");
  if (name.includes("主动买")) return "active_buy";
  if (name.includes("主动卖")) return "active_sell";
  if (name.includes("被动买")) return "passive_buy";
  if (name.includes("被动卖")) return "passive_sell";
  return null;
}

function filterBigDealsInSessionRange(items, sessionRange) {
  if (!sessionRange) return items || [];
  return (items || []).filter((row) => {
    const off = sessionOffset(parseClockMinutes(row?.time));
    return off != null && off >= sessionRange.start && off <= sessionRange.end;
  });
}

function layoutBigDealBarSlots(items, layout, sessionRange) {
  const pane = layout.bigDeal;
  if (!pane) return [];
  const visible = filterBigDealsInSessionRange(items, sessionRange);
  const seconds = new Map();
  for (const row of visible) {
    const type = bigDealEventType(row);
    if (!type || !BIG_DEAL_BAR_TYPES[type]) continue;
    const amount = Number(row.amount);
    if (!Number.isFinite(amount) || amount <= 0) continue;
    const time = String(row.time || "");
    const clock = tickClockSecond(time);
    const mins = parseClockMinutes(clock || time);
    const off = sessionOffset(mins);
    if (!clock || off == null) continue;
    let bucket = seconds.get(clock);
    if (!bucket) {
      bucket = { clock, mins, off, types: { active_buy: [], passive_buy: [], active_sell: [], passive_sell: [] } };
      seconds.set(clock, bucket);
    }
    bucket.types[type].push({
      row,
      type,
      amount,
      eventId: String(row.event_id || `${time}|${type}|${amount}|${row.volume || 0}`),
      time,
      clock,
      mins,
      off,
    });
  }
  if (!seconds.size) return [];

  const span = sessionRange
    ? Math.max(TICKS_SESSION_MIN_SPAN, sessionRange.end - sessionRange.start)
    : sessionDuration() || 1;
  const pxPerSec = pane.w / Math.max(1, span * 60);
  const clusterW = Math.max(4, Math.min(pxPerSec * 0.88, 40));
  const innerGap = clusterW >= 12 ? 1 : 0;
  const barW = Math.max(1, (clusterW - innerGap * 3) / 4);

  const slots = [];
  const buckets = [...seconds.values()].sort((a, b) => a.off - b.off || a.clock.localeCompare(b.clock));
  for (const bucket of buckets) {
    const center = sessionXAtInRange(bucket.mins, layout, sessionRange);
    const left = center - clusterW / 2;
    BIG_DEAL_COLUMNS.forEach((type, col) => {
      const rows = bucket.types[type] || [];
      if (!rows.length) return;
      rows.sort(
        (a, b) =>
          a.off - b.off ||
          String(a.time).localeCompare(String(b.time)) ||
          String(a.eventId).localeCompare(String(b.eventId)),
      );
      const x = left + col * (barW + innerGap) + barW / 2;
      const total = rows.reduce((sum, entry) => sum + entry.amount, 0);
      let acc = 0;
      for (const entry of rows) {
        slots.push({
          ...entry,
          x,
          barW,
          stackFrom: acc,
          stackTo: acc + entry.amount,
          columnTotal: total,
          stacked: rows.length > 1,
        });
        acc += entry.amount;
      }
    });
  }
  return slots;
}

function bigDealSlotIsBuy(type) {
  return type === "active_buy" || type === "passive_buy";
}

function bigDealBarRect(slot, pane, maxAmt) {
  const halfH = pane.h / 2;
  const yZero = pane.y + halfH;
  const scale = halfH / Math.max(maxAmt, 1);
  const from = Math.min(halfH, Math.max(0, (Number(slot.stackFrom) || 0) * scale));
  const to = Math.min(halfH, Math.max(from + 1, (Number(slot.stackTo) || Number(slot.amount) || 0) * scale));
  const h = Math.max(1, to - from);
  const barW = slot.barW;
  const x = slot.x - barW / 2;
  if (bigDealSlotIsBuy(slot.type)) {
    return { x, y: yZero - to, w: barW, h, yZero };
  }
  return { x, y: yZero + from, w: barW, h, yZero };
}

function bigDealColumnTotals(slots) {
  const seen = new Set();
  const totals = [];
  for (const slot of slots || []) {
    const key = `${slot.clock || ""}|${slot.type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const total = Number(slot.columnTotal);
    if (Number.isFinite(total) && total > 0) totals.push(total);
  }
  return totals;
}

function bigDealAtPointer(x, y, layout, sessionRange) {
  const pane = layout.bigDeal;
  if (!pane || x < pane.x || x > pane.x + pane.w || y < pane.y || y > pane.y + pane.h) return null;
  const slots = bigDealChartState.barSlots || [];
  const yMax = Math.max(Number(bigDealChartState.yMax) || 1, 1);
  let best = null;
  let bestScore = Infinity;
  for (const slot of slots) {
    const rect = bigDealBarRect(slot, pane, yMax);
    const pad = 2;
    if (x < rect.x - pad || x > rect.x + rect.w + pad) continue;
    if (y < rect.y - pad || y > rect.y + rect.h + pad) continue;
    const inside =
      x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h;
    const cx = rect.x + rect.w / 2;
    const cy = rect.y + rect.h / 2;
    const score = (inside ? 0 : 400) + Math.hypot(x - cx, y - cy);
    if (score < bestScore) {
      bestScore = score;
      best = slot;
    }
  }
  return best;
}

function drawBigDealEventBars(ctx, layout, items, colors, opts = {}) {
  const pane = layout.bigDeal;
  if (!pane) return [];
  const sessionRange = opts.sessionRange || null;
  const hoverEventId = opts.hoverEventId || null;
  const hoverSecond = tickClockSecond(opts.hoverSecond || "");
  const hoverRange = opts.hoverRange || null;
  const slots = layoutBigDealBarSlots(items, layout, sessionRange);
  bigDealChartState.barSlots = slots;

  const xTicks = sessionAxisXTicks(layout, sessionRange);

  const halfH = pane.h / 2;
  const yZero = pane.y + halfH;
  bigDealChartState.yZero = yZero;

  drawPaneLabel(ctx, pane, "大单", colors);

  if (!slots.length) {
    ctx.save();
    ctx.font = '11px "JetBrains Mono", Consolas, monospace';
    ctx.fillStyle = colors.muted;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("暂无大单", pane.x + pane.w / 2, pane.y + pane.h / 2);
    ctx.restore();
    drawGrid(ctx, pane, [pane.y + halfH * 0.5, yZero, pane.y + pane.h], xTicks, colors);
    ctx.save();
    ctx.strokeStyle = colors.muted || "#8494a8";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(pane.x, yZero);
    ctx.lineTo(pane.x + pane.w, yZero);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
    bigDealChartState.yMax = 1;
    return slots;
  }

  const totals = bigDealColumnTotals(slots);
  const sorted = totals.slice().sort((a, b) => a - b);
  const p95 = quantile(sorted, 0.95);
  const maxAmt = Math.max(p95 ?? sorted[sorted.length - 1] ?? 1, 1);
  bigDealChartState.yMax = maxAmt;

  const yBuyTop = pane.y;
  const ySellBottom = pane.y + pane.h;
  drawGrid(ctx, pane, [yBuyTop + halfH * 0.5, yZero, yZero + halfH * 0.5], xTicks, colors);

  ctx.save();
  ctx.strokeStyle = colors.muted || "#8494a8";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(pane.x, yZero);
  ctx.lineTo(pane.x + pane.w, yZero);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  ctx.save();
  ctx.font = '10px "JetBrains Mono", Consolas, monospace';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillStyle = colors.up;
  ctx.fillText(fmtWan(maxAmt), pane.x - 4, yBuyTop + 8);
  ctx.fillStyle = colors.muted;
  ctx.fillText("0", pane.x - 4, yZero);
  ctx.fillStyle = colors.down;
  ctx.fillText(fmtWan(maxAmt), pane.x - 4, ySellBottom - 8);
  ctx.restore();

  ctx.save();
  ctx.beginPath();
  ctx.rect(pane.x, pane.y, pane.w, pane.h);
  ctx.clip();
  for (const slot of slots) {
    const rect = bigDealBarRect(slot, pane, maxAmt);
    const inHoverRange = hoverRange
      ? dealInHoverRange(slot.time, hoverRange)
      : Boolean(hoverSecond && (slot.clock || tickClockSecond(slot.time)) === hoverSecond);
    const dimmed = hoverRange || hoverSecond
      ? !inHoverRange
      : hoverEventId && hoverEventId !== slot.eventId;
    ctx.globalAlpha = dimmed ? 0.35 : 1;
    ctx.fillStyle = BIG_DEAL_BAR_TYPES[slot.type]?.color || colors.muted;
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    if (slot.stacked) {
      ctx.strokeStyle = "rgba(4, 8, 14, 0.55)";
      ctx.lineWidth = 1;
      ctx.strokeRect(rect.x + 0.5, rect.y + 0.5, Math.max(0, rect.w - 1), Math.max(0, rect.h - 1));
    }
    if (inHoverRange || hoverEventId === slot.eventId) {
      ctx.strokeStyle = colors.cross;
      ctx.lineWidth = 1;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    }
  }
  ctx.globalAlpha = 1;
  ctx.restore();

  if (hoverEventId && !hoverSecond) {
    const hit = slots.find((slot) => slot.eventId === hoverEventId);
    if (hit) {
      const x = hit.x;
      ctx.save();
      ctx.strokeStyle = colors.cross;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, layout.price.y);
      ctx.lineTo(x, pane.y + pane.h);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }
  }

  return slots;
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

function drawRealtimeChart(ctx, layout, items, preClose, mode, colors, hoverIndex, opts = {}) {
  const sessionAxis = Boolean(opts.sessionAxis);
  const sessionRange = opts.sessionRange || null;
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
  const plotBottom = ticksChartBottomY(layout);
  const priceScale = buildPriceScale(minP, maxP, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.015,
    center: Number.isFinite(preClose) ? preClose : null,
  });

  const sessionSpan = sessionRange ? Math.max(1, sessionRange.end - sessionRange.start) : sessionDuration() || 1;
  const xAt = (i) => {
    if (!sessionAxis) return price.x + ((i + 0.5) / Math.max(1, n)) * price.w;
    const mins = parseClockMinutes(items[i]?.time);
    return mins == null ? price.x : sessionXAtInRange(mins, layout, sessionRange);
  };
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;

  const yTicks = (priceScale.ticks || []).map(yAt);
  const xTicks = sessionAxis
    ? sessionAxisXTicks(layout, sessionRange)
    : [0, 0.5, 1].map((t) => price.x + price.w * t);
  drawGrid(ctx, price, yTicks, xTicks, colors);
  drawGrid(ctx, volume, [volume.y, volume.y + volume.h], xTicks, colors);
  if (sessionAxis) drawSessionPhaseDividers(ctx, layout, colors, sessionRange);

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

  if (n) {
    const vols = items.map((d) => Number(d.volume) || 0);
    const maxVol = Math.max(...vols, 1);
    const barW = sessionAxis
      ? Math.max(1, Math.min(4, price.w / sessionSpan))
      : Math.max(1, (price.w / n) * 0.7);
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
    if (sessionAxis && maxVol > 0) {
      ctx.save();
      ctx.font = '10px "JetBrains Mono", Consolas, monospace';
      ctx.fillStyle = colors.muted;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(fmtVolLots(maxVol), volume.x - 4, volume.y + 8);
      ctx.restore();
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
    const nowOff = sessionOffset(nowMinutes);
    if (
      sessionRange &&
      (nowOff == null || nowOff < sessionRange.start || nowOff > sessionRange.end)
    ) {
      /* 当前时间不在可视时段内时不画竖线 */
    } else {
    const x = sessionXAtInRange(nowMinutes, layout, sessionRange);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, plotBottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
    }
  }

  const hoverMinutes = Number.isFinite(opts.hoverMinutes) ? Number(opts.hoverMinutes) : null;
  if (hoverMinutes != null) {
    const x = sessionXAtInRange(hoverMinutes, layout, sessionRange);
    const p = Number.isFinite(opts.hoverPrice) ? Number(opts.hoverPrice) : null;
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, plotBottom);
    ctx.stroke();
    if (p != null) {
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
  } else if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    const p = Number(items[hoverIndex].price);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, plotBottom);
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
  if (sessionAxis && !layout.bigDeal) drawSessionTimeLabels(ctx, layout, colors, sessionRange);
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

const FUND_FLOW_TIERS = [
  { key: "super", field: "super_net", pctField: "super_net_pct", label: "超大单", color: "#e63946" },
  { key: "big", field: "big_net", pctField: "big_net_pct", label: "大单", color: "#f4a261" },
  { key: "mid", field: "mid_net", pctField: "mid_net_pct", label: "中单", color: "#457b9d" },
  { key: "small", field: "small_net", pctField: "small_net_pct", label: "小单", color: "#2a9d8f" },
];

const FUND_FLOW_MAIN = { field: "main_net", pctField: "main_net_pct", label: "主力", color: "#c77dff" };

const fundflowState = {
  loading: false,
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: 90,
  source: "",
  visibleTiers: new Set(["super", "big", "mid", "small"]),
};

const MARGIN_SERIES = {
  rzye: { key: "rzye", label: "融资余额", color: "#e63946" },
  rzrqye: { key: "rzrqye", label: "两融余额", color: "#f4a261" },
  rqye: { key: "rqye", label: "融券余额", color: "#457b9d" },
};

const marginState = {
  loading: false,
  items: [],
  allItems: [],
  viewStart: 0,
  viewSize: 90,
  source: "",
  visibleSeries: new Set(["rzye", "rzrqye"]),
};

function visibleMarginSeries() {
  return Object.keys(MARGIN_SERIES)
    .filter((id) => marginState.visibleSeries.has(id))
    .map((id) => ({ id, ...MARGIN_SERIES[id] }));
}

function marginSeriesValue(d, series) {
  const n = Number(d?.[series?.key]);
  return Number.isFinite(n) ? n : null;
}

function hasMarginSeriesData(items) {
  const series = visibleMarginSeries();
  if (!series.length) return false;
  return (items || []).some((d) => series.some((s) => marginSeriesValue(d, s) != null));
}

function marginAtTime(time) {
  const hit = alignMetricsToKline([{ time }], marginState.allItems)[0];
  if (!hit) return null;
  const has =
    Number.isFinite(Number(hit.rzye)) ||
    Number.isFinite(Number(hit.rqye)) ||
    Number.isFinite(Number(hit.rzjme)) ||
    Number.isFinite(Number(hit.rqjmg));
  return has ? hit : null;
}

function marginSignedHtml(amount, fmt, fallbackFmt) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "-";
  let text = fmt || "";
  if (!text) {
    const raw = fallbackFmt(Math.abs(n));
    text = n > 0 ? `+${raw}` : n < 0 ? `-${raw}` : raw;
  }
  const cls = n > 0 ? "change-up" : n < 0 ? "change-down" : "";
  return `<span class="${cls}">${escapeHtml(text)}</span>`;
}

function marginHoverRows(m, row) {
  const rows = [];
  const rzye = Number(m.rzye);
  if (Number.isFinite(rzye)) {
    const text = m.rzye_fmt || fmtVol(rzye);
    rows.push(
      row("融资余额", `<span style="color:${MARGIN_SERIES.rzye.color}">${escapeHtml(text)}</span>`)
    );
  }
  const rqye = Number(m.rqye);
  if (Number.isFinite(rqye)) {
    const text = m.rqye_fmt || fmtVol(rqye);
    rows.push(
      row("融券余额", `<span style="color:${MARGIN_SERIES.rqye.color}">${escapeHtml(text)}</span>`)
    );
  }
  if (Number.isFinite(Number(m.rzjme))) {
    rows.push(row("融资净买", marginSignedHtml(m.rzjme, m.rzjme_fmt, fmtVol)));
  }
  if (Number.isFinite(Number(m.rqjmg))) {
    rows.push(row("融券净卖", marginSignedHtml(m.rqjmg, m.rqjmg_fmt, fmtVol)));
  }
  return rows;
}

function fundflowTierValue(d, tier) {
  const n = Number(d?.[tier.field]);
  return Number.isFinite(n) ? n : null;
}

function fundflowPctValue(d, tier) {
  const n = Number(d?.[tier.pctField]);
  return Number.isFinite(n) ? n : null;
}

function visibleFundflowTiers() {
  return FUND_FLOW_TIERS.filter((t) => fundflowState.visibleTiers.has(t.key));
}

function hasFundflowData(items) {
  const tiers = visibleFundflowTiers();
  if (!tiers.length) return false;
  return (items || []).some((d) => tiers.some((t) => fundflowTierValue(d, t) != null));
}

function fundflowAtTime(time) {
  const hit = alignFundflowToKline([{ time }], fundflowState.allItems, chartState.mode)[0];
  if (!hit) return null;
  const tiers = visibleFundflowTiers();
  if (!tiers.length) return null;
  return tiers.some((tier) => fundflowTierValue(hit, tier) != null) ? hit : null;
}

function fundflowFlowHtml(amount, pct, color) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "-";
  const sign = n > 0 ? "+" : "";
  let text = `${sign}${fmtVol(n)}`;
  const p = Number(pct);
  if (Number.isFinite(p)) text += ` (${p > 0 ? "+" : ""}${fmtPct(p)})`;
  const cls = n > 0 ? "change-up" : n < 0 ? "change-down" : "";
  const style = color ? ` style="color:${color}"` : "";
  return `<span class="${cls}"${style}>${escapeHtml(text)}</span>`;
}

function fundflowHoverRows(ff, row) {
  const rows = [];
  const showPct = chartState.mode === "day";
  const mainAmt = Number(ff[FUND_FLOW_MAIN.field]);
  if (Number.isFinite(mainAmt)) {
    rows.push(
      row(
        FUND_FLOW_MAIN.label,
        fundflowFlowHtml(mainAmt, showPct ? ff[FUND_FLOW_MAIN.pctField] : null, FUND_FLOW_MAIN.color)
      )
    );
  }
  for (const tier of FUND_FLOW_TIERS) {
    const amt = fundflowTierValue(ff, tier);
    if (amt == null) continue;
    rows.push(
      row(tier.label, fundflowFlowHtml(amt, showPct ? fundflowPctValue(ff, tier) : null, tier.color))
    );
  }
  return rows;
}

function peHoverRows(peRow, row) {
  const rows = [];
  for (const series of visiblePeSeries()) {
    const v = peSeriesValue(peRow, series);
    if (v == null) continue;
    rows.push(
      row(series.label, `<span style="color:${series.color}">${escapeHtml(fmtNum(v))}</span>`)
    );
  }
  return rows;
}

function drawGroupedSignedBars(ctx, layout, items, tiers, colors, hoverIndex, { mode = "day" } = {}) {
  const n = items.length;
  if (!n || !tiers.length) return;

  const { price } = layout;
  const values = [];
  for (const d of items) {
    for (const tier of tiers) {
      const v = fundflowTierValue(d, tier);
      if (v != null) values.push(v);
    }
  }
  if (!values.length) return;

  const absVals = values.map((v) => Math.abs(v)).sort((a, b) => a - b);
  const p95 = quantile(absVals, 0.95);
  const peak = absVals.length ? absVals[absVals.length - 1] : 0;
  const maxAbs = Math.max(p95 ?? peak, 1);
  const priceScale = buildPriceScale(-maxAbs, maxAbs, {
    tickCount: priceScaleTickCount(price.h),
    padRatio: 0.06,
    center: 0,
  });
  const yAt = (p) =>
    price.y + ((priceScale.max - p) / (priceScale.max - priceScale.min || 1)) * price.h;
  const yZero = yAt(0);
  const groupW = price.w / n;
  const tierCount = tiers.length;
  const innerGap = 1;
  const barW = Math.min(6, Math.max(2, (groupW - innerGap * (tierCount - 1)) / tierCount));
  const span = tierCount * barW + innerGap * (tierCount - 1);

  const yTicks = (priceScale.ticks || []).map(yAt);
  const xTicks = [0, 0.5, 1].map((t) => price.x + price.w * t);
  drawGrid(ctx, price, yTicks, xTicks, colors);

  ctx.save();
  ctx.strokeStyle = colors.muted || "#8494a8";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(price.x, yZero);
  ctx.lineTo(price.x + price.w, yZero);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  ctx.save();
  ctx.beginPath();
  ctx.rect(price.x, price.y, price.w, price.h);
  ctx.clip();

  for (let i = 0; i < n; i += 1) {
    const centerX = price.x + (i + 0.5) * groupW;
    const dimmed = hoverIndex != null && hoverIndex !== i;
    let barX = centerX - span / 2;
    for (const tier of tiers) {
      const v = fundflowTierValue(items[i], tier);
      if (v == null) {
        barX += barW + innerGap;
        continue;
      }
      const yVal = yAt(Math.max(-maxAbs, Math.min(maxAbs, v)));
      const barH = Math.max(1, Math.abs(yVal - yZero));
      const barY = v >= 0 ? yVal : yZero;
      ctx.globalAlpha = dimmed ? 0.35 : 1;
      ctx.fillStyle = tier.color;
      ctx.fillRect(barX, barY, barW, barH);
      if (barW >= 2) {
        ctx.strokeStyle = "rgba(0, 0, 0, 0.22)";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(barX, barY, barW, barH);
      }
      barX += barW + innerGap;
    }
  }
  ctx.globalAlpha = 1;
  ctx.restore();

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = price.x + (hoverIndex + 0.5) * groupW;
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, price.y);
    ctx.lineTo(x, price.y + price.h);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  if (mode !== "day") drawPaneLabel(ctx, price, "(汇总)", colors);
  drawAxesLabels(ctx, layout, priceScale, items, mode, colors, {
    yFormat: fmtVol,
    skipTimeLabels: false,
  });
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
  const fundflow = combo && comboMetricState === "fundflow";
  const margin = combo && comboMetricState === "margin";
  const layout = chartLayout(cssW, cssH, { combo, fundflow: fundflow || margin });
  drawKlineChart(ctx, layout, items, chartState.mode, colors, hoverIndex);
  if (!combo || !layout.pe) return;

  const metricColors = {
    accent: cssVar("--accent", "#2ad4b8"),
    muted: colors.muted,
    up: colors.up,
    down: colors.down,
    grid: colors.grid,
    cross: colors.cross,
  };
  const metricPane = {
    price: layout.pe,
    volume: { x: layout.pe.x, y: layout.pe.y + layout.pe.h, w: layout.pe.w, h: 0 },
  };
  if (fundflow) {
    const ffItems = alignFundflowToKline(items, fundflowState.allItems, chartState.mode);
    if (hasFundflowData(ffItems)) {
      drawGroupedSignedBars(ctx, metricPane, ffItems, visibleFundflowTiers(), metricColors, hoverIndex, {
        mode: chartState.mode,
      });
    } else {
      drawPaneCenterLabel(
        ctx,
        layout.pe,
        fundflowState.loading ? "资金流加载中…" : "暂无资金流数据",
        metricColors
      );
    }
    return;
  }
  if (margin) {
    const mgItems = alignMetricsToKline(items, marginState.allItems);
    if (hasMarginSeriesData(mgItems)) {
      drawPeOverlayChart(ctx, metricPane, mgItems, visibleMarginSeries(), metricColors, hoverIndex, {
        yFormat: fmtVol,
        mode: chartState.mode,
        skipHoverHair: true,
      });
    } else {
      drawPaneCenterLabel(
        ctx,
        layout.pe,
        marginState.loading ? "两融加载中…" : "暂无融资融券数据",
        metricColors
      );
    }
    return;
  }
  const peItems = alignMetricsToKline(items, peState.allItems);
  if (hasPeSeriesData(peItems)) {
    drawPeOverlayChart(ctx, metricPane, peItems, visiblePeSeries(), metricColors, hoverIndex, {
      formatLabel: fmtNum,
      mode: chartState.mode,
      skipHoverHair: true,
    });
  } else {
    drawPaneCenterLabel(ctx, layout.pe, peState.loading ? "估值加载中…" : "暂无估值", metricColors);
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

function drawPaneCenterLabel(ctx, rect, text, colors) {
  if (!rect || !text) return;
  ctx.save();
  ctx.fillStyle = colors.muted || "#8494a8";
  ctx.font = '11px "JetBrains Mono", Consolas, monospace';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, rect.x + rect.w / 2, rect.y + rect.h / 2);
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
  const quoteRows = [
    row("开盘", escapeHtml(fmtNum(d.open))),
    row("最低", escapeHtml(fmtNum(d.low))),
    row("最高", escapeHtml(fmtNum(d.high))),
    row("收盘", escapeHtml(fmtNum(d.close)), closeCls),
    p ? row("涨跌幅", escapeHtml(p.text), p.cls) : "",
    row("成交量", escapeHtml(fmtVol(d.volume))),
  ].filter(Boolean);
  const auxRows = [...maRows];
  if (comboPanesEnabled()) {
    if (comboMetricState === "fundflow") {
      const ff = fundflowAtTime(d.time);
      if (ff) auxRows.push(...fundflowHoverRows(ff, row));
    } else if (comboMetricState === "margin") {
      const mg = marginAtTime(d.time);
      if (mg) auxRows.push(...marginHoverRows(mg, row));
    } else {
      const peRow = alignMetricsToKline([d], peState.allItems)[0];
      if (peRow) auxRows.push(...peHoverRows(peRow, row));
    }
  }

  const line = (items, withTime = false) =>
    `<div class="chart-hover-card-rows chart-hover-card-rows--inline">${
      withTime ? `<span class="chart-hover-card-time">${escapeHtml(d.time || "")}</span>` : ""
    }${items.join("")}</div>`;
  els.chartHoverCard.innerHTML = `<div class="chart-hover-card-stack">${line(quoteRows, true)}${
    auxRows.length ? line(auxRows) : ""
  }</div>`;
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

/** 按屏幕宽度决定绘制上限，避免全局预先丢数据。 */
function ticksPlotPointCap(plotWidthPx) {
  return Math.max(160, Math.min(TICKS_DRAW_MAX, Math.floor(plotWidthPx * 2.5)));
}

/**
 * 视口级抽稀：每个桶保留最低价、最高价、末价，避免缩小时抹平尖峰。
 * 比均匀 downsample 更适合价格折线。
 */
function decimateTicksPreservingExtrema(items, maxN) {
  if (!Array.isArray(items) || items.length <= maxN) return items;
  const n = items.length;
  const bucketCount = Math.max(1, Math.floor(maxN / 3));
  const out = [];
  let prev = -1;
  for (let b = 0; b < bucketCount; b += 1) {
    const start = Math.floor((b * n) / bucketCount);
    const end = Math.min(n, Math.floor(((b + 1) * n) / bucketCount));
    if (start >= end) continue;
    let minI = start;
    let maxI = start;
    let minP = Infinity;
    let maxP = -Infinity;
    for (let i = start; i < end; i += 1) {
      const p = Number(items[i].price);
      if (!Number.isFinite(p)) continue;
      if (p < minP) {
        minP = p;
        minI = i;
      }
      if (p > maxP) {
        maxP = p;
        maxI = i;
      }
    }
    const picks = [...new Set([minI, maxI, end - 1])].sort((a, b) => a - b);
    for (const i of picks) {
      if (i === prev) continue;
      out.push(items[i]);
      prev = i;
    }
  }
  if (prev !== n - 1) out.push(items[n - 1]);
  return out;
}

function decimateTicksForPlot(items, plotWidthPx) {
  return decimateTicksPreservingExtrema(items, ticksPlotPointCap(plotWidthPx));
}

function mapTicksHoverToDrawIndex(fullIndex, fullItems, drawItems) {
  if (fullIndex == null || fullIndex < 0 || !fullItems?.length || !drawItems?.length) return null;
  if (fullItems === drawItems) return fullIndex;
  const t = fullItems[fullIndex]?.time;
  if (t == null) return null;
  let best = 0;
  for (let i = 0; i < drawItems.length; i += 1) {
    if (String(drawItems[i].time) <= String(t)) best = i;
    else break;
  }
  return best;
}

function tickRowKey(d, { relaxed = false } = {}) {
  const time = String(d?.time ?? "");
  const price = Number(d?.price);
  const volume = Number(d?.volume) || 0;
  const base = `${time}|${price}|${volume}`;
  if (relaxed) return base;
  return `${base}|${d?.count ?? ""}|${d?.seq ?? ""}`;
}

function findTickOverlapIndex(current, incoming, { relaxed = false } = {}) {
  const lastKey = tickRowKey(current[current.length - 1], { relaxed });
  for (let i = incoming.length - 1; i >= 0; i -= 1) {
    if (tickRowKey(incoming[i], { relaxed }) === lastKey) return i;
  }
  const keyToIndex = new Map();
  incoming.forEach((row, i) => {
    keyToIndex.set(tickRowKey(row, { relaxed }), i);
  });
  for (let i = current.length - 1; i >= 0; i -= 1) {
    const hit = keyToIndex.get(tickRowKey(current[i], { relaxed }));
    if (hit != null) return hit;
  }
  return -1;
}

function mergeTickItems(current, incoming) {
  if (!incoming.length) return current;
  if (!current.length) return incoming;

  let idx = findTickOverlapIndex(current, incoming);
  if (idx < 0) idx = findTickOverlapIndex(current, incoming, { relaxed: true });
  if (idx >= 0) return current.concat(incoming.slice(idx + 1));

  const lastCurT = parseClockMinutes(current[current.length - 1].time);
  const lastIncT = parseClockMinutes(incoming[incoming.length - 1].time);
  if (lastCurT != null && lastIncT != null) {
    if (lastIncT > lastCurT) {
      const newer = incoming.filter((row) => {
        const t = parseClockMinutes(row.time);
        return t != null && t > lastCurT;
      });
      if (newer.length) return current.concat(newer);
    } else if (lastIncT === lastCurT) {
      let cut = current.length;
      while (cut > 0) {
        const t = parseClockMinutes(current[cut - 1].time);
        if (t == null || t < lastCurT) break;
        cut -= 1;
      }
      const tail = incoming.filter((row) => parseClockMinutes(row.time) === lastCurT);
      if (tail.length) return current.slice(0, cut).concat(tail);
    }
  }

  // 增量切片对不上时保留已有全天走势，避免只剩最近几十笔
  if (current.length >= incoming.length) return current;
  return incoming;
}

function applyTicksItems(rawItems, { resetViewport = false } = {}) {
  const raw = Array.isArray(rawItems) ? rawItems : [];
  const prevTotal = (ticksState.allItems || []).length;
  const prevSize = Number(ticksState.viewSize) || 0;
  const prevStart = Number(ticksState.viewStart) || 0;
  const atLatest =
    !prevTotal || prevSize <= 0 || prevSize >= prevTotal || prevStart + prevSize >= prevTotal;

  const decorated = withTickAvg(raw);
  ticksState.allItems = decorated;
  ticksState.items = decorated;
  const total = ticksState.allItems.length;

  if (!total || resetViewport) {
    ticksState.viewSize = total;
    ticksState.viewStart = 0;
    ticksState.sessionView = null;
  } else {
    const minSize = chartMinViewSize(total, { ticks: true });
    let size = prevSize;
    if (size <= 0 || size >= prevTotal) size = total;
    else size = Math.max(minSize, Math.min(total, size));
    let start = atLatest ? Math.max(0, total - size) : Math.min(prevStart, Math.max(0, total - size));
    ticksState.viewSize = size;
    ticksState.viewStart = start;
  }
  syncTicksChartScrollBar();
  refreshTicksTapeList();
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
  const all = ticksState.allItems || [];
  const total = all.length;
  let size = Number(ticksState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(ticksState.viewStart) || 0), maxStart);
  return {
    all,
    total,
    size,
    maxStart,
    start,
    items: total ? all.slice(start, start + size) : [],
  };
}

function refreshTicksLiveStatus() {
  refreshTicksChartWindowStatus();
}

function refreshTicksChartWindowStatus() {
  const plotCount = ticksPlotItems().length;
  const total = (ticksState.allItems || []).length;
  const history = isTicksHistoryView();
  if (!total && !ticksState.tradeDate && !history) return;
  const sess = ticksSessionViewWindow();
  let zoomTip = "";
  if (sess.zoomed) {
    const a = formatClockMinutes(sessionOffsetToClock(sess.start));
    const b = formatClockMinutes(sessionOffsetToClock(sess.end));
    zoomTip = ` · ${a}–${b} · 滚轮放大至秒级 · 拖动平移`;
  } else if (total) {
    zoomTip = " · 滚轮可放大至秒级 · 拖动平移";
  }
  if (sess.zoomed && plotCount) {
    zoomTip += ` · ${plotCount} 点`;
  }
  if (history) {
    const src = ticksState.source ? ` · ${ticksState.source}` : "";
    const cacheTip = ticksState.cached ? " · 盘后缓存" : "";
    const date = ticksViewDay();
    if (!total) {
      setTicksChartStatus("");
      return;
    }
    setTicksChartStatus(`${date} · 09:15:00–15:30:00${zoomTip}${src}${cacheTip}`);
    return;
  }
  if (ticksState.phase === "live") {
    const src = ticksState.source ? ` · ${ticksState.source}` : "";
    const clock = cnNowParts().clockStr;
    setTicksChartStatus(`实时 · ${clock} · 每秒刷新${zoomTip}${src}`);
    return;
  }
  const src = ticksState.source ? ` · ${ticksState.source}` : "";
  const cacheTip = ticksState.cached ? " · 盘后缓存" : "";
  const date = ticksState.tradeDate ? ` · ${ticksState.tradeDate}` : "";
  const axis = "09:15:00–15:30:00";
  if (ticksState.phase === "lunch") {
    setTicksChartStatus(`午间休市 · ${axis}${date}${zoomTip}${src}${cacheTip}`);
    return;
  }
  const today = cnNowParts().dateStr;
  if (ticksState.tradeDate && ticksState.tradeDate === today) {
    setTicksChartStatus(`已收盘${date} · ${axis}${zoomTip}${src}${cacheTip}`);
    return;
  }
  setTicksChartStatus(`上一交易日${date} · ${axis}${zoomTip}${src}${cacheTip}`);
}

function syncTicksChartScrollBar() {
  const bar = els.ticksChartScrollBar;
  const wrap = els.ticksChartAxisScroll;
  if (!bar) return;
  const win = ticksSessionViewWindow();
  const canScroll = win.maxStart > 1e-6;
  if (wrap) wrap.classList.toggle("is-disabled", !canScroll);
  bar.disabled = !canScroll;
  bar.min = "0";
  bar.max = String(Math.max(0, win.maxStart));
  bar.step = String(Math.max(TICKS_SESSION_MIN_SPAN / 10, 0.01));
  bar.value = String(win.start);
  const ratio = win.full > 0 ? Math.min(1, win.span / win.full) : 1;
  const thumbPx = Math.max(28, Math.round(48 + ratio * 72));
  bar.style.setProperty("--thumb-w", `${thumbPx}px`);
}

function setTicksChartViewStart(nextStart, { render = true, hoverIndex = null } = {}) {
  return setTicksChartSessionStart(nextStart, { render, hoverIndex });
}

function zoomTicksChartViewport(anchorRatio, factor, { render = true } = {}) {
  return zoomTicksSessionView(anchorRatio, factor, { render });
}

function panTicksChartByPixels(dx, canvasWidth) {
  return panTicksSessionByPixels(dx, canvasWidth);
}

function ticksHoverIndex() {
  const items = ticksPlotItems();
  const t = ticksState.hoverTime;
  if (!t || !items.length) return null;
  let best = null;
  for (let i = 0; i < items.length; i += 1) {
    if (String(items[i].time) === t) return i;
    if (String(items[i].time) <= t) best = i;
  }
  return best;
}

function renderTicksChart(_hoverIndex = undefined) {
  const canvas = els.ticksChart;
  const wrap = els.ticksChartWrap;
  if (!canvas || !wrap) return;

  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(240, wrap.clientWidth || 320);
  const cssH = Math.max(240, wrap.clientHeight || 300);
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const colors = chartColors();
  paintChartFrame(ctx, cssW, cssH, colors);
  const sessionRange = ticksEffectiveSessionRange();
  const plotItems = ticksPlotItems();
  const showPctAxis = Number.isFinite(ticksState.preClose) && ticksState.preClose;
  const layout = chartLayout(cssW, cssH, ticksLayoutOptions({ pctAxis: showPctAxis }));
  const drawItems = decimateTicksForPlot(plotItems, layout.price.w);
  const inspectClock =
    ticksState.chartHovering || ticksState.listHover
      ? ticksState.hoverSecond
      : ticksState.linkPin?.clock || null;
  const snapshot = inspectClock
    ? summarizeTicksAtSecond(inspectClock) || lastTickSnapshotAtOrBefore(inspectClock) || summarizeDealAtSecond(inspectClock)
    : null;
  const barRange = ticksState.listHover ? ticksState.hoverRange : ticksState.linkPin?.range || null;
  drawRealtimeChart(ctx, layout, drawItems, ticksState.preClose, "ticks", colors, null, {
    sessionAxis: true,
    sessionRange,
    nowMinutes: ticksState.phase === "live" ? cnNowParts().minutes : null,
    hoverMinutes: inspectClock ? parseClockMinutes(inspectClock) : null,
    hoverPrice: snapshot?.price,
    hoverVolume: snapshot?.volume,
  });
  drawBigDealEventBars(ctx, layout, bigDealChartState.items, colors, {
    sessionRange,
    hoverRange: barRange || undefined,
    hoverEventId: ticksState.listHover
      ? ticksState.hoverDealPreferred?.event_id
      : ticksState.linkPin?.preferred?.event_id,
  });
  drawSessionAxisTicks(ctx, layout, colors, sessionRange, layout.bigDeal);
}

function tickIndexAtTime(time, items) {
  const target = String(time || "");
  if (!target || !items.length) return null;
  let best = 0;
  for (let i = 0; i < items.length; i += 1) {
    if (String(items[i].time) === target) return i;
    if (String(items[i].time) <= target) best = i;
    else break;
  }
  return best;
}

function ticksLatestItem() {
  const all = ticksState.allItems || [];
  if (all.length) return all[all.length - 1];
  const items = ticksState.items || [];
  return items.length ? items[items.length - 1] : null;
}

function tickClockSecond(value) {
  const s = String(value || "").trim();
  const m = s.match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return "";
  return `${m[1].padStart(2, "0")}:${m[2]}:${(m[3] || "00").slice(0, 2).padStart(2, "0")}`;
}

function tickSideMeta(d) {
  const label = String(d?.side_label || "").toLowerCase();
  const side = d?.side;
  if (label === "buy" || side === 1 || side === "buy") return { text: "买", cls: "change-up" };
  if (label === "sell" || side === 2 || side === "sell") return { text: "卖", cls: "change-down" };
  if (label === "auction" || side === 4 || side === "auction") return { text: "竞", cls: "" };
  if (label === "mid" || side === 0 || side === "mid") return { text: "中", cls: "" };
  return { text: "", cls: "" };
}

function collectTicksAtSecond(time) {
  const key = tickClockSecond(time);
  const all = ticksState.allItems || [];
  if (!key || !all.length) return [];
  let lo = 0;
  let hi = all.length - 1;
  let hit = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const cur = tickClockSecond(all[mid].time);
    if (!cur || cur < key) lo = mid + 1;
    else if (cur > key) hi = mid - 1;
    else {
      hit = mid;
      break;
    }
  }
  if (hit < 0) return [];
  let start = hit;
  while (start > 0 && tickClockSecond(all[start - 1].time) === key) start -= 1;
  let end = hit;
  while (end + 1 < all.length && tickClockSecond(all[end + 1].time) === key) end += 1;
  return all.slice(start, end + 1);
}

function summarizeTicksAtSecond(time) {
  const list = collectTicksAtSecond(time);
  if (!list.length) return null;
  const last = list[list.length - 1];
  let volume = 0;
  let count = 0;
  for (const row of list) {
    volume += Number(row.volume) || 0;
    const n = Number(row.count);
    count += Number.isFinite(n) && n > 0 ? n : 1;
  }
  const side = tickSideMeta(last);
  return {
    time: last.time || time,
    clock: tickClockSecond(last.time || time),
    price: Number(last.price),
    volume,
    count,
    sideText: side.text,
    sideCls: side.cls,
  };
}

function lastTickSnapshotAtOrBefore(time) {
  const sec = timeToSec(time);
  if (sec == null) return null;
  const items = ticksState.allItems || [];
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const stamp = timeToSec(items[i].time);
    if (stamp != null && stamp <= sec) return summarizeTicksAtSecond(items[i].time);
  }
  return null;
}

function summarizeDealAtSecond(time) {
  const deals = collectBigDealsAtSecond(time);
  if (!deals.length) return null;
  const last = deals[deals.length - 1];
  const price = Number(last.price);
  return {
    time: last.time || time,
    clock: tickClockSecond(last.time || time),
    price: Number.isFinite(price) ? price : null,
    volume: 0,
    count: deals.length,
    sideText: "",
    sideCls: "",
  };
}

function collectBigDealsAtSecond(time) {
  const key = tickClockSecond(time);
  if (!key) return [];
  return (bigDealChartState.items || []).filter((row) => tickClockSecond(row.time) === key);
}

function pickPrimaryDeal(deals, preferred) {
  if (!deals.length) return null;
  const prefId = String(preferred?.event_id || "");
  if (prefId) {
    const hit = deals.find((row) => String(row.event_id || "") === prefId);
    if (hit) return hit;
  }
  return deals.reduce((best, row) => (Number(row.amount) > Number(best.amount) ? row : best), deals[0]);
}

function hideTicksHoverCard() {
  ticksState.listHover = false;
  ticksState.chartHovering = false;
  ticksState.hoverOrigin = ticksState.linkPin ? "chart" : "";
  ticksState.hoverTime = null;
  ticksState.hoverBigDeal = null;
  ticksState.hoverDealPaintId = "";
  if (restoreTicksLinkPin()) {
    fillTicksQuoteCardFromSecond(tickClockSecond(ticksLatestItem()?.time));
    return;
  }
  ticksState.hoverSecond = null;
  ticksState.hoverRange = null;
  ticksState.hoverTickIndexes = [];
  ticksState.hoverLinkKey = "";
  ticksState.hoverDealPreferred = null;
  syncTapeLinkHighlight();
  fillTicksQuoteCardFromSecond(tickClockSecond(ticksLatestItem()?.time));
}

function showTicksHoverCard() {
  if (!els.ticksChartHoverCard) return;
  els.ticksChartHoverCard.classList.remove("hidden");
  els.ticksChartHoverCard.setAttribute("aria-hidden", "false");
}

function fillTicksQuoteCard(d) {
  fillTicksQuoteCardFromSecond(
    ticksState.hoverSecond || tickClockSecond(d?.time) || tickClockSecond(ticksState.hoverDealPreferred?.time)
  );
}

function fillTicksQuoteCardFromSecond(second) {
  if (!els.ticksChartHoverCard) return;
  const clock = tickClockSecond(second);
  if (!clock) {
    ticksState.hoverBigDeal = null;
    els.ticksChartHoverCard.classList.add("hidden");
    els.ticksChartHoverCard.setAttribute("aria-hidden", "true");
    els.ticksChartHoverCard.innerHTML = "";
    return;
  }

  const quoteClock = quoteClockForEvent(clock);
  const snapshot = summarizeTicksAtSecond(quoteClock) || lastTickSnapshotAtOrBefore(quoteClock) || summarizeDealAtSecond(clock);
  const deals = collectBigDealsAtSecond(clock);
  const primary = pickPrimaryDeal(deals, ticksState.hoverDealPreferred);
  ticksState.hoverBigDeal = primary;
  ticksState.hoverTime = quoteClock;

  const price = Number(snapshot?.price);
  let pct = null;
  if (Number.isFinite(ticksState.preClose) && Number.isFinite(price) && ticksState.preClose) {
    pct = ((price - ticksState.preClose) / ticksState.preClose) * 100;
  }
  const priceCls = pct > 0 ? "change-up" : pct < 0 ? "change-down" : "";
  const priceText = Number.isFinite(price) ? fmtNum(price) : "—";
  const pctText =
    pct == null || !Number.isFinite(Number(pct))
      ? "—"
      : `${pct > 0 ? "+" : ""}${Number(pct).toFixed(2)}%`;

  els.ticksChartHoverCard.innerHTML = `<div class="chart-hover-card-rows chart-hover-card-rows--inline chart-ticks-quote">
    <span class="chart-hover-card-time">${escapeHtml(quoteClock || clock)}</span>
    <span class="v chart-hover-item--price ${priceCls}">${escapeHtml(priceText)}</span>
    <span class="v chart-hover-pct ${priceCls}">${escapeHtml(pctText)}</span>
  </div>`;
  showTicksHoverCard();
}

function updateTicksHoverLabel(index) {
  if (index == null) {
    if (!ticksState.listHover) hideTicksHoverCard();
    return;
  }
  fillTicksQuoteCardFromSecond(ticksState.hoverSecond);
}

function refreshTicksQuoteCard() {
  if (ticksState.chartHovering || ticksState.listHover) {
    fillTicksQuoteCardFromSecond(ticksState.hoverSecond);
  } else {
    fillTicksQuoteCardFromSecond(tickClockSecond(ticksLatestItem()?.time));
  }
}

function ticksPointerIndex(evt) {
  const canvas = els.ticksChart;
  const wrap = els.ticksChartWrap;
  if (!canvas || !wrap) return null;
  const rect = canvas.getBoundingClientRect();
  const x = evt.clientX - rect.left;
  const y = evt.clientY - rect.top;
  const showPctAxis = Number.isFinite(ticksState.preClose) && ticksState.preClose;
  const layout = chartLayout(rect.width, rect.height, ticksLayoutOptions({ pctAxis: showPctAxis }));
  const plotRight = layout.price.x + layout.price.w;
  const plotBottom = ticksChartBottomY(layout);
  const sessionRange = ticksEffectiveSessionRange();
  const link = evt.type === "pointerup";
  if (x < layout.price.x || x > plotRight || y < layout.price.y || y > plotBottom) {
    ticksState.chartHovering = false;
    if (link) {
      ticksState.linkPin = null;
      ticksState.hoverDealPreferred = null;
    }
    return null;
  }

  let preferred = null;
  if (layout.bigDeal && y >= layout.bigDeal.y) {
    preferred = bigDealAtPointer(x, y, layout, sessionRange)?.row || null;
  }
  const second = preferred ? tickClockSecond(preferred.time) : eventClockAtX(x, layout, sessionRange);
  ticksState.chartHovering = true;
  if (link) {
    pinTicksChartLink(second, { preferred, scrollLists: true });
  } else {
    ticksState.hoverSecond = tickClockSecond(second) || null;
    if (ticksState.linkPin) {
      ticksState.hoverRange = ticksState.linkPin.range;
      ticksState.hoverTickIndexes = ticksState.linkPin.indexes || [];
      ticksState.hoverDealPreferred = ticksState.linkPin.preferred || null;
    } else {
      ticksState.hoverRange = null;
      ticksState.hoverTickIndexes = [];
      ticksState.hoverDealPreferred = preferred;
    }
    fillTicksQuoteCardFromSecond(ticksState.hoverSecond);
  }
  return sessionSecondKey(second);
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

async function loadTicksChart({ silent = false, refresh = false } = {}) {
  if (!code || !els.ticksChart) return;
  const gen = ++ticksState.loadGen;
  ticksState.loading = true;
  const history = isTicksHistoryView();
  ticksState.phase = history ? "closed" : cnMarketPhase();
  ticksState.live = !history && ticksState.phase === "live";
  if (!silent) {
    setTicksChartStatus(history ? "" : "正在加载实时…");
    hideTicksHoverCard();
  }

  if (!history && ticksState.phase === "live" && !ticksState.allItems.length) {
    void bootstrapTicksFromMinuteKline();
  }

  try {
    const qs = new URLSearchParams({ code, day: ticksViewDay() });
    if (!history && (ticksState.phase === "live" || refresh)) {
      qs.set("refresh", "1");
    }
    const json = await api(`/api/stocks/ticks?${qs.toString()}`);
    if (gen !== ticksState.loadGen) return;
    const data = json.data || {};
    let rawItems = Array.isArray(data.items) ? data.items : [];
    let preClose = Number(data.pre_price);
    let source = data.source || "";
    let tradeDate = inferTicksTradeDate(data, rawItems) || ticksViewDay();

    if (!rawItems.length && !history && ticksState.phase !== "live") {
      const fallback = await loadPreviousSessionTicks();
      if (gen !== ticksState.loadGen) return;
      rawItems = fallback.items;
      if (Number.isFinite(fallback.preClose)) preClose = fallback.preClose;
      source = fallback.source || source;
      tradeDate = fallback.day || tradeDate;
    }

    applyTicksItems(rawItems, { resetViewport: history });
    ticksState.preClose = Number.isFinite(preClose) ? preClose : null;
    ticksState.source = source;
    ticksState.cached = Boolean(data.cached);
    ticksState.tradeDate = tradeDate || inferTicksTradeDate(data, ticksState.allItems) || ticksViewDay();

    const count = ticksState.allItems.length;
    if (!count) {
      if (history) {
        setTicksChartStatus("");
        if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
        fillTicksQuoteCard(null);
        renderTicksChart();
        return;
      }
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
    if (gen !== ticksState.loadGen) return;
    applyTicksItems([], { resetViewport: true });
    if (history) {
      setTicksChartStatus("");
      if (els.ticksChartEmpty) els.ticksChartEmpty.classList.add("hidden");
    } else {
      setTicksChartStatus(err.message || "实时加载失败", { empty: true });
    }
    fillTicksQuoteCard(null);
    renderTicksChart();
  } finally {
    if (gen === ticksState.loadGen) {
      ticksState.loading = false;
      refreshTicksTapeList();
    }
  }
}

async function pollTicksLive() {
  if (!code || !els.ticksChart || !ticksState.live || isTicksHistoryView()) return;
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
    if (gen !== ticksState.liveFetchGen || isTicksHistoryView()) return;

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
    ticksState.cached = Boolean(data.cached);
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
    await loadProfile({ silent: true, liveOnly: true });
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
  if (isTicksHistoryView()) {
    ticksState.live = false;
    return;
  }
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
      loadTicksChart({ silent: true, refresh: true });
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
  layoutTicksCombo = () => false,
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
      if (!(win.total || win.full)) return;
      evt.preventDefault();
      hideHover();
      hoverIdx = null;

      const rect = canvas.getBoundingClientRect();
      const layout = chartLayout(rect.width, rect.height, {
        pctAxis: layoutPctAxis(),
        compact: layoutCompact,
        ticksCombo: layoutTicksCombo(),
      });
      const x = evt.clientX - rect.left;
      let anchorRatio = 0.5;
      if (x >= layout.price.x && x <= layout.price.x + layout.price.w) {
        anchorRatio = (x - layout.price.x) / layout.price.w;
      }

      if (Math.abs(evt.deltaX) > Math.abs(evt.deltaY) * 1.15) {
        const fresh = viewWindow();
        if (fresh.maxStart <= 0) return;
        const step = fresh.full
          ? Math.max(TICKS_SESSION_MIN_SPAN, (fresh.span || sessionDuration()) * 0.06)
          : Math.max(1, Math.round(Math.abs(evt.deltaX) / 40));
        setViewStart(fresh.start + (evt.deltaX > 0 ? step : -step), { render: true });
        return;
      }

      const steps = Math.max(1, Math.min(6, Math.round(Math.abs(evt.deltaY) / 56) || 1));
      const base = evt.deltaY > 0 ? 1.22 : 1 / 1.22;
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
    syncComboLegend(mode);
    renderChart();
    refreshKlineQuoteCard();
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

  bindTapeChartLink();
  bindChartPaneInteractions({
    canvas: els.ticksChart,
    wrap: els.ticksChartWrap,
    scrollBar: els.ticksChartScrollBar,
    hideHover: hideTicksHoverCard,
    updateHover: updateTicksHoverLabel,
    render: renderTicksChart,
    pointerIndexAt: ticksPointerIndex,
    panByPixels: panTicksChartByPixels,
    viewWindow: ticksSessionViewWindow,
    setViewStart: setTicksChartViewStart,
    zoomViewport: zoomTicksChartViewport,
    syncScrollBar: syncTicksChartScrollBar,
    layoutPctAxis: () => Number.isFinite(ticksState.preClose) && ticksState.preClose,
    layoutCompact: true,
    layoutTicksCombo: () => true,
    enablePanZoom: true,
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
  dyn: { key: "pe_dyn", label: "市盈率动", color: "#f4a261" },
  ttm: { key: "pe_ttm", label: "市盈率TTM", color: "#2ad4b8" },
  static: { key: "pe_static", label: "市盈率静", color: "#7aa2f7" },
  pb: { key: "pb", label: "市净率", color: "#e07a5f" },
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
  visibleSeries: new Set(["dyn", "ttm", "static", "pb"]),
};

function peSeriesConf() {
  return PE_SERIES[peState.series] || PE_SERIES.ttm;
}

function visiblePeSeries() {
  return Object.keys(PE_SERIES)
    .filter((id) => peState.visibleSeries.has(id))
    .map((id) => ({ id, ...PE_SERIES[id] }));
}

function peSeriesValue(d, series) {
  const n = Number(d?.[series?.key]);
  return Number.isFinite(n) ? n : null;
}

function peValue(d) {
  const n = Number(d?.[peSeriesConf().key]);
  return Number.isFinite(n) ? n : null;
}

function hasPeSeriesData(items) {
  const series = visiblePeSeries();
  if (!series.length) return false;
  return (items || []).some((d) => series.some((s) => peSeriesValue(d, s) != null));
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

function drawPeOverlayChart(ctx, layout, items, seriesList, colors, hoverIndex, opts = {}) {
  const n = items.length;
  if (!n || !seriesList.length) return false;
  const values = [];
  for (const d of items) {
    for (const series of seriesList) {
      const v = peSeriesValue(d, series);
      if (v != null) values.push(v);
    }
  }
  if (!values.length) return false;

  const { price } = layout;
  let minP = Math.min(...values);
  let maxP = Math.max(...values);
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
  for (const series of seriesList) {
    ctx.beginPath();
    let started = false;
    let lastIdx = -1;
    for (let i = 0; i < n; i += 1) {
      const v = peSeriesValue(items[i], series);
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
      lastIdx = i;
    }
    ctx.strokeStyle = series.color;
    ctx.lineWidth = 1.6;
    ctx.stroke();
    if (lastIdx >= 0) {
      ctx.fillStyle = series.color;
      ctx.beginPath();
      ctx.arc(xAt(lastIdx), yAt(peSeriesValue(items[lastIdx], series)), 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();

  if (hoverIndex != null && hoverIndex >= 0 && hoverIndex < n) {
    const x = xAt(hoverIndex);
    ctx.save();
    ctx.strokeStyle = colors.cross;
    ctx.setLineDash([3, 3]);
    if (!opts.skipHoverHair) {
      ctx.beginPath();
      ctx.moveTo(x, price.y);
      ctx.lineTo(x, price.y + price.h);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    for (const series of seriesList) {
      const v = peSeriesValue(items[hoverIndex], series);
      if (v == null) continue;
      ctx.fillStyle = series.color;
      ctx.beginPath();
      ctx.arc(x, yAt(v), 3.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  drawAxesLabels(ctx, layout, priceScale, items, opts.mode || "day", colors, {
    yFormat: opts.yFormat,
    skipTimeLabels: opts.skipTimeLabels,
  });
  return true;
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
    const hasValue = hasPeSeriesData(peState.items);
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
    renderFundamentals();
  }
}

function fundflowViewWindow() {
  const all = fundflowState.allItems || [];
  const total = all.length;
  let size = Number(fundflowState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(fundflowState.viewStart) || 0), maxStart);
  return { total, size, start, maxStart, items: total ? all.slice(start, start + size) : [] };
}

function resetFundflowViewport(allItems, { preferLinked = true } = {}) {
  fundflowState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = fundflowState.allItems.length;
  const linked = preferLinked && klineJoinsLinkedAxis() ? visibleAxisRange(chartState.items) : null;
  const vp = linked ? viewportFromAxisRange(fundflowState.allItems, linked) : null;
  if (vp) {
    fundflowState.viewStart = vp.viewStart;
    fundflowState.viewSize = vp.viewSize;
  } else {
    let viewSize = METRIC_FALLBACK_VIEW_SIZE;
    if (viewSize <= 0 || viewSize >= total) viewSize = total;
    fundflowState.viewSize = viewSize;
    fundflowState.viewStart = Math.max(0, total - viewSize);
  }
  fundflowState.items = fundflowViewWindow().items;
}

function marginViewWindow() {
  const all = marginState.allItems || [];
  const total = all.length;
  let size = Number(marginState.viewSize) || 0;
  if (size <= 0 || size >= total) size = total;
  const maxStart = Math.max(0, total - size);
  const start = Math.min(Math.max(0, Number(marginState.viewStart) || 0), maxStart);
  return { total, size, start, maxStart, items: total ? all.slice(start, start + size) : [] };
}

function resetMarginViewport(allItems, { preferLinked = true } = {}) {
  marginState.allItems = Array.isArray(allItems) ? allItems : [];
  const total = marginState.allItems.length;
  const linked = preferLinked && klineJoinsLinkedAxis() ? visibleAxisRange(chartState.items) : null;
  const vp = linked ? viewportFromAxisRange(marginState.allItems, linked) : null;
  if (vp) {
    marginState.viewStart = vp.viewStart;
    marginState.viewSize = vp.viewSize;
  } else {
    let viewSize = METRIC_FALLBACK_VIEW_SIZE;
    if (viewSize <= 0 || viewSize >= total) viewSize = total;
    marginState.viewSize = viewSize;
    marginState.viewStart = Math.max(0, total - viewSize);
  }
  marginState.items = marginViewWindow().items;
}

function syncComboMetricSelect(metric = comboMetricState) {
  if (!els.comboMetricSelect) return;
  if (els.comboMetricSelect.value !== metric) els.comboMetricSelect.value = metric;
}

function applyComboMetric(metric) {
  if (!["pe", "fundflow", "margin"].includes(metric) || metric === comboMetricState) return;
  comboMetricState = metric;
  syncComboMetricSelect(metric);
  syncComboLegend();
  if (metric === "fundflow" && !fundflowState.loading && !(fundflowState.allItems || []).length) {
    void loadFundflowChart();
    return;
  }
  if (metric === "margin" && !marginState.loading && !(marginState.allItems || []).length) {
    void loadMarginChart();
    return;
  }
  renderChart();
  refreshKlineQuoteCard();
}

function syncFundflowLegendUi() {
  if (!els.fundflowLegendWrap) return;
  els.fundflowLegendWrap.querySelectorAll(".fundflow-legend-item").forEach((label) => {
    const tier = label.getAttribute("data-tier");
    const input = label.querySelector("input[type=checkbox]");
    if (!tier || !input) return;
    input.checked = fundflowState.visibleTiers.has(tier);
  });
}

function syncPeLegendUi() {
  if (!els.peLegendWrap) return;
  els.peLegendWrap.querySelectorAll(".fundflow-legend-item").forEach((label) => {
    const series = label.getAttribute("data-series");
    const input = label.querySelector("input[type=checkbox]");
    if (!series || !input) return;
    input.checked = peState.visibleSeries.has(series);
  });
}

function syncMarginLegendUi() {
  if (!els.marginLegendWrap) return;
  els.marginLegendWrap.querySelectorAll(".fundflow-legend-item").forEach((label) => {
    const series = label.getAttribute("data-series");
    const input = label.querySelector("input[type=checkbox]");
    if (!series || !input) return;
    input.checked = marginState.visibleSeries.has(series);
  });
}

function setupComboMetric() {
  if (els.comboMetricSelect) {
    els.comboMetricSelect.addEventListener("change", () => {
      applyComboMetric(els.comboMetricSelect.value);
    });
    syncComboMetricSelect();
  }
  if (els.fundflowLegendWrap) {
    els.fundflowLegendWrap.querySelectorAll(".fundflow-legend-item input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        const label = input.closest(".fundflow-legend-item");
        const tier = label?.getAttribute("data-tier");
        if (!tier) return;
        if (input.checked) {
          fundflowState.visibleTiers.add(tier);
        } else if (fundflowState.visibleTiers.size <= 1) {
          input.checked = true;
          return;
        } else {
          fundflowState.visibleTiers.delete(tier);
        }
        syncFundflowLegendUi();
        renderChart();
        refreshKlineQuoteCard();
      });
    });
    syncFundflowLegendUi();
  }
  if (els.peLegendWrap) {
    els.peLegendWrap.querySelectorAll(".fundflow-legend-item input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        const label = input.closest(".fundflow-legend-item");
        const series = label?.getAttribute("data-series");
        if (!series || !PE_SERIES[series]) return;
        if (input.checked) {
          peState.visibleSeries.add(series);
        } else if (peState.visibleSeries.size <= 1) {
          input.checked = true;
          return;
        } else {
          peState.visibleSeries.delete(series);
        }
        syncPeLegendUi();
        renderChart();
        refreshKlineQuoteCard();
      });
    });
    syncPeLegendUi();
  }
  if (els.marginLegendWrap) {
    els.marginLegendWrap.querySelectorAll(".fundflow-legend-item input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        const label = input.closest(".fundflow-legend-item");
        const series = label?.getAttribute("data-series");
        if (!series || !MARGIN_SERIES[series]) return;
        if (input.checked) {
          marginState.visibleSeries.add(series);
        } else if (marginState.visibleSeries.size <= 1) {
          input.checked = true;
          return;
        } else {
          marginState.visibleSeries.delete(series);
        }
        syncMarginLegendUi();
        renderChart();
        refreshKlineQuoteCard();
      });
    });
    syncMarginLegendUi();
  }
  syncComboLegend();
}

async function fetchFundflowPayload({ refresh = false } = {}) {
  const qs = new URLSearchParams({ code, scope: "daily", limit: "120" });
  if (refresh) qs.set("refresh", "1");
  const json = await api(`/api/stocks/fund-flow?${qs.toString()}`);
  return json.data || {};
}

async function loadFundflowChart() {
  if (!code) return;
  fundflowState.loading = true;
  renderChart();
  try {
    let data = { items: [] };
    for (let attempt = 0; attempt < 3; attempt += 1) {
      data = await fetchFundflowPayload({ refresh: attempt > 0 });
      if (Array.isArray(data.items) && data.items.length > 1) break;
      if (attempt < 2) {
        await new Promise((resolve) => {
          window.setTimeout(resolve, 450 * (attempt + 1));
        });
      }
    }
    fundflowState.source = data.source || "";
    resetFundflowViewport(data.items || []);
  } catch {
    resetFundflowViewport([]);
    fundflowState.source = "";
  } finally {
    fundflowState.loading = false;
    renderChart();
    refreshKlineQuoteCard();
  }
}

async function fetchMarginPayload({ refresh = false } = {}) {
  const qs = new URLSearchParams({ code, limit: "1500" });
  if (refresh) qs.set("refresh", "1");
  const json = await api(`/api/stocks/margin-trading?${qs.toString()}`);
  return json.data || {};
}

async function loadMarginChart() {
  if (!code) return;
  marginState.loading = true;
  renderChart();
  try {
    let data = { items: [] };
    for (let attempt = 0; attempt < 3; attempt += 1) {
      data = await fetchMarginPayload({ refresh: attempt > 0 });
      if (Array.isArray(data.items) && data.items.length > 1) break;
      if (attempt < 2) {
        await new Promise((resolve) => {
          window.setTimeout(resolve, 450 * (attempt + 1));
        });
      }
    }
    marginState.source = data.source || "";
    resetMarginViewport(data.items || []);
  } catch {
    resetMarginViewport([]);
    marginState.source = "";
  } finally {
    marginState.loading = false;
    renderChart();
    refreshKlineQuoteCard();
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
      const steps = Math.max(1, Math.min(6, Math.round(Math.abs(evt.deltaY) / 56) || 1));
      const base = evt.deltaY > 0 ? 1.22 : 1 / 1.22;
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
if (els.refreshListBtn) {
  els.refreshListBtn.addEventListener("click", () =>
    loadCompanyList({ refresh: true })
  );
}
if (els.refreshHoldersBtn) {
  els.refreshHoldersBtn.addEventListener("click", () => {
    loadHolders({ refresh: true });
    loadHolderNum({ refresh: true });
    loadFundHolders({ refresh: true });
  });
}
if (els.refreshFinancialsBtn) {
  els.refreshFinancialsBtn.addEventListener("click", () =>
    loadFinancials({ refresh: true })
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
  syncOthersSubTabUi();
  syncJudgmentSubTabUi();
  const tabRaw = (params.get("tab") || "").trim();
  const othersRaw = (params.get("others") || "").trim().toLowerCase();
  let tab = normalizeMainPanel(tabRaw);
  if (!tab && NEWS_FINANCIALS_ALIASES.has(othersRaw)) tab = "news";
  if (tab === "others" && NEWS_FINANCIALS_ALIASES.has(othersRaw)) tab = "news";
  if (tab) switchMainPanel(tab);
  fitChartsToViewport();
}

setupBackLink();
setupExchangeBox();
setupPressBox();
setupPlatformBoxes();
setupCninfoBox();
setupEmotionBox();
setupHoldersBox();
setupFundHoldersBox();
setupFinancialsBox();
setupCompanyListBox();
setupOthersSubTabs();
setupJudgmentSubTabs();
setupNewsFolding();
setupMainTabs();
setupChartsViewport();
setupMetricTips();
bindFundamentalsFold();
setupChart();
setupTicksChart();
setupPeChart();
setupComboMetric();
setupTurnoverChart();
(async () => {
  await loadProfile();
  await loadChart("day");
  window.OrbitPrefetch?.boot("company", { from: fromPage, industry, code });
  await Promise.all([
    loadTicksChart(),
    loadPeChart(),
    loadFundflowChart(),
    loadMarginChart(),
    loadNewsGroup(newsGroup, { refresh: false }),
  ]);
  propagateLinkedAxis("kline");
  if (isQuotesPanel()) refreshChartsLayout();
})();
