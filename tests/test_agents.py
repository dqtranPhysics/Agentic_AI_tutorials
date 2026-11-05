"""Smoke tests: everything runs offline on the simulated cluster."""

import importlib.util
import os
from pathlib import Path

import numpy as np

os.environ["MEDPHYS_LLM"] = "off"
os.environ["POLL_SECONDS"] = "0.2"

from langgraph.types import Command  # noqa: E402

from medphys_agents.agents import analysis_agent, connect_agent, job_agent, pipeline  # noqa: E402
from medphys_agents.config import SKILLS_DIR  # noqa: E402
from medphys_agents.physics.toy_mc_dose import csda_range_cm, simulate  # noqa: E402


def test_toy_mc_range_close_to_csda():
    r = simulate(150, histories=3000, seed=0)
    z, d = r["depth_cm"], r["idd"]
    peak = z[np.argmax(d)]
    assert abs(peak - csda_range_cm(150)) < 0.6


def test_connect_agent_local():
    out = connect_agent.build_graph().invoke({})
    assert out["connected"] and "partitions" in out["facts"]


def test_job_agent_pauses_for_approval_and_declines():
    g = job_agent.build_graph()
    cfg = {"configurable": {"thread_id": "t-decline"}}
    out = g.invoke({"request": "100 MeV with 300 histories"}, cfg)
    assert "__interrupt__" in out
    out = g.invoke(Command(resume="no"), cfg)
    assert out["approved"] is False and "job_id" not in out


def test_pipeline_end_to_end(tmp_path):
    g = pipeline.build_graph()
    cfg = {"configurable": {"thread_id": "t-pipe"}}
    out = g.invoke({"request": "90 and 140 MeV with 2000 histories"}, cfg)
    out = g.invoke(Command(resume="yes"), cfg)
    assert len(out["outputs"]) == 2
    assert Path(out["report_path"]).exists()
    assert {m["energy_mev"] for m in out["metrics"]} == {90.0, 140.0}


def test_analysis_flags_low_statistics():
    g = job_agent.build_graph()
    out = g.invoke({"request": "x", "spec": {"energies_mev": [100], "histories": 200},
                    "auto_approve": True}, {"configurable": {"thread_id": "t-low"}})
    res = analysis_agent.build_graph().invoke({"outputs": out["outputs"]})
    assert any("statistical uncertainty" in f for f in res["flags"])


def _load_skill_script(rel):
    spec = importlib.util.spec_from_file_location("m", SKILLS_DIR / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gamma_skill_script_2d():
    m = _load_skill_script("dose-comparison-qa/scripts/compare_dose.py")
    y, x = np.mgrid[-30:31, -30:31].astype(float)  # 1 mm grid
    ref = np.exp(-(x**2 + y**2) / 200)
    shifted = np.exp(-((x - 1) ** 2 + y**2) / 200)  # 1 mm shift -> should pass 3%/2mm
    assert m.summarize_gamma(m.gamma_index(ref, shifted, 1.0))["pass_rate"] > 99
    far = np.exp(-((x - 5) ** 2 + y**2) / 200)      # 5 mm shift -> should fail
    assert m.summarize_gamma(m.gamma_index(ref, far, 1.0))["pass_rate"] < 80
