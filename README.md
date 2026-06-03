<div align="center">

# TradingAgents-A-share

多 Agent LLM 交易研究框架 — A 股 + 港股双市场版

作者：huangkwsg@gmail.com

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-2EA043)
![Market](https://img.shields.io/badge/Market-A%20Share%20%2B%20HK-D7263D)
![Data](https://img.shields.io/badge/Data-AkShare%20%7C%20yfinance-0052CC)
![Version](https://img.shields.io/badge/Version-v3.0-0f3460)

</div>

<p align="center">
  <a href="./README.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-red"></a>
  <a href="./README_en.md"><img alt="English" src="https://img.shields.io/badge/Language-English-blue"></a>
  <a href="./SETUP.md"><img alt="Setup" src="https://img.shields.io/badge/AI_Agent_部署指南-green"></a>
</p>

<p align="center">
  <a href="#项目定位">项目定位</a> ·
  <a href="#v30-更新摘要">v3.0 更新</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#使用方式">使用方式</a> ·
  <a href="#分析示例">分析示例</a> ·
  <a href="#项目结构">项目结构</a> ·
  <a href="#开源合规">开源合规</a>
</p>

<p align="center">
  <img src="assets/schema.png" alt="TradingAgents 架构图" width="92%" />
</p>

## 项目定位

基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 的衍生实现，聚焦 **A 股 + 港股** 双市场，**12 个 LLM Agent** 协同完成多空辩论、裁决与投资决策。

适用场景：
- A 股/港股多因子研究流程实验
- LLM Agent 金融协作机制验证
- 教学演示、策略原型开发

## v3.0 更新摘要

| 类别 | 内容 |
|------|------|
| **港股支持** | 新增 `run_hk.py`，yfinance 数据管道，支持全部港股 |
| **A 股自动检测** | 入口处自动识别 A 股代码并切换 akshare |
| **Bug 修复** | 9 项（详见下方） |
| **信号解析** | 中英文双语评级词（买入/卖出/持有 → Buy/Sell/Hold） |
| **模型目录** | DeepSeek V4 Flash 加入已知列表 |
| **结构化输出** | None 检查，优雅 fallback |
| **PDF 报告** | pandoc + LibreOffice 工作流 |

### Bug 修复清单（v3.0）

| # | 问题 | 修复 |
|---|------|------|
| 1 | LLM 传非标 ticker 格式导致崩溃 | `normalize_ashare_symbol` 兜底正则 |
| 2 | yfinance 失败不 fallback | `route_to_vendor` try/except 链式切换 |
| 3 | 中文输出信号误判为 Hold | `parse_rating` 中文评级词支持 |
| 4 | A 股技术指标 yfinance 无数据 | `_get_indicator_data` 改用 akshare |
| 5 | 结构化输出 None 导致崩溃 | `invoke_structured_or_freetext` None 检查 |
| 6 | 报告 key 名不匹配，内容全空 | `run_single.py` key 名修正 |
| 7 | yfinance 完全未注册（函数名不匹配） | `interface.py` 导入修正 |
| 8 | DeepSeek 模型警告 | `model_catalog.py` 补全 |
| 9 | 数据缓存 CSV 入 git | `.gitignore` 排除 |

## 核心特性

- **A 股全链路本地化**：AkShare 覆盖行情、技术指标、研报、快讯、公告、基本面、雪球情绪、财新新闻。yfinance 兜底美股参考。
- **港股 yfinance 管道**：`run_hk.py` 直接走 yfinance，覆盖行情、技术指标、新闻、基本面。
- **多 Agent 决策闭环**：Market → Sentiment → News → Fundamentals（4 分析师）→ Bull ×3 / Bear ×3（多空辩论）→ Research Manager（裁决）→ Trader（执行计划）→ 三人风控 → Portfolio Manager（最终决策）
- **结构化输出**：Research Manager / Trader / Portfolio Manager 使用 Pydantic 约束输出格式
- **断点续跑**：LangGraph SqliteSaver 检查点，崩溃后从中断节点恢复
- **跨轮次记忆**：TradingMemoryLog 追加式决策日志，历史回溯注入上下文
- **多模型提供方**：OpenAI / DeepSeek / Azure / Anthropic / Google / xAI / Qwen / OpenRouter / Ollama
- **A 股自动检测**：入口处 `apply_ashare_config_if_needed()` 自动识别并切换数据源

## 快速开始

### 1) 克隆

```bash
git clone https://github.com/hkwsg/TradingAgents-A-share.git
cd TradingAgents-A-share
```

### 2) 安装依赖

```bash
pip install -r requirements.txt
```

### 3) 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，至少填入 DeepSeek Key：

```ini
DEEPSEEK_API_KEY=sk-your-key-here
```

> 其他 provider 按需配置。支持的所有 provider 及 env var 见 `tradingagents/llm_clients/api_key_env.py`。

### 4) 运行

```bash
# A 股（6 位代码）
python run_single.py 000012              # 南玻A，默认最近交易日
python run_single.py 600519 2026-05-22   # 茅台，指定日期

# 港股（.HK 后缀）
python run_hk.py 1258.HK                 # 中国有色矿业
python run_hk.py 0020.HK 2026-05-22      # 商汤，指定日期
```

## 使用方式

### 命令行

| 命令 | 说明 |
|------|------|
| `python run_single.py <代码> [日期]` | A 股单股分析 |
| `python run_hk.py <代码.HK> [日期]` | 港股单股分析 |
| `python main.py` | 旧版平台入口 |
| `tradingagents` 或 `python -m cli.main` | 交互式 CLI |

### AI Agent 对话式操作

本项目设计为可与 **Claude Code / Cursor / Codex CLI** 等 AI Agent 深度协作。详见 **[SETUP.md](./SETUP.md)**。

配置好 `CLAUDE.md` 后，Agent 可理解自然语言指令：

> "跑一下南玻A和茅台，日期今天"
> "三家半导体都看一下结果"
> "把有色矿业的报告出份 PDF"
> "技术指标为什么是空的"

### Python 调用

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.config import apply_ashare_config_if_needed

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-v4-pro"
config["quick_think_llm"] = "deepseek-v4-flash"
config = apply_ashare_config_if_needed("600519", config)  # 自动检测 A 股

ta = TradingAgentsGraph(debug=True, config=config)
# 流式执行
init_state = ta.propagator.create_initial_state("600519", "2026-05-22")
for chunk in ta.graph.stream(init_state, **ta.propagator.get_graph_args()):
    # 处理每个步骤
    pass
```

## 分析示例

### A 股 — 南玻A（000012）

```
$ python run_single.py 000012 2026-05-22

============================================================
  TradingAgent A股分析启动
  股票: 000012  日期: 2026-05-22  模型: deepseek-v4-flash
============================================================
[1/3] 初始化图结构...
[2/3] 开始分析（流式输出）...
  [0s] 步骤1: Market Analyst 启动
  [25s] 步骤3: A-share price data for 000012.SZ # Records: 133
  ...
  [604s] 步骤41: Portfolio Manager 最终决策
[3/3] 分析完成，耗时 10分4秒
最终决策信号: Underweight
报告已保存: C:\Users\xxx\Desktop\TradingAgent报告_000012_2026-05-22\
```

### 港股 — 中国有色矿业（1258.HK）

```
$ python run_hk.py 1258.HK 2026-05-22

最终决策信号: Buy
目标价: HK$18.0 | 时间框架: 12-18 个月
```

## 关键配置

在 `run_single.py` / `run_hk.py` 中可调整：

```python
config["deep_think_llm"] = "deepseek-v4-pro"     # 辩论/决策用深度模型
config["quick_think_llm"] = "deepseek-v4-flash"   # 数据查询用快速模型
config["max_debate_rounds"] = 3                    # 多空辩论轮次
config["output_language"] = "Chinese"              # Chinese / English
config["checkpoint_enabled"] = True                # 断点续跑
```

## 项目结构

```
TradingAgents-A-share/
├── run_single.py              # A 股单股分析入口
├── run_hk.py                  # 港股单股分析入口
├── main.py                    # 旧版平台入口
├── cli/                       # 交互式 CLI
├── tradingagents/
│   ├── agents/                # 12 个 Agent 角色实现
│   │   ├── analysts/          # 市场/情绪/新闻/基本面分析师
│   │   ├── researchers/       # 多头/空头研究员
│   │   ├── managers/          # 研究经理/组合经理
│   │   ├── risk_mgmt/         # 激进/保守/中立风控
│   │   ├── trader/            # 交易员
│   │   └── utils/             # 工具函数（信号/结构化/记忆/评级）
│   ├── graph/                 # LangGraph 状态编排
│   │   ├── trading_graph.py   # 主图编排
│   │   ├── propagation.py     # 状态传播
│   │   ├── conditional_logic.py # 条件分支
│   │   ├── checkpointer.py    # 断点续跑
│   │   └── signal_processing.py # 信号解析
│   ├── dataflows/             # 数据管道
│   │   ├── a_share.py         # A 股 akshare 实现
│   │   ├── a_share_common.py  # A 股工具函数
│   │   ├── y_finance.py       # yfinance 实现（港股/美股）
│   │   ├── interface.py       # Vendor 路由注册
│   │   └── config.py          # 配置管理 + A 股自动检测
│   ├── data_tools/            # 数据工具抽象层
│   └── llm_clients/           # 多模型提供方客户端
├── assets/                    # 架构图/截图
├── SETUP.md                   # AI Agent 部署指南
├── .env.example               # 环境变量模板
└── requirements.txt           # Python 依赖
```

## 报告输出

运行后在桌面生成 `TradingAgent报告_<代码>_<日期>/` 目录：

| 文件 | 内容 |
|------|------|
| `完整分析报告.md` | 四章完整报告（技术分析 + 情绪 + 新闻 + 基本面 + 辩论 + 决策） |
| `原始数据.json` | 所有中间状态数据 |

### 生成 Word

```bash
pandoc 完整分析报告.md -o 分析报告.docx
```

## 角色协作图谱

<p align="center">
  <img src="assets/analyst.png" alt="Analyst Team" width="100%" />
</p>

> 图 1 来源：上游项目 `TauricResearch/TradingAgents` 官方 README
> 链接：https://github.com/TauricResearch/TradingAgents/blob/main/assets/analyst.png

<p align="center">
  <img src="assets/researcher.png" alt="Research Team" width="72%" />
</p>

> 图 2 来源：上游项目

<p align="center">
  <img src="assets/trader.png" alt="Trader" width="72%" />
</p>

> 图 3 来源：上游项目

<p align="center">
  <img src="assets/risk.png" alt="Risk and Portfolio" width="72%" />
</p>

> 图 4 来源：上游项目

## 和历史版本的关键差异

| 维度 | 上游 TradingAgents | 本版本 |
|------|-------------------|--------|
| 市场 | 美股为主 | **A 股 + 港股** |
| 数据主干 | yfinance | A 股 akshare / 港股 yfinance |
| 输出语言 | 英文 | 中英文双语 |
| 单股入口 | 无 | `run_single.py` / `run_hk.py` |
| AI Agent 协作 | 无 | CLAUDE.md + SETUP.md |
| 东方财富新闻 | — | 替代为研报+快讯组合 |

## 开源合规说明

本仓库为衍生开源项目（Apache-2.0）。

1. 上游参考项目：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
2. 本仓库与上游团队无隶属关系，不代表上游官方立场
3. 历史版文档保留在 `README_legacy.md`
4. 架构总览图引用自上游资源
5. 使用前请审阅仓库 `LICENSE` 及第三方依赖许可

## 免责声明

本项目仅用于学术研究、工程实验与教学演示，不构成投资建议。任何实盘交易决策及风险由使用者自行承担。

## 开发者与贡献

- 上游项目：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 多 Agent 金融交易框架
- A 股本地化 + 港股支持：[hkwsg](https://github.com/hkwsg)
  - AkShare 数据全链路集成
  - 东方财富个股新闻 API 失效适配
  - 雪球情绪三维数据 + 财新新闻
  - 港股 yfinance 管道
  - v3.0：9 项 Bug 修复 + AI Agent 协作指南
- 如果项目对你有帮助，欢迎 Star ⭐
