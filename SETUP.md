# TradingAgents-A-share 部署与使用指南

> 本指南面向 **AI Agent 用户**（如 Claude Code、Cursor、Codex CLI 等），教你如何从零配置环境、拉取项目、运行 A 股/港股分析，并让 Agent 像本项目的开发者一样与之交互。

---

## 1. 环境要求

| 组件 | 版本/说明 |
|------|----------|
| Python | 3.12+（推荐 3.12） |
| Node.js | 任意版本（仅用于 `npx` 调用 opencli 等工具） |
| Git | 任意版本 |
| Git Bash | Windows 用户必须（提供 bash 环境） |
| 磁盘空间 | ~2GB（含模型缓存和股票数据缓存） |

以下为常用可选依赖：

| 工具 | 用途 |
|------|------|
| pandoc + LibreOffice | 生成中文 PDF 报告（非必须） |
| opencli | 搜索外部信息（非必须） |
| playwright-cli | 浏览器自动化（非必须） |

---

## 2. 克隆项目

```bash
git clone https://github.com/hkwsg/TradingAgents-A-share.git
cd TradingAgents-A-share
```

---

## 3. 配置 API Key

项目使用 DeepSeek 模型（兼容 OpenAI API 格式）。

### 3.1 创建 `.env` 文件

```bash
cp .env.example .env
```

### 3.2 编辑 `.env`，填入密钥

```ini
# 必填：DeepSeek API Key（从 platform.deepseek.com 获取）
DEEPSEEK_API_KEY=sk-your-key-here

# 可选：其他 provider 的 key
# OPENAI_API_KEY=sk-xxx
# ANTHROPIC_API_KEY=sk-ant-xxx
# GOOGLE_API_KEY=xxx
```

### 3.3 安装 Python 依赖

```bash
pip install -r requirements.txt
```

---

## 4. 基本使用

### 4.1 跑 A 股分析

```bash
# 单只股票，指定日期
python run_single.py 000012 2026-05-22

# 不指定日期则默认取最近交易日
python run_single.py 600519
```

参数：`python run_single.py <股票代码> [交易日期]`

**A 股代码**：6 位数字（如 `000012` 南玻A、`600519` 茅台、`688449` 联芸科技），系统自动识别 A 股并切换 akshare 数据源。

### 4.2 跑港股分析

```bash
python run_hk.py 1258.HK 2026-05-22
```

参数：`python run_hk.py <港股代码.HK> [交易日期]`

**港股代码**：带 `.HK` 后缀（如 `1258.HK` 中国有色矿业、`0020.HK` 商汤、`9880.HK` 优必选），自动走 yfinance 数据管道。

### 4.3 输出

- **终端**：流式输出每一步进度
- **报告**：桌面生成 `TradingAgent报告_<代码>_<日期>/` 目录，内含：
  - `完整分析报告.md` — Markdown 格式完整报告
  - `原始数据.json` — 所有中间状态数据

### 4.4 生成 Word（可选）

```bash
pandoc 完整分析报告.md -o 分析报告.docx
```

---

## 5. 关键配置说明

`run_single.py` 和 `run_hk.py` 中的默认配置：

```python
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-v4-pro"    # 深度思考（辩论、决策）
config["quick_think_llm"] = "deepseek-v4-flash"  # 快速响应（数据查询）
config["max_debate_rounds"] = 3                   # 多空辩论轮次
config["max_risk_discuss_rounds"] = 1             # 风险讨论轮次
config["output_language"] = "Chinese"             # 报告输出语言
```

如需切换模型，修改对应字段即可。支持的 provider 见 `tradingagents/llm_clients/model_catalog.py`。

---

## 6. 让 AI Agent 接管操作

本项目的开发者（hkwsg）日常通过 **Claude Code** 交互。以下是让 Agent 能像他一样操作项目的方法。

### 6.1 创建项目级 CLAUDE.md

在项目根目录创建 `CLAUDE.md`，内容如下：

