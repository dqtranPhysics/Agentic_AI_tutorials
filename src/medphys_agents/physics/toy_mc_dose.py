#!/usr/bin/env python3
"""Toy Monte Carlo: integrated depth dose (IDD) of a proton pencil beam in water.

This is the "workload" the tutorial agents ship to the cluster. It is deliberately
simple (numpy only, seconds to run) but physically sensible:

* CSDA slowing down from the Bragg–Kleeman rule  R = a E^p  (a=0.0022 cm, p=1.77)
* range straggling via Gaussian fluctuation of the per-step energy loss
* initial energy spread
* primary loss to nuclear interactions (~1.2 %/cm); their energy is not scored locally

It is NOT a substitute for TOPAS/Geant4 — swap the RUN_COMMAND in the sbatch template to
run a real code. The output format (npz with depth, idd, idd_std, batches) is what the
analysis agent expects.

Usage:
    python toy_mc_dose.py --energy 150 --histories 20000 --seed 1 --out idd.npz
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

ALPHA_CM = 0.0022   # Bragg–Kleeman a (water), cm / MeV^p
P_EXP = 1.77        # Bragg–Kleeman p
NUCLEAR_PER_CM = 0.012
STRAGGLE_SIGMA = 0.2  # per-step relative fluctuation (gives ~1 % range straggling)


def csda_range_cm(energy_mev: float | np.ndarray) -> float | np.ndarray:
    return ALPHA_CM * np.power(energy_mev, P_EXP)


def stopping_power(energy_mev: np.ndarray) -> np.ndarray:
    """dE/dz in MeV/cm from differentiating the Bragg–Kleeman rule."""
    e = np.maximum(energy_mev, 1e-3)
    return 1.0 / (ALPHA_CM * P_EXP * np.power(e, P_EXP - 1.0))


def simulate(energy_mev: float, histories: int, seed: int, dz_cm: float = 0.05,
             energy_spread: float = 0.006, n_batches: int = 10) -> dict:
    rng = np.random.default_rng(seed)
    n_bins = int(np.ceil(1.2 * csda_range_cm(energy_mev) / dz_cm)) + 10
    depth = (np.arange(n_bins) + 0.5) * dz_cm

    e = energy_mev * (1.0 + energy_spread * rng.standard_normal(histories))
    batch = rng.integers(0, n_batches, histories)
    alive = np.ones(histories, bool)
    edep = np.zeros((n_batches, n_bins))

    for i in range(n_bins):
        idx = np.flatnonzero(alive)
        if idx.size == 0:
            break
        # nuclear removal of primaries
        lost = rng.random(idx.size) < NUCLEAR_PER_CM * dz_cm
        alive[idx[lost]] = False
        idx = idx[~lost]
        # continuous slowing down with straggling
        de = stopping_power(e[idx]) * dz_cm
        de *= np.clip(1.0 + STRAGGLE_SIGMA * rng.standard_normal(idx.size), 0.0, None)
        stop = de >= e[idx]
        de = np.where(stop, e[idx], de)
        e[idx] -= de
        alive[idx[stop]] = False
        edep[:, i] = np.bincount(batch[idx], weights=de, minlength=n_batches)

    counts = np.bincount(batch, minlength=n_batches).astype(float)
    per_batch = edep / counts[:, None] / dz_cm      # MeV / cm per primary
    idd = edep.sum(0) / histories / dz_cm
    idd_std = per_batch.std(0, ddof=1) / np.sqrt(n_batches)  # batch method (TG-105)
    return {"depth_cm": depth, "idd": idd, "idd_std": idd_std, "per_batch": per_batch}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--energy", type=float, required=True, help="MeV")
    ap.add_argument("--histories", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    t0 = time.time()
    res = simulate(a.energy, a.histories, a.seed)
    meta = {"energy_mev": a.energy, "histories": a.histories, "seed": a.seed,
            "runtime_s": round(time.time() - t0, 3), "model": "toy-bragg-kleeman-v1"}
    np.savez(a.out, **res, meta=json.dumps(meta))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
