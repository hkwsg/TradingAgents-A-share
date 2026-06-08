"""TradingAgents 批量分析 — 交错启动并行模式（规避 akshare 连接锁）

用法:
    py run_batch.py                  # 分析"我"的所有股票
    py run_batch.py --market A       # 仅A股
    py run_batch.py --market HK      # 仅港股
    py run_batch.py --person 我      # 指定人物
    py run_batch.py --tickers 600519,600036   # 直接指定代码列表
    py run_batch.py --parallel       # 并发模式（每只间隔10秒启动）
    py run_batch.py --serial         # 串行模式（默认，最安全）
    py run_batch.py --summary-only --summary-date 2026-06-05 --tickers 600036,601899

日报归类规则:
    批量汇总按报告分析使用的交易日归类，优先读取 原始数据.json 里的 trade_date。
    跨午夜完成的报告仍归入该交易日；文件修改时间只代表落盘时间，不参与归类。
"""
import os, sys, io, json, time, argparse, subprocess, re
from datetime import date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJ = Path(__file__).parent
VENV_PYTHON = str(PROJ / ".venv" / "Scripts" / "python.exe")


def load_watchlist():
    """读取关注列表"""
    wp = PROJ / ".watchlist.json"
    if not wp.exists():
        print("⚠ .watchlist.json 不存在，请先创建关注列表")
        return {}
    with open(wp, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def is_hk(ticker):
    """判断是否港股代码（含.HK后缀）"""
    return ".HK" in ticker.upper()


def report_ticker_from_dir(report_dir):
    """从报告目录名提取股票代码。"""
    match = re.match(r"^(.+)_\d{4}-\d{2}-\d{2}$", report_dir.name)
    return match.group(1) if match else None


def report_trade_date(report_dir):
    """返回报告所属交易日，优先以原始数据中的 trade_date 为准。

    跨午夜完成的报告仍归入分析使用的交易日；目录修改时间只代表落盘时间，
    不能作为日报归类依据。
    """
    raw_path = report_dir / "原始数据.json"
    if raw_path.exists():
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            trade_date = raw.get("trade_date")
            if isinstance(trade_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
                return trade_date
        except Exception:
            pass

    match = re.search(r"_(\d{4}-\d{2}-\d{2})$", report_dir.name)
    return match.group(1) if match else None


def find_report_dir(ticker, analysis_date):
    """按分析交易日查找某只股票的报告目录，不使用文件修改时间。"""
    report_root = PROJ / "reports"
    if not report_root.exists():
        return None

    candidates = [
        d for d in report_root.iterdir()
        if d.is_dir()
        and report_ticker_from_dir(d) == ticker
        and report_trade_date(d) == analysis_date
    ]
    return sorted(candidates, key=lambda d: d.name, reverse=True)[0] if candidates else None


def collect_reports_by_trade_date(analysis_date, tickers=None):
    """扫描 reports/，按分析交易日收集报告目录。"""
    report_root = PROJ / "reports"
    if not report_root.exists():
        return []

    ticker_filter = set(tickers) if tickers else None
    reports = []
    for report_dir in report_root.iterdir():
        if not report_dir.is_dir():
            continue
        ticker = report_ticker_from_dir(report_dir)
        if not ticker:
            continue
        if ticker_filter is not None and ticker not in ticker_filter:
            continue
        if report_trade_date(report_dir) == analysis_date:
            reports.append((ticker, report_dir))

    order = {ticker: i for i, ticker in enumerate(tickers or [])}
    return sorted(reports, key=lambda item: (order.get(item[0], 10_000), item[0], item[1].name))


def infer_summary_date(tickers):
    """从指定股票的已生成报告中推断本轮批量汇总交易日。"""
    dates = []
    report_root = PROJ / "reports"
    if not report_root.exists():
        return date.today().isoformat()

    for ticker in tickers:
        for report_dir in report_root.iterdir():
            if not report_dir.is_dir() or report_ticker_from_dir(report_dir) != ticker:
                continue
            trade_date = report_trade_date(report_dir)
            if trade_date:
                dates.append(trade_date)

    if not dates:
        return date.today().isoformat()
    return max(set(dates), key=lambda d: (dates.count(d), d))


def run_one(ticker, market_date=None, quiet=False):
    """运行单只股票分析，返回(成功, 耗时秒)"""
    env = os.environ.copy()
    env["PYMINIRACER_V8_SINGLE_THREAD"] = "1"
    env["PYMINIRACER_DISABLE_CONFIGURE_POOL"] = "1"

    script = "run_hk.py" if is_hk(ticker) else "run_single.py"
    cmd = [VENV_PYTHON, str(PROJ / script), ticker]
    if market_date:
        cmd.append(market_date)

    if not quiet:
        print(f"\n{'='*60}")
        print(f"  开始分析: {ticker}  ({'港股' if is_hk(ticker) else 'A股'})")
        print(f"  命令: {' '.join(cmd)}")
        print(f"{'='*60}")

    t0 = time.time()
    try:
        stdout_target = subprocess.PIPE if quiet else None
        stderr_target = subprocess.PIPE if quiet else None
        result = subprocess.run(cmd, cwd=str(PROJ), env=env,
                                capture_output=quiet, timeout=1800)
        elapsed = time.time() - t0
        ok = result.returncode == 0
        if not quiet:
            status = "✅ 成功" if ok else f"❌ 失败 (exit={result.returncode})"
            print(f"\n  {ticker} 完成: {status} | 耗时: {elapsed/60:.1f} 分钟")
        return ok, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"\n  {ticker} ⏰ 超时（>30分钟）| 已耗时: {elapsed/60:.1f} 分钟")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  {ticker} ❌ 异常: {e}")
        return False, elapsed


def generate_summary(results, total_time=None, analysis_date=None):
    """生成批量分析汇总简报"""
    if analysis_date is None:
        analysis_date = infer_summary_date([ticker for ticker, _ok, _elapsed in results])
    summary_path = PROJ / "reports" / f"批量分析_{analysis_date}.md"
    total_time_text = "—" if total_time is None else f"{total_time/60:.1f} 分钟"

    lines = [
        f"# 批量分析汇总 — {analysis_date}",
        "",
        f"**分析交易日**: {analysis_date} | **总耗时**: {total_time_text} | **总数**: {len(results)} 只",
        "",
        "| 代码 | 结果 | 耗时 | 报告路径 |",
        "|------|------|------|----------|",
    ]

    success = 0
    for ticker, ok, elapsed in results:
        status = "✅" if ok else "❌"
        report_dir = find_report_dir(ticker, analysis_date)
        path = report_dir.name if report_dir else "—"
        elapsed_text = "—" if elapsed is None else f"{elapsed/60:.1f}min"
        lines.append(f"| {ticker} | {status} | {elapsed_text} | {path} |")
        if ok:
            success += 1

    lines += [
        "",
        f"**成功率**: {success}/{len(results)}",
        "",
        "---",
        "*由 run_batch.py 自动生成*",
    ]

    os.makedirs(summary_path.parent, exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n📄 汇总简报: {summary_path}")

    # ---- 飞书推送汇总 ----
    try:
        from cli.feishu_push import push_batch_summary
        push_results = []
        for ticker, ok, elapsed in results:
            # 从报告目录读取信号
            signal = "—"
            try:
                report_dir = find_report_dir(ticker, analysis_date)
                if report_dir:
                    json_path = report_dir / "原始数据.json"
                    if json_path.exists():
                        import json
                        with open(json_path, 'r', encoding='utf-8') as f:
                            raw = json.load(f)
                        from cli.report_formatter import parse_rating
                        signal = parse_rating(raw.get("final_trade_decision", "")) or "—"
            except Exception:
                pass
            push_results.append((ticker, {
                "ok": ok,
                "signal": signal,
                "elapsed": "—" if elapsed is None else f"{elapsed/60:.1f}min"
            }))
        if total_time is not None:
            push_batch_summary(push_results, total_time)
    except Exception as e:
        print(f"[飞书推送失败] {e}")

    return summary_path


def generate_summary_from_reports(analysis_date, tickers=None):
    """基于现有 reports/ 目录生成指定交易日汇总。"""
    reports = collect_reports_by_trade_date(analysis_date, tickers)
    found = {ticker: report_dir for ticker, report_dir in reports}
    target_tickers = tickers or [ticker for ticker, _report_dir in reports]

    results = []
    for ticker in target_tickers:
        results.append((ticker, ticker in found, None))
    return generate_summary(results, total_time=None, analysis_date=analysis_date)


def main():
    parser = argparse.ArgumentParser(description="TradingAgents 批量分析")
    parser.add_argument("--market", choices=["A", "HK"], help="市场筛选：A=仅A股，HK=仅港股")
    parser.add_argument("--person", default="我", help="关注列表中的人物（默认'我'）")
    parser.add_argument("--tickers", help="直接指定代码列表，逗号分隔（如 600519,600036）")
    parser.add_argument("--date", default=None, help="交易日期 YYYY-MM-DD")
    parser.add_argument("--summary-date", default=None,
                        help="只生成/指定汇总的分析交易日 YYYY-MM-DD")
    parser.add_argument("--summary-only", action="store_true", default=False,
                        help="不运行分析，仅按分析交易日扫描 reports/ 生成汇总")
    parser.add_argument("--parallel", action="store_true", default=False,
                        help="并发模式：每只间隔10秒启动")
    parser.add_argument("--serial", action="store_true", default=False,
                        help="串行模式（默认）")
    args = parser.parse_args()

    # 确定股票列表
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
        print(f"使用指定列表: {tickers}")
    else:
        watchlist = load_watchlist()
        if not watchlist:
            return
        if args.person not in watchlist:
            print(f"⚠ 关注列表中没有「{args.person}」，可用: {list(watchlist.keys())}")
            return
        tickers = watchlist[args.person]

    # 市场筛选
    if args.market == "A":
        tickers = [t for t in tickers if not is_hk(t)]
    elif args.market == "HK":
        tickers = [t for t in tickers if is_hk(t)]

    if not tickers:
        print("⚠ 筛选后无股票可分析")
        return

    if args.summary_only:
        if not args.summary_date:
            print("⚠ --summary-only 需要指定 --summary-date YYYY-MM-DD")
            return
        generate_summary_from_reports(args.summary_date, tickers)
        return

    print(f"📊 批量分析启动 | {len(tickers)} 只股票 | 市场: {args.market or '全部'}")
    parallel = args.parallel and not args.serial
    print(f"   模式: {'交错并发（间隔10s）' if parallel else '串行（最安全）'}")
    print(f"   列表: {', '.join(tickers)}\n")

    results = []
    t_start = time.time()

    if parallel:
        # 交错启动：用线程池并行启动子进程，每只间隔 10 秒错开 akshare 锁
        future_map = {}
        with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
            for i, ticker in enumerate(tickers):
                if i > 0:
                    print(f"   间隔 10 秒后启动 {ticker}...")
                    time.sleep(10)
                future = executor.submit(run_one, ticker, args.date, quiet=(i > 0))
                future_map[future] = ticker

            for future in as_completed(future_map):
                ticker = future_map[future]
                ok, elapsed = future.result()
                results.append((ticker, ok, elapsed))
    else:
        for ticker in tickers:
            ok, elapsed = run_one(ticker, args.date)
            results.append((ticker, ok, elapsed))

    total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  批量分析完成！总耗时: {total/60:.1f} 分钟")
    print(f"{'='*60}")

    summary_date = args.summary_date or args.date or infer_summary_date([ticker for ticker, _ok, _elapsed in results])
    generate_summary(results, total, analysis_date=summary_date)


if __name__ == "__main__":
    main()
