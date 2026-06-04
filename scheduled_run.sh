#!/usr/bin/env bash
# TradingAgents 批量分析 — Windows 计划任务兜底脚本
# 用法: schtasks /create /tn "TradingAgentsDaily" /tr "bash <项目路径>/scheduled_run.sh" /sc daily /st 09:10
# 使用前请将 PROJECT_DIR 修改为本机实际路径

set -e

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$PROJECT_DIR"

echo "=== TradingAgents 批量分析 $(date +%Y-%m-%d) ==="

export PYMINIRACER_V8_SINGLE_THREAD=1
export PYMINIRACER_DISABLE_CONFIGURE_POOL=1

.venv/Scripts/python.exe run_batch.py --market A

echo "完成: $(date)"
