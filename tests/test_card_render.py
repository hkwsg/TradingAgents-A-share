"""最小资料卡纯函数测试。只测解析，不渲染图片，不启动浏览器。"""

import tempfile
from pathlib import Path

from scripts.render_card_html import (
    TITLE_PATTERN,
    REPORT_DIR_PATTERN,
    parse_card,
    stock_identity_from_path,
    rating_from_title,
    clean_display_text,
    render_html,
)


SAMPLE_MD = """📅 分析日期：2026-06-05
💰 当前价格：¥45.80
📉 距前高：-18.3%
⏱ 时间维度：3-6 个月

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 最终评级：Hold（持有/观望）

当前估值已反映大部分利空，下行空间有限但缺乏向上催化剂。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 一句话结论

估值合理但成长性不足，等待更好的买点。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

好的一面

✅ 毛利率稳定在 65% 以上
✅ 现金流充裕，资产负债率仅 28%
✅ 回购持续进行

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

坏的一面

🔻 营收增速连续三个季度下滑
🔻 行业竞争加剧，市场份额承压
🔻 新产品管线进度不及预期

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

执行方案

🔴 持仓者：逢高减仓至 50% 以下
🔵 空仓者：暂时观望不急于建仓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

什么时候能买

1️⃣ 价格回到 ¥38 以下
2️⃣ 出现放量阳线

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

止损线：¥35.00

跌破前低支撑，无条件离场。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

组合经理原话

不是不买，是等一个更好的价格。不是恐惧，是纪律。
"""


def test_title_pattern_matches_all_sections():
    """标题模式匹配所有固定模块。"""
    titles = [
        "最终评级：Hold（持有/观望）",
        "一句话结论",
        "好的一面",
        "坏的一面",
        "执行方案",
        "什么时候能买",
        "止损线：¥35.00",
        "组合经理原话",
    ]
    for t in titles:
        assert TITLE_PATTERN.match(t), f"Should match: {t!r}"


def test_parse_card_extracts_metrics():
    """parse_card 提取头部指标。"""
    metrics, sections = parse_card(SAMPLE_MD)
    labels = {label for _, label, _ in metrics}
    assert "当前价格" in labels
    assert "分析日期" in labels


def test_parse_card_extracts_all_sections():
    """parse_card 提取全部固定模块。"""
    _, sections = parse_card(SAMPLE_MD)
    titles = [s[0] for s in sections]
    assert any("最终评级" in t for t in titles)
    assert any("一句话结论" in t for t in titles)
    assert any("好" in t for t in titles)
    assert any("坏" in t for t in titles)
    assert any("执行方案" in t for t in titles)
    assert any("什么时候能买" in t for t in titles)
    assert any("止损线" in t for t in titles)
    assert any("组合经理" in t for t in titles)


def test_rating_from_title_parses_hold():
    """rating_from_title 正确解析评级标签。"""
    label, en = rating_from_title("📊 最终评级：Hold（持有/观望）")
    assert "Hold" in label


def test_stock_identity_from_path():
    """stock_identity_from_path 从标准路径提取代码。"""
    path = Path("reports/600276_2026-06-05/恒瑞医药_资料卡.md")
    code, name = stock_identity_from_path(path)
    assert code == "600276"
    assert "恒瑞医药" in name


def test_stock_identity_no_hardcoded_values():
    """不同股票路径不返回固定值。"""
    cases = [
        ("reports/000858_2026-06-05/五粮液_资料卡.md", "000858", "五粮液"),
        ("reports/600519_2026-06-05/贵州茅台_资料卡.md", "600519", "贵州茅台"),
        ("reports/601318_2026-06-05/中国平安_资料卡.md", "601318", "中国平安"),
    ]
    for dirname, expected_code, expected_name_part in cases:
        path = Path(dirname)
        code, name = stock_identity_from_path(path)
        assert code == expected_code, f"Expected code {expected_code}, got {code}"
        assert expected_name_part in name, f"Expected name containing {expected_name_part}, got {name}"


def test_report_dir_pattern():
    """REPORT_DIR_PATTERN 匹配标准报告目录。"""
    assert REPORT_DIR_PATTERN.match("600276_2026-06-05")
    assert REPORT_DIR_PATTERN.match("000858")
    assert not REPORT_DIR_PATTERN.match("abc")


def test_clean_display_text_removes_emoji_prefix():
    """clean_display_text 去掉 emoji 前缀。"""
    assert "当前价格：¥45.80" in clean_display_text("💰 当前价格：¥45.80")


def test_render_html_contains_stock_code():
    """render_html 输出包含正确股票代码。"""
    with tempfile.TemporaryDirectory() as tmp:
        md_path = Path(tmp) / "reports" / "000858_2026-06-05" / "五粮液_资料卡.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text(SAMPLE_MD, encoding="utf-8")
        out_path = Path(tmp) / "test_output.html"
        render_html(md_path, out_path)
        html = out_path.read_text(encoding="utf-8")
        assert "000858" in html
        assert "五粮液" in html
