"""TradingAgents 批量分析 — 串行跑 .watchlist.json 中所有股票

用法:
    py run_batch.py                  # 分析"我"的所有股票（A股用run_single.py，港股用run_hk.py）
    py run_batch.py --market A       # 仅A股
    py run_batch.py --market HK      # 仅港股
    py run_batch.py --person 我      # 指定人物（默认"我"）
    py run_batch.py --tickers 600519,600036   # 直接指定代码列表
"""
import os, sys, io, json, time, argparse, subprocess
from datetime import date
from pathlib import Path

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


def run_one(ticker, market_date=None):
    """运行单只股票分析，返回(成功, 耗时秒)"""
    env = os.environ.copy()
    env["PYMINIRACER_V8_SINGLE_THREAD"] = "1"
    env["PYMINIRACER_DISABLE_CONFIGURE_POOL"] = "1"

    script = "run_hk.py" if is_hk(ticker) else "run_single.py"
    cmd = [VENV_PYTHON, str(PROJ / script), ticker]
    if market_date:
        cmd.append(market_date)

    print(f"\n{'='*60}")
    print(f"  开始分析: {ticker}  ({'港股' if is_hk(ticker) else 'A股'})")
    print(f"  命令: {' '.join(cmd)}")
    print(f"{'='*60}")

    t0 = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(PROJ), env=env, capture_output=False, timeout=1800)
        elapsed = time.time() - t0
        ok = result.returncode == 0
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


def generate_summary(results, total_time):
    """生成批量分析汇总简报"""
    today = date.today().isoformat()
    summary_path = PROJ / "reports" / f"批量分析_{today}.md"

    lines = [
        f"# 批量分析汇总 — {today}",
        "",
        f"**总耗时**: {total_time/60:.1f} 分钟 | **总数**: {len(results)} 只",
        "",
        "| 代码 | 结果 | 耗时 | 报告路径 |",
        "|------|------|------|----------|",
    ]

    success = 0
    for ticker, ok, elapsed in results:
        status = "✅" if ok else "❌"
        report_dir = PROJ / "reports"
        # 查找最新的报告目录
        dirs = sorted([d for d in report_dir.iterdir() if d.is_dir() and d.name.startswith(ticker)],
                     key=lambda d: d.stat().st_mtime, reverse=True)
        path = dirs[0].name if dirs else "—"
        lines.append(f"| {ticker} | {status} | {elapsed/60:.1f}min | {path} |")
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
                report_dirs = sorted(
                    [d for d in (PROJ / "reports").iterdir() if d.name.startswith(ticker) and d.is_dir()],
                    key=lambda d: d.stat().st_mtime, reverse=True
                )
                if report_dirs:
                    json_path = report_dirs[0] / "原始数据.json"
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
                "elapsed": f"{elapsed/60:.1f}min"
            }))
        push_batch_summary(push_results, total_time)
    except Exception as e:
        print(f"[飞书推送失败] {e}")

    return summary_path


def main():
    parser = argparse.ArgumentParser(description="TradingAgents 批量分析")
    parser.add_argument("--market", choices=["A", "HK"], help="市场筛选：A=仅A股，HK=仅港股")
    parser.add_argument("--person", default="我", help="关注列表中的人物（默认'我'）")
    parser.add_argument("--tickers", help="直接指定代码列表，逗号分隔（如 600519,600036）")
    parser.add_argument("--date", default=None, help="交易日期 YYYY-MM-DD")
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

    print(f"📊 批量分析启动 | {len(tickers)} 只股票 | 市场: {args.market or '全部'}")
    print(f"   列表: {', '.join(tickers)}")
    print(f"   模式: 串行（akshare连接池限制）\n")

    results = []
    t_start = time.time()
    for ticker in tickers:
        ok, elapsed = run_one(ticker, args.date)
        results.append((ticker, ok, elapsed))

    total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  批量分析完成！总耗时: {total/60:.1f} 分钟")
    print(f"{'='*60}")

    generate_summary(results, total)


if __name__ == "__main__":
    main()
