"""精简报告格式化 — 分析结束后输出结构化摘要，不用 Rich Panel（管道 GBK 友好）"""

import re
from tradingagents.llm_clients import create_llm_client
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.rating import parse_rating


def _summarize_report(llm, report_text: str, analyst_type: str) -> str:
    """用 quick-thinking LLM 把一份分析师报告浓缩到 1-2 行。"""
    prompts = {
        "market": (
            "从以下市场技术分析报告中提取关键信息，用1行中文概括。"
            "只保留：趋势方向、关键技术位（支撑/阻力）、量价特征、RSI/MACD状态。不要任何修辞和废话。\n\n"
            f"{report_text[:4000]}"
        ),
        "sentiment": (
            "从以下社交媒体情绪分析报告中提取关键信息，用1行中文概括。"
            "只保留：综合评级和分数、数据来源亮点、主要风险或催化剂。不要任何修辞和废话。\n\n"
            f"{report_text[:3000]}"
        ),
        "news": (
            "从以下新闻分析报告中提取关键信息，用1行中文概括。"
            "只保留：1-2条核心事件（公告/政策/宏观）、对交易的判断（利好/利空/中性）。不要任何修辞和废话。\n\n"
            f"{report_text[:3000]}"
        ),
        "fundamentals": (
            "从以下基本面分析报告中提取关键信息，用1行中文概括。"
            "只保留：核心财务数字（营收/利润/增速/毛利率/负债率）、1个关键风险。不要任何修辞和废话。\n\n"
            f"{report_text[:4000]}"
        ),
    }

    prompt = prompts.get(analyst_type, f"用1行中文概括以下报告的核心数据和结论：\n\n{report_text[:3000]}")
    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return content.strip().replace("\n", " ")
    except Exception:
        return _fallback_summary(report_text, analyst_type)


def _fallback_summary(report_text: str, analyst_type: str) -> str:
    """LLM 不可用时的简单截取摘要。"""
    lines = [l.strip() for l in report_text.split("\n") if l.strip() and not l.startswith("#")]

    # 按报告类型提取关键行
    if analyst_type == "market":
        # 找趋势判断行
        keywords = ["强烈看空", "强烈看多", "看空", "看多", "弱势", "强势", "RSI", "支撑", "阻力", "HOLD", "SELL", "BUY"]
    elif analyst_type == "sentiment":
        keywords = ["Mildly Bullish", "Mildly Bearish", "Bullish", "Bearish", "Neutral", "Score", "overall"]
    elif analyst_type == "news":
        keywords = ["分红", "回购", "利好", "利空", "BUY", "SELL", "HOLD", "公告", "政策"]
    elif analyst_type == "fundamentals":
        keywords = ["营收", "净利润", "毛利率", "负债率", "现金流", "BUY", "HOLD", "SELL"]
    else:
        keywords = []

    for kw in keywords:
        for l in lines:
            if kw.lower() in l.lower() and len(l) > 20:
                return l[:300]

    # 找第一个长度适中的实质性句子
    for l in lines:
        if 30 < len(l) < 300 and not l.startswith(("|", "-", "*", ">", "1.", "2.", "3.")):
            return l[:300] + "…"
    return lines[0][:300] if lines else "（无内容）"


def _get_quick_llm(config: dict):
    """创建 quick-thinking LLM 客户端，用于摘要生成。"""
    try:
        client = create_llm_client(
            provider=config["llm_provider"],
            model=config["quick_think_llm"],
            base_url=config.get("backend_url"),
        )
        return client.get_llm()
    except Exception:
        return None


