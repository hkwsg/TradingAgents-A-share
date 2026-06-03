import unittest
from unittest.mock import patch

import pandas as pd

from tradingagents.dataflows.a_share_common import get_previous_trade_date, is_trade_date


class AShareCalendarTests(unittest.TestCase):
    @patch(
        "tradingagents.dataflows.a_share_common.get_trade_calendar",
        return_value=(
            pd.Timestamp("2024-03-28"),
            pd.Timestamp("2024-03-29"),
            pd.Timestamp("2024-04-01"),
        ),
    )
    def test_previous_trade_date_rolls_back_over_weekend(self, _mock_calendar):
        """
        测试此前交易日会在周末正确回退。
        
        参数：
            _mock_calendar: 模拟的交易日历接口。
        
        返回：
            None: 无返回值。
        """
        self.assertEqual(get_previous_trade_date("2024-03-31"), "2024-03-29")

    @patch(
        "tradingagents.dataflows.a_share_common.get_trade_calendar",
        return_value=(
            pd.Timestamp("2024-03-28"),
            pd.Timestamp("2024-03-29"),
            pd.Timestamp("2024-04-01"),
        ),
    )
    def test_is_trade_date_uses_calendar(self, _mock_calendar):
        """
        测试是否为交易日的判断依赖交易日历。
        
        参数：
            _mock_calendar: 模拟的交易日历接口。
        
        返回：
            None: 无返回值。
        """
        self.assertTrue(is_trade_date("2024-04-01"))
        self.assertFalse(is_trade_date("2024-03-30"))


if __name__ == "__main__":
    unittest.main()
