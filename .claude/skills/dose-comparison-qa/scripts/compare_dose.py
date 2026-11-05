#!/usr/bin/env python3
"""Gamma analysis + dose-difference summary for 1D/2D/3D dose arrays on the same grid.

Standalone (numpy only) so the skill can be copied to any project or HPC login node.

Example:
    python compare_dose.py --ref ref.npy --eval mc.npy --spacing 1 --dd 3 --dta 2 --cutoff 10
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np


def _shift(arr: np.ndarray, offset: tuple[int, ...]) -> np.ndarray:
    """Shift array by integer offsets, filling uncovered voxels with NaN (no wrap-around)."""
    out = np.full_like(arr, np.nan, dtype=float)
    src, dst = [], []
    for o, n in zip(offset, arr.shape):
        if o >= 0:
            src.append(slice(0, n - o))
            dst.append(slice(o, n))
        else:
            src.append(slice(-o, n))
            dst.append(slice(0, n + o))
    out[tuple(dst)] = arr[tuple(src)]
    return out


def gamma_index(
    ref: np.ndarray,
    evl: np.ndarray,
    spacing: float | tuple[float, ...],
    dd_percent: float = 3.0,
    dta_mm: float = 2.0,
    cutoff_percent: float = 10.0,
    local: bool = False,
    search_factor: float = 2.0,
) -> np.ndarray:
    """Gamma map on the reference grid (NaN below cutoff).

    For each reference point, searches evaluated-grid points within search_factor*DTA.
    Accuracy requires grid spacing <= DTA/3; upsample beforehand otherwise.
    """
    ref = np.asarray(ref, float)
    evl = np.asarray(evl, float)
    if ref.shape != evl.shape:
        raise ValueError(f"grid mismatch {ref.shape} vs {evl.shape}; resample first")
    sp = np.broadcast_to(np.asarray(spacing, float), (ref.ndim,))
    dmax = np.nanmax(ref)
    norm = (dd_percent / 100.0) * (np.where(ref > 0, ref, np.nan) if local else dmax)

    radius = [int(np.ceil(search_factor * dta_mm / s)) for s in sp]
    best = np.full(ref.shape, np.inf)
    for off in itertools.product(*[range(-r, r + 1) for r in radius]):
        dist2 = sum((o * s) ** 2 for o, s in zip(off, sp))
        if dist2 > (search_factor * dta_mm) ** 2:
            continue
        shifted = _shift(evl, off)
        g2 = dist2 / dta_mm**2 + ((shifted - ref) / norm) ** 2
        best = np.fmin(best, g2)
    gamma = np.sqrt(best)
    gamma[ref < cutoff_percent / 100.0 * dmax] = np.nan
    return gamma


def summarize_gamma(gamma: np.ndarray) -> dict:
    g = gamma[np.isfinite(gamma)]
    if g.size == 0:
        return {"n_points": 0, "pass_rate": float("nan")}
    return {
        "n_points": int(g.size),
        "pass_rate": float(100.0 * np.mean(g <= 1.0)),
        "gamma_mean": float(g.mean()),
        "gamma_max": float(g.max()),
    }


def load(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    if path.suffix == ".npz":
        z = np.load(path)
        return z["dose"], (z["spacing"] if "spacing" in z else None)
    return np.load(path), None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--eval", type=Path, required=True)
    ap.add_argument("--spacing", type=float, nargs="+", help="mm per axis (or one value)")
    ap.add_argument("--dd", type=float, default=3.0, help="dose difference, %%")
    ap.add_argument("--dta", type=float, default=2.0, help="distance to agreement, mm")
    ap.add_argument("--cutoff", type=float, default=10.0, help="low-dose threshold, %% of max")
    ap.add_argument("--local", action="store_true", help="local instead of global normalization")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ref, sp_r = load(a.ref)
    evl, _ = load(a.eval)
    spacing = a.spacing if a.spacing else (sp_r if sp_r is not None else [1.0])
    gamma = gamma_index(ref, evl, tuple(spacing), a.dd, a.dta, a.cutoff, a.local)
    res = summarize_gamma(gamma)
    mask = ref >= a.cutoff / 100 * ref.max()
    res.update(
        criteria=f"{a.dd:g}%/{a.dta:g}mm {'local' if a.local else 'global'}, {a.cutoff:g}% threshold",
        fine_enough_grid=bool(min(spacing) <= a.dta / 3),
        mean_dose_diff_percent=float(100 * np.mean((evl - ref)[mask]) / ref.max()),
    )
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for k, v in res.items():
            print(f"{k:>24}: {v:.3f}" if isinstance(v, float) else f"{k:>24}: {v}")


if __name__ == "__main__":
    main()
