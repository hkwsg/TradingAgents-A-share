from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Dict, List, Optional
from collections import defaultdict
import json

from langchain_core.callbacks import BaseCallbackHandler


def _safe_serialize(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)[:500]


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


@dataclass
class TimeSpan:
    kind: str
    start: float
    end: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        if self.end is None:
            return 0.0
        return max(0.0, self.end - self.start)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class NodeBreakdown:
    node_name: str
    round_num: int
    llm_calls: List[TimeSpan] = field(default_factory=list)
    tool_calls: List[TimeSpan] = field(default_factory=list)

    @property
    def llm_total(self) -> float:
        return sum(s.duration for s in self.llm_calls)

    @property
    def tool_total(self) -> float:
        return sum(s.duration for s in self.tool_calls)

    @property
    def total(self) -> float:
        return self.llm_total + self.tool_total

    @property
    def prompt_tokens_total(self) -> int:
        return sum(s.prompt_tokens for s in self.llm_calls)

    @property
    def completion_tokens_total(self) -> int:
        return sum(s.completion_tokens for s in self.llm_calls)

    @property
    def tokens_total(self) -> int:
        return self.prompt_tokens_total + self.completion_tokens_total


class PerfCallbacks(BaseCallbackHandler):

    def __init__(self):
        super().__init__()
        self._nodes: Dict[str, NodeBreakdown] = {}
        self._rounds: Dict[str, int] = defaultdict(int)
        self._llm_spans: Dict[str, TimeSpan] = {}
        self._tool_spans: Dict[str, TimeSpan] = {}
        self._run_nodes: Dict[str, str] = {}
        self._current_node: Optional[str] = None

    def _ensure_node(self, name: str) -> NodeBreakdown:
        if name not in self._nodes:
            self._rounds[name] += 1
            self._nodes[name] = NodeBreakdown(
                node_name=name, round_num=self._rounds[name])
        return self._nodes[name]

    def _node_from_context(self, serialized=None, tags=None, metadata=None) -> Optional[str]:
        metadata = metadata or {}
        tags = tags or []
        node = metadata.get("langgraph_node") or metadata.get("node")
        if node:
            return str(node)
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("langgraph_node:"):
                return tag.split(":", 1)[1]
        if serialized:
            name = serialized.get("name")
            if name:
                return str(name)
        return self._current_node

    def on_llm_start(self, serialized, prompts, *, run_id=None,
                     parent_run_id=None, tags=None, metadata=None, **kwargs):
        key = str(run_id)
        node_name = self._node_from_context(serialized, tags, metadata)
        if node_name:
            self._run_nodes[key] = node_name
        self._llm_spans[key] = TimeSpan(
            kind="llm",
            start=monotonic(),
            metadata={"run_id": key},
        )

    def on_llm_end(self, response, *, run_id=None,
                   parent_run_id=None, **kwargs):
        key = str(run_id)
        span = self._llm_spans.pop(key, None)
        if span is not None:
            span.end = monotonic()
            # extract token usage from LLM response
            token_usage = {}
            if hasattr(response, "llm_output") and response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})
            span.prompt_tokens = token_usage.get("prompt_tokens", 0) or 0
            span.completion_tokens = token_usage.get("completion_tokens", 0) or 0
            node_name = self._run_nodes.pop(key, None) or self._current_node
            if node_name:
                node = self._ensure_node(node_name)
                node.llm_calls.append(span)

    def on_llm_error(self, error, *, run_id=None,
                     parent_run_id=None, **kwargs):
        key = str(run_id)
        span = self._llm_spans.pop(key, None)
        if span is not None:
            span.end = monotonic()
        self._run_nodes.pop(key, None)

    def on_tool_start(self, serialized, input_str, *, run_id=None,
                      parent_run_id=None, tags=None, metadata=None, **kwargs):
        serialized = serialized or {}
        key = str(run_id)
        node_name = self._node_from_context(serialized, tags, metadata)
        if node_name:
            self._run_nodes[key] = node_name
        self._tool_spans[key] = TimeSpan(
            kind="tool", start=monotonic(),
            metadata={"run_id": key,
                      "tool": serialized.get("name", "unknown")})

    def on_tool_end(self, output, *, run_id=None,
                    parent_run_id=None, **kwargs):
        key = str(run_id)
        span = self._tool_spans.pop(key, None)
        if span is not None:
            span.end = monotonic()
            node_name = self._run_nodes.pop(key, None) or self._current_node
            if node_name:
                node = self._ensure_node(node_name)
                node.tool_calls.append(span)

    def on_tool_error(self, error, *, run_id=None,
                      parent_run_id=None, **kwargs):
        key = str(run_id)
        span = self._tool_spans.pop(key, None)
        if span is not None:
            span.end = monotonic()
        self._run_nodes.pop(key, None)

    def on_chain_start(self, serialized, inputs, *, run_id=None,
                       parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._current_node = serialized.get("name", "")

    def on_chain_end(self, outputs, *, run_id=None,
                     parent_run_id=None, **kwargs):
        self._current_node = None

    def get_nodes(self) -> List[NodeBreakdown]:
        return list(self._nodes.values())

    def to_dict(self) -> Dict:
        nodes_data = []
        for node in self.get_nodes():
            llm_detail = [{"duration_s": round(s.duration, 2),
                          "prompt_tokens": s.prompt_tokens,
                          "completion_tokens": s.completion_tokens,
                          "metadata": {k: _safe_serialize(v)
                                      for k, v in s.metadata.items()}}
                         for s in node.llm_calls]
            tool_detail = [{"duration_s": round(s.duration, 2),
                           "metadata": {k: _safe_serialize(v)
                                       for k, v in s.metadata.items()}}
                          for s in node.tool_calls]
            nodes_data.append({
                "node": node.node_name,
                "round": node.round_num,
                "llm_total_s": round(node.llm_total, 1),
                "tool_total_s": round(node.tool_total, 1),
                "total_s": round(node.total, 1),
                "prompt_tokens": node.prompt_tokens_total,
                "completion_tokens": node.completion_tokens_total,
                "total_tokens": node.tokens_total,
                "llm_calls": llm_detail,
                "tool_calls": tool_detail,
            })
        total_llm = sum(n.llm_total for n in self.get_nodes())
        total_tool = sum(n.tool_total for n in self.get_nodes())
        all_prompt = sum(n.prompt_tokens_total for n in self.get_nodes())
        all_completion = sum(n.completion_tokens_total for n in self.get_nodes())
        return {
            "total_llm_s": round(total_llm, 1),
            "total_tool_s": round(total_tool, 1),
            "total_s": round(total_llm + total_tool, 1),
            "total_prompt_tokens": all_prompt,
            "total_completion_tokens": all_completion,
            "total_tokens": all_prompt + all_completion,
            "nodes": nodes_data,
        }

    def format_rich_table(self, console=None):
        from rich.table import Table
        from rich.console import Console
        if console is None:
            console = Console()
        table = Table(title="LLM vs 工具调用耗时 + Token 分解", border_style="dim magenta",
                      show_header=True, header_style="bold white")
        table.add_column("节点", style="cyan", no_wrap=True)
        table.add_column("轮", justify="center", style="dim")
        table.add_column("LLM", justify="right", style="green")
        table.add_column("工具", justify="right", style="yellow")
        table.add_column("输入Token", justify="right", style="blue")
        table.add_column("输出Token", justify="right", style="magenta")
        table.add_column("合计Token", justify="right", style="bold white")

        total_llm = 0.0
        total_tool = 0.0
        total_prompt = 0
        total_completion = 0
        for node in self.get_nodes():
            table.add_row(
                node.node_name, str(node.round_num),
                f"{node.llm_total:.0f}s", f"{node.tool_total:.0f}s",
                _fmt_tokens(node.prompt_tokens_total),
                _fmt_tokens(node.completion_tokens_total),
                _fmt_tokens(node.tokens_total),
            )
            total_llm += node.llm_total
            total_tool += node.tool_total
            total_prompt += node.prompt_tokens_total
            total_completion += node.completion_tokens_total

        table.add_row("总计", "",
                      f"{total_llm:.0f}s", f"{total_tool:.0f}s",
                      _fmt_tokens(total_prompt),
                      _fmt_tokens(total_completion),
                      _fmt_tokens(total_prompt + total_completion),
                      style="bold white")
        return table

    def print_report(self, console=None):
        if console is None:
            from rich.console import Console
            console = Console()
        console.print(self.format_rich_table(console))
