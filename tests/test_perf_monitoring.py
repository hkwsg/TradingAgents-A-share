import time
import unittest
from types import SimpleNamespace

from tradingagents.graph.monitoring import (
    active_nodes_from_update_chunk,
    merge_stream_updates,
)
from tradingagents.graph.perf_callbacks import PerfCallbacks
from tradingagents.graph.propagation import Propagator


class MonitoringStreamTests(unittest.TestCase):
    def test_graph_args_can_request_update_stream_with_callbacks(self):
        callback = object()
        args = Propagator(max_recur_limit=7).get_graph_args(
            callbacks=[callback],
            stream_mode="updates",
        )

        self.assertEqual(args["stream_mode"], "updates")
        self.assertEqual(args["config"]["recursion_limit"], 7)
        self.assertEqual(args["config"]["callbacks"], [callback])

    def test_active_nodes_use_update_chunk_keys_not_state_keys(self):
        chunk = {
            "Market Analyst": {"market_report": "done"},
            "messages": [("ai", "ignored outer value")],
        }

        self.assertEqual(active_nodes_from_update_chunk(chunk), ["Market Analyst"])

    def test_merge_stream_updates_unwraps_node_deltas(self):
        trace = [
            {"Market Analyst": {"market_report": "done"}},
            {"Msg Clear Market": {"messages": []}},
            {"Trader": {"final_trade_decision": "BUY"}},
        ]

        self.assertEqual(
            merge_stream_updates(trace),
            {
                "market_report": "done",
                "messages": [],
                "final_trade_decision": "BUY",
            },
        )

    def test_merge_stream_updates_keeps_values_mode_state_fields(self):
        values_chunk = {
            "company_of_interest": "600276",
            "investment_debate_state": {"count": 1},
            "risk_debate_state": {"count": 0},
            "final_trade_decision": "BUY",
        }

        self.assertEqual(merge_stream_updates([values_chunk]), values_chunk)


class PerfCallbacksTests(unittest.TestCase):
    def test_records_llm_call_from_langgraph_node_metadata(self):
        handler = PerfCallbacks()
        response = SimpleNamespace(
            llm_output={
                "token_usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                }
            }
        )

        handler.on_llm_start(
            {},
            ["prompt"],
            run_id="llm-1",
            metadata={"langgraph_node": "Market Analyst"},
        )
        time.sleep(0.06)
        handler.on_llm_end(response, run_id="llm-1")

        data = handler.to_dict()
        self.assertEqual(data["nodes"][0]["node"], "Market Analyst")
        self.assertEqual(data["total_prompt_tokens"], 11)
        self.assertEqual(data["total_completion_tokens"], 7)
        self.assertGreater(data["total_llm_s"], 0)


if __name__ == "__main__":
    unittest.main()
