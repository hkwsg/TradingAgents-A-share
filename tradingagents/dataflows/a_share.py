from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from http.client import RemoteDisconnected
import math
import os
import sys
import time
import textwrap

import logging
import akshare as ak
import pandas as pd
import requests

logger = logging.getLogger(__name__)
from akshare.utils import tqdm as ak_tqdm

# AkShare 请求层改进说明：
#   1. akshare_patch.py：全局拦截 requests.get，为东方财富域名自动注入浏览器 headers + 限速 + 重试
#   2. curl_cffi 修复：已修改 akshare/news_stock.py, news_baidu.py, fx_quote_baidu.py
#      将 from curl_cffi import requests → import requests（Win10 TLS 兼容）
#   3. stock_news_em：东方财富搜索 API 已于 2026 年彻底改为返回 passportWeb，
#      不是 headers/重试能解决的。替代方案为研报+市场快讯组合。
#   4. _call_akshare_api：指数退避重试，覆盖 JSONDecodeError/passportWeb/cmsArticleWebOld 等异常

from . import akshare_patch  # noqa: F401  # 必须在所有 AkShare 调用前激活 requests 补丁

from .a_share_common import (
    format_date_for_api,
    get_date_range,
    get_previous_trade_date,
    normalize_ashare_symbol,
    parse_date_column,
    to_exchange_prefixed_symbol,
    to_plain_symbol,
)



INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50日简单移动平均线，用于识别中期趋势和动态支撑阻力。",
    "close_200_sma": "200日简单移动平均线，用于识别长期趋势和牛熊切换。",
    "close_10_ema": "10日指数移动平均线，用于捕捉更快的短期趋势变化。",
    "macd": "MACD 指标，用于识别趋势变化与动量。",
    "macds": "MACD 信号线，用于配合 MACD 判断金叉死叉。",
    "macdh": "MACD 柱状图，用于衡量动量强弱变化。",
    "rsi": "RSI 指标，用于识别超买超卖与背离。",
    "boll": "布林带中轨，衡量价格相对中枢。",
    "boll_ub": "布林带上轨，衡量价格上沿压力。",
    "boll_lb": "布林带下轨，衡量价格下沿支撑。",
    "atr": "ATR 波动率指标，用于仓位和止损参考。",
    "vwma": "成交量加权均线，用于结合量价确认趋势。",
    "mfi": "资金流量指标，用于衡量量价驱动的超买超卖。",
}

IMPORTANT_FINANCIAL_METRICS = [
    "归母净利润",
    "扣非净利润",
    "营业总收入",
    "基本每股收益",
    "每股净资产",
    "每股经营性现金流",
    "销售毛利率",
    "净资产收益率",
    "资产负债率",
]

BALANCE_SHEET_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOTAL_PARENT_EQUITY",
    "MONETARYFUNDS",
    "INVENTORY",
    "ACCOUNTS_RECE",
    "GOODWILL",
]

CASHFLOW_COLUMNS = [
    "REPORT_DATE_NAME",
    "NETCASH_OPERATE",
    "NETCASH_INVEST",
    "NETCASH_FINANCE",
    "CCE_ADD",
    "PAY_STAFF_CASH",
    "PAY_ALL_TAX",
]

INCOME_COLUMNS = [
    "REPORT_DATE_NAME",
    "TOTAL_OPERATE_INCOME",
    "OPERATE_PROFIT",
    "TOTAL_PROFIT",
    "NETPROFIT",
    "PARENT_NETPROFIT",
    "DEDUCT_PARENT_NETPROFIT",
    "BASIC_EPS",
]


@contextmanager
def _temporary_string_storage(storage: str):
    """
    临时切换 pandas 字符串存储模式，并在退出后恢复原配置。

    参数：
        storage: 临时使用的字符串存储模式。

    返回：
        None: 无返回值。
    """
    original = pd.get_option("mode.string_storage")
    pd.set_option("mode.string_storage", storage)
    try:
        yield
    finally:
        pd.set_option("mode.string_storage", original)


@contextmanager
def _suppress_akshare_progress():
    """
    临时关闭 AkShare 内部 tqdm 进度条输出。

    返回：
        None: 无返回值。
    """
    replacements = {}
    silent_get_tqdm = lambda enable=True: (lambda iterable, *args, **kwargs: iterable)

    replacements[(ak_tqdm, "get_tqdm")] = ak_tqdm.get_tqdm
    ak_tqdm.get_tqdm = silent_get_tqdm

    for module in list(sys.modules.values()):
        module_name = getattr(module, "__name__", "")
        if not module_name.startswith("akshare."):
            continue
        if hasattr(module, "get_tqdm"):
            replacements[(module, "get_tqdm")] = getattr(module, "get_tqdm")
            setattr(module, "get_tqdm", silent_get_tqdm)
    try:
        yield
    finally:
        for (module, attr), original in replacements.items():
            setattr(module, attr, original)


