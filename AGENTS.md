# TradingAgents-A-share

## 项目定位
A 股 + 港股双市场 AI 投资分析系统。基于 LangGraph 多 Agent 辩论框架（12 个 Agent），A 股走 akshare 数据管道，港股走 yfinance 数据管道。

## 启动命令
- **A股**：`.venv/Scripts/python.exe run_single.py <6位代码> [日期]`
- **港股**：`.venv/Scripts/python.exe run_hk.py <代码.HK> [日期]`
- Windows 上 **必须** 前置环境变量（akshare 的 V8 引擎兼容性）：
  ```bash
  PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_single.py 000012 2026-05-22
  ```
- 示例港股：`PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_hk.py 1258.HK`

## 环境
- Python：3.12.3，依赖见 `pyproject.toml`
- 模型：DeepSeek V4 Pro（深度思考）+ V4 Flash（快速响应）
- API Key：`.env` 中 `DEEPSEEK_API_KEY`
- 中文字体：`C:\Windows\Fonts\simhei.ttf`（黑体）

## 关键文件索引

### 入口脚本
- `run_single.py` — A股单股分析入口
- `run_hk.py` — 港股分析入口
- `main.py` — 冒烟测试（NVDA 硬编码）

### 数据层 `tradingagents/dataflows/`
- `interface.py` — Vendor 路由注册
- `a_share.py` — A股数据（akshare，约 2000 行）
- `y_finance.py` — 港股/美股数据

### Agent 层 `tradingagents/agents/`
- `analysts/` — 4 分析师（market/sentiment/news/fundamentals）
- `researchers/` — 多空辩论
- `managers/` — 研究经理 + 组合经理
- `risk_mgmt/` — 三人风控（aggressive/conservative/neutral）

### 编排层 `tradingagents/graph/`
- `trading_graph.py` — 总调度
- `setup.py` — StateGraph 构建

### LLM 客户端
- `tradingagents/llm_clients/` — DeepSeek 兼容客户端

## 个人关注列表
- `.watchlist.json` — 结构：`{"人名": ["代码1", "代码2"]}`（gitignore）
- 用户说「我的股票」→ 读此文件识别列表

## 报告输出
- `reports/<代码>_<日期>/` 目录（gitignore）
- 包含：`完整分析报告.md` + `原始数据.json`
- 单次分析：约 10-15 分钟，约 50-100 万 input tokens

## 常见问题
- **py_mini_racer 崩溃**：Windows 上 akshare 的 V8 引擎与多进程不兼容 → 必须用上面的环境变量
- **技术指标 N/A**：次新股数据不足，正常现象
- **Structured output warning**：DeepSeek 偶尔返回 None，自动 fallback
- **Reddit/StockTwits 404**：海外源对 A/港股无覆盖，忽略
