from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_caixin_news,
    get_company_announcements,
    get_global_news,
    get_instrument_context_from_state,
    get_language_instruction,
    get_market_news,
    get_news,
)
from tradingagents.dataflows.a_share_common import is_ashare_ticker
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)
        ashare = is_ashare_ticker(ticker)

        if ashare:
            tools = [
                get_news,
                get_caixin_news,
                get_company_announcements,
                get_market_news,
            ]
        else:
            tools = [
                get_news,
                get_global_news,
            ]

        system_message = _build_system_message(ashare=ashare, asset_label=asset_label)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node


def _build_system_message(*, ashare: bool, asset_label: str) -> str:
    if ashare:
        return (
            f"你是一名 A 股新闻研究员，负责分析过去一周关于该{asset_label}的新闻与宏观动态。请撰写一份全面的 A 股市场新闻分析报告，为交易决策提供依据。"
            " 可用工具：\n"
            "  - get_news(query, start_date, end_date)：搜索个股相关新闻与券商研报\n"
            "  - get_caixin_news(ticker, limit)：获取财新专业媒体关于该股的深度报道\n"
            "  - get_company_announcements(ticker, start_date, end_date, category)：获取公司公告（业绩预告、分红、增减持、重大合同等）\n"
            "  - get_market_news(curr_date, look_back_days, limit)：获取 A 股市场宏观政策新闻\n"
            " 请依次调用这些工具获取完整信息。提供具体、可操作的见解并附上支撑证据。"
            " 报告末尾用 Markdown 表格汇总关键要点，便于快速查阅。"
            + get_language_instruction()
        )
    else:
        return (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )
