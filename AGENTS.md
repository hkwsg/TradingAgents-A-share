# TradingAgents-A-share

## 项目定位
A 股 + 港股双市场 AI 投资分析系统。基于 LangGraph 多 Agent 辩论框架（12 个 Agent），A 股走 akshare 数据管道，港股走 yfinance 数据管道。

## Agent 协作边界

- Claude Code / Codex 协作时，优先读取 `AGENTS.md`，Claude Code 另读 `CLAUDE.md`。
- 不得提交 `.env`、`.watchlist.json`、`CLAUDE.local.md`、`.claude/`、`reports/` 生成物。
- 涉及飞书推送时，`FEISHU_OPEN_ID` 必须来自环境变量，不得写入代码、文档或示例。
- 涉及 `main` 推送前，必须先做 `git diff origin/main..HEAD` 只读审计。
- push 后建议由另一个 Agent 或 ChatGPT 直接读取 GitHub 远端 diff 做交叉确认。
- 修改 `AGENTS.md` / `CLAUDE.md` / `.codex/` 文档时，必须检查是否混入本机路径、密钥、个人标识。

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

## 性能监控

运行分析时可加 `--perf` 启用深度耗时追踪：

```bash
# 基础计时（默认，报告目录输出 耗时分析.json）
PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_single.py 000012

# 深度追踪（拆分 LLM 推理 vs 工具调用耗时，额外输出 耗时明细.json）
PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_single.py 000012 --perf
```

输出文件：
- `耗时分析.json` — 各阶段/节点墙钟时间，带轮次编号（默认就有）
- `耗时明细.json` — LLM 推理 vs 工具调用逐调用拆解（加 `--perf` 才有）

详见 `tradingagents/graph/stage_timer.py`（基础计时器）和 `tradingagents/graph/perf_callbacks.py`（深度回调追踪）。

## 报告输出
- `reports/<代码>_<日期>/` 目录（gitignore）
- 包含：`完整分析报告.md` + `原始数据.json`
- 单次分析：约 10-15 分钟，约 50-100 万 input tokens

## 专项文档
- [LESSONS.md](LESSONS.md) — 踩坑记录、故障排查、环境速查

## 常见问题
- **py_mini_racer 崩溃**：Windows 上 akshare 的 V8 引擎与多进程不兼容 → 必须用上面的环境变量
- **技术指标 N/A**：次新股数据不足，正常现象
- **Structured output warning**：DeepSeek 偶尔返回 None，自动 fallback
- **Reddit/StockTwits 404**：海外源对 A/港股无覆盖，忽略
## 资料卡生成规范

用户说「生成资料卡」或「出个卡片」时，按此规范从 `complete_report.md` 提取关键信息，生成精简版投资摘要。

### 格式来源
- 模板规范：`.codex/资料卡模板.md`（具体模块、语言风格、摘录技巧）
- 完整范例：`reports/600276_2026-06-05/恒瑞医药_资料卡.md`

### 核心原则
- emoji 分区 + 分隔线 + 短句，不堆表格
- 好坏两面并列，说人话，不写官腔
- 入场信号具体到数字和K线形态
- 止损线有明确价格和理由
- 结尾必加组合经理原话（从报告裁决段落中找最有张力的一句）

### 固定模块
1. 头部指标条（日期/现价/跌幅/周期）
2. 最终评级 + 一句话结论
3. 好的一面（✅ 数据驱动）
4. 坏的一面（🔻 逻辑驱动）
5. 执行方案（按持仓状态分角色）
6. 入场信号/加仓计划
7. 止损线
8. 组合经理原话

### 评级配色
- SELL/Underweight → 🔴 | HOLD/Neutral → 🟡 | BUY/Overweight → 🟢
