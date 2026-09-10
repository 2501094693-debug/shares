/** 智能分析模块 — 四种模式配置 */
window.AI_MODES = {
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

  earnings: {
    id: "earnings",
    label: "财报简述",
    pageTitle: "ORBIT · 智能分析",
    heading: "财报简述",
    subtitle: "近一年定期报告 · 每段附原始数据 · 巴菲特视角评估安全边际",
    startBtn: "生成简述",
    historyHead: "历史报告",
    reportTitle: "财报简述",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复财报简述任务失败",
    apiRoot: "/api/ai/earnings-brief",
    jobStoreKey: "orbit.earnings.activeJob",
    reportNameRe: /财报解读|财报简述/,
    agentDefs: [
      { id: "er_init", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "er_fetch", name: "采集财报", subtitle: "东财F10报表 / 估值 / 巨潮" },
      { id: "er_explain", name: "生成简述", subtitle: "每段附原始数据 · 巴菲特视角" },
      { id: "er_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">▤</div>
        <h3>先看数字，再谈判断</h3>
        <p>拉取近一年年报/半年报/季报原始科目，每段解释都附带财报数据，最后从巴菲特视角评估安全边际。</p>
        <ul class="ai-empty-tips">
          <li>近3-5年营收、净利润、经营利润</li>
          <li>ROE / ROA / 毛利率 / 经营利润率</li>
          <li>经营现金流、自由现金流、资本开支</li>
          <li>资产负债、估值与内在价值</li>
        </ul>
      </div>`,
    resultTitle(result) {
      return `${result.stock_name || ""} 财报简述`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 财报简述`;
    },
  },

  competition: {
    id: "competition",
    label: "行业竞争",
    pageTitle: "ORBIT · 智能分析",
    heading: "行业竞争分析",
    subtitle: "主线：交易所 / 巨潮 / 七网 / 公告 PDF · 联网补充最新行业数据 · 同业对照",
    startBtn: "生成分析",
    historyHead: "历史报告",
    reportTitle: "行业竞争分析",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复行业竞争分析任务失败",
    apiRoot: "/api/ai/competition-analysis",
    jobStoreKey: "orbit.competition.activeJob",
    reportNameRe: /行业竞争分析/,
    agentDefs: [
      { id: "ic_init", name: "解析公司", subtitle: "识别代码、名称与行业" },
      { id: "ic_fetch", name: "采集资料", subtitle: "交易所 / 巨潮 / 七网 / 同业" },
      { id: "ic_search", name: "联网补充", subtitle: "最新行业数据与竞争动态" },
      { id: "ic_analyze", name: "生成分析", subtitle: "行业格局 · 竞争态势" },
      { id: "ic_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">⬡</div>
        <h3>先看格局，再判位置</h3>
        <p>以交易所、巨潮、七网披露为主线，结合申万同业对照与联网搜索的最新行业数据，分析行业格局与该公司竞争态势。</p>
        <ul class="ai-empty-tips">
          <li>行业规模、增速、渗透率</li>
          <li>竞争格局与主要对手威胁评估</li>
          <li>细分赛道格局与产业链分析</li>
          <li>技术变革、政策影响、新进入者</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const industry = result.industry_name ? ` · ${result.industry_name}` : "";
      return `${result.stock_name || ""} 行业竞争分析${industry}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.industry_name ? `行业 ${result.industry_name}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 行业竞争分析`;
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
};

window.AI_MODE_ORDER = ["business", "earnings", "competition", "risk"];

window.AI_MODE_ALIASES = {
  business: "business",
  brief: "business",
  ai: "business",
  earnings: "earnings",
  competition: "competition",
  risk: "risk",
};