```markdown
# TradingAgents-A-share

## 项目定位
A 股 + 港股双市场 AI 投资分析系统。基于 LangGraph 多 Agent 辩论框架，
A 股走 akshare 数据管道，港股走 yfinance 数据管道。

## 启动命令
- A股：python run_single.py <6位代码> [日期]
- 港股：python run_hk.py <代码.HK> [日期]
- 示例：python run_single.py 000012 2026-05-22
- 示例：python run_hk.py 1258.HK 2026-05-22

## 环境
- Python：py 3.12，依赖见 requirements.txt
- 模型：DeepSeek V4 Pro + V4 Flash
- API Key：.env 中 DEEPSEEK_API_KEY
- 中文字体：simhei.ttf / simfang.ttf / simkai.ttf（C:\Windows\Fonts\）

## 关键文件
- run_single.py — A股单股分析入口
- run_hk.py — 港股单股分析入口
- tradingagents/dataflows/a_share.py — A股数据实现（akshare）
- tradingagents/dataflows/y_finance.py — 港股/美股数据实现（yfinance）
- tradingagents/dataflows/interface.py — Vendor 路由注册
- tradingagents/dataflows/a_share_common.py — A股工具函数
- tradingagents/agents/utils/rating.py — 信号解析（中英文）
- tradingagents/agents/utils/structured.py — 结构化输出

## 报告输出
- 桌面 TradingAgent报告_<代码>_<日期>/ 目录
- 完整分析报告.md + 原始数据.json

## Word 生成
- pandoc 一键转换
- 命令：pandoc 完整分析报告.md -o 分析报告.docx

## 常见问题
- 指标返回 N/A：次新股数据不足，技术指标无法计算
- Structured output warning：DeepSeek 偶尔返回 None，自动 fallback 到自由文本
- yfinance 尝试 A 股下载：预期行为，已被 fallback 兜住
- Reddit/StockTwits 404/403：海外源对 A/港股无覆盖，不影响结果
```

### 6.2 Agent 对话示例

以下是本项目的实际 Agent 交互记录，展示了从指令到结果的全流程。

#### 单股票分析

```
用户：跑一下南玻A，日期今天

Agent：启动南玻A (000012) 分析，3轮辩论预计10-12分钟。

[0s] 步骤1: Market Analyst 启动
[25s] 步骤3: A-share price data for 000012.SZ # Records: 133
[110s] 步骤10: 技术分析报告完成
[200s] 步骤12: 社交媒体情绪分析完成
[244s] 步骤28: 基本面分析完成
[644s] 步骤36: 研究经理裁决 + 投资计划
[866s] 步骤41: Portfolio Manager 最终决策

分析完成，耗时 14分26秒
最终决策信号: Underweight

## 南玻A（000012）2026-05-22 结果
 
| 维度 | 内容 |
|------|------|
| 信号 | Underweight |
| 当前价 | ¥4.40 |
| 核心问题 | 营收-11.2% + 存货+30%，基本面恶化未触底 |
| 致命矛盾 | 营收下滑 vs 存货激增 → 滞销证据 |

执行策略：
| 第一档 | 现价 ¥4.40 | 减持 50% |
| 第二档 | ¥4.55 | 再减 30% |
| 剩余仓 | — | 40%以¥3.90硬止损 |
| 空仓者 | 当前禁买 | 等 ¥3.80以下 + 基本面改善 |

报告已保存: 桌面\TradingAgent报告_000012_2026-05-22\
```

#### 批量对比分析

```
用户：联芸科技，大普微和盛合晶微，跑一下，日期今天

Agent：三家代码确认：688449 / 301666 / 688820，并行启动。

=== 联芸科技 (688449) | 当前价:87.79 | 信号:Underweight ===
致命伤：Q1扣非仅607万，年化不足3500万，市值404亿 → PE 282倍
PM：减持50%，81元硬止损，空仓者等60-70

=== 大普微 (301666) | 信号:Sell ===
致命伤：毛利率3.07%，21天涨263%后放量滞涨
PM：立即清仓，一股不留。"纯动量博弈，非投资"

=== 盛合晶微 (688820) | 信号:Underweight ===
致命伤：存货暴增4倍，145%涨幅后买家枯竭
PM：分批减持50-70%，保留30-50%底仓（AI赛道逻辑）

三家对比：
大普微最危险（Sell清仓），盛合晶微有赛道底仓逻辑，联芸纯估值贵
```

