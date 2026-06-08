"""Helpers for LangGraph streaming based performance monitoring."""

from typing import Any, Dict, Iterable, List

STATE_FIELD_NAMES = {
    "messages",
    "company_of_interest",
    "asset_type",
    "instrument_context",
    "trade_date",
    "sender",
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_debate_state",
    "investment_plan",
    "trader_investment_plan",
    "risk_debate_state",
    "final_trade_decision",
    "past_context",
}


def active_nodes_from_update_chunk(chunk: Dict[str, Any]) -> List[str]:
    """Return graph node names from a ``stream_mode="updates"`` chunk."""
    return [
        name
        for name, value in chunk.items()
        if name not in STATE_FIELD_NAMES and name != "__end__" and isinstance(value, dict)
    ]


def merge_stream_updates(chunks: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge LangGraph update chunks into a final state-like dictionary.

    In ``updates`` mode each stream item is shaped as ``{node_name: delta}``.
    Report generation expects the accumulated state fields, so unwrap the
    per-node deltas before merging.
    """
    final_state: Dict[str, Any] = {}
    for chunk in chunks:
        active_nodes = active_nodes_from_update_chunk(chunk)
        if active_nodes:
            for node_name in active_nodes:
                final_state.update(chunk[node_name])
        else:
            # Keep a fail-open path for callers that still pass values-mode
            # chunks in tests or debug utilities.
            final_state.update(chunk)
    return final_state
