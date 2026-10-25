/** 智能分析模块配置 */
window.AI_MODES = {
  business: {
    id: "business",
    label: "业务简述",
    pageTitle: "ORBIT · 智能分析",
    heading: "业务简述 · AI视角",
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
      return `${company} · 业务简述（AI视角）`;
    },
  },

  bizprofile: {
    id: "bizprofile",
    kind: "engine",
    label: "规则视角",
    pageTitle: "ORBIT · 智能分析",
    heading: "业务简述 · 规则视角",
    subtitle: "主营构成三维度（按产品/按行业/按地区）+ 收入结构变化 + 盈利结构 · 确定性规则，不经过大模型",
    startBtn: "重新计算",
    historyHead: "规则结果",
    reportTitle: "业务简述 · 规则视角",
    reportMetaDefault: "同花顺 F10 经营分析：主营构成、收入结构迁移与盈利结构",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "业务简述（规则视角）计算失败",
    apiRoot: "/api/stocks/biz-profile",
    jobStoreKey: "orbit.bizprofile.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◫</div>
        <h3>这家公司的生意由哪几块构成</h3>
        <p>取同花顺 F10「经营分析」的主营构成，按产品 / 按行业 / 按地区三个维度分别列示，并给出收入结构迁移与盈利结构。</p>
        <ul class="ai-empty-tips">
          <li>三个维度一次请求取全，不重复抓取</li>
          <li>整体毛利率由分部毛利 ÷ 分部收入派生，不直接采信源字段</li>
          <li>维度期数与最新期不同，横向比较前请留意各维度的报告期</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const name = result.name || result.code || "";
      return `${name} 业务简述 · 规则视角`.trim();
    },
    resultMeta(result) {
      const dims = result.dim_latest || {};
      const latest = dims[result.primary] || "";
      return [
        "规则视角",
        result.source_label || "",
        latest ? `报告期 ${latest}` : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 业务简述（规则视角）`;
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
    kind: "engine",
    label: "风险评估",
    pageTitle: "ORBIT · 智能分析",
    heading: "风险评估",
    subtitle: "巨潮非定期公告七维排查：检索方式表 + 按子查询分组的检索结果 · 不经过大模型",
    startBtn: "重新扫描",
    historyHead: "规则结果",
    reportTitle: "风险评估",
    reportMetaDefault: "按七维从巨潮检索；结果按 Q1/Q2/… 分组展示",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "风险评估扫描失败",
    apiRoot: "/api/stocks/risk-assessment",
    jobStoreKey: "orbit.risk.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">⚠</div>
        <h3>按七维扫巨潮公告</h3>
        <p>每个维度用统一公式描述检索：Qi := 源 ∧ 语料 ∧ 通道 ∧ 分类 ∧ 标题关键词 ∧ 窗口。前端按维阅读：检索方式 → 按子查询分组的检索结果。</p>
        <ul class="ai-empty-tips">
          <li>监管与合规 · 治理与内控 · 股本与控制权</li>
          <li>资本运作与债务 · 披露质量 · 存续性 · 经营与沟通</li>
          <li>同一维度内按 Q1 / Q2 / … 分组列出命中公告</li>
          <li>数据源：巨潮资讯（非定期公告）</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const name = result.name || result.code || "";
      return `${name} 风险评估`.trim();
    },
    resultMeta(result) {
      const s = result.summary || {};
      const source = String(result.source_label || result.source || "")
        .replace(/\s*·\s*仅用\s*fetch_announcements/gi, "")
        .trim();
      return [
        source,
        Number.isFinite(Number(s.hit_dimensions))
          ? `命中维 ${s.hit_dimensions}/${s.dimension_count || 7}`
          : "",
        Number.isFinite(Number(s.total_items)) ? `去重 ${s.total_items}` : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 风险评估`;
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

};

window.AI_MODE_ORDER = ["business", "bizprofile", "zhang-views", "peers", "risk", "sentiment"];

window.AI_MODE_ALIASES = {
  business: "business",
  brief: "business",
  ai: "business",
  "ai视角": "business",
  "业务简述": "business",
  "智能视角": "business",
  bizprofile: "bizprofile",
  "biz-profile": "bizprofile",
  "业务概述": "bizprofile",
  "规则视角": "bizprofile",
  "规则": "bizprofile",
  "主营构成": "bizprofile",
  earnings: "zhang-views",
  "财报简述": "zhang-views",
  peers: "peers",
  "竞争分析": "peers",
  "同业对比": "peers",
  "industry-compare": "peers",
  risk: "risk",
  "risk-assessment": "risk",
  "风险评估": "risk",
  "风险排查": "risk",
  "风险": "risk",
  "张新民视角": "zhang-views",
  "zhang-views": "zhang-views",
  sentiment: "sentiment",
  retail: "sentiment",
  "retail-sentiment": "sentiment",
  "情绪分析": "sentiment",
  "散户情绪": "sentiment",
};
