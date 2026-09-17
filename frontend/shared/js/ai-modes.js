/** 智能分析模块配置 */
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

  essence: {
    id: "essence",
    label: "生意本质",
    pageTitle: "ORBIT · 智能分析",
    heading: "生意本质",
    subtitle: "官方公告认主营 → 讲清业务并举例 → 关键因素为什么关键 · 每章起草后由质疑官反复确认",
    startBtn: "开始确认",
    historyHead: "历史报告",
    reportTitle: "生意本质",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复生意本质任务失败",
    apiRoot: "/api/ai/essence-analysis",
    jobStoreKey: "orbit.essence.activeJob",
    reportNameRe: /生意本质/,
    agentDefs: [
      { id: "es_resolve", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "es_official", name: "官方公告", subtitle: "交易所 / 巨潮 / 七网 / PDF" },
      { id: "es_businesses", name: "主营确认", subtitle: "起草 → 质疑 → 重写" },
      { id: "es_web", name: "联网补充", subtitle: "机制与例子" },
      { id: "es_explain", name: "讲清业务", subtitle: "起草 → 质疑 → 重写" },
      { id: "es_factors", name: "关键因素", subtitle: "起草 → 质疑 → 重写" },
      { id: "es_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◎</div>
        <h3>先搞清这家公司做什么</h3>
        <p>主营业务只认交易所、巨潮、七网官方公告。列出官方承认的业务后，用白话解释并举例，再找出真正能改变这门生意的关键因素。每一章由起草官写成稿，质疑官独立复核；不通过就退回重写，缺证据就补检索。</p>
        <ul class="ai-empty-tips">
          <li>官方清单 → 人话解释 + 例子 → 关键因素为什么关键</li>
          <li>不拉财报数字，不做巴菲特视角解读</li>
          <li>每章最多三轮质疑，轮次用尽按最后一稿收录并标注</li>
          <li>判断生意，不写买卖建议</li>
        </ul>
      </div>`,
    resultTitle(result) {
      return `${result.stock_name || ""} 生意本质`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 生意本质`;
    },
  },

  duan: {
    id: "duan",
    label: "段永平看业务",
    pageTitle: "ORBIT · 智能分析",
    heading: "段永平看业务",
    subtitle: "先看生意模式，刮到谢字就停 · 企业文化 · 好价钱 · 必要条件过滤",
    startBtn: "开始看业务",
    historyHead: "历史报告",
    reportTitle: "段永平看业务",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复段永平看业务任务失败",
    apiRoot: "/api/ai/duan-analysis",
    jobStoreKey: "orbit.duan.activeJob",
    reportNameRe: /段永平看业务/,
    agentDefs: [
      { id: "dy_init", name: "解析公司", subtitle: "识别代码与名称" },
      { id: "dy_fetch", name: "采集数据", subtitle: "年报数字 + 用户口碑补充" },
      { id: "dy_business", name: "一、生意模式", subtitle: "差异化 · 毛利率 · 净现金" },
      { id: "dy_culture", name: "二、企业文化", subtitle: "本分 · 用户导向 · 可跳过" },
      { id: "dy_price", name: "三、好价钱", subtitle: "毛估估 · 前两关不过则跳过" },
      { id: "dy_synthesis", name: "四、能不能看懂", subtitle: "离开 / 等待 / 毛估估" },
      { id: "dy_assemble", name: "拼装报告", subtitle: "整合各章节" },
      { id: "dy_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◎</div>
        <h3>先刮彩票，谢字就停</h3>
        <p>按段永平的流程看生意：生意模式、企业文化是必要条件，不是加权打分。模式不行或看不懂，企业文化与价钱直接跳过。</p>
        <ul class="ai-empty-tips">
          <li>差异化 = 用户需要而别人给不了</li>
          <li>把自己当消费者：5% 折扣换不换</li>
          <li>长期毛利率 · 净现金流 · 杠杆只是旁证</li>
          <li>不给买卖建议，看不懂就是终点</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const att = result.final_attitude ? ` · ${result.final_attitude}` : "";
      return `${result.stock_name || ""} 段永平看业务${att}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.numeric_hint || "",
        result.final_attitude || "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 段永平看业务`;
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

  comprehensive: {
    id: "comprehensive",
    label: "综合研判",
    pageTitle: "ORBIT · 智能分析",
    heading: "综合深度研判",
    subtitle: "年报/半年报/季报 · 三表独立分析 · 三情景估值 · 市场前景",
    startBtn: "生成报告",
    historyHead: "历史报告",
    reportTitle: "综合深度分析",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复综合研判任务失败",
    apiRoot: "/api/ai/comprehensive-analysis",
    jobStoreKey: "orbit.comprehensive.activeJob",
    reportNameRe: /综合深度分析|综合研判/,
    agentDefs: [
      { id: "ca_init", name: "解析公司", subtitle: "识别代码与行业" },
      { id: "ca_fetch", name: "采集数据", subtitle: "财报 / 估值 / 公告 PDF" },
      { id: "ca_business", name: "业务分析", subtitle: "构成 · 关键驱动因素" },
      { id: "ca_balance", name: "资产负债表", subtitle: "资产质量 · 偿债能力" },
      { id: "ca_income", name: "利润表", subtitle: "盈利质量 · 费用结构" },
      { id: "ca_cashflow", name: "现金流量表", subtitle: "FCF · 现金流类型" },
      { id: "ca_synthesis", name: "三表汇总", subtitle: "交叉验证 · 财务画像" },
      { id: "ca_valuation", name: "估值分析", subtitle: "乐观/中性/悲观三情景" },
      { id: "ca_search", name: "市场信息", subtitle: "新闻 / 研报 / 政策" },
      { id: "ca_outlook", name: "前景研判", subtitle: "短中长期展望" },
      { id: "ca_assemble", name: "拼装报告", subtitle: "整合各章节" },
      { id: "ca_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◎</div>
        <h3>全链路深度研判</h3>
        <p>从定期报告与三大报表出发，独立分析资产负债、利润与现金流，结合历史 PE/PB/PS 做三情景估值，并联网补充市场信息研判未来前景。</p>
        <ul class="ai-empty-tips">
          <li>近5年年报 + 近4季季报</li>
          <li>三表独立分析 → 汇总交叉验证</li>
          <li>乐观 / 中性 / 悲观估值情景</li>
          <li>关键驱动因素 × 市场信号 → 前景</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const industry = result.industry_name ? ` · ${result.industry_name}` : "";
      return `${result.stock_name || ""} 综合深度分析${industry}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.industry_name ? `行业 ${result.industry_name}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 综合深度研判`;
    },
  },

  bazhang: {
    id: "bazhang",
    label: "八看解读",
    pageTitle: "ORBIT · 智能分析",
    heading: "张新民「八看」财报解读",
    subtitle: "战略 · 经营资产 · 核心利润 · 财务状况质量 · 规则引擎预计算",
    startBtn: "生成报告",
    historyHead: "历史报告",
    reportTitle: "八看财报解读",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复八看解读任务失败",
    apiRoot: "/api/ai/bazhang-analysis",
    jobStoreKey: "orbit.bazhang.activeJob",
    reportNameRe: /八看财报解读|八看解读/,
    agentDefs: [
      { id: "bz_init", name: "解析公司", subtitle: "识别代码与行业" },
      { id: "bz_fetch", name: "采集数据", subtitle: "财报 + 规则引擎预计算" },
      { id: "bz_strategy", name: "一看：战略", subtitle: "资产配置 · 战略类型" },
      { id: "bz_operating", name: "二看：经营资产", subtitle: "两头吃 · 周转效率" },
      { id: "bz_profit", name: "三看：效益质量", subtitle: "核心利润 · 利润成色" },
      { id: "bz_value", name: "四看：价值", subtitle: "ROE · ROIC · 价值创造" },
      { id: "bz_cost", name: "五看：成本", subtitle: "费用结构 · 成本机制" },
      { id: "bz_quality", name: "六看：财务状况", subtitle: "资产质量 · 负债结构" },
      { id: "bz_risk", name: "七看：风险", subtitle: "三脱节 · 偿债 · 商誉" },
      { id: "bz_outlook", name: "八看：前景", subtitle: "扩张/收缩 · 可持续性" },
      { id: "bz_synthesis", name: "综合诊断", subtitle: "战略-质量-现金流自洽性" },
      { id: "bz_assemble", name: "拼装报告", subtitle: "整合各章节" },
      { id: "bz_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">◈</div>
        <h3>从报表看企业</h3>
        <p>基于张新民「八看」框架，Python 规则引擎预计算资产分类、核心利润、两头吃指数与三脱节检测，LLM 逐章解读财务状况质量。</p>
        <ul class="ai-empty-tips">
          <li>年报、半年报、季报全量定期报告</li>
          <li>经营性 vs 投资性资产分类</li>
          <li>核心利润 + 经营现金流验证</li>
          <li>两头吃竞争力 · 三脱节风险</li>
          <li>八看逐章 + 综合诊断</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const st = result.strategy_type ? ` · ${result.strategy_type}` : "";
      return `${result.stock_name || ""} 八看财报解读${st}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.strategy_type ? `战略 ${result.strategy_type}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 八看财报解读`;
    },
  },

  buffett: {
    id: "buffett",
    label: "巴菲特读表",
    pageTitle: "ORBIT · 智能分析",
    heading: "巴菲特读表",
    subtitle: "所有者盈余 · 有形回报 · 资本配置 · 规则引擎预计算",
    startBtn: "生成报告",
    historyHead: "历史报告",
    reportTitle: "巴菲特读表",
    reportMetaDefault: "选择历史报告或生成新的",
    historyMeta: "历史报告",
    emptyReports: "暂无历史报告",
    resumeFail: "恢复巴菲特读表任务失败",
    apiRoot: "/api/ai/buffett-analysis",
    jobStoreKey: "orbit.buffett.activeJob",
    reportNameRe: /巴菲特读表/,
    agentDefs: [
      { id: "bf_init", name: "解析公司", subtitle: "识别代码与行业" },
      { id: "bf_fetch", name: "采集数据", subtitle: "财报 + 所有者盈余预计算" },
      { id: "bf_understand", name: "一、生意能否看懂", subtitle: "能力圈 · 怎么赚钱" },
      { id: "bf_owner", name: "二、所有者盈余", subtitle: "上沿 / 下沿 / 现金核对" },
      { id: "bf_capital", name: "三、资本饥饿", subtitle: "有形回报 · 四种生意" },
      { id: "bf_honesty", name: "四、会计与配置", subtitle: "商誉 · 留存 · 发股" },
      { id: "bf_synthesis", name: "五、综合判决", subtitle: "六问 · 安全边际" },
      { id: "bf_assemble", name: "拼装报告", subtitle: "整合各章节" },
      { id: "bf_save", name: "保存报告", subtitle: "写入 Markdown" },
    ],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">▣</div>
        <h3>先算能取出的现金</h3>
        <p>按巴菲特 1986 年所有者盈余公式，Python 先给出上沿（折旧）与下沿（资本开支）区间，再逐章解读生意能否看懂、资本饥饿、会计诚实与资本配置。</p>
        <ul class="ai-empty-tips">
          <li>所有者盈余区间，不把 (c) 装成精确值</li>
          <li>有形 ROE · capex/D&amp;A · 四种生意分类</li>
          <li>留存 1 美元测试的可计算近似</li>
          <li>综合判决引用已有估值，不做独立三情景模型</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const bt = result.business_type ? ` · ${result.business_type}` : "";
      return `${result.stock_name || ""} 巴菲特读表${bt}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.business_type ? `类型 ${result.business_type}` : "",
        result.report_path ? "已保存" : "",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 巴菲特读表`;
    },
  },

  "buffett-rules": {
    id: "buffett-rules",
    kind: "engine",
    label: "巴菲特规则引擎",
    pageTitle: "ORBIT · 智能分析",
    heading: "巴菲特规则引擎",
    subtitle: "强制刷新东财最新全量定期报告 · 所有者盈余区间 · 不经过大模型",
    startBtn: "重新计算",
    historyHead: "规则结果",
    reportTitle: "巴菲特规则引擎",
    reportMetaDefault: "强制刷新最新全量定期报告后按固定公式计算，不调用大模型",
    historyMeta: "规则结果",
    emptyReports: "暂无结果",
    resumeFail: "巴菲特规则引擎计算失败",
    apiRoot: "/api/ai/buffett-rules",
    jobStoreKey: "orbit.buffettRules.pack",
    reportNameRe: /$^/,
    agentDefs: [],
    emptyStateHtml: `
      <div class="ai-empty-state">
        <div class="ai-empty-icon" aria-hidden="true">∑</div>
        <h3>先算，再解释</h3>
        <p>巴菲特规则引擎强制刷新东方财富 F10：利润表、资产负债表、现金流量表、主要指标、业绩报表，覆盖最新一期及历史定期报告，再按巴菲特公式给出上沿/下沿、有形 ROE 和生意类型。</p>
        <ul class="ai-empty-tips">
          <li>强制刷新，不吃一小时缓存</li>
          <li>有形 ROE · capex/D&amp;A · 四种生意</li>
          <li>留存 1 美元测试的可计算近似</li>
          <li>折旧附注缺失时下沿标「未披露」</li>
        </ul>
      </div>`,
    resultTitle(result) {
      const bt = result.business_type ? ` · ${result.business_type}` : "";
      return `${result.stock_name || ""} 巴菲特规则引擎${bt}`.trim();
    },
    resultMeta(result) {
      return [
        result.stock_code ? `代码 ${result.stock_code}` : "",
        result.latest_period || "",
        result.period_kind || "",
        result.coverage || "",
        result.data_available ? "已计算" : "无定期报告",
      ].filter(Boolean).join(" · ");
    },
    runningTitle(company) {
      return `${company} · 巴菲特规则引擎`;
    },
  },
};

window.AI_MODE_ORDER = ["comprehensive", "business", "essence", "duan", "bazhang", "buffett", "buffett-rules", "competition", "risk"];

window.AI_MODE_ALIASES = {
  business: "business",
  brief: "business",
  ai: "business",
  essence: "essence",
  "生意本质": "essence",
  "主营业务": "essence",
  duan: "duan",
  dyp: "duan",
  "段永平": "duan",
  "段永平看业务": "duan",
  "大道": "duan",
  earnings: "bazhang",
  "财报简述": "bazhang",
  competition: "competition",
  risk: "risk",
  comprehensive: "comprehensive",
  deep: "comprehensive",
  bazhang: "bazhang",
  zhang: "bazhang",
  "八看": "bazhang",
  "张新民": "bazhang",
  "张新明": "bazhang",
  buffett: "buffett",
  owner: "buffett",
  "巴菲特": "buffett",
  "巴菲特读表": "buffett",
  "巴菲特视角": "buffett",
  "buffett-rules": "buffett-rules",
  rules: "buffett-rules",
  engine: "buffett-rules",
  "规则引擎": "buffett-rules",
  "巴菲特规则引擎": "buffett-rules",
};
