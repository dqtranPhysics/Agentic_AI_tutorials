"""Agent 6 (optional, needs an LLM) — a tool-calling "research assistant".

Agents 1–5 are *workflows*: you drew the graph, the code decides the path.
This one is an *agent*: the model decides which tool to call next (a ReAct loop built with
`langchain.agents.create_agent`, which compiles to a LangGraph graph under the hood).

Guardrails worth copying into anything that touches a real cluster:
* `cluster_command` only runs an allowlist of read-only commands, no shell metacharacters.
* `submit_idd_job` spends allocation, so it is wrapped by HumanInTheLoopMiddleware:
  the graph pauses and a human must approve every call.
"""

from __future__ import annotations

import json
import re

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from ..hpc import get_backend
from ..llm import get_llm
from . import analysis_agent, job_agent, report_agent

READ_ONLY = {"sinfo", "squeue", "sacct", "sshare", "scontrol", "df", "du", "ls", "cat", "head",
             "tail", "hostname", "whoami", "quota", "module", "balance"}
FORBIDDEN = re.compile(r"[;&|><`$\\]|\bscontrol\s+(update|delete|create)")


@tool
def cluster_command(command: str) -> str:
    """Run a READ-ONLY command on the HPC login node (sinfo, squeue, sacct, ls, cat, df ...)."""
    first = command.strip().split()[0] if command.strip() else ""
    if first not in READ_ONLY or FORBIDDEN.search(command):
        return f"REFUSED: only read-only commands without shell operators are allowed: {sorted(READ_ONLY)}"
    r = get_backend().run(command)
    return (r.stdout or r.stderr)[-4000:]


@tool
def submit_idd_job(energies_mev: list[float], histories: int) -> str:
    """Submit a proton integrated-depth-dose Monte Carlo array job (one task per energy),
    wait for it to finish, and return the output files. Requires human approval."""
    graph = job_agent.build_graph()
    cfg = {"configurable": {"thread_id": "tool-agent-job"}}
    spec = job_agent.JobSpec(energies_mev=energies_mev, histories=histories).model_dump()
    out = graph.invoke({"request": "(from tool agent)", "spec": spec,
                        "auto_approve": True}, cfg)  # approval already happened in middleware
    return json.dumps({k: out.get(k) for k in ("job_id", "local_dir", "outputs", "error", "spec")})


@tool
def analyze_and_report(outputs: list[str], spec: dict | None = None, job_id: str = "") -> str:
    """Analyze idd.npz output files (R80, uncertainty, gamma vs reference), make a plot, and
    write a Markdown report. Returns metrics, QA flags, and the report path."""
    a = analysis_agent.build_graph().invoke({"outputs": outputs})
    r = report_agent.build_graph().invoke({**a, "spec": spec or {}, "job_id": job_id,
                                           "backend": get_backend().name})
    slim = [{k: round(v, 3) if isinstance(v, float) else v for k, v in m.items() if k != "file"}
            for m in a["metrics"]]
    return json.dumps({"metrics": slim, "flags": a["flags"], "report": r["report_path"]})


SYSTEM = """You are a research assistant for a medical physics group.
You can inspect the HPC cluster, run proton depth-dose Monte Carlo jobs, and analyze them.
Before submitting, check the cluster state. Never invent numbers; quote tool outputs.
When done, summarize results and give the report path."""


def build_agent():
    llm = get_llm()
    if llm is None:
        raise RuntimeError("The tool-calling agent needs an LLM: set ANTHROPIC_API_KEY "
                           "(or MEDPHYS_MODEL to another provider). Agents 1–5 work offline.")
    return create_agent(
        llm,
        tools=[cluster_command, submit_idd_job, analyze_and_report],
        system_prompt=SYSTEM,
        middleware=[HumanInTheLoopMiddleware(interrupt_on={"submit_idd_job": True})],
        checkpointer=InMemorySaver(),
    )
