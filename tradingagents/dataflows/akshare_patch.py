"""
AkShare 请求层补丁：自动注入东方财富浏览器 headers / 请求延迟 / 重试。

必须在任何 AkShare 调用之前导入本模块，补丁会在 import 时自动生效。
用法：在 a_share.py 最顶部加入 `from . import akshare_patch  # noqa: F401`
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

# ---- 东方财富专用请求头 ----
_EASTMONEY_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.eastmoney.com/",
    "Connection": "keep-alive",
}

# ---- 速率控制 ----
_last_eastmoney_request: float = 0.0
_MIN_EASTMONEY_INTERVAL: float = 0.5  # 东方财富请求最小间隔（秒）

# 重试配置
_MAX_RETRIES: int = 3
_BASE_RETRY_DELAY: float = 1.0  # 首次重试延迟（秒），后续指数增长


def _is_eastmoney_url(url: str) -> bool:
    """判断 URL 是否指向东方财富域名。"""
    return "eastmoney.com" in url


def _wait_for_rate_limit(url: str) -> None:
    """东方财富域名的请求间隔控制，避免反爬封禁。"""
    global _last_eastmoney_request
    if not _is_eastmoney_url(url):
        return
    elapsed = time.time() - _last_eastmoney_request
    if elapsed < _MIN_EASTMONEY_INTERVAL:
        time.sleep(_MIN_EASTMONEY_INTERVAL - elapsed)
    _last_eastmoney_request = time.time()


def _merge_eastmoney_headers(kwargs: dict) -> None:
    """为东方财富请求注入缺失的浏览器 headers。"""
    headers = kwargs.get("headers")
    if headers is None:
        kwargs["headers"] = dict(_EASTMONEY_HEADERS)
        return
    if not isinstance(headers, dict):
        return
    for key, value in _EASTMONEY_HEADERS.items():
        if key not in headers:
            headers[key] = value


# ---- 拦截请求并重试 ----
_original_get = requests.get
_patch_applied: bool = False


def _patched_get(url: str, **kwargs):
    """
    包装后的 requests.get：
    1. 东方财富域名自动限速
    2. 自动补齐浏览器请求头
    3. 指数退避重试（最多 3 次）
    """
    if not _is_eastmoney_url(url):
        return _original_get(url, **kwargs)

    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            _wait_for_rate_limit(url)
            _merge_eastmoney_headers(kwargs)
            return _original_get(url, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES - 1:
                raise
            delay = _BASE_RETRY_DELAY * (2 ** attempt)
            logger.debug(
                "东方财富请求失败 (第 %d/%d 次): %s，%.1fs 后重试",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)

    # 理论不可达，但保持类型安全
    raise last_exc  # type: ignore[misc]


def apply_patch() -> bool:
    """
    激活 requests.get 补丁（幂等调用，重复执行无副作用）。

    Returns:
        bool: True 表示本次调用实际执行了补丁，False 表示补丁已存在。
    """
    global _patch_applied
    if _patch_applied:
        return False
    requests.get = _patched_get
    _patch_applied = True
    logger.info("AkShare 请求补丁已激活：东方财富自动 Headers + 限速 + 重试")
    return True


def is_patch_applied() -> bool:
    """查询补丁是否已激活。"""
    return _patch_applied


# 模块导入时自动激活补丁
apply_patch()
