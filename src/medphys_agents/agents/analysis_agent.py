"""Agent 3 — analyze MC outputs: depth-dose metrics, gamma vs reference, QA flags, plot.

Graph:

    START -> load -> metrics -> qa_check -> plot -> END

Teaches: pure-Python analysis nodes (no LLM needed!), rule-based QA that produces
machine-readable flags the report agent can explain. Not every node should be an LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..physics.analysis import compare_to_reference, depth_dose_metrics, load_run, plot_runs

# QA tolerances (documented in the dose-comparison-qa skill)
MAX_REL_UNC_PERCENT = 2.0
MIN_GAMMA_PASS = 95.0
MAX_R80_DEVIATION_MM = 2.0


class AnalysisState(TypedDict, total=False):
    outputs: list[str]       # npz files from the job agent
    out_dir: str
    metrics: list[dict]
    flags: list[str]
    figure: str


def load(state: AnalysisState) -> AnalysisState:
    missing = [p for p in state["outputs"] if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(missing)
    return {}


def metrics(state: AnalysisState) -> AnalysisState:
    rows = []
    for p in state["outputs"]:
        run = load_run(p)
        rows.append({**depth_dose_metrics(run), **compare_to_reference(run), "file": p})
    rows.sort(key=lambda r: r["energy_mev"])
    return {"metrics": rows}


def qa_check(state: AnalysisState) -> AnalysisState:
    flags = []
    for m in state["metrics"]:
        e = m["energy_mev"]
        if m["mean_rel_unc_percent"] > MAX_REL_UNC_PERCENT:
            factor = (m["mean_rel_unc_percent"] / MAX_REL_UNC_PERCENT) ** 2
            flags.append(f"{e:g} MeV: statistical uncertainty {m['mean_rel_unc_percent']:.2f}% > "
                         f"{MAX_REL_UNC_PERCENT}% — rerun with ≥{factor:.1f}× histories")
        if m["gamma_pass_rate"] < MIN_GAMMA_PASS:
            flags.append(f"{e:g} MeV: gamma pass rate {m['gamma_pass_rate']:.1f}% < {MIN_GAMMA_PASS}% "
                         f"({m['gamma_criteria']})")
        if abs(m["R80_minus_csda_mm"]) > MAX_R80_DEVIATION_MM:
            flags.append(f"{e:g} MeV: R80 differs from CSDA range by {m['R80_minus_csda_mm']:+.2f} mm")
    return {"flags": flags}


def plot(state: AnalysisState) -> AnalysisState:
    out_dir = Path(state.get("out_dir") or Path(state["outputs"][0]).parents[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    fig = plot_runs([load_run(p) for p in state["outputs"]], out_dir / "idd_comparison.png")
    return {"figure": fig, "out_dir": str(out_dir)}


def build_graph():
    g = StateGraph(AnalysisState)
    for name, fn in [("load", load), ("metrics", metrics), ("qa_check", qa_check), ("plot", plot)]:
        g.add_node(name, fn)
    g.add_edge(START, "load")
    g.add_edge("load", "metrics")
    g.add_edge("metrics", "qa_check")
    g.add_edge("qa_check", "plot")
    g.add_edge("plot", END)
    return g.compile()
