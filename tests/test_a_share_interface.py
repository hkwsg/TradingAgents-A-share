import unittest
from unittest.mock import patch

from tradingagents.dataflows.interface import route_to_vendor


class AShareInterfaceTests(unittest.TestCase):
    def test_route_to_vendor_uses_a_share_method(self):
        """
        测试路由调用会落到 A 股数据方法。
        
        返回：
            None: 无返回值。
        """
        with patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {"get_stock_data": {"akshare": lambda symbol, start, end: f"{symbol}|{start}|{end}"}},
            clear=False,
        ):
            result = route_to_vendor("get_stock_data", "600519.SH", "2024-03-01", "2024-03-05")

        self.assertEqual(result, "600519.SH|2024-03-01|2024-03-05")


if __name__ == "__main__":
    unittest.main()
