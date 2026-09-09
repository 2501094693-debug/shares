# 智能分析（agent）

业务简述、财报简述、行业竞争、风险评估 — HTTP API + LangGraph 智能体。

## 目录结构

```
agent/
├── api.py                  # FastAPI 路由（由 backend/app.py 挂载）
├── service.py              # 各分析类型的任务编排
├── config.py               # LLM / 搜索配置
├── business_explainer/     # 业务简述智能体
├── earnings_reviewer/      # 财报简述
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
python -m agent.explain_earnings 600519
python -m agent.explain_competition 600519
python -m agent.explain_risk 600519
```

或在 `agent/` 目录：

```bash
python explain_business.py 600519
```

环境变量见 `.env.example`，根目录 `.env` 会自动加载。
