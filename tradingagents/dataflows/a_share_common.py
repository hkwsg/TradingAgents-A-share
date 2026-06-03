from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import re

import akshare as ak
import pandas as pd


SH_PREFIXES = ("600", "601", "603", "605", "688", "689")
SZ_PREFIXES = ("000", "001", "002", "003", "300", "301")
BJ_PREFIXES = ("430", "431", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879", "920")


def _infer_exchange(code: str) -> str:
    """
    推断股票所属交易所。
    
    参数：
        code: 证券代码。
    
    返回：
        str: 函数执行结果。
    """
    if code.startswith(SH_PREFIXES):
        return "SH"
    if code.startswith(SZ_PREFIXES):
        return "SZ"
    if code.startswith(BJ_PREFIXES):
        return "BJ"
    raise ValueError(
        f"Unsupported A-share symbol '{code}'. Expected a 6-digit Shanghai, Shenzhen, or Beijing code."
    )


def normalize_ashare_symbol(symbol: str) -> str:
    """
    将用户输入规范化为 ``000001.SZ``、``600519.SH`` 或 ``430047.BJ``。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
    
    返回：
        str: 规范化后的代码结果。
    """
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("Ticker symbol cannot be empty.")

    exchange_prefix_match = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", normalized)
    if exchange_prefix_match:
        exchange, code = exchange_prefix_match.groups()
        return f"{code}.{exchange}"

    exchange_suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", normalized)
    if exchange_suffix_match:
        code, exchange = exchange_suffix_match.groups()
        return f"{code}.{exchange}"

    digits_match = re.fullmatch(r"\d{6}", normalized)
    if digits_match:
        code = digits_match.group(0)
        return f"{code}.{_infer_exchange(code)}"

    # 最后兜底：从输入中提取首个6位数字作为代码
    fallback = re.search(r"\d{6}", normalized)
    if fallback:
        code = fallback.group(0)
        return f"{code}.{_infer_exchange(code)}"

    raise ValueError(
        f"Unsupported A-share symbol format: '{symbol}'. Use a 6-digit code such as 600519 or 000001."
    )


def to_plain_symbol(symbol: str) -> str:
    """
    转换为不带交易所后缀的代码。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
    
    返回：
        str: 转换后的代码结果。
    """
    return normalize_ashare_symbol(symbol).split(".", 1)[0]


def to_exchange_prefixed_symbol(symbol: str) -> str:
    """
    转换为带交易所前缀的代码。
    
    参数：
        symbol: 待分析标的的 A 股股票代码。
    
    返回：
        str: 转换后的代码结果。
    """
    code, exchange = normalize_ashare_symbol(symbol).split(".", 1)
    return f"{exchange}{code}"


def format_date_for_api(date_str: str) -> str:
    """
    将日期格式化为接口所需格式。
    
    参数：
        date_str: YYYY-MM-DD 格式的日期字符串。
    
    返回：
        str: 格式化后的字符串结果。
    """
    return pd.Timestamp(date_str).strftime("%Y%m%d")


def is_ashare_ticker(ticker: str) -> bool:
    """
    判断给定的股票代码是否为 A 股。

    参数：
        ticker: 原始股票代码字符串。

    返回：
        bool: 当代码可以被规范化为 A 股格式时返回 True。
    """
    try:
        normalize_ashare_symbol(ticker)
        return True
    except ValueError:
        return False


@lru_cache(maxsize=1)
def get_trade_calendar() -> tuple[pd.Timestamp, ...]:
    """
    返回交易日历。
    
    返回：
        tuple[pd.Timestamp, ...]: 交易日时间戳元组。
    """
    trade_dates = ak.tool_trade_date_hist_sina()["trade_date"]
    return tuple(pd.to_datetime(trade_dates, errors="coerce").dropna().sort_values())


def is_trade_date(date_str: str) -> bool:
    """
    判断是否为交易日。
    
    参数：
        date_str: YYYY-MM-DD 格式的日期字符串。
    
    返回：
        bool: 条件满足时返回 True，否则返回 False。
    """
    target = pd.Timestamp(date_str).normalize()
    return target in set(get_trade_calendar())


def get_previous_trade_date(date_str: str) -> str:
    """
    返回此前最近一个交易日。
    
    参数：
        date_str: YYYY-MM-DD 格式的日期字符串。
    
    返回：
        str: 当前查询结果。
    """
    target = pd.Timestamp(date_str).normalize()
    eligible = [trade_date for trade_date in get_trade_calendar() if trade_date <= target]
    if not eligible:
        raise ValueError(f"No A-share trading date found on or before {date_str}.")
    return eligible[-1].strftime("%Y-%m-%d")


def get_date_range(start_date: str, end_date: str) -> list[str]:
    """
    返回日期区间列表。
    
    参数：
        start_date: 起始日期（含当日），格式为 YYYY-MM-DD。
        end_date: 结束日期（含当日），格式为 YYYY-MM-DD。
    
    返回：
        list[str]: 当前查询得到的日期列表。
    """
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return [value.strftime("%Y-%m-%d") for value in pd.date_range(start=start, end=end, freq="D")]


def parse_date_column(series: pd.Series) -> pd.Series:
    """
    解析日期列。
    
    参数：
        series: 包含日期型值的 Pandas Series。
    
    返回：
        pd.Series: 解析后的序列结果。
    """
    return pd.to_datetime(series, errors="coerce")
