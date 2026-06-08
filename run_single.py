"""TradingAgents 单股分析 — 命令行快捷版

通过 .env 配置 LLM 提供商和模型，一行命令直接分析：

用法:
    py run_single.py 600519                 # 自动取最近交易日
    py run_single.py 600519 2025-12-01      # 指定日期
    py run_single.py 600519 --output word   # 额外生成 Word 报告
"""

import os
os.environ.setdefault("PYMINIRACER_V8_SINGLE_THREAD", "1")
os.environ.setdefault("PYMINIRACER_DISABLE_CONFIGURE_POOL", "1")

import sys
import os
import io
import time
import json
import argparse
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.a_share_common import get_previous_trade_date
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.monitoring import (
    active_nodes_from_update_chunk,
    merge_stream_updates,
)
from tradingagents.graph.perf_callbacks import PerfCallbacks
from tradingagents.graph.stage_timer import StageTimer
from cli.main import save_report_to_disk  # 复用 CLI 的目录化报告保存


def main():
    parser = argparse.ArgumentParser(description="TradingAgents A股单股分析")
    parser.add_argument("ticker", help="股票代码，如 600519")
    parser.add_argument("date", nargs="?", default=None,
                        help="交易日期 YYYY-MM-DD，默认最近交易日")
    parser.add_argument("--output", choices=["md", "word"], default="md",
                        help="报告格式：md 或 word（需 LibreOffice/pandoc）")
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

    ticker = args.ticker.strip()
    trade_date = args.date or get_previous_trade_date(date.today().isoformat())

    # ---- 配置 ----
    config = DEFAULT_CONFIG.copy()
    if args.debate is not None:
        config["max_debate_rounds"] = args.debate
        config["max_risk_discuss_rounds"] = max(1, args.debate - 1)
    if args.analysts:
        config["selected_analysts"] = args.analysts

    # ---- 启动信息 ----
    console.print()
    console.print(Panel.fit(
        f"[bold]股票:[/bold] {ticker}\n"
        f"[bold]日期:[/bold] {trade_date}\n"
        f"[bold]LLM:[/bold] {config['llm_provider']} / {config['quick_think_llm']} (quick)  "
        f"{config['deep_think_llm']} (deep)\n"
        f"[bold]语言:[/bold] {config['output_language']}  "
        f"[bold]辩论:[/bold] {config['max_debate_rounds']}轮  "
        f"[bold]断点:[/bold] {'开' if config['checkpoint_enabled'] else '关'}",
        title="TradingAgents A股分析",
        border_style="green",
    ))

    try:
        # ---- 初始化 ----
        with console.status("[bold green]初始化分析引擎...[/bold green]"):
            perf_handler = PerfCallbacks() if args.perf else None
            callbacks = [perf_handler] if perf_handler else None
            graph = TradingAgentsGraph(debug=False, config=config, callbacks=callbacks)
            instrument_context = graph.resolve_instrument_context(ticker)
            init_state = graph.propagator.create_initial_state(
                ticker, trade_date, instrument_context=instrument_context,
            )
            flow_args = graph.propagator.get_graph_args(
                callbacks=callbacks,
                stream_mode="updates",
            )

            # 分析师执行计划
            selected_keys = [a for a in ["market", "social", "news", "fundamentals"]
                             if a in graph.workflow.nodes]
            if not selected_keys:
                selected_keys = config.get("selected_analysts",
                                            ["market", "social", "news", "fundamentals"])
            exec_plan = build_analyst_execution_plan(selected_keys)
            wall_tracker = AnalystWallTimeTracker(exec_plan)
            stage_timer = StageTimer()

        # ---- 流式执行 ----
        console.print(Panel("开始分析...", border_style="cyan"))
        start_time = time.time()
        step = 0
        trace = []

        for chunk in graph.graph.stream(init_state, **flow_args):
            step += 1
            trace.append(chunk)
            chunk_state = merge_stream_updates([chunk])
            sync_analyst_tracker_from_chunk(wall_tracker, chunk_state)

            # 提取本轮活跃节点
            active = active_nodes_from_update_chunk(chunk)
            if active:
                stage_timer.tick(active)
                elapsed = time.time() - start_time
                console.print(f"  [dim][{int(elapsed)}s][/dim] 步骤{step}: "
                              f"[cyan]{' → '.join(active)}[/cyan]")

        stage_timer.finalize()
        elapsed = time.time() - start_time

        # 合并增量状态
        final_state = merge_stream_updates(trace)

        decision = final_state.get("final_trade_decision", "")
        signal = graph.process_signal(decision)

        # ---- 结果摘要 ----
        table = Table(title="分析结果", border_style="green")
        table.add_column("阶段", style="cyan")
        table.add_column("结论", style="bold")
        table.add_column("耗时", style="dim")

        table.add_row("最终决策", str(signal),
                      f"{int(elapsed // 60)}分{int(elapsed % 60)}秒")
        table.add_row("市场分析", "✓" if final_state.get("market_report") else "✗", "")
        table.add_row("情绪分析", "✓" if final_state.get("sentiment_report") else "✗", "")
        table.add_row("新闻分析", "✓" if final_state.get("news_report") else "✗", "")
        table.add_row("基本面", "✓" if final_state.get("fundamentals_report") else "✗", "")
        console.print(table)

        # ---- 保存报告 ----
        report_dir = Path(__file__).parent / "reports" / f"{ticker}_{trade_date}"
        report_path = save_report_to_disk(final_state, ticker, report_dir)
        console.print(f"\n[green]报告已保存:[/green] {report_path}")

        # 原始 JSON
        json_path = report_dir / "原始数据.json"
        safe = {}
        for k, v in final_state.items():
            try:
                json.dumps(v, ensure_ascii=False)
                safe[k] = v
            except (TypeError, ValueError):
                safe[k] = str(v)[:2000]
        json_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")

        # 基础阶段耗时统计
        timing_path = report_dir / "耗时分析.json"
        timing_path.write_text(json.dumps(stage_timer.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[dim]耗时分析已保存: {timing_path}[/dim]")

        if perf_handler:
            perf_path = report_dir / "耗时明细.json"
            perf_path.write_text(json.dumps(perf_handler.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"[dim]耗时明细已保存: {perf_path}[/dim]")

        # 分析师耗时统计
        console.print(f"\n[dim]{wall_tracker.format_summary()}[/dim]")
        stage_timer.print_report(console)
        if perf_handler:
            perf_handler.print_report(console)

        # 精简结果输出
        if config.get("output_language", "").lower() in ("chinese", "中文"):
            from cli.report_formatter import format_condensed_result
            condensed = format_condensed_result(final_state, elapsed, ticker, config)
            console.print(f"\n{condensed}")

        # ---- 飞书推送 ----
        if not args.no_push:
            try:
                from cli.feishu_push import push_analysis_result, push_start_notification
                push_start_notification(ticker)
                push_analysis_result(final_state, elapsed, ticker, config)
            except Exception as e:
                console.print(f"[yellow]飞书推送失败（不影响分析结果）: {e}[/yellow]")

        # ---- Word 转换 ----
        if args.output == "word":
            console.print()
            with console.status("[bold]生成 Word 报告..."):
                try:
                    from convert_raw_to_word import convert_markdown_to_word
                    word_path = report_dir / "完整分析报告.docx"
                    convert_markdown_to_word(str(report_path), str(word_path))
                    console.print(f"[green]Word 已保存:[/green] {word_path}")
                except Exception as e:
                    console.print(f"[yellow]Word 转换失败: {e}[/yellow]")

        console.print(f"\n[bold green]=== DONE {ticker} ===[/bold green]\n")

    except Exception as e:
        console.print(f"\n[red]分析失败: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
