# 业务解读智能体（复原版）

本目录用于**复原**当时生成 `agent/reports/四创电子业务解读_20260908.md` 的智能体。

## 复原依据

| 项 | 结论 |
|----|------|
| 隶属 | `business_explainer`（业务解读 / 业务简述智能体）家族 |
| 首次入库 | 提交 `7b1dd54 "增加ai模块"`（2026-09-08，与报告数据截止日同日），当时路径 `ai/reports/四创电子业务解读_20260908.md` |
| 编排 | LangGraph：`init → fetch → explain → save` |
| 冻结版 | 提交 `7b1dd54` 的 `ai/business_explainer/*` |

**关键说明**：报告结构（7 段：一句话看懂 / 公司做什么 / 钱从哪来 / 最近一年变化 / 行业位置与竞争优势 / 投资者常问 / 参考资料索引）
与 `7b1dd54` 入库的 prompt（4 段、标题“业务简述”）**不一致**，且报告引用了“公司画像 / 盘口 / F10”数据。
全历史检索 `资料窗口`、`一句话看懂`、`投资者常问`、`业务解读` 等字符串，均**只命中报告文件本身**，
说明生成它的 prompt **未入库**。因此：

- 代码骨架、节点、状态、数据采集：**冻结版**（忠实还原）；
- `nodes.py` 的头部文案与落盘文件名、`prompts.py` 的 prompt：**依据报告反推复原**；
- `data_fetcher.py` 在冻结版基础上，补回了当时报告用到的「公司画像与盘口」「估值序列（F10）」采集。

同批次的 `四创电子业务简述_20260908.md` 才是 `7b1dd54` 版 prompt 的精确对应输出，可作为交叉验证锚点。

## 目录结构

```
business_explainer_recon/
├── __init__.py
├── __main__.py          # CLI: python -m agent.business_explainer_recon 600990
├── explain_business.py  # 等价 CLI（对齐冻结版入口）
├── config.py            # 复原自 ai/config.py（落盘目录改为本目录 reports/）
├── state.py             # 冻结版状态
├── graph.py             # init → fetch → explain → save
├── nodes.py             # 冻结版节点 + 复原的头部/文件名
├── prompts.py           # 复原的「公司业务解读」prompt
├── data_fetcher.py      # 冻结版 + 公司画像/盘口 + F10 估值序列
├── tools/progress.py    # 冻结版进度上报
├── utils/llm.py         # 冻结版 LLM 初始化
├── requirements.txt
└── .env.example
```

## 运行

```bash
# 在仓库根目录
pip install -r agent/business_explainer_recon/requirements.txt

# 配置 .env（复制 .env.example 到仓库根或本目录并填写 OPENAI_API_KEY）
python -m agent.business_explainer_recon 600990 --stream
```

输出落盘到 `business_explainer_recon/reports/{名称}业务解读_{YYYYMMDD}.md`，避免覆盖现有 `agent/reports`。
