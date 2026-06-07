# 当前交接状态

## 项目

项目名称：TradingAgents-A-share

## 最近状态

- 当前状态：正常运行，v3.0 版本已稳定
- 最近一次重要改动：v3.0 发布（港股支持、9项Bug修复、DeepSeek V4模型适配）
- 最近一次验证：`run_single.py` / `run_hk.py` / `run_batch.py` 均正常运行

## 关键入口

- 规则入口：`CLAUDE.md`、`AGENTS.md`
- README：`README.md`
- 主要代码/资料目录：`tradingagents/`、`run_single.py`、`run_hk.py`、`run_batch.py`、`reports/`

## 未完成事项

- 待补充

## 风险与注意事项

- API Key 在 `.env`，永远不打印、不提交
- Windows 上必须设置 `PYMINIRACER_V8_SINGLE_THREAD=1` 和 `PYMINIRACER_DISABLE_CONFIGURE_POOL=1`
- akshare 连接池有限，多股分析建议串行
- DeepSeek 结构化输出偶尔返回 None，已有 fallback 处理
- 不修改 `tradingagents/` 核心框架代码（除非用户明确要求）

## 下一步建议

- 待补充

## 交接记录

- 日期：2026-06-08
- 代理：Claude Code
- 说明：P1 修复包——新建 operations/current-state.md
