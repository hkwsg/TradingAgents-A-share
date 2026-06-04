#!/usr/bin/env python3
"""
飞书推送编排脚本 — 调用 report_formatter 生成内容 + reply.py 发送

职责：编排推送流程，不包含格式化逻辑。
     L0: 开始通知
     L1: 决策卡片（format_feishu_card）
     L2: 综合摘要（format_feishu_summary）
     L3: PDF 完整报告（用户主动要才发）

用法：
  py cli/feishu_push.py card <ticker>       # 测试 L1 卡片
  py cli/feishu_push.py summary <ticker>    # 测试 L2 摘要
  py cli/feishu_push.py send <ticker>       # 完整推送（L1+L2）

环境变量：
  FEISHU_OPEN_ID  — 覆盖默认接收者 open_id
  FEISHU_PUSH_ENABLED=0 — 禁用推送
"""

import json
import os
import subprocess
import sys

# 用户 open_id（必须通过环境变量 FEISHU_OPEN_ID 设置，否则推送跳过）
DEFAULT_OPEN_ID = None

# reply.py 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPLY_PY = os.path.join(SCRIPT_DIR, "..", "..", "飞书集成", "feishu-bot", "reply.py")
REPLY_PY = os.path.abspath(REPLY_PY)

# TradingAgents-A-share 根目录
TA_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


def get_open_id() -> str:
    return os.environ.get("FEISHU_OPEN_ID", DEFAULT_OPEN_ID)


def push_enabled() -> bool:
    return os.environ.get("FEISHU_PUSH_ENABLED", "1") != "0"


def _call_reply(cmd: str, open_id: str, text: str = None, file_path: str = None) -> dict:
    """调用 reply.py 子命令，返回 {"ok": bool, ...}"""
    args = ["py", REPLY_PY, cmd, open_id]
    if text is not None:
        args.append(text)
    if file_path is not None:
        args.append(file_path)
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            timeout=90, cwd=TA_ROOT)
        return json.loads(result.stdout)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def push_start_notification(ticker: str, open_id: str = None) -> dict:
    """L0: 分析开始通知"""
    if not push_enabled():
        return {"ok": False, "error": "推送已禁用"}
    oid = open_id or get_open_id()
    text = f"分析开始  {ticker} 预计 5-8 分钟完成"
    return _call_reply("send", oid, text)


def push_analysis_result(final_state: dict, elapsed_seconds: float,
                         ticker: str, config: dict = None,
                         open_id: str = None) -> dict:
    """L1+L2: 分析完成推送"""
    if not push_enabled():
        return {"ok": False, "error": "推送已禁用"}

    oid = open_id or get_open_id()

    # 延迟导入
    sys.path.insert(0, os.path.join(TA_ROOT, "cli"))
    from report_formatter import format_feishu_card, format_feishu_summary

    # L1 决策卡片
    card_text = format_feishu_card(final_state, elapsed_seconds, ticker, config)
    r1 = _call_reply("send-chunked", oid, card_text)

    return {"ok": r1.get("ok"), "layers_sent": ["L1"],
            "l1": r1}


def push_detailed(final_state: dict, elapsed_seconds: float,
                  ticker: str, config: dict = None,
                  open_id: str = None) -> dict:
    """补充版推送：组合经理完整结论 + 三分析师观点"""
    if not push_enabled():
        return {"ok": False, "error": "推送已禁用"}

    oid = open_id or get_open_id()

    sys.path.insert(0, os.path.join(TA_ROOT, "cli"))
    from report_formatter import format_feishu_detailed

    text = format_feishu_detailed(final_state, elapsed_seconds, ticker, config)
    return _call_reply("send-chunked", oid, text)


def push_batch_summary(results: list, total_time: float,
                       open_id: str = None) -> dict:
    """批量分析完成汇总推送"""
    if not push_enabled():
        return {"ok": False, "error": "推送已禁用"}
    if not results:
        return {"ok": False, "error": "无结果"}

    oid = open_id or get_open_id()
    total_min = f"{int(total_time // 60)}.{int(total_time % 60 // 6)}"
    ok_count = sum(1 for r in results if r[1].get("ok", True))

    lines = [f"批量分析完成  总耗时: {total_min}min  |  {ok_count}/{len(results)} 成功", ""]

    signal_emoji = {"Buy": "🟢", "Hold": "🟡", "Sell": "🔴",
                    "Overweight": "🔵", "Underweight": "🟠"}

    for r in results:
        ticker = r[0]
        info = r[1] if len(r) > 1 else {}
        signal = info.get("signal", "—")
        emoji = signal_emoji.get(signal, "⚪")
        elapsed = info.get("elapsed", "?")
        lines.append(f"{ticker}  {emoji} {signal}  {elapsed}")

    return _call_reply("send-chunked", oid, "\n".join(lines))


