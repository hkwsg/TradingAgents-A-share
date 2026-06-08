from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


Section = tuple[str, list[str], str]
TITLE_PATTERN = re.compile(
    r"^(?:[📊🧠📈📉🔴🟢🎯🛑💡]\s*)?"
    r"(最终评级|一句话结论|好的一面|坏的一面|执行方案|什么时候能买|止损线|组合经理原话)"
)
REPORT_DIR_PATTERN = re.compile(r"^(?P<code>\d{6})(?:_\d{4}-\d{2}-\d{2})?$")


def parse_card(md: str) -> tuple[list[tuple[str, str, str]], list[Section]]:
    chunks = [
        [line.rstrip() for line in chunk.splitlines() if line.strip()]
        for chunk in re.split(r"\n?━{8,}\n?", md)
        if chunk.strip()
    ]

    def is_title(line: str) -> bool:
        return bool(TITLE_PATTERN.match(line.strip()))

    header_lines = chunks[0] if chunks else []
    metrics: list[tuple[str, str, str]] = []
    known_labels = ("分析日期", "当前价格", "距前高", "时间维度")
    for raw in header_lines:
        line = raw.strip()
        if not line:
            continue
        icon = line[0]
        rest = line[1:].strip()
        label = ""
        value = rest
        for candidate in known_labels:
            if rest.startswith(candidate):
                label = candidate
                value = rest[len(candidate) :].strip()
                break
        metrics.append((icon, label, value))

    sections: list[Section] = []
    i = 1
    while i < len(chunks):
        chunk = chunks[i]
        if not chunk:
            i += 1
            continue
        title = chunk[0].strip()
        body = [line.rstrip() for line in chunk[1:] if line.strip()]

        if is_title(title) and not body and i + 1 < len(chunks) and not is_title(chunks[i + 1][0].strip()):
            body = [line.rstrip() for line in chunks[i + 1] if line.strip()]
            i += 1
        elif not is_title(title):
            i += 1
            continue

        kind = "neutral"
        if "好的一面" in title:
            kind = "green"
        elif "坏的一面" in title or title.startswith("🛑"):
            kind = "red"
        elif "执行方案" in title:
            kind = "action"
        elif "什么时候能买" in title:
            kind = "buy"
        elif "组合经理" in title:
            kind = "quote"
        sections.append((title, body, kind))
        i += 1
    return metrics, sections


def css_class_for_line(line: str) -> str:
    if line.startswith(("✅", "🟢")):
        return "good"
    if line.startswith(("🔻", "🔴")):
        return "bad"
    if line.startswith("🔵"):
        return "watch"
    if re.match(r"^[1-4]️⃣", line):
        return "signal"
    return ""


def clean_display_text(text: str) -> str:
    text = re.sub(r"^[📅💰📉⏱📊🧠📈🔴🔵🟢🎯🛑💡✅🔻]\s*", "", text)
    text = re.sub(r"^[1-4]️⃣\s*", lambda m: m.group(0).replace("️⃣", "."), text)
    return text


def line_marker(line: str) -> str:
    if line.startswith("✅"):
        return "✅"
    if line.startswith("🟢"):
        return "🟢"
    if line.startswith("🔻"):
        return "🔻"
    if line.startswith("🔴"):
        return "🔴"
    if line.startswith("🔵"):
        return "🔵"
    match = re.match(r"^([1-4])️⃣", line)
    if match:
        return match.group(1) + "️⃣"
    return ""


def display_section_title(title: str, kind: str) -> str:
    if kind == "buy":
        return re.sub(r"^[🟢🎯]?", "🎯", title, count=1)
    return title


def stock_identity_from_path(md_path: Path) -> tuple[str, str]:
    code_match = REPORT_DIR_PATTERN.match(md_path.parent.name)
    code = code_match.group("code") if code_match else ""
    name = re.sub(r"_?资料卡$", "", md_path.stem)

    inline_match = re.search(r"(?P<code>\d{6})[）)]?(?P<name>[\u4e00-\u9fffA-Za-z0-9]+)?", md_path.stem)
    if not code and inline_match:
        code = inline_match.group("code")
    if not name and inline_match and inline_match.group("name"):
        name = inline_match.group("name")

    return code or "------", name or md_path.stem


