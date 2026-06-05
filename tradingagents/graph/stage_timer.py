from dataclasses import dataclass, field
from time import monotonic
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.text import Text

# phase definitions: (display_name, emoji, node_name_patterns)
PHASES: List[Tuple[str, str, List[str]]] = [
    ("分析师阶段", "=", [
        "Market Analyst",
        "Sentiment Analyst",
        "News Analyst",
        "Fundamentals Analyst",
    ]),
    ("多空辩论", "=", [
        "Bull Researcher",
        "Bear Researcher",
    ]),
    ("研究经理", "=", [
        "Research Manager",
    ]),
    ("交易计划", "=", [
        "Trader",
    ]),
    ("风险辩论", "=", [
        "Aggressive Analyst",
        "Conservative Analyst",
        "Neutral Analyst",
    ]),
    ("组合经理", "=", [
        "Portfolio Manager",
    ]),
]


@dataclass
class NodeSpan:
    node_name: str
    round_num: int
    wall_seconds: float


@dataclass
class PhaseSummary:
    display_name: str
    spans: List[NodeSpan] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return sum(s.wall_seconds for s in self.spans)


class StageTimer:
    """Per-node wall-clock timer driven by LangGraph streaming chunks.

    Usage::

        timer = StageTimer()
        for chunk in graph.stream(state):
            active = [k for k in chunk if k != "messages"]
            if active:
                timer.tick(active)
        timer.finalize()
        timer.print_report()
    """

    def __init__(self):
        self._prev_node: Optional[str] = None
        self._prev_time: Optional[float] = None
        self._spans: List[NodeSpan] = []
        self._rounds: Dict[str, int] = {}
        self.total_seconds: float = 0.0
        self._start_time: float = monotonic()

    def tick(self, active_nodes: List[str]) -> None:
        """Record a node transition. Call once per stream chunk."""
        now = monotonic()
        current = active_nodes[0]

        if self._prev_node is not None and self._prev_time is not None:
            duration = now - self._prev_time
            if duration > 0:
                self._spans.append(NodeSpan(
                    node_name=self._prev_node,
                    round_num=self._rounds.get(self._prev_node, 1),
                    wall_seconds=duration,
                ))

        self._rounds[current] = self._rounds.get(current, 0) + 1
        self._prev_node = current
        self._prev_time = now

    def finalize(self) -> None:
        """Call after stream loop ends to close the last node span."""
        now = monotonic()
        if self._prev_node is not None and self._prev_time is not None:
            duration = now - self._prev_time
            if duration > 0:
                self._spans.append(NodeSpan(
                    node_name=self._prev_node,
                    round_num=self._rounds.get(self._prev_node, 1),
                    wall_seconds=duration,
                ))
        self.total_seconds = now - self._start_time
        self._prev_node = None
        self._prev_time = None

    def phase_summaries(self) -> List[PhaseSummary]:
        """Group recorded spans by phase."""
        name_to_phase: Dict[str, Tuple[int, str]] = {}
        for idx, (display, _emoji, patterns) in enumerate(PHASES):
            for p in patterns:
                name_to_phase[p] = (idx, display)

        phases: Dict[int, PhaseSummary] = {}
        for idx in range(len(PHASES)):
            phases[idx] = PhaseSummary(display_name=PHASES[idx][0])

        for span in self._spans:
            info = name_to_phase.get(span.node_name)
            if info is None:
                idx = len(PHASES)
                if idx not in phases:
                    phases[idx] = PhaseSummary(display_name=span.node_name)
            else:
                idx = info[0]
                if idx not in phases:
                    phases[idx] = PhaseSummary(display_name=info[1])
            phases[idx].spans.append(span)

        return [phases[i] for i in sorted(phases) if phases[i].spans]

    def to_dict(self) -> Dict:
        """Export timing data as a JSON-serializable dict."""
        return {
            "total_seconds": round(self.total_seconds, 1),
            "phases": [
                {
                    "phase": p.display_name,
                    "total_seconds": round(p.total_seconds, 1),
                    "nodes": [
                        {
                            "node": s.node_name,
                            "round": s.round_num,
                            "seconds": round(s.wall_seconds, 1),
                        }
                        for s in p.spans
                    ],
                }
                for p in self.phase_summaries()
            ],
        }

    def format_rich_table(self, console: Optional[Console] = None) -> Table:
        """Return a Rich Table for display."""
        if console is None:
            console = Console()
        table = Table(title="各阶段耗时分析", border_style="dim cyan",
                      show_header=True, header_style="bold white")
        table.add_column("阶段 / 节点", style="cyan", no_wrap=True)
        table.add_column("轮次", justify="center", style="dim")
        table.add_column("耗时", justify="right", style="green")
        table.add_column("占比", justify="right", style="yellow")

        for phase in self.phase_summaries():
            pct = (phase.total_seconds / self.total_seconds * 100) if self.total_seconds > 0 else 0
            if len(phase.spans) == 1:
                s = phase.spans[0]
                table.add_row(phase.display_name, "-",
                              f"{s.wall_seconds:.0f}s", f"{pct:.0f}%")
            else:
                table.add_row(phase.display_name, "",
                              f"{phase.total_seconds:.0f}s", f"{pct:.0f}%")
                for s in phase.spans:
                    sub_pct = (s.wall_seconds / self.total_seconds * 100) if self.total_seconds > 0 else 0
                    table.add_row(f"  {s.node_name}",
                                  f"R{s.round_num}",
                                  f"{s.wall_seconds:.0f}s",
                                  f"{sub_pct:.0f}%")

        table.add_row("总计", "", f"{self.total_seconds:.0f}s", "100%",
                      style="bold white")
        return table

    def print_report(self, console: Optional[Console] = None) -> None:
        """Print timing report to console."""
        if console is None:
            console = Console()
        console.print(self.format_rich_table(console))
