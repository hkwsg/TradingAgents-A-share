# TradingAgents-A-share · Claude Code 专属指令

通用项目约定见 `@AGENTS.md`。本文件仅包含 Claude Code 特有的行为指令和补充规则。

## 硬性约束
- 永远不修改 `tradingagents/` 核心框架代码（agent层/编排层/LLM客户端），除非用户明确要求
- 分析报告仅输出到 `reports/` 目录，不得覆盖历史报告
- 用户说「跑一下我的股票」→ 先读 `.watchlist.json`，确认列表后再批量跑
- API Key 在 `.env`，永远不打印、不提交、不写入报告

## 启动命令（环境变量是 Windows + akshare 的命门）
```bash
PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_single.py <代码> [日期]
```
**必须在 shell 层面设置**这两个 env var，放 Python 代码里 `os.environ.setdefault` 来不及。

## Claude Code 专属能力
- 遇到分析报错 → 先 grep 日志里的关键字，再查 `经验/` 目录（如果存在）
- 批量跑多只股票 → 每只独立 SQLite checkpoint，可并行但建议串行（akshare 连接池有限）
- 要对比多个分析结果 → 直接读 `reports/<代码>/完整分析报告.md`，用 subagent 并行提取关键数据

## 按需加载规则
`.claude/rules/` 目录按文件路径自动匹配加载：
- `analysis-execution.md` → 操作入口脚本时加载
- `agent-framework.md` → 操作 `tradingagents/` 核心代码时加载
- `report-output.md` → 操作 `reports/`、`cli/` 时加载

每个规则文件从空开始，同个问题被纠正 2 次后自动填充。

## 批量分析
- `run_batch.py` — 读取 `.watchlist.json` 串行跑所有股票
  - 用法：`PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_batch.py`
  - `--market A` 仅A股，`--market HK` 仅港股
  - `--person 张三` 指定人物，`--tickers 600519,600036` 手动指定
  - 完成后生成 `reports/批量分析_<日期>.md` 汇总简报

## 定时任务（CronCreate 模板）

用户说「开启定时分析」时，按以下模板创建：

```bash
# 交易日开盘后 上午9:10 自动跑关注列表
CronCreate("10 9 * * 1-5", "切换到 TradingAgents-A-share 项目。读取 .watchlist.json 中「我」的列表，串行运行 run_batch.py 分析所有A股。命令：PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_batch.py --market A")

# 交易日收盘后 下午3:30 汇总当日简报
CronCreate("30 15 * * 1-5", "切换到 TradingAgents-A-share 项目。扫描今天 reports/ 目录所有生成的分析报告，提取每只股票的关键结论（操作建议、PE/PB、ROE），汇总为一份当日简报写入 reports/每日简报/<日期>.md。")
```

用户说「停止定时分析」时删除所有相关 CronCreate。

## 离线兜底
使用 Windows 计划任务 + `scheduled_run.sh`：
```bash
schtasks /create /tn "TradingAgentsDaily" /tr "bash <项目路径>/scheduled_run.sh" /sc daily /st 09:10
```

将 `<项目路径>` 替换为本机 `TradingAgents-A-share` 仓库的实际绝对路径。

## 项目记忆
- `~/.claude/projects/.../memory/tradingagents-project-setup.md` — 上次会话的状态快照
