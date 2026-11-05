"""Agent 5 — the end-to-end research pipeline, built by composing agents 1–4 as subgraphs.

    START -> connect --ok--> job --outputs--> analyze -> report -> END
                 \\--fail--> END    \\--none--> END

Each compiled subgraph is added directly as a node. LangGraph passes the keys the parent
and child state share, so the parent state is just the union of the four child states.
The human approval interrupt inside the job subgraph bubbles up to this graph.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import analysis_agent, connect_agent, job_agent, report_agent


class PipelineState(
    connect_agent.ConnectState,
    job_agent.JobState,
    analysis_agent.AnalysisState,
    report_agent.ReportState,
    total=False,
):
    pass


def route_after_connect(state: PipelineState) -> str:
    return "job" if state.get("connected") else END


def route_after_job(state: PipelineState) -> str:
    return "analyze" if state.get("outputs") else END


def build_graph(checkpointer=None):
    g = StateGraph(PipelineState)
    g.add_node("connect", connect_agent.build_graph())
    g.add_node("job", job_agent.build_graph(standalone=False))
    g.add_node("analyze", analysis_agent.build_graph())
    g.add_node("report", report_agent.build_graph())
    g.add_edge(START, "connect")
    g.add_conditional_edges("connect", route_after_connect, ["job", END])
    g.add_conditional_edges("job", route_after_job, ["analyze", END])
    g.add_edge("analyze", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())