def _format_table(df: pd.DataFrame, title: str, rows: int = 10) -> str:
    """
    格式化表格输出。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        title: 表格标题。
        rows: 格式化输出中保留的最大行数。
    
    返回：
        str: 格式化后的字符串结果。
    """
    if df.empty:
        return f"{title}\n\n暂无数据。"
    return f"{title}\n\n{df.head(rows).to_csv(index=False)}"


def _round_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    对数值型数据表执行四舍五入。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    rounded = df.copy()
    for column in rounded.columns:
        if pd.api.types.is_numeric_dtype(rounded[column]):
            rounded[column] = rounded[column].round(4)
    return rounded


def _select_statement_columns(df: pd.DataFrame, preferred_columns: list[str]) -> pd.DataFrame:
    """
    选择财务报表字段。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        preferred_columns: 输出中优先保留的字段顺序列表。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    available = [column for column in preferred_columns if column in df.columns]
    if not available:
        return df.head(8)
    return df.loc[:, available].head(8)


def _filter_report_rows(df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    """
    筛选报告行。
    
    参数：
        df: 需要格式化、筛选或转换的数据表。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    if df.empty or not curr_date:
        return df
    for column in ("REPORT_DATE", "NOTICE_DATE", "报告日期", "公告日期"):
        if column in df.columns:
            filtered = df.copy()
            filtered[column] = parse_date_column(filtered[column])
            cutoff = pd.Timestamp(curr_date)
            filtered = filtered[filtered[column] <= cutoff]
            filtered = filtered.sort_values(column, ascending=False)
            return filtered
    return df