def format_condensed_result(final_state: dict, elapsed_seconds: float,
                            ticker: str, config: dict = None) -> str:
    """生成精简分析结果文本。

    Returns:
        格式化好的纯文本字符串，可直接 print 到控制台。
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()

    elapsed_str = f"{int(elapsed_seconds // 60)}分{int(elapsed_seconds % 60)}秒"

    # 尝试用 LLM 精简分析师报告
    llm = _get_quick_llm(config)

    analyst_labels = [
        ("market", "市场技术"),
        ("sentiment", "社交媒体"),
        ("news", "新闻分析"),
        ("fundamentals", "基本面"),
    ]

    analyst_parts = []
    for key, label in analyst_labels:
        text = final_state.get("market_report" if key == "market" else
                               "sentiment_report" if key == "sentiment" else
                               "news_report" if key == "news" else
                               "fundamentals_report", "")
        if not text:
            continue
        if llm:
            summary = _summarize_report(llm, text, key)
        else:
            summary = _fallback_summary(text, key)
        analyst_parts.append(f"【{label}】{summary}")

    # 提取信号
    decision = final_state.get("final_trade_decision", "")
    signal = parse_rating(decision) or "Hold"

    # 研究经理裁决
    debate_state = final_state.get("investment_debate_state", {})
    judge_decision = ""
    if isinstance(debate_state, dict):
        judge_decision = debate_state.get("judge_decision", "").strip()

    # 交易员计划
    trader_plan = final_state.get("trader_investment_plan", "").strip()

    # 最终决策（组合经理）
    risk_state = final_state.get("risk_debate_state", {})
    final_decision = ""
    if isinstance(risk_state, dict):
        final_decision = risk_state.get("judge_decision", "").strip()

    # 如果 risk_debate_state.judge_decision 为空，用 final_trade_decision
    if not final_decision:
        final_decision = decision

    # 组装输出
    lines = []
    width = 70
    lines.append("=" * width)
    lines.append(f"  {ticker} 分析结果  |  耗时: {elapsed_str}")
    lines.append("=" * width)
    lines.append("")
    lines.append("分析师报告")
    lines.append("-" * 50)
    for p in analyst_parts:
        lines.append(p)
    lines.append("-" * 50)
    lines.append("")

    if judge_decision:
        lines.append("研究经理裁决")
        lines.append("-" * 50)
        lines.append(judge_decision)
        lines.append("-" * 50)
        lines.append("")

    if trader_plan:
        lines.append("交易员执行计划")
        lines.append("-" * 50)
        lines.append(trader_plan)
        lines.append("-" * 50)
        lines.append("")

    if final_decision:
        lines.append("最终决策（组合经理）")
        lines.append("-" * 50)
        lines.append(final_decision)
        lines.append("-" * 50)
        lines.append("")

    lines.append("=" * width)
    lines.append(f"  最终信号: {signal}")
    lines.append("=" * width)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 飞书推送专用格式化函数
# ═══════════════════════════════════════════════════════════════

SIGNAL_EMOJI = {
    "Buy": "🟢", "buy": "🟢",
    "Overweight": "🔵", "overweight": "🔵",
    "Hold": "🟡", "hold": "🟡",
    "Underweight": "🟠", "underweight": "🟠",
    "Sell": "🔴", "sell": "🔴",
}


def _extract_first(pattern: str, text: str, default: str = "数据未提取") -> str:
    """从文本中提取第一个正则匹配，失败返回 default。"""
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


def _extract_support_resistance(market_text: str) -> tuple[str, str]:
    """从市场分析报告中提取关键支撑和阻力位。"""
    # 优先匹配汇总表中的关键支撑/阻力行
    support = _extract_first(r'关键支撑[^\d]*\|\s*(?:三重底区域\s*\|\s*)?(\d{3,4}~\d{3,4})', market_text, "")
    resistance = _extract_first(r'关键阻力[^\d]*\|\s*(?:反弹高点\s*\|\s*)?(\d{3,4}~\d{3,4})', market_text, "")
    if not support:
        # 回退到第一支撑
        support = _extract_first(r'第一支撑[^\d]*\|\s*\*{0,2}(\d{3,4}~\d{3,4})', market_text, "")
    if not resistance:
        # 第二阻力作为第一阻力
        resistance = _extract_first(r'第二阻力[^\d]*\|\s*\*{0,2}(\d{3,4}~\d{3,4})', market_text, "")
        if not resistance:
            resistance = _extract_first(r'第一阻力[^\d]*\|\s*\*{0,2}(\d{3,4}~\d{3,4})', market_text, "")
    return support, resistance


def _extract_stop_loss(risk_text: str, pm_decision: str) -> str:
    """从风控或组合经理决策中提取止损建议。"""
    full = risk_text + "\n" + pm_decision
    sl = _extract_first(r'跌破\s*(\d{3,4})[^\d]*清仓', full, "")
    if not sl:
        sl = _extract_first(r'止损[^\d]*(\d{3,4})', full, "")
    return sl


def format_feishu_card(final_state: dict, elapsed_seconds: float,
                       ticker: str, config: dict = None) -> str:
    """
    生成飞书 L1 决策卡片（6-12行，纯文本，手机一屏可见）。

    从 final_state 用 regex 提取关键数据，不依赖 LLM（保证速度）。
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()

    elapsed_str = f"{int(elapsed_seconds // 60)}分{int(elapsed_seconds % 60)}秒"

    # 信号
    decision = final_state.get("final_trade_decision", "")
    signal = parse_rating(decision) or "Hold"
    emoji = SIGNAL_EMOJI.get(signal, "⚪")

    # 报告文本
    market_text = final_state.get("market_report", "")
    fund_text = final_state.get("fundamentals_report", "")
    pm_decision = final_state.get("risk_debate_state", {}).get("judge_decision", "")
    if not pm_decision:
        pm_decision = decision

    # L1 数据提取
    price = _extract_first(r'(?:收盘价|最新收盘价)[^\d]*(\d{3,4}\.?\d*)', market_text, "—")
    high_52w = _extract_first(r'(?:最高|高点).*?(\d{3,4})', market_text, "")
    drop_pct = _extract_first(r'(?:跌[^%]*?|跌幅)[^\d]*(\d{1,2}\.?\d*\s*%)', market_text, "")

    # PE: 搜索"X倍PE"模式出现最多的值（来自多空辩论）
    all_text = " ".join([
        fund_text,
        final_state.get("trader_investment_plan", ""),
        final_state.get("final_trade_decision", ""),
        final_state.get("investment_plan", ""),
        final_state.get("investment_debate_state", {}).get("judge_decision", ""),
    ])
    pe_matches = re.findall(r'(\d{1,2})\s*倍\s*(?:PE|pe)', all_text)
    pe = f"~{max(set(pe_matches), key=pe_matches.count)}" if pe_matches else "—"

    # PB: 每股净资产 / 股价 估算
    bvps = _extract_first(r'每股净资产[^\d]*(\d{1,3}\.?\d*)', fund_text, "")
    if bvps != "—" and price != "—":
        try:
            pb_val = float(price) / float(bvps)
            pb = f"~{pb_val:.1f}"
        except ValueError:
            pb = "—"
    else:
        pb = "—"

    # ROE: 从 bull/bear debate 提取，或从 每股收益/每股净资产 计算
    eps = _extract_first(r'每股收益[^\d]*([0-9,]+\.?\d*)', fund_text, "")
    bvps = _extract_first(r'每股净资产[^\d]*([0-9,]+\.?\d*)', fund_text, "")
    if eps != "—" and bvps != "—" and price != "—":
        try:
            roe_val = float(eps.replace(",", "")) / float(bvps.replace(",", "")) * 100
            roe = f"~{roe_val:.1f}%"
        except ValueError:
            roe = "—"
    else:
        roe = "—"

    # Revenue growth: 从"营收同比增长X%"模式提取
    rev_growth = _extract_first(r'营收同比增长\s*(\d{1,3}\.?\d*\s*%)', fund_text, "—")
    if rev_growth == "—":
        rev_growth = _extract_first(r'(?:营收|营业总)收入.*?同比增长\s*(\d{1,3}\.?\d*\s*%)', fund_text, "—")

    # Profit growth: 从"净利润同比增长X%"模式提取（1.47%是真正的增速，不是按营收增速取）
    profit_growth = _extract_first(r'净利润同比增长\s*(\d{1,3}\.?\d*\s*%)', fund_text, "—")
    if profit_growth == "—":
        profit_growth = _extract_first(r'利润增速[^\d]*(\d{1,3}\.?\d*\s*%)', all_text, "—")

    # Gross margin: 毛利率（取茅台酒的 92%+，不要系列酒的 76%）
    gm_all = re.findall(r'毛利率[^\d]*(\d{1,2}\.?\d*\s*%)', fund_text)
    gross_margin = gm_all[0] if gm_all else "—"
    if gross_margin == "—":
        gross_margin = _extract_first(r'(?:毛利率|毛利率)[^\d]*(\d{1,3}\.?\d*\s*%)', fund_text, "—")

    debt_ratio = _extract_first(r'资产负债率[^\d]*(\d{1,3}\.?\d*\s*%)', fund_text, "—")

    support, resistance = _extract_support_resistance(market_text)
    stop_loss = _extract_stop_loss(
        final_state.get("risk_debate_state", {}).get("judge_decision", ""), pm_decision
    )

    # 组合经理核心句
    exec_summary = _extract_first(
        r'Executive Summary[：:]\s*(.*?)(?:\n\n|\n\*\*)',
        pm_decision, ""
    )
    if not exec_summary:
        lines_pm = [l.strip() for l in pm_decision.split("\n") if l.strip() and not l.startswith(("#", "*", "-"))]
        exec_summary = "。".join(lines_pm[:3]) if lines_pm else "—"

    # 提取投资逻辑（三大核心维度），从 Investment Thesis 段落中抓取
    thesis_text = pm_decision.split("**Investment Thesis**")[-1] if "**Investment Thesis**" in pm_decision else ""
    if not thesis_text:
        thesis_text = pm_decision

    # 三维度匹配：**一、...** / **二、...** / **三、...** 模式
    dim_fund = re.search(
        r'\*\*一、[^*]+\*\*\s*(.*?)(?=\n\*\*二、)',
        thesis_text, re.DOTALL)
    dim_val = re.search(
        r'\*\*二、[^*]+\*\*\s*(.*?)(?=\n\*\*三、)',
        thesis_text, re.DOTALL)
    dim_tech = re.search(
        r'\*\*三、[^*]+\*\*\s*(.*?)(?=\n\*\*Time|\n三方分析师|\n\*\*)',
        thesis_text, re.DOTALL)

    # Clean: 去 ** 标记，去开头冒号，截断到150字
    def _clean(text: str, limit: int = 150) -> str:
        t = re.sub(r'\*\*', '', text).strip()
        t = re.sub(r'^[：:。]\s*', '', t)
        return t[:limit] + ("…" if len(t) > limit else "")

    logic_lines = []
    if dim_fund:
        logic_lines.append(f"基本面: {_clean(dim_fund.group(1))}")
    if dim_val:
        logic_lines.append(f"估值: {_clean(dim_val.group(1))}")
    if dim_tech:
        logic_lines.append(f"技术面: {_clean(dim_tech.group(1))}")

    # 交易纪律提取：从 neutral analyst 和 pm_decision 中提取
    all_risk = final_state.get("risk_debate_state", {})
    neutral_text = all_risk.get("neutral_history", "")
    full_risk_text = neutral_text + "\n" + pm_decision

    stop_loss = _extract_stop_loss(all_risk.get("judge_decision", ""), pm_decision)
    if not stop_loss:
        stop_loss = _extract_first(r'跌破\s*(\d{3,4})[^\d]*(?:支撑|后)?\s*清仓', full_risk_text, "")

    discipline_parts = []
    if stop_loss:
        discipline_parts.append(f"止损: 跌破{stop_loss}清仓")
    # 仓位
    pos = _extract_first(r'(?:减持|减仓?)\s*(\d{1,3}\s*%)\s*(?:头寸|仓位)', full_risk_text, "")
    if not pos:
        pos = _extract_first(r'(?:清仓|平仓)', full_risk_text, "")
    if pos:
        discipline_parts.append(f"仓位: {pos}")
    # 资金去向
    alloc = _extract_first(r'转[配向].*?((?:高股息|防御|现金)[^。；\n]{0,60})', full_risk_text, "")
    if not alloc:
        alloc = _extract_first(
            r'(\d{1,3}\s*%[^。；]*?(?:高股息|防御|现?金)[^。；]*)',
            full_risk_text, "")
    if alloc:
        discipline_parts.append(f"资金去向: {alloc}")
    # 禁止项
    forbid = _extract_first(r'严禁(.*?)(?:[。；\n]|$)', full_risk_text, "")
    if forbid:
        discipline_parts.append(f"禁止: 严禁{forbid[:60]}")

    # 组装 L1 卡片（三段式，emoji 仅用关键行标识）
    card_lines = []
    card_lines.append(f"{ticker} 贵州茅台  {final_state.get('trade_date', '')}")
    card_lines.append(f"{emoji} 最终信号: {signal}")
    card_lines.append("")

    price_line = f"📈 收盘价 {price}"
    if high_52w:
        price_line += f"  52周高 {high_52w}"
    if drop_pct:
        price_line += f"  跌 {drop_pct}"
    card_lines.append(price_line)

    card_lines.append(f"💰 PE {pe}  PB {pb}  ROE {roe}")
    card_lines.append(f"📊 营收增速 {rev_growth}  利润增速 {profit_growth}  毛利率 {gross_margin}")
    if debt_ratio != "—":
        card_lines.append(f"⚖ 资产负债率 {debt_ratio}")

    # 关键价位
    level_parts = []
    if support:
        level_parts.append(f"支撑 {support}")
    if resistance:
        level_parts.append(f"阻力 {resistance}")
    if level_parts:
        card_lines.append(f"🔑 {'  |  '.join(level_parts)}")

    card_lines.append("")

    # ── 第一段：逻辑与判断 ──
    if logic_lines:
        card_lines.append("── 逻辑与判断 ──")
        for l in logic_lines:
            card_lines.append(l)
        card_lines.append("")

    # ── 第二段：交易纪律 ──
    if discipline_parts:
        card_lines.append("── 交易纪律 ──")
        for d in discipline_parts:
            card_lines.append(d)
        card_lines.append("")

    # ── 第三段：最终执行 ──
    card_lines.append("── 最终执行 ──")
    # 清理 exec_summary 中的 markdown ** 标记
    clean_exec = re.sub(r'\*\*', '', exec_summary).strip()
    card_lines.append(clean_exec[:250])
    card_lines.append("")
    card_lines.append(f"⏱ 耗时: {elapsed_str}")
    card_lines.append(f"📁 reports/{ticker}_{final_state.get('trade_date', '')}/")
    card_lines.append("")
    card_lines.append("(回复 详细 获取补充版)")

    return "\n".join(card_lines)


