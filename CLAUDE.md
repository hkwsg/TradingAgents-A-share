# TradingAgents-A-share

## 项目定位
A 股 + 港股双市场 AI 投资分析系统。基于 LangGraph 多 Agent 辩论框架（12 个 Agent），A 股走 akshare 数据管道，港股走 yfinance 数据管道。

## 启动命令
- A股：`py run_single.py <6位代码> [日期]`
- 港股：`py run_hk.py <代码.HK> [日期]`
- 示例：`py run_single.py 000012 2026-05-22`
- 示例：`py run_hk.py 1258.HK 2026-05-22`

## 环境
- Python：`py`（3.12.3），依赖见 `pyproject.toml`
- 模型：DeepSeek V4 Pro（深度思考）+ V4 Flash（快速响应）
- API Key：`.env` 中 `DEEPSEEK_API_KEY`
- 中文字体：`C:\Windows\Fonts\simhei.ttf`（黑体）、`simfang.ttf`（仿宋）、`simkai.ttf`（楷体）

## 关键文件索引

### 入口脚本
- `run_single.py` — A股单股分析入口（argparse + Rich UI）
- `run_hk.py` — 港股分析入口
- `main.py` — 快速冒烟测试（NVDA 硬编码，仅验证流程）

### 数据层 `tradingagents/dataflows/`
- `interface.py` — Vendor 路由注册（akshare/yfinance/alpha_vantage）
- `a_share.py` — A股数据实现（akshare，约 2000 行）
- `a_share_common.py` — A股工具函数（代码标准化、交易日历）
- `y_finance.py` — 港股/美股数据实现
- `config.py` — 运行时配置单例

### Agent 层 `tradingagents/agents/`
- `analysts/` — 4 个分析师（market/sentiment/news/fundamentals）
- `researchers/` — 多空辩论研究员（bull/bear）
- `managers/` — 研究经理 + 投资组合经理
- `trader/` — 交易执行计划
- `risk_mgmt/` — 三人风控（aggressive/conservative/neutral）
- `utils/rating.py` — 信号解析（中英文评级词）
- `utils/structured.py` — 结构化输出 fallback

### 编排层 `tradingagents/graph/`
- `trading_graph.py` — TradingAgentsGraph 总调度
- `setup.py` — LangGraph StateGraph 构建
- `conditional_logic.py` — 辩论/风控轮次控制
- `reflection.py` — 事后反思与记忆

### LLM 客户端 `tradingagents/llm_clients/`
- `factory.py` — LLM 客户端工厂
- `model_catalog.py` — 所有 provider 的模型列表
- `openai_client.py` — OpenAI 兼容客户端（含 deepseek/xai/qwen/ollama 等 11 个 provider）

## 个人关注列表
- `.watchlist.json` — 本地文件（gitignore），结构：`{"人名": ["代码1", "代码2"]}`
- 分析前先读取此文件，识别"我的股票""XX的股票"等自然语言
- 用户说「跑一下我的股票」→ 遍历 `我` 的列表批量分析

## 报告输出
- 项目内 `reports/<代码>_<日期>/` 目录（不提交 git）
- `完整分析报告.md` + `原始数据.json`

## 常见问题
- **技术指标 N/A**：次新股数据不足，指标无法计算，正常现象
- **Structured output warning**：DeepSeek 偶尔返回 None，自动 fallback 到自由文本
- **yfinance 尝试 A 股下载**：预期行为，已被 akshare fallback 兜住
- **Reddit/StockTwits 404/403**：海外源对 A/港股无覆盖，不影响结果
- **单次分析耗时**：约 10-15 分钟，消耗约 50-100 万 input tokens
