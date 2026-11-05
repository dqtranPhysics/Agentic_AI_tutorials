"""Command line entry point: `uv run medphys-agents <command>`.

    connect                      Agent 1: check the cluster
    submit  "<request>" [--yes]  Agent 2: plan, approve, submit, monitor, collect
    analyze <run_dir>            Agents 3+4: analyze idd.npz files in run_dir and write a report
    pipeline "<request>" [--yes] Agent 5: everything end to end
    chat                         Agent 6: tool-calling assistant (needs an LLM)
    graph <name>                 Print a Mermaid diagram of an agent's graph
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from langgraph.types import Command

from .hpc import get_backend


def _run_with_approval(graph, inputs: dict, auto_yes: bool) -> dict:
    """Invoke a graph; whenever it pauses on interrupt(), show the payload and ask."""
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke(inputs, cfg)
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n" + "=" * 70)
        print("APPROVAL NEEDED —", payload.get("question"))
        print("Spec:", json.dumps(payload.get("spec"), indent=2))
        print("-" * 70 + "\n" + payload.get("script", "") + "\n" + "=" * 70)
        answer = "yes" if auto_yes else input("Submit? [yes/no] ")
        result = graph.invoke(Command(resume=answer), cfg)
    return result


def cmd_connect(_):
    from .agents import connect_agent

    print(connect_agent.build_graph().invoke({})["summary"])


def cmd_submit(a):
    from .agents import job_agent

    out = _run_with_approval(job_agent.build_graph(), {"request": a.request}, a.yes)
    if not out.get("approved"):
        print("Not submitted.")
        return
    print(f"\nJob {out['job_id']} finished. Outputs in {out['local_dir']}")
    if out.get("error"):
        print("WARNING:", out["error"])


def cmd_analyze(a):
    from .agents import analysis_agent, report_agent

    outputs = sorted(str(p) for p in Path(a.run_dir).glob("task_*/idd.npz"))
    if not outputs:
        raise SystemExit(f"no task_*/idd.npz under {a.run_dir}")
    res = analysis_agent.build_graph().invoke({"outputs": outputs, "out_dir": a.run_dir})
    job_id = Path(a.run_dir).name.removeprefix("job_")
    rep = report_agent.build_graph().invoke({**res, "backend": get_backend().name, "job_id": job_id})
    print("\n".join(res["flags"]) or "No QA flags.")
    print("Report:", rep["report_path"])


def cmd_pipeline(a):
    from .agents import pipeline

    out = _run_with_approval(pipeline.build_graph(), {"request": a.request}, a.yes)
    print("\n" + (out.get("summary") or ""))
    if out.get("report_path"):
        print("\nQA flags:", *(out.get("flags") or ["none"]), sep="\n  ")
        print("Report:", out["report_path"])
    elif not out.get("connected"):
        print("Stopped: could not connect.")
    else:
        print("Stopped before analysis (not approved or no outputs).")


def cmd_chat(_):
    from .agents import tool_agent

    agent = tool_agent.build_agent()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("Research assistant ready. Ctrl-D to quit.")
    while True:
        try:
            msg = input("\nyou> ")
        except EOFError:
            break
        result = agent.invoke({"messages": [{"role": "user", "content": msg}]}, cfg)
        while "__interrupt__" in result:
            req = result["__interrupt__"][0].value
            for action in req.get("action_requests", []):
                print(f"\n[approval] {action['name']}({json.dumps(action['args'])})")
            ok = input("approve? [yes/no] ").strip().lower().startswith("y")
            decision = {"type": "approve"} if ok else {"type": "reject", "message": "User declined."}
            n = len(req.get("action_requests", [])) or 1
            result = agent.invoke(Command(resume={"decisions": [decision] * n}), cfg)
        print("\nassistant>", result["messages"][-1].text)


def cmd_graph(a):
    from .agents import analysis_agent, connect_agent, job_agent, pipeline, report_agent

    builders = {"connect": connect_agent.build_graph, "job": job_agent.build_graph,
                "analysis": analysis_agent.build_graph, "report": report_agent.build_graph,
                "pipeline": pipeline.build_graph}
    print(builders[a.name]().get_graph(xray=a.name == "pipeline").draw_mermaid())


def main() -> None:
    ap = argparse.ArgumentParser(prog="medphys-agents", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("connect").set_defaults(fn=cmd_connect)
    p = sub.add_parser("submit"); p.add_argument("request"); p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_submit)
    p = sub.add_parser("analyze"); p.add_argument("run_dir"); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("pipeline"); p.add_argument("request"); p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_pipeline)
    sub.add_parser("chat").set_defaults(fn=cmd_chat)
    p = sub.add_parser("graph")
    p.add_argument("name", choices=["connect", "job", "analysis", "report", "pipeline"])
    p.set_defaults(fn=cmd_graph)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
