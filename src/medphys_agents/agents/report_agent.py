"""Agent 4 — write a Markdown report from numbers the analysis agent computed.

Graph:

    START -> draft_discussion -> assemble -> END

Teaches: keep numbers deterministic (tables are generated in code) and let the LLM write
only the prose, with an instruction not to invent values. Offline, a template is used.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..llm import llm_text


class ReportState(TypedDict, total=False):
    title: str
    spec: dict
    job_id: str
    backend: str
    metrics: list[dict]
    flags: list[str]
    figure: str
    out_dir: str
    discussion: str
    report_path: str


COLUMNS = [
    ("energy_mev", "E (MeV)", "{:g}"), ("histories", "N", "{:,}"),
    ("R80_cm", "R80 (cm)", "{:.2f}"), ("csda_range_cm", "CSDA (cm)", "{:.2f}"),
    ("R80_minus_csda_mm", "ΔR80 (mm)", "{:+.2f}"), ("DFO_80_20_mm", "DFO80-20 (mm)", "{:.2f}"),
    ("peak_to_plateau", "Peak/plateau", "{:.2f}"), ("mean_rel_unc_percent", "σ_rel (%)", "{:.2f}"),
    ("gamma_pass_rate", "γ pass (%)", "{:.1f}"),
]


def metrics_table(rows: list[dict]) -> str:
    head = "| " + " | ".join(c[1] for c in COLUMNS) + " |"
    sep = "|" + "|".join("---:" for _ in COLUMNS) + "|"
    body = ["| " + " | ".join(fmt.format(r[k]) for k, _, fmt in COLUMNS) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def draft_discussion(state: ReportState) -> ReportState:
    flags = state.get("flags", [])
    fallback = (
        "All runs passed the QA tolerances (σ_rel ≤ 2 %, γ ≥ 95 %, |ΔR80| ≤ 2 mm)."
        if not flags else "The following QA flags were raised:\n\n" + "\n".join(f"- {f}" for f in flags)
    )
    slim = [{k: r[k] for k, _, _ in COLUMNS} for r in state["metrics"]]
    text = llm_text(
        "Write a short (<=200 words) discussion section for an internal medical-physics "
        "report on proton integrated depth-dose Monte Carlo runs. Interpret R80 vs CSDA "
        "range, the statistical uncertainty, and the gamma results vs the reference. "
        "Mention each QA flag and the recommended action. Use ONLY these numbers:\n"
        f"metrics={json.dumps(slim)}\nflags={json.dumps(flags)}\n"
        f"gamma criteria: {state['metrics'][0]['gamma_criteria']}",
        system="You are a careful medical physicist. Never invent numbers. No headings.",
        fallback=fallback,
    )
    return {"discussion": text}


def assemble(state: ReportState) -> ReportState:
    out_dir = Path(state["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    fig = Path(state["figure"]).name if state.get("figure") else None
    rows = state["metrics"]
    spec = state.get("spec") or {}
    energies = spec.get("energies_mev") or [r["energy_mev"] for r in rows]
    histories = spec.get("histories") or rows[0]["histories"]
    md = [
        f"# {state.get('title', 'Monte Carlo depth-dose report')}",
        "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M')} by medphys-agents · "
        f"backend `{state.get('backend', '?')}` · job `{state.get('job_id', '?')}`*",
        "",
        "## Setup",
        "",
        f"- Energies: {', '.join(f'{e:g}' for e in energies)} MeV",
        f"- Histories per energy: {histories:,}",
        "- Code: toy Bragg–Kleeman MC (`toy-bragg-kleeman-v1`) — tutorial workload, not clinical",
        f"- Gamma: {state['metrics'][0]['gamma_criteria']} vs high-statistics reference",
        "",
        "## Results",
        "",
        metrics_table(state["metrics"]),
        "",
    ]
    if fig:
        md += [f"![Depth-dose curves]({fig})", ""]
    md += ["## Discussion", "", state["discussion"], "",
           "## QA flags", ""]
    md += [f"- ⚠️ {f}" for f in state.get("flags", [])] or ["- none"]
    path = out_dir / "report.md"
    path.write_text("\n".join(md) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(state["metrics"], indent=2))
    return {"report_path": str(path)}


def build_graph():
    g = StateGraph(ReportState)
    g.add_node("draft_discussion", draft_discussion)
    g.add_node("assemble", assemble)
    g.add_edge(START, "draft_discussion")
    g.add_edge("draft_discussion", "assemble")
    g.add_edge("assemble", END)
    return g.compile()
