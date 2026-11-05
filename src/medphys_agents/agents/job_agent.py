"""Agent 2 — turn a request into a Slurm array job, get approval, submit, monitor, collect.

Graph:

    START -> plan -> render -> approve --yes--> submit -> monitor --done--> collect -> END
                                 \\--no--> END             ^    |
                                                           +----+  (poll loop)

Teaches: structured LLM output (with offline fallback), human-in-the-loop `interrupt()`,
checkpointing, and a polling loop expressed as a self-edge.

The sbatch script is rendered from the `slurm-mc-dose-job` skill's template, so the agent
and Claude Code follow the same group conventions.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from ..config import RUNS_DIR, SKILLS_DIR, get_settings
from ..hpc import all_done, get_backend
from ..llm import llm_structured

TEMPLATE = SKILLS_DIR / "slurm-mc-dose-job" / "templates" / "mc_array.sbatch"
TOY_SCRIPT = Path(__file__).resolve().parents[1] / "physics" / "toy_mc_dose.py"


class JobSpec(BaseModel):
    """What to run. One array task per energy."""

    energies_mev: list[float] = Field(description="proton beam energies in MeV, one task each")
    histories: int = Field(description="primary protons per task", ge=100, le=10_000_000)
    walltime: str = Field(default="00:30:00", description="HH:MM:SS")
    job_name: str = Field(default="toy_idd")
    base_seed: int = Field(default=1000)


class JobState(TypedDict, total=False):
    request: str
    auto_approve: bool
    spec: dict
    script: str
    remote_dir: str
    approved: bool
    job_id: str
    task_states: dict[int, str]
    polls: int
    local_dir: str
    outputs: list[str]
    error: str


# --------------------------------------------------------------------------- nodes
def _fallback_spec(request: str) -> JobSpec:
    """Regex parsing so the tutorial works without an LLM."""
    energies = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:,|and|MeV)", request)]
    energies = [e for e in energies if 30 <= e <= 250] or [100.0, 150.0]
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([kKmM]?)\s*(?:histories|protons|primaries)", request)
    hist = 20000
    if m:
        hist = int(float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))
    return JobSpec(energies_mev=sorted(set(energies)), histories=hist)


def plan(state: JobState) -> JobState:
    if state.get("spec"):  # caller already provided a spec (e.g. the tool agent)
        return {"spec": JobSpec(**state["spec"]).model_dump(), "polls": 0}
    spec = llm_structured(
        f"Extract a Monte Carlo job spec from this request:\n\n{state['request']}\n\n"
        "Defaults if unspecified: 20000 histories, walltime 00:30:00.",
        JobSpec,
        system="You configure proton Monte Carlo jobs. Energies must be 30-250 MeV.",
    ) or _fallback_spec(state["request"])
    return {"spec": spec.model_dump(), "polls": 0}


def render(state: JobState) -> JobState:
    s = get_settings()
    hpc = get_backend()
    spec = JobSpec(**state["spec"])
    tag = time.strftime("%Y%m%d_%H%M%S")
    remote_dir = f"{hpc.workdir}/{spec.job_name}_{tag}"
    modules = "\n".join(f"module load {m}" for m in s.hpc_modules.split()) or "# (no modules)"
    run_cmd = (f'{hpc.python} {remote_dir}/toy_mc_dose.py --energy "$PARAM" '
               f'--histories {spec.histories} --seed "$SEED" --out "$OUT/idd.npz"')
    fill = {
        "JOB_NAME": spec.job_name, "ACCOUNT": s.slurm_account, "PARTITION": s.slurm_partition,
        "WALLTIME": spec.walltime, "CPUS": "1", "MEM": "2G",
        "N_TASKS_MINUS_1": str(len(spec.energies_mev) - 1), "THROTTLE": "20",
        "OUTDIR": remote_dir, "MODULE_LINES": modules, "BASE_SEED": str(spec.base_seed),
        "SWEEP_VALUES": " ".join(f"{e:g}" for e in spec.energies_mev),
        "CODE_VERSION": "toy-bragg-kleeman-v1", "RUN_COMMAND": run_cmd,
    }
    script = TEMPLATE.read_text()
    for k, v in fill.items():
        script = script.replace("{{" + k + "}}", v)
    assert "{{" not in script, "unfilled template placeholder"
    return {"script": script, "remote_dir": remote_dir}


def approve(state: JobState) -> JobState:
    """Pause the graph and ask a human. Resume with Command(resume='yes'|'no')."""
    if state.get("auto_approve"):
        return {"approved": True}
    answer = interrupt({
        "question": "Submit this job? (yes/no)",
        "spec": state["spec"],
        "script": state["script"],
    })
    return {"approved": str(answer).strip().lower() in ("y", "yes")}


def route_after_approve(state: JobState) -> str:
    return "submit" if state["approved"] else END


def submit(state: JobState) -> JobState:
    hpc = get_backend()
    hpc.put(TOY_SCRIPT, f"{state['remote_dir']}/toy_mc_dose.py")
    job_id = hpc.submit(state["script"], state["remote_dir"])
    return {"job_id": job_id}


def monitor(state: JobState) -> JobState:
    s = get_settings()
    if state.get("polls", 0) > 0:
        time.sleep(s.poll_seconds)
    states = get_backend().status(state["job_id"])
    counts = {st: list(states.values()).count(st) for st in set(states.values())}
    print(f"[monitor] job {state['job_id']} poll {state.get('polls', 0)}: {counts}")
    return {"task_states": states, "polls": state.get("polls", 0) + 1}


def route_after_monitor(state: JobState) -> str:
    if all_done(state["task_states"]):
        return "collect"
    if state["polls"] >= get_settings().max_polls:
        return END
    return "monitor"


def collect(state: JobState) -> JobState:
    hpc = get_backend()
    local = RUNS_DIR / f"job_{state['job_id']}"
    hpc.get(state["remote_dir"], local)
    outputs = sorted(str(p) for p in local.glob("task_*/idd.npz"))
    failed = [t for t, st in state["task_states"].items() if st != "COMPLETED"]
    err = f"tasks failed: {failed} (see {local}/logs)" if failed else ""
    return {"local_dir": str(local), "outputs": outputs, "error": err}


def build_graph(checkpointer=None, standalone: bool = True):
    g = StateGraph(JobState)
    for name, fn in [("plan", plan), ("render", render), ("approve", approve),
                     ("submit", submit), ("monitor", monitor), ("collect", collect)]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "render")
    g.add_edge("render", "approve")
    g.add_conditional_edges("approve", route_after_approve, ["submit", END])
    g.add_edge("submit", "monitor")
    g.add_conditional_edges("monitor", route_after_monitor, ["monitor", "collect", END])
    g.add_edge("collect", END)
    # interrupt() needs a checkpointer to save the paused state. When used as a subgraph
    # (standalone=False) it inherits the parent graph's checkpointer instead.
    if not standalone:
        return g.compile()
    return g.compile(checkpointer=checkpointer or InMemorySaver())
