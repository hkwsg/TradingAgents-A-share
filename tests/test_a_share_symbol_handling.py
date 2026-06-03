import unittest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.dataflows.a_share_common import (
    normalize_ashare_symbol,
    to_exchange_prefixed_symbol,
    to_plain_symbol,
)


class AShareTickerHandlingTests(unittest.TestCase):
    def test_normalize_plain_symbol_adds_market_suffix(self):
        """
        测试纯数字代码会补齐市场后缀。
        
        返回：
            None: 无返回值。
        """
        self.assertEqual(normalize_ticker_symbol(" 600519 "), "600519")
        self.assertEqual(normalize_ticker_symbol("000001"), "000001")

    def test_normalize_exchange_prefixed_symbol(self):
        """
        测试带交易所前缀的代码会被规范化。
        
        返回：
            None: 无返回值。
        """
        self.assertEqual(normalize_ashare_symbol("sh600519"), "600519.SH")
        self.assertEqual(normalize_ashare_symbol("SZ000001"), "000001.SZ")

    def test_symbol_conversion_helpers(self):
        """
        测试股票代码转换辅助函数。
        
        返回：
            None: 无返回值。
        """
        self.assertEqual(to_plain_symbol("600519.SH"), "600519")
        self.assertEqual(to_exchange_prefixed_symbol("000001"), "SZ000001")

    def test_build_instrument_context_mentions_a_share_suffix(self):
        """
        测试标的上下文会明确包含 A 股后缀。
        
        返回：
            None: 无返回值。
        """
        context = build_instrument_context("600519.SH")
        self.assertIn("600519.SH", context)
        self.assertIn(".SH", context)
        self.assertIn("exchange suffix", context.lower())
        self.assertIn(".SH", context)


if __name__ == "__main__":
    unittest.main()
