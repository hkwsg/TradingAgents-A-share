"""TradingAgent A股分析脚本 — 监控运行 + 报告输出到桌面"""
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

# 预初始化 py_mini_racer，避免 LangGraph 并发调用时竞态崩溃
try:
    import py_mini_racer
    _racer = py_mini_racer.MiniRacer()
    _racer.eval("1")
    del _racer
except Exception:
    pass

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.a_share_common import get_previous_trade_date

# ============ 配置 ============
TICKER = "600519"        # A股代码：贵州茅台
TRADE_DATE = get_previous_trade_date(date.today().isoformat())  # 最近一个交易日
DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"
config["quick_think_llm"] = "deepseek-chat"
config["selected_analysts"] = ["market", "social", "news", "fundamentals"]
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["timeout"] = 600
config["output_language"] = "Chinese"
config["data_vendors"] = {
    "core_stock_apis": "akshare",
    "technical_indicators": "akshare",
    "fundamental_data": "akshare",
    "news_data": "akshare",
}

# ============ 运行 ============
print("=" * 60, flush=True)
print(f"  TradingAgent A股分析启动", flush=True)
print(f"  股票: {TICKER}", flush=True)
print(f"  日期: {TRADE_DATE}", flush=True)
print(f"  快速模型: {config['quick_think_llm']}", flush=True)
print(f"  深度模型: {config['deep_think_llm']}", flush=True)
print(f"  超时: {config['timeout']}秒", flush=True)
print("=" * 60, flush=True)

try:
    print("\n[1/3] 初始化图结构...", flush=True)
    ta = TradingAgentsGraph(debug=False, config=config)

    print("[2/3] 开始分析（流式输出）...", flush=True)
    start_time = time.time()

    # 使用流式模式输出进度
    init_state = ta.propagator.create_initial_state(TICKER, TRADE_DATE)
    args = ta.propagator.get_graph_args()

    step_count = 0
    for chunk in ta.graph.stream(init_state, **args):
        step_count += 1
        elapsed = time.time() - start_time

        # 识别当前活跃的节点
        active_nodes = [k for k in chunk.keys() if k not in ("messages",)]
        if active_nodes:
            print(f"  [{int(elapsed)}s] 步骤{step_count}: {' → '.join(active_nodes)}", flush=True)

        # 显示LLM消息摘要
        msgs = chunk.get("messages", [])
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", "")
            if content and isinstance(content, str) and len(content) > 10:
                preview = content[:80].replace("\n", " ")
                print(f"        输出预览: {preview}...", flush=True)

    elapsed = time.time() - start_time
    print(f"\n[3/3] 分析完成，耗时 {int(elapsed//60)}分{int(elapsed%60)}秒", flush=True)

    # 获取最终状态
    final_state = chunk  # 最后一个chunk就是最终状态

    # 提取决策
    decision = final_state.get("final_trade_decision", "")
    print(f"\n最终决策信号: {ta.process_signal(decision)}", flush=True)

    # ============ 报告生成 ============
    report_dir = DESKTOP / f"TradingAgent报告_{TICKER}_{TRADE_DATE}"
    report_dir.mkdir(exist_ok=True)

    sections = []

    # 分析师报告
    analyst_reports = []
    if final_state.get("final_market_report"):
        analyst_reports.append(("市场技术分析", final_state["final_market_report"]))
    if final_state.get("final_sentiment_report"):
        analyst_reports.append(("社交媒体情绪分析", final_state["final_sentiment_report"]))
    if final_state.get("final_news_report"):
        analyst_reports.append(("新闻分析", final_state["final_news_report"]))
    if final_state.get("final_fundamentals_report"):
        analyst_reports.append(("基本面分析", final_state["final_fundamentals_report"]))

    if analyst_reports:
        sections.append("# 一、分析师团队报告\n")
        for title, content in analyst_reports:
            sections.append(f"## {title}\n\n{content}\n")

    # 研究团队决策
    if final_state.get("final_investment_plan_report"):
        sections.append("# 二、研究团队决策\n")
        sections.append(final_state["final_investment_plan_report"])

        # 辩论详情
        debate = final_state.get("investment_debate_state", {})
        if debate.get("bull_history") or debate.get("bear_history"):
            sections.append("\n### 多头观点\n")
            sections.append(debate.get("bull_history", ""))
            sections.append("\n### 空头观点\n")
            sections.append(debate.get("bear_history", ""))
            if debate.get("judge_decision"):
                sections.append("\n### 研究经理裁决\n")
                sections.append(debate.get("judge_decision", ""))

    # 交易员计划
    if final_state.get("final_trader_investment_plan_report"):
        sections.append("\n# 三、交易员执行计划\n")
        sections.append(final_state["final_trader_investment_plan_report"])

    # 组合经理最终决策
    if final_state.get("final_trade_decision_report"):
        sections.append("\n# 四、组合经理最终决策\n")
        sections.append(final_state["final_trade_decision_report"])

    # 信号提取
    sections.append("\n---\n")
    sections.append(f"**提取的交易信号**: `{ta.process_signal(decision)}`\n")

    # 写入完整报告
    complete_report = "\n\n".join(sections)
    report_file = report_dir / "完整分析报告.md"
    report_file.write_text(complete_report, encoding="utf-8")

    print(f"\n✓ 报告已保存至: {report_file}", flush=True)
    print(f"✓ 文件夹: {report_dir}", flush=True)

    # 也保存一份JSON原始数据
    json_file = report_dir / "原始数据.json"
    safe_state = {}
    for k, v in final_state.items():
        try:
            json.dumps(v, ensure_ascii=False)
            safe_state[k] = v
        except (TypeError, ValueError):
            safe_state[k] = str(v)[:2000]
    json_file.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ JSON原始数据: {json_file}", flush=True)

except Exception as e:
    print(f"\n✗ 运行失败: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
