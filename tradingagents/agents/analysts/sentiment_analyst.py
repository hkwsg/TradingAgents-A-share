"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  A-share tickers:
    1. News headlines     — A-share ticker-specific news
    2. Xueqiu sentiment   — retail sentiment ranking (followers/discussion/activity)

  Non-A-share tickers:
    1. News headlines     — Yahoo Finance (institutional framing)
    2. StockTwits messages — retail-trader posts indexed by cashtag
    3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. Output uses the structured-output pattern (json_schema for
OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic), falling
back to free-text generation for providers that lack native support, so
the sentiment header (band + score + confidence) is deterministic across
runs and providers instead of free-form per-model prose.

See: https://github.com/TauricResearch/TradingAgents/issues/557
See: https://github.com/TauricResearch/TradingAgents/issues/796
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_news,
    get_xueqiu_sentiment,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.a_share_common import is_ashare_ticker
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    A-share tickers use Xueqiu + A-share news; non-A-share tickers use
    StockTwits + Reddit + Yahoo Finance news.
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)
        ashare = is_ashare_ticker(ticker)

        # Pre-fetch data sources. For A-share tickers, use Xueqiu sentiment
        # and A-share news instead of StockTwits/Reddit which return empty.
        news_block = get_news.func(ticker, start_date, end_date)

        if ashare:
            xueqiu_block = get_xueqiu_sentiment.func(ticker)
            stocktwits_block = ""
            reddit_block = ""
        else:
            xueqiu_block = ""
            stocktwits_block = fetch_stocktwits_messages(ticker, limit=30)
            reddit_block = fetch_reddit_posts(ticker)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            xueqiu_block=xueqiu_block,
            stocktwits_block=stocktwits_block,
            reddit_block=reddit_block,
            ashare=ashare,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    xueqiu_block: str,
    stocktwits_block: str,
    reddit_block: str,
    ashare: bool,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    if ashare:
        return _build_ashare_message(ticker, start_date, end_date, news_block, xueqiu_block)
    return _build_global_message(ticker, start_date, end_date, news_block, stocktwits_block, reddit_block)


def _build_ashare_message(
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    xueqiu_block: str,
) -> str:
    """A-share sentiment analysis prompt using domestic data sources."""
    return f"""你是一名 A 股市场情绪分析师。请为 {ticker} 撰写一份全面的情绪分析报告，覆盖 {start_date} 至 {end_date}。

## 数据源（已预先获取，在下方 prompt 中）

### 个股新闻 — 过去 7 天
机构视角。关注券商研报、公司公告、行业政策等影响情绪的实质性信息。

<start_of_news>
{news_block}
<end_of_news>

### 雪球情绪数据 — 散户关注度/讨论度/交易热度排名
散户情绪的代理指标。高排名意味着该股在散户群体中关注度高，短期波动可能放大。

<start_of_xueqiu>
{xueqiu_block}
<end_of_xueqiu>

## 分析方法

1. **雪球排名解读**：综合排名前 10 表明极高关注度，容易引发情绪驱动的短期波动；前 100 为高关注度，散户情绪有一定定价权；100 名以后情绪影响力递减。

2. **新闻面信号提取**：从新闻中识别券商评级变化、业绩预期调整、行业政策动向、公司重大事件（如分红、回购、增减持）。

3. **情绪一致性判断**：新闻偏正面但散户偏冷清 → 机构主导，情绪稳定；新闻平淡但散户高度关注 → 可能有预期差行情；新闻负面且散户恐慌 → 短期压力放大。

4. **区分观点与事实**：券商研报的"买入/增持"是观点；公司公告的业绩数据是事实。两者权重不同。

5. **诚实标注数据质量**：如果雪球数据无法获取或新闻极少，务必在报告中明确标注，降低置信度。

6. **识别催化剂与风险**：从新闻和情绪数据中提取可能影响短期股价的事件（财报发布、分红公告、行业政策变化等）。

7. **情绪不预测价格**：你的结论是情绪快照，为交易员提供参考，不是价格预测。

## 输出字段

- **overall_band**: Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish 六选一
- **overall_score**: 0（极度看空）到 10（极度看多），5 为中性，与 overall_band 保持一致
- **confidence**: low / medium / high，取决于数据质量和样本量
- **narrative**: 完整的逐源分析、来源间分歧、主导叙事主题、催化剂与风险、关键情绪信号汇总表

{get_language_instruction()}"""


def _build_global_message(
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    """Non-A-share sentiment analysis prompt (original StockTwits + Reddit + Yahoo)."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this explicitly in the `confidence` field and the narrative. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
