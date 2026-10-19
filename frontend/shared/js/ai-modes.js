/** 智能分析模块配置 */
window.AI_MODES = {
  compare: {
    id: "compare",
    kind: "engine",
    label: "对比分析",
    pageTitle: "ORBIT · 智能分析",
    heading: "对比分析",
    subtitle: "个股相对指数的 OHLC 四图偏离度：每图一分 + 加权总分，可设指数与区间",
    startBtn: "重新计算",
    historyHead: "历史报告",
    reportTitle: "对比分析",
    reportMetaDefault: "设置参数后计算",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复对比分析失败",
    apiRoot: "/api/analysis/compare",
    jobStoreKey: "orbit.compare.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">⇄</div>
        <h3>先定指数与区间，再看偏离</h3>
        <p>计算个股相对指数在开/高/低/收四个维度上的平均偏离（逆向加权1.5倍），再按权重合成总分。默认对比上证指数、近一年。</p>
        <ul class="ai-empty-tips">
          <li>总分 &lt;0.5 紧贴，&lt;1.0 轻度偏离，&lt;2.0 明显偏离</li>
          <li>股涨指跌 / 股跌指涨按 1.5 倍加权</li>
          <li>收盘权重最高（0.40）</li>
        </ul>
      </div>`,
    resultTitle(pack) {
      const meta = pack.meta || {};
      return `${meta.stock_name || meta.stock || ""} 对比分析`.trim();
    },
    resultMeta(pack) {
      const meta = pack.meta || {};
      const total = pack.total || {};
      return [
        meta.index_name || meta.index ? `指数 ${meta.index_name || meta.index}` : "",
        total.value != null ? `总分 ${total.value}` : "",
        total.level || "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 对比分析`;
    },
    startQuery(company) {
      return { company };
    },
  },


  chip: {
    id: "chip",
    kind: "engine",
    label: "筹码分析",
    pageTitle: "ORBIT · 智能分析",
    heading: "筹码分析",
    subtitle: "目标日 OHLC 在区间同类价格中的位置：排名 + 百分位，可设区间与目标日",
    startBtn: "重新计算",
    historyHead: "历史报告",
    reportTitle: "筹码分析",
    reportMetaDefault: "设置参数后计算",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复筹码分析失败",
    apiRoot: "/api/analysis/chip",
    jobStoreKey: "orbit.chip.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◈</div>
        <h3>先定区间，再看位置</h3>
        <p>计算目标日开/高/低/收在所选区间同类价格中的排名与百分位（0%=区间最小，100%=区间最大）。默认近一年、目标日为区间末端。</p>
        <ul class="ai-empty-tips">
          <li>百分位越高，目标价越接近区间上沿</li>
          <li>rank 从大到小第几（1=最高），可切 asc 看从小到大</li>
          <li>目标日非交易日自动取前一个交易日</li>
        </ul>
      </div>`,
    resultTitle(pack) {
      return `${pack.symbol || ""} 筹码分析`.trim();
    },
    resultMeta(pack) {
      return [
        pack.target ? `目标日 ${pack.target}` : "",
        pack.N ? `样本 ${pack.N}` : "",
        pack.order ? `排序 ${pack.order}` : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 筹码分析`;
    },
    startQuery(company) {
      return { company };
    },
  },


  business: {
    id: "business",
    label: "业务简述",
    pageTitle: "ORBIT · 智能分析",
    heading: "业务简述",
    subtitle: "主线：交易所 / 巨潮 / 七网 / 公告 PDF 正文 · 联网补充 · 段永平视角",
    startBtn: "生成简述",
    historyHead: "历史报告",
    reportTitle: "业务简述",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复业务简述任务失败",
    apiRoot: "/api/ai/business-brief",
    reportsApi: "/api/ai/reports",
    jobStoreKey: "orbit.brief.activeJob",
    reportNameRe: /业务简述|近一年业务|业务解读/,
    agentDefs: [
      { id: "be_init", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "be_fetch", name: "采集资料", subtitle: "交易所 / 巨潮 / 七网 / PDF正文" },
      { id: "be_search", name: "联网补充", subtitle: "最新财报 / 行业公开信息" },
      { id: "be_explain", name: "生成简述", subtitle: "商业模式 · 护城河 · 段永平视角" },
      { id: "be_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◉</div>
        <h3>先看生意，再听段永平</h3>
        <p>以交易所、巨潮、七网披露为主线，下载年报等公告 PDF 抽取经营正文，联网补充最新公开信息，逐段标注来源，最后用段永平的标准评价这是不是一门好生意。</p>
        <ul class="ai-empty-tips">
          <li>商业模式、收入结构、飞轮</li>
          <li>护城河五项逐一验证</li>
          <li>用户价值与业务协同</li>
          <li>每一段注明来源 · 段永平收尾</li>
        </ul>
      </div>`,
    resultTitle(result) {
      return `${result.stock_name || ""} 业务简述`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 业务简述`;
    },
  },

  bizprofile: {
    id: "bizprofile",
    kind: "engine",
    label: "业务概述",
    pageTitle: "ORBIT · 智能分析",
    heading: "业务概述",
    subtitle: "主营构成三维度（按产品/按行业/按地区）+ 收入结构变化 + 盈利结构 · 确定性规则，不经过大模型",
    startBtn: "重新计算",
    historyHead: "规则结果",
    reportTitle: "业务概述",
    reportMetaDefault: "同花顺 F10 经营分析：主营构成、收入结构迁移、盈利结构与口径提示",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "业务概述计算失败",
    apiRoot: "/api/stocks/biz-profile",
    jobStoreKey: "orbit.bizprofile.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◫</div>
        <h3>这家公司的生意由哪几块构成</h3>
        <p>取同花顺 F10「经营分析」的主营构成，按产品 / 按行业 / 按地区三个维度分别列示，并给出收入结构迁移、盈利结构与口径提示。</p>
        <ul class="ai-empty-tips">
          <li>三个维度一次请求取全，不重复抓取</li>
          <li>整体毛利率由分部毛利 ÷ 分部收入派生，不直接采信源字段</li>
          <li>维度期数与最新期不同，横向比较前请留意尾注提示</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const name = result.name || result.code || "";
      return `${name} 业务概述`.trim();
    },
    resultMeta(result) {
      const dims = result.dim_latest || {};
      const latest = dims[result.primary] || "";
      return [
        result.source_label || "",
        latest ? `报告期 ${latest}` : "",
        result.guardrails?.length ? `口径提示 ${result.guardrails.length} 条` : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 业务概述`;
    },
  },

  peers: {
    id: "peers",
    kind: "engine",
    label: "竞争分析",
    pageTitle: "ORBIT · 智能分析",
    heading: "竞争分析",
    subtitle: "同申万三级行业横截面对比：八看逐项算分、行业名次与中位数基准 · 不经过大模型",
    startBtn: "重新计算",
    historyHead: "规则结果",
    reportTitle: "竞争分析",
    reportMetaDefault: "选取目标公司所在申万三级行业，与同行按同一报告口径横截面对比八看指标",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "竞争分析计算失败",
    apiRoot: "/api/stocks/industry-compare",
    jobStoreKey: "orbit.peers.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">⊞</div>
        <h3>先圈行业，再排座次</h3>
        <p>把目标公司放进它所属的申万三级行业，与全部（或市值靠前的）可比公司按同一报告期口径，逐项计算张新民「八看」指标，给出行业内名次与中位数基准。</p>
        <ul class="ai-empty-tips">
          <li>报告口径：年报 / 半年报 / 一季报 / 三季报（同口径对齐）</li>
          <li>八看指标：战略 · 竞争力 · 效益 · 价值 · 成本 · 质量 · 风险 · 前景</li>
          <li>方向性指标排名，中性指标只展示偏离</li>
          <li>自动剔除 ST / 退市 / 无同期数据样本</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const name = result.target?.name || result.target?.code || "";
      return `${name} 竞争分析`.trim();
    },
    resultMeta(result) {
      const used = result.universe?.used;
      return [
        result.industry?.l3_name || result.industry?.l3_code || "",
        result.latest_period || result.report_type_label || "",
        Number.isFinite(Number(used)) ? `可比 ${used} 家` : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 竞争分析`;
    },
  },

  risk: {
    id: "risk",
    label: "风险评估",
    pageTitle: "ORBIT · 智能分析",
    heading: "风险与管理层评估",
    subtitle: "主线：交易所 / 巨潮 / 七网 / 公告 PDF · 联网补充监管动态与管理层言论",
    startBtn: "生成评估",
    historyHead: "历史报告",
    reportTitle: "风险与管理层评估",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复风险评估任务失败",
    apiRoot: "/api/ai/risk-review",
    jobStoreKey: "orbit.risk.activeJob",
    reportNameRe: /风险与管理层评估/,
    agentDefs: [
      { id: "rr_init", name: "解析公司", subtitle: "识别代码、名称与行业" },
      { id: "rr_fetch", name: "采集资料", subtitle: "交易所 / 巨潮 / 七网 / 公告 PDF" },
      { id: "rr_search", name: "联网补充", subtitle: "监管动态与管理层言论" },
      { id: "rr_analyze", name: "生成评估", subtitle: "风险矩阵 · 管理层质量" },
      { id: "rr_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">△</div>
        <h3>先看风险，再看人</h3>
        <p>以交易所、巨潮、七网披露为主线，结合联网搜索的最新监管动态与管理层言论，评估投资风险与管理层质量。</p>
        <ul class="ai-empty-tips">
          <li>管理层：能力圈、诚信度、战略眼光、资本配置</li>
          <li>监管、竞争、业务、宏观各维度风险分级</li>
          <li>治理结构：股权、关联交易、股东回报</li>
          <li>长期确定性：10 年展望与商业模式颠覆风险</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const industry = result.industry_name ? ` · ${result.industry_name}` : "";
      return `${result.stock_name || ""} 风险与管理层评估${industry}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.industry_name ? `行业 ${result.industry_name}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 风险与管理层评估`;
    },
  },


  "zhang-views": {
    id: "zhang-views",
    kind: "engine",
    label: "张新民视角",
    pageTitle: "ORBIT · 智能分析",
    heading: "张新民视角",
    subtitle: "可选年报/半年报/一季报/三季报口径 · 八看逐项计算 + 综合汇总 · 不经过大模型",
    startBtn: "重新计算",
    historyHead: "规则结果",
    reportTitle: "张新民视角",
    reportMetaDefault: "按所选报告口径运行八看规则方法，不调用大模型",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "张新民视角计算失败",
    apiRoot: "/api/stocks/financial-views",
    jobStoreKey: "orbit.zhangViews.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">∑</div>
        <h3>先选口径，再算八看</h3>
        <p>张新民视角按「一看～八看」逐项列出原始数据、计算公式、计算结果与结论，再汇总成综合诊断；可切换年报 / 半年报 / 一季报 / 三季报口径，全程不调用大模型。</p>
        <ul class="ai-empty-tips">
          <li>报告口径：年报 / 半年报 / 一季报 / 三季报（同口径同比）</li>
          <li>一看战略 · 二看竞争力 · 三看效益 · 四看价值</li>
          <li>五看成本 · 六看质量 · 七看风险 · 八看前景</li>
          <li>八看汇总：五维评级 + 综合诊断</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const st = result.strategy_type && result.strategy_type !== "未知" ? ` · ${result.strategy_type}` : "";
      return `${result.name || result.stock_name || ""} 张新民视角${st}`.trim();
    },
    resultMeta(result) {
      return [
        result.code ? `代码 ${result.code}` : "",
        result.report_type_label || "",
        result.latest_period || "",
        result.coverage || "",
        result.data_available ? "已计算" : "无定期报告",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 张新民视角`;
    },
  },

  sentiment: {
    id: "sentiment",
    label: "情绪分析",
    pageTitle: "ORBIT · 智能分析",
    heading: "发声散户情绪",
    subtitle: "东财股吧 / 同花顺讨论 / 雪球 · 按用户去重 · 看多看空与买卖观望",
    startBtn: "生成分析",
    historyHead: "历史报告",
    reportTitle: "发声散户情绪",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复情绪分析任务失败",
    apiRoot: "/api/ai/retail-sentiment",
    jobStoreKey: "orbit.retailSentiment.activeJob",
    reportNameRe: /发声散户情绪/,
    agentDefs: [
      { id: "rs_init", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "rs_fetch_em", name: "采集东财股吧", subtitle: "帖子 + 千股千评" },
      { id: "rs_fetch_ths", name: "采集同花顺", subtitle: "手机讨论流" },
      { id: "rs_fetch_xq", name: "采集雪球", subtitle: "讨论帖" },
      { id: "rs_merge", name: "合并语料", subtitle: "三源统一字段" },
      { id: "rs_filter", name: "识别散户", subtitle: "剔除官号 / 研报 / KOL" },
      { id: "rs_classify", name: "标注立场", subtitle: "规则词典 + 模型补判" },
      { id: "rs_agg", name: "按用户计数", subtitle: "一人一票" },
      { id: "rs_synth", name: "生成解读", subtitle: "样本情绪，不是成交" },
      { id: "rs_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◎</div>
        <h3>先看谁在说话</h3>
        <p>采集东方财富股吧、同花顺讨论、雪球近三日评论，过滤媒体与认证号后按用户去重，估计发声散户的看多/看空与买入/卖出/观望。这是评论样本，不是真实持仓。</p>
        <ul class="ai-empty-tips">
          <li>散户人数 = 去重用户，不是帖子条数</li>
          <li>买入/卖出是文本意图</li>
          <li>三源分列，跨平台不对齐真人</li>
          <li>对照千股千评，不当真相</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const n = result.metrics?.n_retail_users;
      const tail = Number.isFinite(Number(n)) ? ` · ${n} 人发声` : "";
      return `${result.stock_name || ""} 发声散户情绪${tail}`.trim();
    },
    resultMeta(result) {
      const m = result.metrics || {};
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        Number.isFinite(Number(m.n_retail_users)) ? `散户 ${m.n_retail_users}` : "",
        Number.isFinite(Number(m.buy_users)) ? `买 ${m.buy_users} / 卖 ${m.sell_users} / 观望 ${m.wait_users}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 发声散户情绪`;
    },
    startQuery(company) {
      return {
        company,
        days: "3",
        max_pages: "3",
        replies: "1",
      };
    },
  },

  valuation: {
    id: "valuation",
    label: "估值分析",
    pageTitle: "ORBIT · 智能分析",
    heading: "估值分析",
    subtitle: "四路 × 三情景：历史倍数 / 财报正常化 / 巴菲特 / 收入因素；数字由规则引擎先算",
    startBtn: "生成分析",
    historyHead: "历史报告",
    reportTitle: "估值分析",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复估值分析任务失败",
    apiRoot: "/api/ai/valuation-analysis",
    jobStoreKey: "orbit.valuationAnalysis.activeJob",
    reportNameRe: /估值分析/,
    agentDefs: [
      { id: "va_init", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "va_fetch", name: "采集估值数据", subtitle: "盘口 · 近十年倍数 · 财报" },
      { id: "va_history", name: "历史倍数", subtitle: "近10年 P25 / P50 / P75" },
      { id: "va_fundamentals", name: "财报正常化", subtitle: "扣非中位数 × 退出倍数" },
      { id: "va_buffett", name: "巴菲特路径", subtitle: "所有者盈余资本化" },
      { id: "va_drivers", name: "收入关键因素", subtitle: "营收冲击 × 利润率分位" },
      { id: "va_synth", name: "交叉对照", subtitle: "综合锚 + 安全边际下限" },
      { id: "va_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">∑</div>
        <h3>先算四路，再解释假设</h3>
        <p>对一只股票给出历史倍数、财报正常化、巴菲特、收入关键因素四组悲观/中性/乐观隐含市值与股价。数字全部由规则引擎计算，模型只说明假设。综合锚贴近近10年定价带，巴菲特中性只作安全边际下限。</p>
        <ul class="ai-empty-tips">
          <li>历史窗口近 10 年 P25 / P50 / P75，不用极值</li>
          <li>亏损或金融股自动换主口径</li>
          <li>综合态度不是买卖点</li>
          <li>看不懂时不得「值得进一步研究」</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const stance = result.stance ? ` · ${result.stance}` : "";
      return `${result.stock_name || ""} 估值分析${stance}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.business_type || "",
        result.primary ? `主倍数 ${result.primary}` : "",
        result.stance ? `态度 ${result.stance}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 估值分析`;
    },
    startQuery(company) {
      return { company };
    },
  },

};

window.AI_MODE_ORDER = ["business", "bizprofile", "zhang-views", "peers", "risk", "valuation", "sentiment", "chip", "compare"];

window.AI_MODE_ALIASES = {
  business: "business",
  brief: "business",
  ai: "business",
  bizprofile: "bizprofile",
  "biz-profile": "bizprofile",
  "业务概述": "bizprofile",
  "主营构成": "bizprofile",
  earnings: "zhang-views",
  "财报简述": "zhang-views",
  peers: "peers",
  "竞争分析": "peers",
  "同业对比": "peers",
  "industry-compare": "peers",
  risk: "risk",
  "张新民视角": "zhang-views",
  "zhang-views": "zhang-views",
  sentiment: "sentiment",
  retail: "sentiment",
  "retail-sentiment": "sentiment",
  "情绪分析": "sentiment",
  "散户情绪": "sentiment",
  valuation: "valuation",
  "valuation-analysis": "valuation",
  "估值分析": "valuation",
  "估值": "valuation",
  chip: "chip",
  "筹码分析": "chip",
  "筹码": "chip",
  compare: "compare",
  "对比分析": "compare",
  "对比": "compare",
};
