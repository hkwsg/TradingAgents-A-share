"""TradingAgent 港股分析 — 走 yfinance 数据管道"""
import sys
import os
import io
import time
import json
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

# 预初始化 py_mini_racer
try:
    import py_mini_racer
    _racer = py_mini_racer.MiniRacer()
    _racer.eval("1")
    del _racer
except Exception:
    pass

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ============ 参数解析 ============
if len(sys.argv) < 2:
    print("用法: python run_hk.py <港股代码> [交易日期]")
    print("示例: python run_hk.py 0020.HK")
    print("示例: python run_hk.py 9880.HK 2026-05-22")
    sys.exit(1)

TICKER = sys.argv[1].strip()
TRADE_DATE = sys.argv[2].strip() if len(sys.argv) > 2 else date.today().isoformat()
PROJECT_ROOT = Path(__file__).parent
safe_name = TICKER.replace(".", "_")
REPORT_DIR = PROJECT_ROOT / "reports" / f"{safe_name}_{TRADE_DATE}"

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-v4-pro"
config["quick_think_llm"] = "deepseek-v4-flash"
config["selected_analysts"] = ["market", "social", "news", "fundamentals"]
config["max_debate_rounds"] = 3
config["max_risk_discuss_rounds"] = 1
config["data_tools_cache_dir"] = os.path.join(config["project_dir"], "local_data", "data_tools", "cache")
config["data_tools_snapshot_dir"] = os.path.join(config["project_dir"], "local_data", "data_tools", "snapshots")
config["local_data_dir"] = os.path.join(config["project_dir"], "local_data")
config["market_data_dir"] = os.path.join(config["project_dir"], "local_data", "market_tools")
config["checkpoint_enabled"] = True
config["memory_log_path"] = os.path.join(os.path.expanduser("~"), ".tradingagents", "memory", "trading_memory.md")
config["timeout"] = 600
config["output_language"] = "Chinese"
# 港股统一走 yfinance
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

# ============ 运行 ============
print("=" * 60, flush=True)
print(f"  TradingAgent 港股分析启动", flush=True)
print(f"  股票: {TICKER}", flush=True)
print(f"  日期: {TRADE_DATE}", flush=True)
print(f"  模型: {config['quick_think_llm']}", flush=True)
print(f"  数据源: yfinance", flush=True)
print("=" * 60, flush=True)

try:
    print("\n[1/3] 初始化图结构...", flush=True)
    ta = TradingAgentsGraph(debug=False, config=config)

    print("[2/3] 开始分析（流式输出）...", flush=True)
    start_time = time.time()

    init_state = ta.propagator.create_initial_state(TICKER, TRADE_DATE)
    args = ta.propagator.get_graph_args()

    step_count = 0
    final_chunk = None
    for chunk in ta.graph.stream(init_state, **args):
        step_count += 1
        final_chunk = chunk
        elapsed = time.time() - start_time

        active_nodes = [k for k in chunk.keys() if k not in ("messages",)]
        if active_nodes:
            print(f"  [{int(elapsed)}s] 步骤{step_count}: {' → '.join(active_nodes)}", flush=True)

        msgs = chunk.get("messages", [])
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", "")
            if content and isinstance(content, str) and len(content) > 10:
                preview = content[:80].replace("\n", " ")
                print(f"        输出: {preview}...", flush=True)

    elapsed = time.time() - start_time
    print(f"\n[3/3] 分析完成，耗时 {int(elapsed//60)}分{int(elapsed%60)}秒", flush=True)

    final_state = final_chunk

    decision = final_state.get("final_trade_decision", "")
    signal = ta.process_signal(decision)
    print(f"\n最终决策信号: {signal}", flush=True)

    # ============ 报告生成 ============
    REPORT_DIR.mkdir(exist_ok=True)

    report_map = {
        "market_report": "市场技术分析",
        "sentiment_report": "社交媒体情绪分析",
        "news_report": "新闻分析",
        "fundamentals_report": "基本面分析",
    }
    sections = []
    analyst_reports = []
    for key, title in report_map.items():
        if final_state.get(key):
            analyst_reports.append((title, final_state[key]))

    if analyst_reports:
        sections.append("# 一、分析师团队报告\n")
        for title, content in analyst_reports:
            sections.append(f"## {title}\n\n{content}\n")

    if final_state.get("investment_plan"):
        sections.append("# 二、研究团队决策\n")
        sections.append(final_state["investment_plan"])
    debate = final_state.get("investment_debate_state", {})
    if debate:
        if debate.get("bull_history"):
            sections.append("\n### 多头观点\n")
            sections.append(debate["bull_history"])
        if debate.get("bear_history"):
            sections.append("\n### 空头观点\n")
            sections.append(debate["bear_history"])
        if debate.get("judge_decision"):
            sections.append("\n### 研究经理裁决\n")
            sections.append(debate["judge_decision"])

    if final_state.get("trader_investment_plan"):
        sections.append("\n# 三、交易员执行计划\n")
        sections.append(final_state["trader_investment_plan"])

    if final_state.get("final_trade_decision"):
        sections.append("\n# 四、组合经理最终决策\n")
        sections.append(final_state["final_trade_decision"])

    sections.append("\n---\n")
    sections.append(f"**交易信号**: `{signal}`\n")

    complete_report = "\n\n".join(sections)
    report_file = REPORT_DIR / "完整分析报告.md"
    report_file.write_text(complete_report, encoding="utf-8")

    print(f"\n报告已保存: {report_file}", flush=True)

    json_file = REPORT_DIR / "原始数据.json"
    safe_state = {}
    for k, v in final_state.items():
        try:
            json.dumps(v, ensure_ascii=False)
            safe_state[k] = v
        except (TypeError, ValueError):
            safe_state[k] = str(v)[:2000]
    json_file.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {json_file}", flush=True)

    print(f"\n=== DONE {TICKER} ===", flush=True)

except Exception as e:
    print(f"\n错误 {TICKER}: {e}", flush=True)
    import traceback
    traceback.print_exc()
    print(f"\n=== FAILED {TICKER} ===", flush=True)
    sys.exit(1)
