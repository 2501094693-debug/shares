# 智能分析（agent）

业务简述、生意本质、段永平看业务、八看财报解读、巴菲特读表、行业竞争、风险评估 — HTTP API + LangGraph 智能体。

## 目录结构

```
agent/
├── api.py                  # FastAPI 路由（由 backend/app.py 挂载）
├── service.py              # 各分析类型的任务编排
├── config.py               # LLM / 搜索配置
├── business_explainer/     # 业务简述智能体
├── essence_analyst/        # 生意本质（官方主营 → 解释举例 → 关键因素）
├── duan_analyst/           # 段永平看业务（过滤器可中途离开）
├── bazhang_analyst/        # 张新民八看财报解读
├── buffett_analyst/        # 巴菲特读表
├── industry_competition/   # 行业竞争
├── risk_reviewer/          # 风险评估
├── tools/                  # 数据采集、PDF、联网搜索
├── utils/
├── reports/                # 生成的 Markdown 报告
└── explain_*.py            # CLI 入口
```

## 启动 Web 服务

在仓库根目录：

```bash
pip install -r requirements.txt
python backend/app.py
```

前端访问 `/ai` 智能分析页面。

## CLI

在仓库根目录：

```bash
python -m agent.explain_business 600519
python -m agent.essence_analyst 600519
python -m agent.duan_analyst 600519
python -m agent.buffett_analyst 600519
python -m agent.bazhang_analyst 600519
python -m agent.explain_competition 600519
python -m agent.explain_risk 600519
```

或在 `agent/` 目录：

```bash
python explain_business.py 600519
```

## 段永平看业务

过滤器是必要条件，不是加权打分：

1. 生意模式（差异化、长期毛利率、净现金）→ 离开 / 看不懂则停
2. 企业文化（本分、用户导向）→ 不喜欢则停
3. 价钱（毛估估）→ 仅当前两关通过或存疑
4. 综合态度锁定为：离开 / 看不懂 / 等待好价钱 / 可以毛估估

环境变量见 `.env.example`，根目录 `.env` 会自动加载。

## 生意本质

每章都是起草官写稿、质疑官独立复核：不通过就退回重写，缺证据就按质疑官的检索词补一次联网。最多三轮。主营只认交易所/巨潮/七网官方公告；讲清业务并举例后，写出关键影响因素。不拉财报数字，不做巴菲特视角解读。

```bash
python -m agent.essence_analyst 600519
```