#### 港股分析

```
用户：中国有色矿业 1258.HK 跑一下

Agent：yfinance 确认可用，代码 1258.HK，启动港股管道。

分析完成，耗时 10分12秒
最终决策信号: Buy ← 三只港股中唯一看多

核心逻辑：
- 零有息负债，净现金13.86亿美元
- 毛利率 19.7→31.1% 连升四年
- ROE 18.11%，远期PE仅10.53倍
- WSJ赞比亚调查未点名，是被动卷入非主动欺诈

PM执行：首期15-20%试探建仓，12.45止损，目标18.0（12-18月）
```

#### 故障排查对话

```
用户：技术指标API返回结果为空是什么情况？

Agent：根因是 _get_indicator_data 用 load_ohlcv（yfinance）
拉数据，A股代码 yfinance 不认。改成 akshare 的 
_load_stock_hist_with_fallback，列名中翻英后交给 stockstats。

验证：重新获取 000012 的 ATR/MACD/布林带，返回实际数值确认修复。

用户：结构化输出有问题，这是bug吗？

Agent：不是严重bug。DeepSeek 的 with_structured_output 
偶尔返回 None，render(result) 调用 result.rating 崩了。
invoke_structured_or_freetext 里 catch 后自动切到普通 LLM 
自由文本重试。代价是浪费一次 LLM 调用。已加 None 检查优化。
```

#### 报告格式

Agent 给出的报告摘要遵循统一的执行策略格式：

```
## XX股票（代码）2026-05-22 结果
 
| 维度 | 内容 |
|------|------|
| 信号 | Buy/Sell/Hold/Underweight/Overweight |
| 当前价 | ¥XX |
| 核心问题 | 一句话概括致命伤或核心逻辑 |
 
执行策略：
| 第一档 | 触发价 | 操作 | 仓位变化 |
| 硬止损 | 价格 | 无条件清仓 |
| 空仓者 | 条件 | 操作 |
| 时间框架 | X-X个月 | 关键验证节点 |
```

### 6.3 其他 Agent 工具配置

| 工具 | 配置方式 |
|------|---------|
| **Claude Code** | 项目根目录放 `CLAUDE.md` 即可自动加载 |
| **Cursor** | 同上，或写入 `.cursorrules` |
| **Codex CLI** | 写入 `CODEX.md` 或 `AGENTS.md` |
| **通用 Agent** | 在 system prompt 中注入本文件的内容 |

---

## 7. 项目架构速览

```
用户输入（股票代码+日期）
        │
        ▼
  run_single.py / run_hk.py        ← 入口：配置模型、数据源、辩论轮次
        │
        ▼
  TradingAgentsGraph               ← LangGraph 多 Agent 编排
        │
        ├─ Market Analyst          ← 技术面分析（均线/MACD/RSI/布林带）
        ├─ Sentiment Analyst       ← 社交媒体情绪（雪球/Reddit/StockTwits）
        ├─ News Analyst            ← 新闻宏观（财新/市场快讯/yfinance）
        ├─ Fundamentals Analyst    ← 基本面（利润表/负债表/现金流）
        │
        ├─ Bull Researcher ×3      ← 多头辩论
        ├─ Bear Researcher ×3      ← 空头辩论
        ├─ Research Manager        ← 裁决 + 投资计划
        │
        ├─ Trader                  ← 交易执行计划
        └─ Portfolio Manager       ← 最终决策（Buy/Sell/Hold/Underweight/Overweight）
```

---

## 8. 注意事项

- **API 费用**：DeepSeek V4 Pro 按 token 计费，每次完整分析约消耗 50万-100万 input tokens + 1万-3万 output tokens
- **运行时间**：单只股票约 10-15 分钟（3 轮辩论）
- **数据限制**：次新股（上市 < 3 个月）技术指标可能无法计算
- **非投资建议**：所有分析结果仅供研究参考，不构成投资建议