def _latest_abstract_snapshot(abstract_df: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    """
    返回最新财务摘要快照。
    
    参数：
        abstract_df: AkShare 返回的财务摘要数据表。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        pd.DataFrame: 处理后的数据表。
    """
    report_columns = [column for column in abstract_df.columns if str(column).isdigit()]
    if not report_columns:
        return pd.DataFrame()

    parsed_dates = {
        column: pd.to_datetime(str(column), format="%Y%m%d", errors="coerce")
        for column in report_columns
    }

    if curr_date:
        cutoff = pd.Timestamp(curr_date)
        eligible = [column for column, value in parsed_dates.items() if value <= cutoff]
    else:
        eligible = report_columns

    if not eligible:
        eligible = report_columns

    latest_column = max(eligible, key=lambda column: parsed_dates[column])
    filtered = abstract_df[abstract_df["指标"].isin(IMPORTANT_FINANCIAL_METRICS)][["指标", latest_column]].copy()
    filtered.columns = ["指标", latest_column]
    return filtered


def _safe_truncate(text: str, limit: int = 160) -> str:
    """
    安全截断文本。
    
    参数：
        text: 需要截断或处理的输入文本。
        limit: 结果中允许保留的最大长度。
    
    返回：
        str: 安全处理后的字符串结果。
    """
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _is_retryable_akshare_error(exc: Exception) -> bool:
    """
    判断异常是否属于可重试的 AkShare 网络错误。

    参数：
        exc: 待判断的异常对象。

    返回：
        bool: 条件满足时返回 True，否则返回 False。
    """
    if isinstance(exc, (requests.exceptions.RequestException, RemoteDisconnected, TimeoutError)):
        return True

    # JSON 解析失败通常是东方财富返回异常页面（如 passportWeb），重试可能拿到正确响应
    if isinstance(exc, __import__("json").JSONDecodeError):
        return True

    message = str(exc)
    retryable_markers = (
        "Remote end closed connection without response",
        "Connection aborted",
        "Read timed out",
        "ConnectTimeout",
        "Max retries exceeded",
        "temporarily unavailable",
        "Expecting value",            # JSON 解析失败（空响应或异常页面）
        "cmsArticleWebOld",           # stock_news_em 返回 passportWeb 替代页面
        "passportWeb",                # 东方财富反爬/登录页
        "Invalid URL",                # 临时 DNS/路由问题
    )
    return any(marker in message for marker in retryable_markers)


def _call_akshare_api(func, *args, retries: int = 3, retry_delay: float = 1.0, **kwargs):
    """
    调用 AkShare 接口，指数退避重试（适配东方财富反爬策略）。

    重试延迟：delay * 2^(attempt-1)，即 1s → 2s → 4s。
    遇到 cmsArticleWebOld / passportWeb / JSONDecodeError 也触发重试。

    参数：
        func: 需要执行的 AkShare 函数。
        args: 传给 AkShare 函数的位置参数。
        retries: 最大重试次数。
        retry_delay: 首次重试前的等待秒数，后续指数增长。
        kwargs: 传给 AkShare 函数的关键字参数。

    返回：
        Any: AkShare 原始返回结果。
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not _is_retryable_akshare_error(exc):
                raise
            delay = retry_delay * (2 ** (attempt - 1))
            logger.debug(
                "AkShare API 调用失败 (第 %d/%d 次): %s: %s，%.1fs 后重试",
                attempt,
                retries,
                type(exc).__name__,
                str(exc)[:200],
                delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _format_data_error(title: str, exc: Exception) -> str:
    """
    将外部数据源异常转换为可读文本，避免工具节点直接崩溃。

    参数：
        title: 当前数据块标题。
        exc: 原始异常对象。

    返回：
        str: 适合直接返回给上层代理的错误说明。
    """
    return (
        f"{title}\n\n"
        f"数据源访问失败：{type(exc).__name__}: {_safe_truncate(str(exc), 220)}"
    )


def _load_stock_hist_with_fallback(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取历史行情，并在东方财富源失败时回退到腾讯源。

    参数：
        symbol: 待分析标的的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        pd.DataFrame: 历史行情数据表。
    """
    plain_symbol = to_plain_symbol(symbol)
    try:
        return _call_akshare_api(
            ak.stock_zh_a_hist,
            symbol=plain_symbol,
            period="daily",
            start_date=format_date_for_api(start_date),
            end_date=format_date_for_api(end_date),
            adjust="qfq",
        )
    except Exception:  # noqa: BLE001
        with _suppress_akshare_progress():
            return _call_akshare_api(
                ak.stock_zh_a_hist_tx,
                symbol=to_exchange_prefixed_symbol(symbol).lower(),
                start_date=format_date_for_api(start_date),
                end_date=format_date_for_api(end_date),
                adjust="qfq",
            )


def _load_company_profile(plain_symbol: str) -> pd.DataFrame:
    """
    获取公司概况，并优先使用更稳定的巨潮资讯接口。

    参数：
        plain_symbol: 不带交易所前缀的纯数字股票代码。

    返回：
        pd.DataFrame: 公司概况数据表。
    """
    try:
        return _call_akshare_api(ak.stock_profile_cninfo, symbol=plain_symbol)
    except Exception:  # noqa: BLE001
        return _call_akshare_api(ak.stock_individual_info_em, symbol=plain_symbol)


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    返回股票行情数据。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(symbol)
    try:
        df = _load_stock_hist_with_fallback(symbol, start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share price data for {normalized_symbol} from {start_date} to {end_date}",
            exc,
        )

    if df.empty:
        return f"未找到 {normalized_symbol} 在 {start_date} 到 {end_date} 之间的 A 股行情数据。"

    renamed = df.rename(
        columns={
            "日期": "Date",
            "date": "Date",
            "开盘": "Open",
            "open": "Open",
            "收盘": "Close",
            "close": "Close",
            "最高": "High",
            "high": "High",
            "最低": "Low",
            "low": "Low",
            "成交量": "Volume",
            "成交额": "Amount",
            "amount": "Amount",
            "振幅": "AmplitudePct",
            "涨跌幅": "PctChange",
            "涨跌额": "PriceChange",
            "换手率": "TurnoverPct",
        }
    )
    renamed["Date"] = pd.to_datetime(renamed["Date"]).dt.strftime("%Y-%m-%d")
    if "PctChange" not in renamed.columns and "Close" in renamed.columns:
        renamed["PctChange"] = renamed["Close"].pct_change().mul(100).round(4)
    selected_columns = [
        column
        for column in ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "PctChange", "TurnoverPct"]
        if column in renamed.columns
    ]
    output = _round_numeric_frame(renamed.loc[:, selected_columns])
    header = f"# A-share price data for {normalized_symbol} from {start_date} to {end_date}\n"
    header += f"# Records: {len(output)}\n\n"
    return header + output.to_csv(index=False)


