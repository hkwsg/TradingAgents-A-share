# 当前交接状态

## 项目

项目名称：TradingAgents-A-share

## 最近状态

- 当前状态：远端 `main` 已完成 **14 个 commit push**，本地与远端同步
- 最近一次重要改动：本轮项目初始化→飞书推送→批量汇总→性能监控→资料卡产品化→敏感信息清理→Markdown 协作治理 cleanup

## 本轮主要内容

- **项目初始化与报告路径迁移**：报告输出全部收敛到项目本地 `reports/`，不再散落总目录
- **飞书推送与报告格式化**：L1/L2 报告格式化 + 飞书推送编排
- **批量运行与交易日汇总**：`run_batch.py` 入口 + 交易日批量汇总简报
- **性能监控**：阶段计时（`stage_timer.py`）+ 回调级追踪（`perf_callbacks.py`）+ Token 用量汇总
- **资料卡生成产品化**：Markdown→HTML→PNG 管线 + 纯函数测试
- **敏感信息与个人配置清理**（详见下节）

## 已清理

- `DEFAULT_OPEN_ID` 改为 `None`（不再硬编码飞书 open_id）
- `CLAUDE.local.md` 已从 Git 跟踪移除
- `.gitignore` 已忽略 `.env`、`.watchlist.json`、`.claude/`、`CLAUDE.local.md`、`reports/`
- `scheduled_run.sh` 已移除本机绝对路径
- 本次 Markdown cleanup：`CLAUDE.md` 离线兜底段已无本机绝对路径

## 待确认 / 后续事项

- 本次 Markdown cleanup 后再做一次远端只读交叉审计
- 备份分支 `backup/pre-push-cleanup-2026-06-08` 暂时保留，确认无异常后再删
- 敏感文件持续不入版本控制

## 风险与注意事项

- API Key 只在 `.env`，永远不打印、不提交
- 飞书 `open_id` 只走 `FEISHU_OPEN_ID` 环境变量
- 不提交个人关注列表（`.watchlist.json`）
- 不提交 `reports/` 生成物
- Windows 上必须设置 `PYMINIRACER_V8_SINGLE_THREAD=1` 和 `PYMINIRACER_DISABLE_CONFIGURE_POOL=1`
- akshare 连接池有限，多股分析建议串行
- DeepSeek 结构化输出偶尔返回 None，已有 fallback 处理
- 不修改 `tradingagents/` 核心框架代码（除非用户明确要求）

## 下一步建议

- ChatGPT / 另一 Agent 远端只读审计 GitHub diff
- 确认无异常后删除备份分支 `backup/pre-push-cleanup-2026-06-08`

## 交接记录

- 日期：2026-06-08
- 代理：Claude Code
- 说明：P1 修复包——新建 operations/current-state.md
- 日期：2026-06-08
- 代理：Claude Code
- 说明：Markdown 协作治理 cleanup——对齐 AGENTS.md / CLAUDE.md / CHANGELOG.md / LESSONS.md / operations/current-state.md / .codex/资料卡模板.md
