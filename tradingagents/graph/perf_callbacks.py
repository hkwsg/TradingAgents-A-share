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


@dataclass
class TimeSpan:
    kind: str
    start: float
    end: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        if self.end is None:
            return 0.0
        return max(0.0, self.end - self.start)


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


class PerfCallbacks(BaseCallbackHandler):

    def __init__(self):
        super().__init__()
        self._nodes: Dict[str, NodeBreakdown] = {}
        self._rounds: Dict[str, int] = defaultdict(int)
        self._current_llm: Optional[TimeSpan] = None
        self._current_tool: Optional[TimeSpan] = None
        self._current_node: Optional[str] = None

    def _ensure_node(self, name: str) -> NodeBreakdown:
        if name not in self._nodes:
            self._rounds[name] += 1
            self._nodes[name] = NodeBreakdown(
                node_name=name, round_num=self._rounds[name])
        return self._nodes[name]

    def on_llm_start(self, serialized, prompts, *, run_id=None,
                     parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._current_llm = TimeSpan(kind="llm", start=monotonic(),
                                     metadata={"run_id": str(run_id)})

    def on_llm_end(self, response, *, run_id=None,
                   parent_run_id=None, **kwargs):
        if self._current_llm is not None:
            self._current_llm.end = monotonic()
            if self._current_node:
                node = self._ensure_node(self._current_node)
                node.llm_calls.append(self._current_llm)
            self._current_llm = None

    def on_llm_error(self, error, *, run_id=None,
                     parent_run_id=None, **kwargs):
        if self._current_llm is not None:
            self._current_llm.end = monotonic()
            self._current_llm = None

    def on_tool_start(self, serialized, input_str, *, run_id=None,
                      parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._current_tool = TimeSpan(
            kind="tool", start=monotonic(),
            metadata={"run_id": str(run_id),
                      "tool": serialized.get("name", "unknown")})

    def on_tool_end(self, output, *, run_id=None,
                    parent_run_id=None, **kwargs):
        if self._current_tool is not None:
            self._current_tool.end = monotonic()
            if self._current_node:
                node = self._ensure_node(self._current_node)
                node.tool_calls.append(self._current_tool)
            self._current_tool = None

    def on_tool_error(self, error, *, run_id=None,
                      parent_run_id=None, **kwargs):
        if self._current_tool is not None:
            self._current_tool.end = monotonic()
            self._current_tool = None

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
                "llm_calls": llm_detail,
                "tool_calls": tool_detail,
            })
        total_llm = sum(n.llm_total for n in self.get_nodes())
        total_tool = sum(n.tool_total for n in self.get_nodes())
        return {
            "total_llm_s": round(total_llm, 1),
            "total_tool_s": round(total_tool, 1),
            "total_s": round(total_llm + total_tool, 1),
            "nodes": nodes_data,
        }

    def format_rich_table(self, console=None):
        from rich.table import Table
        from rich.console import Console
        if console is None:
            console = Console()
        table = Table(title="LLM vs 工具调用耗时分解", border_style="dim magenta",
                      show_header=True, header_style="bold white")
        table.add_column("节点", style="cyan", no_wrap=True)
        table.add_column("轮", justify="center", style="dim")
        table.add_column("LLM推理", justify="right", style="green")
        table.add_column("工具调用", justify="right", style="yellow")
        table.add_column("合计", justify="right", style="bold white")

        total_llm = 0.0
        total_tool = 0.0
        for node in self.get_nodes():
            table.add_row(node.node_name, str(node.round_num),
                          f"{node.llm_total:.0f}s", f"{node.tool_total:.0f}s",
                          f"{node.total:.0f}s")
            total_llm += node.llm_total
            total_tool += node.tool_total

        table.add_row("总计", "", f"{total_llm:.0f}s", f"{total_tool:.0f}s",
                      f"{total_llm + total_tool:.0f}s", style="bold white")
        return table

    def print_report(self, console=None):
        if console is None:
            from rich.console import Console
            console = Console()
        console.print(self.format_rich_table(console))