def push_l3_report(report_dir: str, ticker: str, trade_date: str,
                   open_id: str = None) -> dict:
    """L3: 推送完整报告文件（PDF 或 Markdown）"""
    if not push_enabled():
        return {"ok": False, "error": "推送已禁用"}

    oid = open_id or get_open_id()
    dir_path = os.path.abspath(report_dir)
    md_file = os.path.join(dir_path, "complete_report.md")
    pdf_file = os.path.join(dir_path, f"{ticker}_{trade_date}_报告.pdf")

    # 优先找已有 PDF
    if os.path.exists(pdf_file):
        return _call_reply("send-file", oid, file_path=pdf_file)

    # 降级：尝试转 PDF
    try:
        import subprocess as sp
        result = sp.run(
            ["py", "-c",
             f"from fpdf import FPDF; import sys; "
             f"pdf=FPDF(); pdf.add_font('SimHei','','C:/Windows/Fonts/simhei.ttf',uni=True); "
             f"pdf.add_page(); pdf.set_font('SimHei','',10); "
             f"with open(r'{md_file}','r',encoding='utf-8') as f: text=f.read()[:50000]; "
             f"for line in text.split('\\n'): "
             f"  try: pdf.cell(0,6,line[:200]); pdf.ln(); except: pdf.ln(); "
             f"pdf.output(r'{pdf_file}')"],
            capture_output=True, text=True, timeout=60, cwd=os.path.dirname(dir_path))
        if result.returncode == 0 and os.path.exists(pdf_file):
            return _call_reply("send-file", oid, file_path=pdf_file)
    except Exception:
        pass

    # 最终降级：发送 markdown 原文文件
    if os.path.exists(md_file):
        return _call_reply("send-file", oid, file_path=md_file)

    return {"ok": False, "error": "报告文件不存在"}


# ── CLI 测试入口 ──

if __name__ == "__main__":
    import json as _json

    if len(sys.argv) < 2:
        print("用法: py feishu_push.py card|summary|send|batch|report <ticker>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd in ("card", "summary", "send"):
        ticker = sys.argv[2] if len(sys.argv) > 2 else "600519"

        # 加载最新报告数据
        reports_base = os.path.join(TA_ROOT, "reports")
        dirs = sorted([d for d in os.listdir(reports_base) if d.startswith(ticker)], reverse=True)
        if not dirs:
            print(f"未找到 {ticker} 的报告")
            sys.exit(1)

        report_dir = os.path.join(reports_base, dirs[0])
        json_path = os.path.join(report_dir, "原始数据.json")

        if not os.path.exists(json_path):
            print(f"未找到: {json_path}")
            sys.exit(1)

        with open(json_path, "r", encoding="utf-8") as f:
            final_state = _json.load(f)

        # 注入默认值（兼容测试）
        if "risk_debate_state" not in final_state:
            final_state["risk_debate_state"] = {}
        if "trade_date" not in final_state:
            final_state["trade_date"] = dirs[0].split("_")[-1]

        elapsed = 450  # 模拟 7分30秒

        if cmd == "card":
            from report_formatter import format_feishu_card
            print(format_feishu_card(final_state, elapsed, ticker))
        elif cmd == "summary":
            from report_formatter import format_feishu_summary
            print(format_feishu_summary(final_state, elapsed, ticker))
        elif cmd == "send":
            result = push_analysis_result(final_state, elapsed, ticker)
            print(_json.dumps(result, ensure_ascii=False))

    elif cmd == "batch":
        # 测试批量汇总
        results = [
            ("600519", {"signal": "Sell", "elapsed": "7.5min"}),
            ("600036", {"signal": "Hold", "elapsed": "6.2min"}),
            ("601899", {"signal": "Buy", "elapsed": "5.8min"}),
        ]
        result = push_batch_summary(results, 1200)
        print(_json.dumps(result, ensure_ascii=False))

    elif cmd == "report":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "600519"
        reports_base = os.path.join(TA_ROOT, "reports")
        dirs = sorted([d for d in os.listdir(reports_base) if d.startswith(ticker)], reverse=True)
        if dirs:
            report_dir = os.path.join(reports_base, dirs[0])
            date = dirs[0].split("_")[-1]
            result = push_l3_report(report_dir, ticker, date)
            print(_json.dumps(result, ensure_ascii=False))
        else:
            print(f"未找到 {ticker} 的报告")

    else:
        print(f"未知命令: {cmd}")
