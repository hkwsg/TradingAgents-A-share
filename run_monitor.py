"""TradingAgents -- 外挂监控入口（不修改 run_single.py 一行代码）

用法:
    .venv/Scripts/python.exe run_monitor.py 600519                    # 基础计时
    .venv/Scripts/python.exe run_monitor.py 600519 --perf             # 深度追踪
    .venv/Scripts/python.exe run_monitor.py 600519 --debate 1        # 限制辩论轮数

与 run_single.py 的唯一区别：此脚本在流式循环外包了一层计时器。
其他所有逻辑（配置、Graph、报告保存）完全复用项目内部模块。
"""

import os
os.environ.setdefault("PYMINIRACER_V8_SINGLE_THREAD", "1")
os.environ.setdefault("PYMINIRACER_DISABLE_CONFIGURE_POOL", "1")

import sys
import io
import time
import json
import argparse
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(override=True)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.a_share_common import get_previous_trade_date
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.stage_timer import StageTimer
from tradingagents.graph.perf_callbacks import PerfCallbacks
from cli.main import save_report_to_disk


def main():
    parser = argparse.ArgumentParser(description="TradingAgents A股 -- 外挂监控入口")
    parser.add_argument("ticker", help="股票代码，如 600519")
    parser.add_argument("date", nargs="?", default=None,
                        help="交易日期 YYYY-MM-DD，默认最近交易日")
    parser.add_argument("--debate", type=int, default=None,
                        help="辩论轮数，默认从 .env / DEFAULT_CONFIG 读取")
    parser.add_argument("--analysts", nargs="+",
                        choices=["market", "social", "news", "fundamentals"],
                        help="选择分析师，默认全部四个")
    parser.add_argument("--perf", action="store_true",
                        help="启用深度耗时追踪（LLM vs 工具调用拆分）")
    parser.add_argument("--no-push", action="store_true",
                        help="禁用飞书推送")
    args = parser.parse_args()

    ticker = args.ticker
    trade_date = args.date or get_previous_trade_date(date.today().isoformat())

    # ---- 加载配置 ---- #
    config = DEFAULT_CONFIG.copy()
    env_overrides = {
        "deep_think_llm": os.getenv("TRADINGAGENTS_DEEP_LLM"),
        "quick_think_llm": os.getenv("TRADINGAGENTS_QUICK_LLM"),
        "backend_url": os.getenv("TRADINGAGENTS_BACKEND_URL"),
        "llm_provider": os.getenv("TRADINGAGENTS_LLM_PROVIDER"),
        "max_debate_rounds": int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS")) if os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS") else None,
        "max_risk_discuss_rounds": int(os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS")) if os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS") else None,
        "output_language": os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE"),
        "temperature": os.getenv("TRADINGAGENTS_TEMPERATURE"),
    }
    for k, v in env_overrides.items():
        if v is not None and v != "":
            config[k] = v
    if args.debate is not None:
        config["max_debate_rounds"] = int(args.debate)

    selected_analysts = args.analysts if args.analysts else ["market", "social", "news", "fundamentals"]
    debug = os.getenv("TRADINGAGENTS_DEBUG", "").lower() in ("1", "true", "yes")

    # ---- 构建 Graph ---- #
    console.print(Panel(f"正在初始化 {ticker} {trade_date}...", border_style="cyan"))
        # perf handler must be created BEFORE graph so callbacks are wired into LLMs
    perf_handler = PerfCallbacks() if args.perf else None
    callbacks = [perf_handler] if perf_handler else None

    graph = TradingAgentsGraph(debug=debug, config=config, callbacks=callbacks)

    instrument_context = graph.resolve_instrument_context(ticker)
    init_state = graph.propagator.create_initial_state(
        ticker, trade_date, instrument_context=instrument_context,
    )
    flow_args = graph.propagator.get_graph_args()

    # ---- 初始化计时器（外挂层）---- #
    stage_timer = StageTimer()

    # ---- 流式执行 + 计时 ---- #
    console.print(Panel("开始分析...", border_style="cyan"))
    start_time = time.time()
    step = 0
    trace = []

    for chunk in graph.graph.stream(init_state, stream_mode="updates", **flow_args):
        step += 1
        trace.append(chunk)

        active = [k for k in chunk if k != "messages"]
        if active:
            stage_timer.tick(active)
            elapsed = time.time() - start_time
            console.print(f"  [dim][{int(elapsed)}s][/dim] 步骤{step}: "
                          f"[cyan]{' -> '.join(active)}[/cyan]")

    stage_timer.finalize()
    elapsed = time.time() - start_time

    # ---- 合并状态 ---- #
    final_state = {}
    for c in trace:
        final_state.update(c)

    decision = final_state.get("final_trade_decision", "")
    signal = graph.process_signal(decision)

    # ---- 结果摘要 ---- #
    table = Table(title="分析结果", border_style="green")
    table.add_column("阶段", style="cyan")
    table.add_column("结论", style="bold")
    table.add_column("耗时", style="dim")

    table.add_row("最终决策", str(signal),
                  f"{int(elapsed // 60)}分{int(elapsed % 60)}秒")
    table.add_row("市场分析", "Y" if final_state.get("market_report") else "X", "")
    table.add_row("情绪分析", "Y" if final_state.get("sentiment_report") else "X", "")
    table.add_row("新闻分析", "Y" if final_state.get("news_report") else "X", "")
    table.add_row("基本面", "Y" if final_state.get("fundamentals_report") else "X", "")
    console.print(table)

    # ---- 保存报告 ---- #
    report_dir = Path(__file__).parent / "reports" / f"{ticker}_{trade_date}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = save_report_to_disk(final_state, ticker, report_dir)
    console.print(f"\n[green]报告已保存:[/green] {report_path}")

    json_path = report_dir / "原始数据.json"
    safe = {}
    for k, v in final_state.items():
        try:
            json.dumps(v, ensure_ascii=False)
            safe[k] = v
        except (TypeError, ValueError):
            safe[k] = str(v)[:2000]
    json_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 计时报告 ---- #
    timing_path = report_dir / "耗时分析.json"
    timing_path.write_text(json.dumps(stage_timer.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    console.print()
    stage_timer.print_report(console)

    if perf_handler:
        console.print()
        perf_handler.print_report(console)
        perf_path = report_dir / "耗时明细.json"
        perf_path.write_text(json.dumps(perf_handler.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[dim]耗时明细已保存: {perf_path}[/dim]")

        # total token summary
        total_prompt = sum(n.prompt_tokens_total for n in perf_handler.get_nodes())
        total_completion = sum(n.completion_tokens_total for n in perf_handler.get_nodes())
        total_tok = total_prompt + total_completion

        def _fmt(n):
            if n >= 1000:
                return f"{n/1000:.1f}k"
            return str(n)

        console.print(f"\n[bold yellow]  Token 总消耗: 输入 {_fmt(total_prompt)} + 输出 {_fmt(total_completion)} = {_fmt(total_tok)}[/bold yellow]")

    # ---- 精简结果 ---- #
    if config.get("output_language", "").lower() in ("chinese", ""):
        from cli.report_formatter import format_condensed_result
        condensed = format_condensed_result(final_state, elapsed, ticker, config)
        console.print(f"\n{condensed}")

    # ---- 飞书推送 ---- #
    if not args.no_push:
        try:
            from cli.feishu_push import push_analysis_result
            push_analysis_result(final_state, elapsed, ticker, config)
        except Exception:
            console.print("[dim]飞书推送跳过（模块不可用或无配置）[/dim]")

    console.print("\n[bold green]分析完成[/bold green]")


if __name__ == "__main__":
    main()