def rating_from_title(title: str) -> tuple[str, str]:
    label = clean_display_text(title)
    if "：" in label:
        label = label.split("：", 1)[-1].strip()
    elif ":" in label:
        label = label.split(":", 1)[-1].strip()
    label = label or "未评级"
    rating_en = re.split(r"[（(]", label, 1)[0].strip() or label
    return label, rating_en


def first_price_text(*texts: str) -> str:
    for text in texts:
        match = re.search(r"¥\s*[0-9][0-9,.]*", text)
        if match:
            return match.group(0).replace(" ", "")
    return ""


def find_section(sections: list[Section], keyword: str) -> Section | None:
    for section in sections:
        if keyword in section[0]:
            return section
    return None


def render_section(section: Section, extra_class: str = "") -> str:
    title, body, kind = section
    lines = "\n".join(
        (
            f'<p class="{css_class_for_line(line)}">'
            f'<span class="marker">{html.escape(line_marker(line))}</span>'
            f'<span>{html.escape(clean_display_text(line).strip())}</span>'
            f"</p>"
        )
        for line in body
    )
    return f"""
    <section class="section {kind} {extra_class}">
      <h2>{html.escape(display_section_title(title, kind))}</h2>
      <div class="body">{lines}</div>
    </section>
    """


def render_html(md_path: Path, out_path: Path) -> None:
    md = md_path.read_text(encoding="utf-8")
    metrics, sections = parse_card(md)
    stock_code, stock_name = stock_identity_from_path(md_path)

    metric_html = "\n".join(
        f"""
        <div class="metric">
          <div class="metric-label">{html.escape(icon)} {html.escape(label)}</div>
          <div class="metric-value">{html.escape(value)}</div>
        </div>
        """
        for icon, label, value in metrics[:4]
    )
    metric_lookup = {label: value for _, label, value in metrics}

    rating = find_section(sections, "最终评级")
    conclusion = find_section(sections, "一句话结论")
    good = find_section(sections, "好的一面")
    bad = find_section(sections, "坏的一面")
    action = find_section(sections, "执行方案")
    buy = find_section(sections, "什么时候能买")
    stop = find_section(sections, "止损线")
    quote = find_section(sections, "组合经理")

    used_ids = {
        id(item)
        for item in (rating, conclusion, good, bad, action, buy, stop, quote)
        if item
    }
    unused = [section for section in sections if id(section) not in used_ids]

    rating_title = rating[0] if rating else "📊 最终评级：Underweight（减持/低配）"
    rating_body = rating[1] if rating else []
    rating_label, rating_en = rating_from_title(rating_title)
    conclusion_title = conclusion[0] if conclusion else "🧠 一句话结论"
    conclusion_body = conclusion[1] if conclusion else []

    summary_html = f"""
    <section class="summary">
      <div class="verdict">
        <div class="eyebrow">Decision</div>
        <h2>{html.escape(rating_title)}</h2>
        {''.join(f'<p>{html.escape(clean_display_text(line))}</p>' for line in rating_body)}
      </div>
      <div class="thesis">
        <div class="eyebrow">Thesis</div>
        <h2>{html.escape(conclusion_title)}</h2>
        {''.join(f'<p>{html.escape(line)}</p>' for line in conclusion_body)}
      </div>
    </section>
    """

    single_flow_html = f"""
    <div class="single-flow">
      {render_section(good, "dense research-table") if good else ""}
      {render_section(bad, "dense research-table") if bad else ""}
      {render_section(action) if action else ""}
      {render_section(buy, "compact research-table") if buy else ""}
      {render_section(stop, "compact") if stop else ""}
    </div>
    """

    body_html = (
        summary_html
        + single_flow_html
        + (render_section(quote) if quote else "")
        + "\n".join(render_section(section) for section in unused)
    )
    stop_value = ""
    if stop:
        stop_value = first_price_text(stop[0], *stop[1])

    rating_table_html = f"""
      <div class="rating-table">
        <div><span>Rating</span><strong>{html.escape(rating_en)}</strong></div>
        <div><span>Price</span><strong>{html.escape(metric_lookup.get("当前价格", ""))}</strong></div>
        <div><span>Stop-loss</span><strong>{html.escape(stop_value)}</strong></div>
        <div><span>Horizon</span><strong>{html.escape(metric_lookup.get("时间维度", ""))}</strong></div>
      </div>
    """

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(stock_name)}资料卡</title>
<style>
  :root {{
    --paper: #f3f6f9;
    --ink: #172033;
    --muted: #697386;
    --line: #d8e0ea;
    --card: #ffffff;
    --black: #111827;
    --navy: #0b2545;
    --navy-2: #12375c;
    --red: #a73535;
    --red-soft: #fffafa;
    --green: #1d6b57;
    --green-soft: #fbfdfc;
    --blue: #1f5f99;
    --blue-soft: #f3f7fb;
    --amber: #85601f;
    --amber-soft: #f8fafc;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #dce3eb;
    color: var(--ink);
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI Emoji", sans-serif;
  }}
  .poster {{
    width: 1080px;
    margin: 0 auto;
    background: var(--paper);
    padding: 42px 54px 54px;
  }}
  .sheet {{
    background: var(--card);
    border: 1px solid #cdd7e3;
    box-shadow: 0 22px 54px rgba(22, 42, 70, .14);
  }}
  .hero {{
    min-height: 248px;
    padding: 36px 46px 30px;
    color: #fff;
    background: linear-gradient(135deg, #08213f 0%, #0d2f55 60%, #174b78 100%);
    position: relative;
    overflow: hidden;
  }}
  .hero::after {{
    content: "";
    position: absolute;
    left: 48px;
    right: 48px;
    bottom: 24px;
    height: 1px;
    background: rgba(255,255,255,.22);
  }}
  .topline {{
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 24px;
    position: relative;
    z-index: 1;
  }}
  .label {{
    color: rgba(255,255,255,.72);
    font-size: 19px;
    text-transform: uppercase;
    font-weight: 700;
  }}
  h1 {{
    margin: 14px 0 0;
    font-size: 58px;
    line-height: 1;
    letter-spacing: 0;
    font-weight: 900;
  }}
  .subtitle {{
    margin-top: 16px;
    font-size: 29px;
    color: #dbeafe;
    font-weight: 800;
  }}
  .risk-stamp {{
    border: 1px solid rgba(255,255,255,.38);
    padding: 15px 20px;
    min-width: 236px;
    text-align: center;
    transform: none;
    background: rgba(255,255,255,.08);
  }}
  .risk-stamp strong {{
    display: block;
    font-size: 34px;
    line-height: 1;
    color: #fff;
  }}
  .risk-stamp span {{
    display: block;
    margin-top: 8px;
    color: rgba(255,255,255,.78);
    font-size: 20px;
  }}
  .rating-table {{
    width: 296px;
    border: 1px solid rgba(255,255,255,.28);
    background: rgba(255,255,255,.075);
    position: relative;
    z-index: 1;
  }}
  .rating-table div {{
    display: grid;
    grid-template-columns: 112px 1fr;
    gap: 14px;
    align-items: center;
    min-height: 42px;
    padding: 8px 14px;
    border-bottom: 1px solid rgba(255,255,255,.16);
  }}
  .rating-table div:last-child {{
    border-bottom: 0;
  }}
  .rating-table span {{
    color: rgba(255,255,255,.66);
    font-size: 17px;
    font-weight: 700;
  }}
  .rating-table strong {{
    color: #fff;
    font-size: 20px;
    line-height: 1.15;
    font-weight: 900;
  }}
  .metrics {{
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-top: 34px;
  }}
  .metric {{
    min-height: 94px;
    border: 1px solid rgba(255,255,255,.18);
    background: rgba(255,255,255,.085);
    padding: 16px 15px;
  }}
  .metric-label {{
    font-size: 18px;
    color: rgba(255,255,255,.66);
    white-space: nowrap;
  }}
  .metric-value {{
    margin-top: 10px;
    font-size: 25px;
    line-height: 1.18;
    font-weight: 900;
    color: #fff;
  }}
  .content {{
    padding: 30px 36px 40px;
  }}
  .summary {{
    display: grid;
    grid-template-columns: 324px 1fr;
    gap: 18px;
    margin-bottom: 18px;
  }}
  .verdict,
  .thesis,
  .section {{
    border: 1px solid var(--line);
    background: #ffffff;
  }}
  .verdict,
  .thesis {{
    padding: 24px 26px 26px;
    min-height: 166px;
  }}
  .verdict {{
    background: #ffffff;
    border-color: #cad8e7;
  }}
  .eyebrow {{
    color: var(--muted);
    font-size: 17px;
    font-weight: 900;
    text-transform: uppercase;
    margin-bottom: 10px;
  }}
  .summary h2 {{
    margin: 0 0 18px;
    font-size: 29px;
    line-height: 1.25;
    color: var(--navy);
  }}
  .thesis h2 {{ color: var(--navy); }}
  .summary p {{
    margin: 0 0 7px;
    font-size: 28px;
    line-height: 1.45;
    font-weight: 800;
  }}
  .single-flow {{
    display: block;
    margin-bottom: 18px;
  }}
  .section {{
    position: relative;
    padding: 25px 28px 27px;
    margin: 0 0 18px;
    overflow: hidden;
  }}
  .section::before {{
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 5px;
    background: var(--navy-2);
  }}
  .section h2 {{
    margin: 0 0 18px;
    font-size: 29px;
    line-height: 1.25;
    color: var(--navy);
    font-weight: 900;
  }}
  .section .body {{
    font-size: 24px;
    line-height: 1.52;
    font-weight: 500;
  }}
  .section.dense .body {{
    font-size: 24px;
    line-height: 1.52;
  }}
  .section.compact .body {{
    font-size: 24px;
    line-height: 1.5;
  }}
  .body p {{
    margin: 0 0 8px;
    overflow-wrap: anywhere;
    display: flex;
    gap: 9px;
    align-items: flex-start;
  }}
  .marker {{
    flex: 0 0 22px;
    height: 22px;
    margin-top: 5px;
    border: 0;
    color: var(--navy-2);
    font-size: 18px;
    line-height: 22px;
    text-align: center;
    font-weight: 800;
  }}
  .marker:empty {{
    visibility: hidden;
  }}
  p.good .marker {{
    color: #1f5f50;
  }}
  p.bad .marker {{
    color: #9e3636;
  }}
  p.watch .marker,
  p.signal .marker {{
    color: var(--blue);
  }}
  .body p.good {{ color: #1f5f50; font-weight: 760; }}
  .body p.bad {{ color: #9e3636; font-weight: 760; }}
  .body p.watch {{ color: var(--blue); font-weight: 900; }}
  .body p.signal {{ color: var(--blue); font-weight: 760; }}
  .green {{ background: var(--green-soft); border-color: #d8e5df; }}
  .green::before {{ background: #2c6f5b; }}
  .green h2 {{ color: #1c604f; }}
  .red {{ background: var(--red-soft); border-color: #e7d7d7; }}
  .red::before {{ background: #a13a3a; }}
  .red h2 {{ color: #963535; }}
  .research-table {{
    background: #fff;
    padding: 0;
  }}
  .research-table::before {{
    width: 5px;
  }}
  .research-table h2 {{
    margin: 0;
    padding: 24px 28px 20px 34px;
    border-bottom: 1px solid var(--line);
  }}
  .research-table .body {{
    padding: 16px 28px 18px 34px;
  }}
  .research-table .body p {{
    margin: 0;
    padding: 11px 0;
    border-bottom: 1px solid #edf1f5;
  }}
  .research-table .body p:last-child {{
    border-bottom: 0;
  }}
  .action {{ background: #ffffff; border-color: #d8e0ea; }}
  .action::before {{ background: #a13a3a; }}
  .action h2 {{ color: var(--navy); }}
  .buy {{ background: var(--blue-soft); border-color: #cbdceb; }}
  .buy::before {{ background: var(--blue); }}
  .buy h2 {{ color: var(--navy-2); }}
  .quote {{
    background: #f8fafc;
    border-color: #d6e0ea;
    margin-bottom: 0;
  }}
  .quote::before {{ background: var(--navy-2); }}
  .quote h2 {{ color: var(--navy); }}
  .quote .body {{
    font-size: 31px;
    line-height: 1.48;
    font-weight: 800;
    color: #18212b;
    padding-left: 18px;
    border-left: 5px solid rgba(31,95,153,.34);
  }}
  .quote .body p {{ margin-bottom: 4px; }}
</style>
</head>
<body>
  <main class="poster">
    <div class="sheet">
      <header class="hero">
        <div class="topline">
          <div>
            <div class="label">A Share Investment Memo</div>
            <h1>{html.escape(stock_code)}&nbsp;&nbsp;{html.escape(stock_name)}</h1>
            <div class="subtitle">{html.escape(rating_label)}</div>
          </div>
          {rating_table_html}
        </div>
        <div class="metrics">{metric_html}</div>
      </header>
      <div class="content">{body_html}</div>
    </div>
  </main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render_html(args.input, args.output)


if __name__ == "__main__":
    main()
