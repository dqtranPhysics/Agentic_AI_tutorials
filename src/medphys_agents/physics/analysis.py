"""Depth-dose analysis used by the analysis agent.

Metrics follow the conventions documented in the `dose-comparison-qa` skill.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import RUNS_DIR
from .toy_mc_dose import csda_range_cm, simulate


def load_run(npz_path: str | Path) -> dict:
    z = np.load(npz_path, allow_pickle=False)
    return {
        "depth_cm": z["depth_cm"], "idd": z["idd"], "idd_std": z["idd_std"],
        "meta": json.loads(str(z["meta"])),
    }


def distal_depth(depth: np.ndarray, dose: np.ndarray, level: float) -> float:
    """Depth beyond the peak where dose falls to `level` x peak (linear interpolation)."""
    ip = int(np.argmax(dose))
    target = level * dose[ip]
    tail = dose[ip:]
    below = np.flatnonzero(tail < target)
    if below.size == 0:
        return float("nan")
    j = ip + below[0]
    d0, d1, z0, z1 = dose[j - 1], dose[j], depth[j - 1], depth[j]
    return float(z0 + (target - d0) * (z1 - z0) / (d1 - d0))


def depth_dose_metrics(run: dict) -> dict:
    z, d, s = run["depth_cm"], run["idd"], run["idd_std"]
    e = run["meta"]["energy_mev"]
    r80, r90, r20 = (distal_depth(z, d, lv) for lv in (0.8, 0.9, 0.2))
    plateau = float(np.interp(2.0, z, d))
    hi = d > 0.5 * d.max()
    csda = float(csda_range_cm(e))
    return {
        "energy_mev": e,
        "histories": run["meta"]["histories"],
        "peak_depth_cm": float(z[np.argmax(d)]),
        "R90_cm": r90,
        "R80_cm": r80,
        "DFO_80_20_mm": 10 * (r20 - r80),
        "peak_to_plateau": float(d.max() / plateau),
        "csda_range_cm": csda,
        "R80_minus_csda_mm": 10 * (r80 - csda),
        "mean_rel_unc_percent": float(100 * np.mean(s[hi] / d[hi])),
    }


@lru_cache(maxsize=32)
def reference_idd(energy_mev: float) -> tuple[np.ndarray, np.ndarray]:
    """'Commissioning' reference curve: high-statistics run with a slightly different
    energy spread, cached on disk. Plays the role of measured data in the tutorials."""
    cache = RUNS_DIR / "reference" / f"idd_{energy_mev:g}MeV.npz"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        r = simulate(energy_mev, histories=100_000, seed=424242, energy_spread=0.008)
        np.savez(cache, depth_cm=r["depth_cm"], idd=r["idd"])
    z = np.load(cache)
    return z["depth_cm"], z["idd"]


def gamma_1d(z_ref, d_ref, z_eval, d_eval, dd=0.03, dta_mm=2.0, cutoff=0.1) -> dict:
    """Global 1D gamma; the evaluated curve is upsampled to 0.1 mm so DTA is resolved."""
    zf = np.arange(z_eval[0], z_eval[-1], 0.01)  # cm
    df = np.interp(zf, z_eval, d_eval)
    dmax = d_ref.max()
    mask = d_ref >= cutoff * dmax
    g = []
    for z, d in zip(z_ref[mask], d_ref[mask]):
        g2 = ((zf - z) * 10 / dta_mm) ** 2 + ((df - d) / (dd * dmax)) ** 2
        g.append(np.sqrt(g2.min()))
    g = np.asarray(g)
    return {"gamma_pass_rate": float(100 * np.mean(g <= 1)), "gamma_mean": float(g.mean()),
            "gamma_max": float(g.max()), "gamma_criteria": f"{dd*100:g}%/{dta_mm:g}mm global, {cutoff*100:g}% threshold"}


def compare_to_reference(run: dict) -> dict:
    z_ref, d_ref = reference_idd(float(run["meta"]["energy_mev"]))
    # normalize both to their peak (relative IDD), as is usual for range QA
    return gamma_1d(z_ref, d_ref / d_ref.max(), run["depth_cm"], run["idd"] / run["idd"].max())


def plot_runs(runs: list[dict], out_png: str | Path) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=130)
    for r in sorted(runs, key=lambda r: r["meta"]["energy_mev"]):
        e = r["meta"]["energy_mev"]
        n = r["idd"].max()
        (line,) = ax.plot(r["depth_cm"], r["idd"] / n, lw=1.6, label=f"{e:g} MeV")
        ax.fill_between(r["depth_cm"], (r["idd"] - 2 * r["idd_std"]) / n,
                        (r["idd"] + 2 * r["idd_std"]) / n, color=line.get_color(), alpha=0.25, lw=0)
        z_ref, d_ref = reference_idd(float(e))
        ax.plot(z_ref, d_ref / d_ref.max(), ls=":", color=line.get_color(), lw=1)
    ax.set_xlabel("Depth in water (cm)")
    ax.set_ylabel("Relative integrated depth dose")
    ax.set_title("Toy MC proton IDDs (solid ±2σ) vs reference (dotted)")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
    return str(out_png)
