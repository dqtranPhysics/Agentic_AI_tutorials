"""Agent 1 — connect to the HPC system and take stock.

Graph:

    START -> check_connection --ok--> probe_cluster -> summarize -> END
                              \\--fail--> diagnose -> END

Teaches: typed state, nodes as plain functions, conditional edges.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..hpc import get_backend
from ..llm import llm_text


class ConnectState(TypedDict, total=False):
    backend: str
    connected: bool
    error: str
    facts: dict[str, str]   # command -> output
    summary: str


PROBES = {
    "identity": "hostname && whoami",
    "partitions": "sinfo -s",
    "my_jobs": "squeue -u $USER",
    "allocation": "sshare -U -l 2>/dev/null || balance 2>/dev/null || echo 'n/a'",
    "disk": "df -h $HOME | tail -1",
}


def check_connection(state: ConnectState) -> ConnectState:
    hpc = get_backend()
    try:
        r = hpc.run("hostname", timeout=60)
    except Exception as exc:  # e.g. ssh timeout
        return {"backend": hpc.name, "connected": False, "error": repr(exc)}
    if not r.ok:
        return {"backend": hpc.name, "connected": False, "error": r.stderr.strip()}
    return {"backend": hpc.name, "connected": True}


def route_after_check(state: ConnectState) -> str:
    return "probe_cluster" if state["connected"] else "diagnose"


def probe_cluster(state: ConnectState) -> ConnectState:
    hpc = get_backend()
    facts = {}
    for key, cmd in PROBES.items():
        r = hpc.run(cmd)
        facts[key] = (r.stdout or r.stderr).strip()
    return {"facts": facts}


def summarize(state: ConnectState) -> ConnectState:
    facts = state["facts"]
    fallback = "\n".join(f"### {k}\n```\n{v}\n```" for k, v in facts.items())
    summary = llm_text(
        "Summarize this HPC cluster status for a medical physicist in <=6 bullet points: "
        "which partitions look free, how many of my jobs are queued, allocation balance, "
        f"disk usage. Raw command outputs:\n{facts}",
        system="You are a concise HPC assistant. Do not invent numbers not in the data.",
        fallback=fallback,
    )
    return {"summary": summary}


def diagnose(state: ConnectState) -> ConnectState:
    err = state.get("error", "")
    tips = (
        f"Could not connect via backend '{state.get('backend')}'. Error: {err}\n\n"
        "Checklist:\n"
        "1. Does `ssh $HPC_HOST hostname` work in your terminal? (It must, without prompts,\n"
        "   or open a master connection first: `ssh -fNM $HPC_HOST`.)\n"
        "2. Is HPC_HOST an alias in ~/.ssh/config (HostName, User, IdentityFile)?\n"
        "3. On VPN if the cluster requires it?\n"
        "4. 2FA/Duo: approve the prompt in the terminal session that opened the master socket."
    )
    return {"summary": llm_text(f"Explain this SSH error and suggest fixes briefly:\n{err}",
                                fallback=tips) if err else tips}


def build_graph():
    g = StateGraph(ConnectState)
    g.add_node("check_connection", check_connection)
    g.add_node("probe_cluster", probe_cluster)
    g.add_node("summarize", summarize)
    g.add_node("diagnose", diagnose)
    g.add_edge(START, "check_connection")
    g.add_conditional_edges("check_connection", route_after_check, ["probe_cluster", "diagnose"])
    g.add_edge("probe_cluster", "summarize")
    g.add_edge("summarize", END)
    g.add_edge("diagnose", END)
    return g.compile()


if __name__ == "__main__":
    print(build_graph().invoke({})["summary"])
