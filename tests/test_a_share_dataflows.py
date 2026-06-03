import unittest
from unittest.mock import patch

import pandas as pd
import requests

from tradingagents.dataflows.a_share import (
    get_balance_sheet,
    get_cashflow,
    get_company_announcements,
    get_fundamentals,
    get_indicators,
    get_income_statement,
    get_market_news,
    get_news,
    get_stock_data,
)


class AShareDataflowTests(unittest.TestCase):
    @patch("tradingagents.dataflows.a_share.ak.stock_zh_a_hist")
    def test_get_stock_data_formats_a_share_ohlcv(self, mock_hist):
        """
        测试获取股票数据时会正确格式化 A 股 OHLCV。
        
        参数：
            mock_hist: 模拟的历史行情接口。
        
        返回：
            None: 无返回值。
        """
        mock_hist.return_value = pd.DataFrame(
            {
                "日期": ["2024-03-01", "2024-03-04"],
                "股票代码": ["600519", "600519"],
                "开盘": [100.1234, 101.0],
                "收盘": [101.0, 102.0],
                "最高": [102.0, 103.0],
                "最低": [99.0, 100.0],
                "成交量": [1000, 1200],
                "成交额": [1_000_000, 1_200_000],
                "振幅": [3.0, 2.0],
                "涨跌幅": [1.1, 0.9],
                "涨跌额": [1.0, 1.0],
                "换手率": [0.5, 0.6],
            }
        )

        result = get_stock_data("600519", "2024-03-01", "2024-03-04")
        # import pdb; pdb.set_trace()

        self.assertIn("600519.SH", result)
        self.assertIn("TurnoverPct", result)
        self.assertIn("2024-03-04", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_zh_a_hist_tx")
    @patch("tradingagents.dataflows.a_share.ak.stock_zh_a_hist")
    def test_get_stock_data_falls_back_to_tencent_when_eastmoney_fails(self, mock_hist, mock_hist_tx):
        """
        测试东方财富行情接口失败时会自动回退腾讯行情接口。

        参数：
            mock_hist: 模拟的东方财富历史行情接口。
            mock_hist_tx: 模拟的腾讯历史行情接口。

        返回：
            None: 无返回值。
        """
        mock_hist.side_effect = requests.exceptions.ConnectionError("Connection aborted")
        mock_hist_tx.return_value = pd.DataFrame(
            {
                "date": ["2024-03-01", "2024-03-04"],
                "open": [100.0, 101.0],
                "close": [101.0, 102.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "amount": [12345.0, 23456.0],
            }
        )

        result = get_stock_data("600519", "2024-03-01", "2024-03-04")

        self.assertIn("600519.SH", result)
        self.assertIn("Amount", result)
        self.assertIn("PctChange", result)
        self.assertIn("2024-03-04", result)
        mock_hist_tx.assert_called_once()

    @patch("tradingagents.dataflows.a_share.ak.stock_financial_abstract")
    @patch("tradingagents.dataflows.a_share.ak.stock_zygc_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_zyjs_ths")
    @patch("tradingagents.dataflows.a_share.ak.stock_individual_info_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_profile_cninfo")
    def test_get_fundamentals_builds_multi_section_summary(
        self,
        mock_profile,
        mock_info,
        mock_intro,
        mock_business,
        mock_abstract,
    ):
        """
        测试基本面数据会生成多分段摘要。

        参数：
            mock_profile: 模拟的巨潮公司概况接口。
            mock_info: 模拟的东方财富个股信息接口。
            mock_intro: 模拟的公司简介接口。
            mock_business: 模拟的主营构成接口。
            mock_abstract: 模拟的财务摘要接口。

        返回：
            None: 无返回值。
        """
        mock_profile.return_value = pd.DataFrame(
            {
                "公司名称": ["贵州茅台酒股份有限公司"],
                "A股代码": ["600519"],
                "A股简称": ["贵州茅台"],
                "所属行业": ["酒、饮料和精制茶制造业"],
            }
        )
        mock_info.return_value = pd.DataFrame({"item": ["股票代码", "股票简称"], "value": ["600519", "贵州茅台"]})
        mock_intro.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "主营业务": ["白酒生产与销售"],
                "产品类型": ["白酒"],
                "产品名称": ["茅台酒"],
                "经营范围": ["白酒相关业务"],
            }
        )
        mock_business.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "报告日期": ["2024-09-30"],
                "分类类型": ["按产品分类"],
                "主营构成": ["茅台酒"],
                "主营收入": [100.0],
                "收入比例": [0.9],
                "主营成本": [30.0],
                "成本比例": [0.3],
                "主营利润": [70.0],
                "利润比例": [0.7],
                "毛利率": [0.7],
            }
        )
        mock_abstract.return_value = pd.DataFrame(
            {
                "选项": ["常用指标", "常用指标"],
                "指标": ["归母净利润", "营业总收入"],
                "20240930": [1.0, 2.0],
                "20240630": [0.8, 1.5],
            }
        )

        result = get_fundamentals("600519", "2024-10-01")

        self.assertIn("A-share company profile", result)
        self.assertIn("贵州茅台酒股份有限公司", result)
        self.assertIn("主营业务简介", result)
        self.assertIn("最新关键财务摘要", result)
        self.assertIn("归母净利润", result)
        mock_info.assert_not_called()

    @patch("tradingagents.dataflows.a_share.ak.stock_financial_abstract")
    @patch("tradingagents.dataflows.a_share.ak.stock_zygc_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_zyjs_ths")
    @patch("tradingagents.dataflows.a_share.ak.stock_individual_info_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_profile_cninfo")
    def test_get_fundamentals_falls_back_to_eastmoney_profile_when_cninfo_fails(
        self,
        mock_profile,
        mock_info,
        mock_intro,
        mock_business,
        mock_abstract,
    ):
        """
        测试巨潮公司概况失败时会回退到东方财富个股信息接口。

        参数：
            mock_profile: 模拟的巨潮公司概况接口。
            mock_info: 模拟的个股信息接口。
            mock_intro: 模拟的公司简介接口。
            mock_business: 模拟的主营构成接口。
            mock_abstract: 模拟的财务摘要接口。

        返回：
            None: 无返回值。
        """
        mock_profile.side_effect = requests.exceptions.ConnectionError("Connection aborted")
        mock_info.return_value = pd.DataFrame({"item": ["股票代码", "股票简称"], "value": ["600519", "贵州茅台"]})
        mock_intro.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "主营业务": ["白酒生产与销售"],
                "产品类型": ["白酒"],
                "产品名称": ["茅台酒"],
                "经营范围": ["白酒相关业务"],
            }
        )
        mock_business.return_value = pd.DataFrame(
            {
                "股票代码": ["600519"],
                "报告日期": ["2024-09-30"],
                "分类类型": ["按产品分类"],
                "主营构成": ["茅台酒"],
                "主营收入": [100.0],
                "收入比例": [0.9],
                "主营成本": [30.0],
                "成本比例": [0.3],
                "主营利润": [70.0],
                "利润比例": [0.7],
                "毛利率": [0.7],
            }
        )
        mock_abstract.return_value = pd.DataFrame(
            {
                "选项": ["常用指标", "常用指标"],
                "指标": ["归母净利润", "营业总收入"],
                "20240930": [1.0, 2.0],
                "20240630": [0.8, 1.5],
            }
        )

        result = get_fundamentals("600519", "2024-10-01")

        self.assertIn("A-share company profile", result)
        self.assertIn("股票代码", result)
        self.assertIn("主营业务简介", result)
        self.assertIn("最新关键财务摘要", result)
        self.assertIn("归母净利润", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_balance_sheet_by_report_em")
    def test_get_balance_sheet_selects_key_columns(self, mock_balance):
        """
        测试资产负债表会筛选关键字段。
        
        参数：
            mock_balance: 模拟的资产负债表接口。
        
        返回：
            None: 无返回值。
        """
        mock_balance.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2024-09-30"],
                "REPORT_DATE_NAME": ["2024三季报"],
                "TOTAL_ASSETS": [100.0],
                "TOTAL_LIABILITIES": [40.0],
                "TOTAL_PARENT_EQUITY": [60.0],
                "MONETARYFUNDS": [20.0],
                "INVENTORY": [10.0],
                "ACCOUNTS_RECE": [5.0],
                "GOODWILL": [1.0],
            }
        )

        result = get_balance_sheet("600519")
        # import pdb; pdb.set_trace()

        self.assertIn("TOTAL_ASSETS", result)
        self.assertIn("2024三季报", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_cash_flow_sheet_by_report_em")
    def test_get_cashflow_selects_key_columns(self, mock_cashflow):
        """
        测试现金流量表会筛选关键字段。
        
        参数：
            mock_cashflow: 模拟的现金流量表接口。
        
        返回：
            None: 无返回值。
        """
        mock_cashflow.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2024-09-30"],
                "REPORT_DATE_NAME": ["2024三季报"],
                "NETCASH_OPERATE": [30.0],
                "NETCASH_INVEST": [-10.0],
                "NETCASH_FINANCE": [-5.0],
                "CCE_ADD": [15.0],
                "PAY_STAFF_CASH": [2.0],
                "PAY_ALL_TAX": [8.0],
            }
        )

        result = get_cashflow("600519")
        # import pdb; pdb.set_trace()

        self.assertIn("NETCASH_OPERATE", result)
        self.assertIn("2024三季报", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_profit_sheet_by_report_em")
    def test_get_income_statement_selects_key_columns(self, mock_income):
        """
        测试利润表会筛选关键字段。
        
        参数：
            mock_income: 模拟的利润表接口。
        
        返回：
            None: 无返回值。
        """
        mock_income.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2024-09-30"],
                "REPORT_DATE_NAME": ["2024三季报"],
                "TOTAL_OPERATE_INCOME": [100.0],
                "OPERATE_PROFIT": [30.0],
                "TOTAL_PROFIT": [28.0],
                "NETPROFIT": [25.0],
                "PARENT_NETPROFIT": [24.0],
                "DEDUCT_PARENT_NETPROFIT": [23.0],
                "BASIC_EPS": [1.5],
            }
        )

        result = get_income_statement("600519")
        # import pdb; pdb.set_trace()

        self.assertIn("TOTAL_OPERATE_INCOME", result)
        self.assertIn("2024三季报", result)

    @patch("tradingagents.dataflows.a_share._get_indicator_data")
    @patch("tradingagents.dataflows.a_share.get_previous_trade_date")
    def test_get_indicators_formats_series_with_gaps(self, mock_prev_trade_date, mock_indicator_data):
        """
        测试技术指标结果会按日期展开，并对缺失日期补充提示。

        参数：
            mock_prev_trade_date: 模拟的最近交易日函数。
            mock_indicator_data: 模拟的指标数据函数。

        返回：
            None: 无返回值。
        """
        mock_prev_trade_date.return_value = "2024-03-01"
        mock_indicator_data.return_value = {
            "2024-02-29": "1.23",
            "2024-03-01": "2.34",
        }

        result = get_indicators("600519", "macd", "2024-03-03", 2)

        self.assertIn("## 600519.SH macd values through 2024-03-01", result)
        self.assertIn("2024-02-28: N/A: 非交易日或无数据", result)
        self.assertIn("2024-02-29: 1.23", result)
        self.assertIn("2024-03-01: 2.34", result)
        self.assertIn("MACD 指标", result)

    def test_get_indicators_rejects_unsupported_indicator(self):
        """
        测试不支持的技术指标会抛出明确异常。

        返回：
            None: 无返回值。
        """
        with self.assertRaises(ValueError) as context:
            get_indicators("600519", "not_supported", "2024-03-01", 5)

        self.assertIn("is not supported", str(context.exception))
        self.assertIn("macd", str(context.exception))

    @patch("tradingagents.dataflows.a_share._get_indicator_data")
    @patch("tradingagents.dataflows.a_share.get_previous_trade_date")
    def test_get_indicators_returns_readable_error_when_data_source_fails(self, mock_prev_trade_date, mock_indicator_data):
        """
        测试技术指标底层数据源失败时会返回可读错误文本，而不是抛出异常。

        参数：
            mock_prev_trade_date: 模拟最近交易日函数。
            mock_indicator_data: 模拟的指标数据函数。

        返回：
            None: 无返回值。
        """
        mock_prev_trade_date.return_value = "2024-03-01"
        mock_indicator_data.side_effect = RuntimeError("mock data failure")

        result = get_indicators("600519", "macd", "2024-03-03", 2)

        self.assertIn("数据源访问失败", result)
        self.assertIn("mock data failure", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_balance_sheet_by_report_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_balance_sheet_by_yearly_em")
    def test_get_balance_sheet_annual_uses_yearly_endpoint(self, mock_yearly, mock_report):
        """
        测试资产负债表在 annual 模式下会调用年报接口。

        参数：
            mock_yearly: 模拟的年报资产负债表接口。
            mock_report: 模拟的定期报告资产负债表接口。

        返回：
            None: 无返回值。
        """
        mock_yearly.return_value = pd.DataFrame(
            {
                "REPORT_DATE_NAME": ["2024年报"],
                "TOTAL_ASSETS": [100.0],
            }
        )

        result = get_balance_sheet("600519", freq="annual")

        mock_yearly.assert_called_once()
        mock_report.assert_not_called()
        self.assertIn("2024年报", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_cash_flow_sheet_by_report_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_cash_flow_sheet_by_quarterly_em")
    def test_get_cashflow_annual_uses_quarterly_endpoint(self, mock_quarterly, mock_report):
        """
        测试现金流量表在 annual 模式下会调用年度接口分支。

        参数：
            mock_quarterly: 模拟的年度现金流接口。
            mock_report: 模拟的定期报告现金流接口。

        返回：
            None: 无返回值。
        """
        mock_quarterly.return_value = pd.DataFrame(
            {
                "REPORT_DATE_NAME": ["2024年报"],
                "NETCASH_OPERATE": [10.0],
            }
        )

        result = get_cashflow("600519", freq="annual")

        mock_quarterly.assert_called_once()
        mock_report.assert_not_called()
        self.assertIn("2024年报", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_profit_sheet_by_report_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_profit_sheet_by_quarterly_em")
    def test_get_income_statement_annual_uses_quarterly_endpoint(self, mock_quarterly, mock_report):
        """
        测试利润表在 annual 模式下会调用年度接口分支。

        参数：
            mock_quarterly: 模拟的年度利润表接口。
            mock_report: 模拟的定期报告利润表接口。

        返回：
            None: 无返回值。
        """
        mock_quarterly.return_value = pd.DataFrame(
            {
                "REPORT_DATE_NAME": ["2024年报"],
                "TOTAL_OPERATE_INCOME": [10.0],
            }
        )

        result = get_income_statement("600519", freq="annual")

        mock_quarterly.assert_called_once()
        mock_report.assert_not_called()
        self.assertIn("2024年报", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_info_global_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_research_report_em")
    def test_get_news_filters_company_news_by_date(self, mock_report, mock_market):
        """
        测试个股综合资讯会按日期过滤研报。

        参数：
            mock_report: 模拟的券商研报接口。
            mock_market: 模拟的市场快讯接口。

        返回：
            None: 无返回值。
        """
        mock_report.return_value = pd.DataFrame(
            {
                "日期": ["2024-03-02 10:00:00", "2024-02-20 10:00:00"],
                "股票代码": ["600519", "600519"],
                "报告名称": ["标题A", "标题B"],
                "机构": ["机构A", "机构B"],
                "东财评级": ["买入", "增持"],
                "报告PDF链接": ["http://a", "http://b"],
            }
        )
        mock_market.return_value = pd.DataFrame()

        result = get_news("600519", "2024-03-01", "2024-03-03")

        self.assertIn("标题A", result)
        self.assertNotIn("标题B", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_info_global_em")
    @patch("tradingagents.dataflows.a_share.ak.stock_research_report_em")
    def test_get_news_temporarily_switches_string_storage(self, mock_report, mock_market):
        """
        测试个股综合资讯接口能正确调用研报接口并返回结果。

        参数：
            mock_report: 模拟的券商研报接口。
            mock_market: 模拟的市场快讯接口。

        返回：
            None: 无返回值。
        """
        mock_report.return_value = pd.DataFrame(
            {
                "日期": ["2024-03-02 10:00:00"],
                "股票代码": ["600519"],
                "报告名称": ["标题A"],
                "机构": ["机构A"],
                "东财评级": ["买入"],
                "报告PDF链接": ["http://a"],
            }
        )
        mock_market.return_value = pd.DataFrame()

        result = get_news("600519", "2024-03-01", "2024-03-03")

        mock_report.assert_called_once()
        self.assertIn("标题A", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_info_global_em")
    def test_get_market_news_filters_range_and_limit(self, mock_market_news):
        """
        测试市场新闻会按区间与数量限制过滤。
        
        参数：
            mock_market_news: 模拟的市场新闻接口。
        
        返回：
            None: 无返回值。
        """
        mock_market_news.return_value = pd.DataFrame(
            {
                "标题": ["政策新闻", "过期新闻"],
                "摘要": ["摘要A", "摘要B"],
                "发布时间": ["2024-03-03 08:00:00", "2024-02-01 08:00:00"],
                "链接": ["http://a", "http://b"],
            }
        )

        result = get_market_news("2024-03-03", look_back_days=7, limit=5)
        # import pdb; pdb.set_trace()

        self.assertIn("政策新闻", result)
        self.assertNotIn("过期新闻", result)

    @patch("tradingagents.dataflows.a_share.ak.stock_notice_report")
    def test_get_company_announcements_aggregates_by_symbol(self, mock_notice):
        """
        测试公司公告会按股票代码聚合。
        
        参数：
            mock_notice: 模拟的公司公告接口。
        
        返回：
            None: 无返回值。
        """
        mock_notice.side_effect = [
            pd.DataFrame(
                {
                    "代码": ["600519", "000001"],
                    "名称": ["贵州茅台", "平安银行"],
                    "公告标题": ["茅台公告", "平安公告"],
                    "公告类型": ["财务报告", "风险提示"],
                    "公告日期": ["2024-03-01", "2024-03-01"],
                    "网址": ["http://a", "http://b"],
                }
            ),
            pd.DataFrame(
                {
                    "代码": ["600519"],
                    "名称": ["贵州茅台"],
                    "公告标题": ["茅台公告2"],
                    "公告类型": ["重大事项"],
                    "公告日期": ["2024-03-02"],
                    "网址": ["http://c"],
                }
            ),
        ]

        result = get_company_announcements("600519", "2024-03-01", "2024-03-02")
        # import pdb; pdb.set_trace()

        self.assertIn("茅台公告", result)
        self.assertIn("茅台公告2", result)
        self.assertNotIn("平安公告", result)


if __name__ == "__main__":
    unittest.main()