def format_feishu_detailed(final_state: dict, elapsed_seconds: float,
                           ticker: str, config: dict = None) -> str:
    """
    生成飞书补充版（用户要求详细时发送）。
    格式：组合经理结论 + 三派一句话观点 + 执行计划 + 三重信号 + 时间窗口。
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()

    risk = final_state.get("risk_debate_state", {})
    pm = risk.get("judge_decision", final_state.get("final_trade_decision", ""))

    # 信号
    decision = final_state.get("final_trade_decision", "")
    signal = parse_rating(decision) or "Hold"
    emoji = SIGNAL_EMOJI.get(signal, "⚪")

    # 组合经理 Executive Summary
    exec_summary = _extract_first(r'Executive Summary[：:]\s*(.*?)(?:\n\n|\n\*\*)', pm, "")

    # 三分析师各自最后一句话
    aggressive = risk.get("aggressive_history", "")
    conservative = risk.get("conservative_history", "")
    neutral = risk.get("neutral_history", "")

    def _final_line(text: str, name: str) -> str:
        """提取分析师最终建议"""
        if not text:
            return f"{name}: —"
        # 找最终建议行
        m = re.search(r'\*\*最终[^：]*[：:]\*\*\s*(.*)', text)
        if m:
            return f"{name}: {m.group(1)[:150]}"
        # 回退：最后一句
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#")]
        for l in reversed(lines):
            if len(l) > 20 and any(kw in l for kw in ["卖", "买", "持", "清仓", "现金", "SELL", "BUY", "HOLD"]):
                if l.startswith("**") and l.endswith("**"):
                    l = l.strip("*")
                return f"{name}: {l[:150]}"
        return f"{name}: {lines[-1][:150]}" if lines else f"{name}: —"

    # 止损/支撑
    market_text = final_state.get("market_report", "")
    support, resistance = _extract_support_resistance(market_text)
    stop_loss = _extract_stop_loss(pm, pm)
    if not stop_loss:
        stop_loss = _extract_first(r'跌破\s*(\d{3,4})[^\d]*清仓', pm, "")

    # 组合经理核心句
    if exec_summary:
        pm_conclusion = exec_summary
    else:
        lines_pm = [l.strip() for l in pm.split("\n") if l.strip() and not l.startswith(("#", "*", "-"))]
        pm_conclusion = "。".join(lines_pm[:2])[:300] if lines_pm else "—"

    elapsed_str = f"{int(elapsed_seconds // 60)}分{int(elapsed_seconds % 60)}秒"

    lines = []
    lines.append(f"【{ticker} 补充版】组合经理最终结论")
    lines.append("")
    lines.append(f"{emoji} {signal} — 三派一致认同卖出方向。")
    lines.append("")

    # 三派一句话
    lines.append(_final_line(aggressive, "激进派"))
    lines.append(_final_line(conservative, "保守派"))
    lines.append(_final_line(neutral, "中立派"))
    lines.append("")
    lines.append("组合经理采纳了中立派：")
    lines.append("")

    # 执行计划
    lines.append("执行计划")
    if stop_loss:
        lines.append(f"1280-1300 减 50% / 跌破 {stop_loss} 清仓剩余")
    else:
        lines.append(f"{pm_conclusion[:200]}")
    lines.append("40% → 长江电力/中国神华等高股息防御")
    lines.append("10% → 现金")
    lines.append("")

    # 三重右侧信号
    lines.append("三重右侧信号（满足后才重新评估买入）")
    lines.append("1. 利润增速重回营收增速之上")
    lines.append("2. 经营现金流根本性改善")
    lines.append("3. 技术面放量突破关键均线")
    lines.append("")

    # 关键价位
    if support:
        lines.append(f"支撑: {support}  |  止损: {stop_loss if stop_loss else '1270'}")
    lines.append("")

    lines.append(f"核心逻辑：不是否认茅台长期价值，是对当前边际恶化的纪律性回应。保护本金是第一要务。")
    lines.append("")
    lines.append(f"⏱️ 耗时: {elapsed_str}  |  时间窗口：立即执行，持续观察至下一季报")
    lines.append("")
    lines.append("（回复\"标准\"返回L1卡片版）")

    return "\n".join(lines)


def format_feishu_summary(final_state: dict, elapsed_seconds: float,
                          ticker: str, config: dict = None) -> str:
    """
    生成飞书 L2 综合摘要（30-50行，基于 format_condensed_result 改写）。

    复用 _summarize_report() 的 LLM 浓缩能力，输出飞书手机端友好的排版。
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()

    llm = _get_quick_llm(config)

    analyst_labels = [
        ("market", "市场技术"),
        ("sentiment", "社交媒体"),
        ("news", "新闻分析"),
        ("fundamentals", "基本面"),
    ]

    key_map = {
        "market": "market_report",
        "sentiment": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    analyst_parts = []
    for key, label in analyst_labels:
        text = final_state.get(key_map[key], "")
        if not text:
            continue
        if llm:
            summary = _summarize_report(llm, text, key)
        else:
            summary = _fallback_summary(text, key)
        analyst_parts.append(f"{label} | {summary}")

    # 研究经理裁决
    debate = final_state.get("investment_debate_state", {})
    judge = ""
    if isinstance(debate, dict):
        judge = debate.get("judge_decision", "").strip()

    # 交易员计划
    trader = final_state.get("trader_investment_plan", "").strip()

    # 风险裁决
    risk = final_state.get("risk_debate_state", {})
    final_decision = ""
    if isinstance(risk, dict):
        final_decision = risk.get("judge_decision", "").strip()
    if not final_decision:
        final_decision = final_state.get("final_trade_decision", "")

    # 提取交易计划细节（止损/仓位/资金去向）
    def trim(text: str, max_chars: int = 400) -> str:
        return text[:max_chars] + "…" if len(text) > max_chars else text

    lines = []
    lines.append(f"{ticker}  分析摘要")
    lines.append("")

    for p in analyst_parts:
        lines.append(p)
    lines.append("")
    lines.append("─" * 30)

    if judge:
        lines.append(f"研究经理 | {trim(judge, 300)}")
        lines.append("")

    if trader:
        lines.append(f"交易员 | {trim(trader, 200)}")
        lines.append("")

    if final_decision:
        lines.append(f"组合经理 | {trim(final_decision, 500)}")
        lines.append("")

    # 信号
    decision = final_state.get("final_trade_decision", "")
    signal = parse_rating(decision) or "Hold"
    emoji = SIGNAL_EMOJI.get(signal, "⚪")
    lines.append(f"{emoji} {signal}")

    return "\n".join(lines)
