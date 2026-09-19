# 智能分析（agent）

业务简述、八看财报解读、巴菲特读表、行业竞争、产业链、风险评估 — HTTP API + LangGraph 智能体。

## 目录结构

```
agent/
├── api.py                  # FastAPI 路由（由 backend/app.py 挂载）
├── service.py              # 各分析类型的任务编排
├── config.py               # LLM / 搜索配置
├── business_explainer/     # 业务简述智能体
├── bazhang_analyst/        # 张新民八看财报解读
├── buffett_analyst/        # 巴菲特读表
├── industry_competition/   # 行业竞争
├── chain_analyst/          # 产业链分析
├── risk_reviewer/          # 风险评估
├── rules/                  # 规则引擎公共工具
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
python -m agent.buffett_analyst 600519
python -m agent.bazhang_analyst 600519
python -m agent.explain_competition 600519
python -m agent.chain_analyst 000338
python -m agent.explain_risk 600519
```

或在 `agent/` 目录：

```bash
python explain_business.py 600519
python explain_chain.py 000338
```

环境变量见 `.env.example`，根目录 `.env` 会自动加载。