def _get_indicator_data(symbol: str, indicator: str, curr_date: str) -> dict[str, str]:
    """
    返回指标原始数据。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        indicator: 需要计算或查询的技术指标名称。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        dict[str, str]: 指标名称与结果文本的映射。
    """
    from stockstats import wrap

    aligned_trade_date = get_previous_trade_date(curr_date)
    start_date = (pd.Timestamp(aligned_trade_date) - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    data = _load_stock_hist_with_fallback(symbol, start_date, aligned_trade_date)
    if data.empty:
        return {}
    data = data.rename(
        columns={
            "日期": "Date", "date": "Date",
            "开盘": "Open", "open": "Open",
            "收盘": "Close", "close": "Close",
            "最高": "High", "high": "High",
            "最低": "Low", "low": "Low",
            "成交量": "Volume", "volume": "Volume",
        }
    )
    for col in ["Date", "Open", "High", "Low", "Close", "Volume"]:
        if col not in data.columns:
            return {}
    data = data[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    data["Date"] = pd.to_datetime(data["Date"])
    data = data.dropna(subset=["Close"])
    data[["Open", "High", "Low", "Close", "Volume"]] = data[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    df = wrap(data.copy())
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df[indicator]

    result = {}
    for _, row in df.iterrows():
        value = row[indicator]
        if pd.isna(value):
            result[row["Date"]] = "N/A"
        else:
            result[row["Date"]] = str(value)
    return result


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """
    返回指标结果。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
        indicator: 需要计算或查询的技术指标名称。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
        look_back_days: Number of calendar days to look back from the current date.
    
    返回：
        str: 当前查询结果。
    """
    if indicator not in INDICATOR_DESCRIPTIONS:
        supported = ", ".join(sorted(INDICATOR_DESCRIPTIONS))
        raise ValueError(f"Indicator {indicator} is not supported for A-share analysis. Choose from: {supported}")

    normalized_symbol = normalize_ashare_symbol(symbol)
    aligned_trade_date = get_previous_trade_date(curr_date)
    try:
        indicator_values = _get_indicator_data(symbol, indicator, aligned_trade_date)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"## {normalized_symbol} {indicator} values through {aligned_trade_date}",
            exc,
        )
    end = pd.Timestamp(aligned_trade_date)
    start = end - pd.Timedelta(days=look_back_days)

    lines = []
    for date_value in pd.date_range(start=start, end=end, freq="D"):
        date_str = date_value.strftime("%Y-%m-%d")
        lines.append(f"{date_str}: {indicator_values.get(date_str, 'N/A: 非交易日或无数据')}")

    return (
        f"## {normalized_symbol} {indicator} values through {aligned_trade_date}\n\n"
        + "\n".join(lines)
        + "\n\n"
        + INDICATOR_DESCRIPTIONS[indicator]
    )


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """
    返回基本面数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    errors = []

    try:
        info_df = _load_company_profile(plain_symbol)
    except Exception as exc:  # noqa: BLE001
        info_df = pd.DataFrame()
        errors.append(f"公司概况接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        intro_df = _call_akshare_api(ak.stock_zyjs_ths, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        intro_df = pd.DataFrame()
        errors.append(f"主营业务简介接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        business_df = _call_akshare_api(ak.stock_zygc_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        business_df = pd.DataFrame()
        errors.append(f"主营构成接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    try:
        abstract_df = _call_akshare_api(ak.stock_financial_abstract, symbol=plain_symbol)
    except Exception as exc:  # noqa: BLE001
        abstract_df = pd.DataFrame()
        errors.append(f"财务摘要接口失败：{type(exc).__name__}: {_safe_truncate(str(exc), 120)}")

    info_snapshot = info_df.head(20).copy()
    intro_snapshot = intro_df.head(1).copy()
    business_snapshot = business_df.head(6).copy()
    abstract_snapshot = _latest_abstract_snapshot(abstract_df, curr_date) if not abstract_df.empty else pd.DataFrame()

    sections = [
        _format_table(info_snapshot, f"# A-share company profile for {normalized_symbol}", rows=20),
        _format_table(intro_snapshot, "## 主营业务简介", rows=3),
        _format_table(business_snapshot, "## 最新主营构成", rows=6),
        _format_table(abstract_snapshot, "## 最新关键财务摘要", rows=12),
    ]
    if errors:
        sections.append("## 数据获取说明\n\n" + "\n".join(f"- {item}" for item in errors))
    return "\n\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回资产负债表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_balance_sheet_by_yearly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_balance_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share balance sheet for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, BALANCE_SHEET_COLUMNS))
    return _format_table(selected, f"# A-share balance sheet for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回现金流量表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_cash_flow_sheet_by_quarterly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_cash_flow_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share cash flow for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, CASHFLOW_COLUMNS))
    return _format_table(selected, f"# A-share cash flow for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """
    返回利润表数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        freq: Requested reporting frequency, such as quarterly or annual.
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
    
    返回：
        str: 当前查询结果。
    """
    exchange_symbol = to_exchange_prefixed_symbol(ticker)
    try:
        if freq == "annual":
            df = _call_akshare_api(ak.stock_profit_sheet_by_quarterly_em, symbol=exchange_symbol)
        else:
            df = _call_akshare_api(ak.stock_profit_sheet_by_report_em, symbol=exchange_symbol)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error(
            f"# A-share income statement for {normalize_ashare_symbol(ticker)} ({freq})",
            exc,
        )

    filtered = _filter_report_rows(df, curr_date)
    selected = _round_numeric_frame(_select_statement_columns(filtered, INCOME_COLUMNS))
    return _format_table(selected, f"# A-share income statement for {normalize_ashare_symbol(ticker)} ({freq})", rows=8)


def get_caixin_news(ticker: str, limit: int = 10) -> str:
    """
    返回财新个股相关新闻（关键词筛选）。

    从 ak.stock_news_main_cx 获取财新 100 条最新资讯，
    按股票名称筛选匹配的新闻。股票名称优先从雪球缓存获取
    （网络故障时回退到 akshare 查询）。

    参数：
        ticker: A 股股票代码。
        limit: 最多返回条数。

    返回：
        str: 格式化后的新闻摘要。
    """
    plain_symbol = to_plain_symbol(ticker)
    normalized = normalize_ashare_symbol(ticker)
    prefix = "SH" if plain_symbol.startswith(("6", "5", "9")) else "SZ"
    xq_code = f"{prefix}{plain_symbol}"

    # 优先从雪球缓存获取股票名称（不受东方财富 API 故障影响）
    stock_name = ""
    df_xq = _load_xueqiu_source("关注")
    if not df_xq.empty:
        row = df_xq[df_xq["股票代码"] == xq_code]
        if not row.empty:
            stock_name = str(row["股票简称"].values[0])
    if not stock_name:
        stock_name = _get_stock_name(plain_symbol)

    try:
        with _suppress_akshare_progress():
            df = _call_akshare_api(ak.stock_news_main_cx, retries=1, retry_delay=0.5)
    except Exception as exc:
        return _format_data_error(f"# Caixin news for {normalized}", exc)

    if df.empty:
        return f"未获取到财新新闻数据。"

    # 只用股票名称关键词，不用代码匹配（数字容易误匹配）
    keywords = []
    if stock_name and stock_name != plain_symbol and not stock_name.startswith("SH") and not stock_name.startswith("SZ"):
        keywords.append(stock_name)
        if len(stock_name) > 2:
            keywords.append(stock_name[:2])

    if not keywords:
        return f"财新新闻未找到 {normalized}（{stock_name}）相关资讯。"

    kw_pattern = "|".join(keywords)
    matched = df[df["summary"].str.contains(kw_pattern, na=False)]
    if matched.empty:
        return f"财新新闻最近 100 条中未找到 {normalized}（{stock_name}）相关资讯。"

    matched = matched.head(limit)
    lines = [f"# 财新新闻 — {normalized}（{stock_name}）", ""]
    for _, row_data in matched.iterrows():
        tag = row_data.get("tag", "")
        summary = _safe_truncate(str(row_data.get("summary", "")), 200)
        url = row_data.get("url", "")
        lines.append(f"- [{tag}] {summary}")
        if url:
            lines.append(f"  {url}")

    return "\n".join(lines)


def _get_stock_name(plain_symbol: str) -> str:
    """通过 akshare 获取 A 股简称，失败时返回代码本身。"""
    try:
        with _suppress_akshare_progress():
            info = _call_akshare_api(ak.stock_individual_info_em, symbol=plain_symbol, retries=1)
        row = info[info["item"] == "股票简称"]
        if not row.empty:
            return str(row["value"].values[0])
    except Exception:
        pass
    return plain_symbol


_XUEQIU_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
_XUEQIU_SOURCES = {
    "关注": "xueqiu_hot_follow.csv",
    "讨论": "xueqiu_hot_tweet.csv",
    "交易": "xueqiu_hot_deal.csv",
}
_XUEQIU_CACHE: dict[str, pd.DataFrame] = {}
_XUEQIU_CACHE_MTIME: dict[str, float] = {}


def _load_xueqiu_source(name: str) -> pd.DataFrame:
    """加载单个雪球榜单缓存，文件未更新则复用内存副本。"""
    global _XUEQIU_CACHE, _XUEQIU_CACHE_MTIME
    filename = _XUEQIU_SOURCES.get(name, "")
    path = os.path.join(_XUEQIU_CACHE_DIR, filename) if filename else ""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return pd.DataFrame()
    if name in _XUEQIU_CACHE and _XUEQIU_CACHE_MTIME.get(name) == mtime:
        return _XUEQIU_CACHE[name]
    try:
        df = pd.read_csv(path, dtype={"股票代码": str})
        _XUEQIU_CACHE[name] = df
        _XUEQIU_CACHE_MTIME[name] = mtime
        return df
    except Exception:
        return pd.DataFrame()


def get_xueqiu_sentiment(ticker: str) -> str:
    """
    返回雪球个股情绪三维数据（关注度 + 讨论度 + 交易热度）。

    从缓存的雪球三大榜单中查找目标股票的排名，
    作为 A 股散户情绪的全面代理指标。

    参数：
        ticker: A 股股票代码。

    返回：
        str: 格式化后的情绪摘要。
    """
    plain_symbol = to_plain_symbol(ticker)
    prefix = "SH" if plain_symbol.startswith(("6", "5", "9")) else "SZ"
    xq_code = f"{prefix}{plain_symbol}"
    normalized = normalize_ashare_symbol(ticker)

    lines = [f"# 雪球情绪数据 — {normalized}"]
    lines.append("")
    stock_name = ""
    total = 0

    for label, name in _XUEQIU_SOURCES.items():
        df = _load_xueqiu_source(label)
        if df.empty:
            lines.append(f"- {label}度：缓存不可用")
            continue

        row = df[df["股票代码"] == xq_code]
        if row.empty:
            lines.append(f"- {label}度：未上榜")
            continue

        value = int(row.iloc[0, 2])
        if not stock_name:
            stock_name = str(row["股票简称"].values[0])
        df_sorted = df.sort_values(df.columns[2], ascending=False).reset_index(drop=True)
        rank = int(df_sorted[df_sorted["股票代码"] == xq_code].index[0]) + 1
        total = len(df_sorted)
        lines.append(f"- {label}度：**{value:,}**（第 {rank}/{total} 名，前 {rank/total*100:.1f}%）")

    if not stock_name:
        return f"未在雪球任何榜单中找到 {xq_code}（{normalized}）。"

    lines[0] = f"# 雪球情绪数据 — {normalized}（{stock_name}）"
    lines.append("")

    # 综合情绪判断：取三个榜单中最低排名作为保守估计
    min_rank = total
    for label in _XUEQIU_SOURCES:
        df = _load_xueqiu_source(label)
        if df.empty:
            continue
        row = df[df["股票代码"] == xq_code]
        if row.empty:
            continue
        df_sorted = df.sort_values(df.columns[2], ascending=False).reset_index(drop=True)
        rank = int(df_sorted[df_sorted["股票代码"] == xq_code].index[0]) + 1
        min_rank = min(min_rank, rank)

    if min_rank <= 10:
        lines.append("**综合情绪：极高关注度** — 散户情绪集中，短期波动可能放大，需警惕情绪反转。")
    elif min_rank <= 100:
        lines.append("**综合情绪：高关注度** — 属于散户活跃标的，情绪定价权较强。")
    elif min_rank <= 500:
        lines.append("**综合情绪：中等关注度** — 散户情绪影响有限，机构定价为主。")
    else:
        lines.append("**综合情绪：低关注度** — 散户参与度低，情绪面驱动力弱。")

    # ---- 实时估值（spot 行情） ----
    lines.append("")
    try:
        with _suppress_akshare_progress():
            spot = _call_akshare_api(ak.stock_individual_spot_xq, symbol=xq_code, retries=1, retry_delay=0.5)
    except Exception:
        spot = pd.DataFrame()

    if not spot.empty:
        spot_map = dict(zip(spot["item"], spot["value"]))
        pe_ttm = spot_map.get("市盈率(TTM)")
        pe_dynamic = spot_map.get("市盈率(动)")
        pb = spot_map.get("市净率")
        div_yield = spot_map.get("股息率(TTM)")
        ytd = spot_map.get("今年以来涨幅")
        turnover = spot_map.get("周转率")
        eps = spot_map.get("每股收益")
        nav = spot_map.get("每股净资产")

        lines.append("## 实时估值（雪球实时行情）")
        lines.append("")
        if pe_ttm:
            lines.append(f"- 市盈率(TTM)：**{pe_ttm}**")
        if pe_dynamic and pe_dynamic != pe_ttm:
            lines.append(f"- 市盈率(动)：**{pe_dynamic}**")
        if pb:
            lines.append(f"- 市净率：**{pb}**")
        if eps:
            lines.append(f"- 每股收益：**{eps}**元")
        if nav:
            lines.append(f"- 每股净资产：**{nav}**元")
        if div_yield:
            lines.append(f"- 股息率(TTM)：**{div_yield}%**")
        if ytd:
            lines.append(f"- 今年以来涨幅：**{ytd}%**")
        if turnover:
            lines.append(f"- 周转率：**{turnover}%**")

    # ---- 内部交易（董监高买卖） ----
    lines.append("")
    try:
        with _suppress_akshare_progress():
            it_df = _call_akshare_api(ak.stock_inner_trade_xq, retries=1, retry_delay=0.5)
    except Exception:
        it_df = pd.DataFrame()

    if not it_df.empty:
        it_stock = it_df[it_df["股票代码"] == xq_code].copy()
        if not it_stock.empty:
            it_stock["变动日期"] = parse_date_column(it_stock["变动日期"])
            cutoff = pd.Timestamp.now() - timedelta(days=60)
            recent = it_stock[it_stock["变动日期"] >= cutoff].sort_values("变动日期", ascending=False)
            if not recent.empty:
                lines.append("## 近期内部交易（董监高买卖）")
                lines.append("")
                buy_count = 0
                sell_count = 0
                for _, row_data in recent.iterrows():
                    shares = int(row_data["变动股数"])
                    price = row_data["成交均价"]
                    name_person = row_data["变动人"]
                    role = row_data.get("董监高职务", "")
                    direction = "买入" if shares > 0 else "减持"
                    if shares > 0:
                        buy_count += 1
                    else:
                        sell_count += 1
                    lines.append(
                        f"- {row_data['变动日期'].strftime('%m-%d')} | {name_person}（{role}）"
                        f" | **{direction}** {abs(shares):,}股 @ {price}元"
                    )
                lines.append("")
                if sell_count > buy_count:
                    lines.append(f"内部情绪：**偏空**（近 60 天减持 {sell_count} 笔，增持 {buy_count} 笔）")
                elif buy_count > sell_count:
                    lines.append(f"内部情绪：**偏多**（近 60 天增持 {buy_count} 笔，减持 {sell_count} 笔）")
                else:
                    lines.append("内部情绪：**中性**（买卖持平）")

    return "\n".join(lines)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    返回个股综合资讯（研报为主 + 市场背景）。

    ak.stock_news_em（东方财富搜索）已于 2026 年彻底失效，
    改用研报（个股专项） + 市场快讯（宏观背景）组合方案。

    参数：
        ticker: 待分析公司的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。

    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    stock_name = _get_stock_name(plain_symbol)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + timedelta(days=1) - timedelta(seconds=1)
    sections: list[str] = []

    # ---- 1. 个股研报（专项） ----
    try:
        with _suppress_akshare_progress():
            df_report = _call_akshare_api(ak.stock_research_report_em, symbol=plain_symbol)
    except Exception:
        df_report = pd.DataFrame()

    if not df_report.empty:
        df_report["发布时间"] = parse_date_column(df_report["日期"])
        mask = (df_report["发布时间"] >= start_ts) & (df_report["发布时间"] <= end_ts)
        df_report = df_report[mask].sort_values("发布时间", ascending=False)
        if not df_report.empty:
            fmt = df_report.head(20).copy()
            fmt["发布时间"] = fmt["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
            fmt["新闻标题"] = "[" + fmt["东财评级"].fillna("研报") + "] " + fmt["报告名称"].fillna("")
            fmt["新闻内容"] = fmt["机构"].fillna("")
            fmt["文章来源"] = fmt["机构"].fillna("机构研报")
            fmt["新闻链接"] = fmt["报告PDF链接"].fillna("")
            selected = fmt.loc[:, ["发布时间", "文章来源", "新闻标题", "新闻内容", "新闻链接"]]
            sections.append(_format_table(selected, "## 券商研报（个股专项）", rows=20))

    # ---- 2. 市场快讯（宏观背景） ----
    try:
        with _suppress_akshare_progress():
            df_market = _call_akshare_api(ak.stock_info_global_em)
    except Exception:
        df_market = pd.DataFrame()

    if not df_market.empty:
        df_market["发布时间"] = parse_date_column(df_market["发布时间"])
        mask = (df_market["发布时间"] >= start_ts) & (df_market["发布时间"] <= end_ts)
        df_market = df_market[mask].sort_values("发布时间", ascending=False)
        if not df_market.empty:
            fmt = df_market.head(5).copy()
            fmt["发布时间"] = fmt["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
            fmt["摘要"] = fmt["摘要"].map(lambda v: _safe_truncate(v, 160))
            selected = fmt.loc[:, ["发布时间", "标题", "摘要"]]
            sections.append(_format_table(selected, "## 市场快讯（宏观背景 TOP5）", rows=5))

    if not sections:
        return f"{normalized_symbol}（{stock_name}）在 {start_date} 到 {end_date} 之间未找到相关资讯。"

    header = f"# {normalized_symbol} 个股综合资讯（{stock_name}）  |  {start_date} ~ {end_date}\n"
    return header + "\n".join(sections)


def get_market_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """
    返回市场新闻数据。
    
    参数：
        curr_date: 当前分析或交易日期，格式为 YYYY-MM-DD。
        look_back_days: Number of calendar days to look back from the current date.
        limit: 结果中允许保留的最大长度。
    
    返回：
        str: 当前查询结果。
    """
    try:
        df = _call_akshare_api(ak.stock_info_global_em)
    except Exception as exc:  # noqa: BLE001
        return _format_data_error("# A-share market and policy news", exc)
    if df.empty:
        return "未获取到 A 股市场与宏观快讯。"

    filtered = df.copy()
    filtered["发布时间"] = parse_date_column(filtered["发布时间"])
    end = pd.Timestamp(curr_date) + timedelta(days=1) - timedelta(seconds=1)
    start = end - timedelta(days=look_back_days)
    filtered = filtered[(filtered["发布时间"] >= start) & (filtered["发布时间"] <= end)]
    filtered = filtered.sort_values("发布时间", ascending=False)

    if filtered.empty:
        return f"{curr_date} 前 {look_back_days} 天没有可用的市场快讯。"

    formatted = filtered.loc[:, ["发布时间", "标题", "摘要", "链接"]].head(limit).copy()
    formatted["发布时间"] = formatted["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S")
    formatted["摘要"] = formatted["摘要"].map(lambda value: _safe_truncate(value, 180))
    return _format_table(formatted, "# A-share market and policy news", rows=limit)


def get_company_announcements(
    ticker: str,
    start_date: str,
    end_date: str,
    category: str = "全部",
) -> str:
    """
    返回公司公告数据。
    
    参数：
        ticker: 待分析公司的 A 股股票代码。
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
        category: Category name or announcement category for the request.
    
    返回：
        str: 当前查询结果。
    """
    normalized_symbol = normalize_ashare_symbol(ticker)
    plain_symbol = to_plain_symbol(ticker)
    frames = []
    errors = []

    for date_value in get_date_range(start_date, end_date):
        try:
            with _suppress_akshare_progress():
                daily = _call_akshare_api(
                    ak.stock_notice_report,
                    symbol=category,
                    date=format_date_for_api(date_value),
                    retries=2,
                    retry_delay=0.5,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_value}: {type(exc).__name__}: {_safe_truncate(str(exc), 100)}")
            continue
        if daily.empty:
            continue
        matched = daily[daily["代码"].astype(str).str.upper() == plain_symbol]
        if not matched.empty:
            frames.append(matched)

    if not frames:
        if errors:
            return (
                f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间未能稳定获取公告数据。\n\n"
                + "\n".join(errors[:5])
            )
        return f"{normalized_symbol} 在 {start_date} 到 {end_date} 之间没有匹配的公告。"

    combined = pd.concat(frames, ignore_index=True)
    combined["公告日期"] = parse_date_column(combined["公告日期"])
    combined = combined.sort_values("公告日期", ascending=False).drop_duplicates(subset=["公告标题", "公告日期"])
    formatted = combined.loc[:, ["公告日期", "公告类型", "公告标题", "网址"]].head(20).copy()
    formatted["公告日期"] = formatted["公告日期"].dt.strftime("%Y-%m-%d")
    output = _format_table(formatted, f"# A-share company announcements for {normalized_symbol}", rows=20)
    if errors:
        output += "\n\n## 数据获取说明\n\n" + "\n".join(f"- {item}" for item in errors[:5])
    return output


def get_insider_transactions(ticker: str) -> str:
    """获取A股高管/大股东增减持数据。

    使用 AkShare stock_executive_team_em 获取高管信息和增持数据。
    """
    normalized_symbol = _normalize_symbol(ticker)
    try:
        import akshare as ak
        df = ak.stock_executive_team_em(symbol=normalized_symbol)
        if df is None or df.empty:
            return f"{ticker} 的高管/内部人交易数据暂不可用。"
        output = _format_table(df, f"# A-share insider transactions & executive data for {normalized_symbol}", rows=25)
        return output
    except Exception as e:
        return f"{ticker} 的高管/内部人交易数据暂不可用（{e}）。"
