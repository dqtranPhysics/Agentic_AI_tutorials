---
name: dose-comparison-qa
description: Compare two dose distributions (MC vs TPS, measured vs calculated, new vs reference run) with gamma analysis, dose-difference maps, Monte Carlo statistical uncertainty, depth-dose metrics (R80/R90, distal falloff), and DVH points, and report results following AAPM TG-218 / TG-105 conventions. Use when the user asks for a gamma pass rate, "does this dose agree", an uncertainty estimate for an MC run, or a QA summary.
---

# Dose comparison QA

## How to run

```bash
uv run python .claude/skills/dose-comparison-qa/scripts/compare_dose.py \
    --ref reference.npy --eval evaluated.npy --spacing 1.0 [1.0 1.0] \
    --dd 3 --dta 2 --cutoff 10 [--local] [--json]
```

Inputs are `.npy` arrays, or `.npz` files with a `dose` key (and optional `spacing`).
Works for 1D (depth-dose), 2D (film / planar) and 3D (volumetric) arrays on the same grid.
For DICOM RTDOSE, first convert with `dicom-rt-inspector` + `pixel_array * DoseGridScaling`.

## What to always report (TG-218 style)

A gamma pass rate is **meaningless without its criteria**. Always state:

1. Dose-difference criterion (%) and whether **global** (normalized to max of reference)
   or **local** normalization
2. DTA criterion (mm)
3. Low-dose threshold (% of max) used to exclude points
4. Number of evaluated points and pass rate (%), mean and max γ
5. Whether the evaluated grid was finer than DTA/3 (otherwise γ is overestimated)

Default/TG-218 universal tolerance: **3%/2 mm, global, 10% threshold, pass rate ≥ 95%**
(action limit 90%). For SRS/SBRT the group uses 3%/1 mm.

## Monte Carlo uncertainty (TG-105)

- Use the **batch method**: split histories into n ≥ 10 independent batches,
  σ_mean = std(batch means, ddof=1)/√n.
- Report the relative uncertainty averaged over voxels with dose > 50 % D_max.
- Target ≤ 1–2 % for comparisons; if larger, the right fix is more histories
  (σ ∝ 1/√N), not looser gamma criteria.

## Depth-dose metrics (protons)

- **R80 / R90**: depth on the distal falloff where dose = 80 % / 90 % of the peak
  (linear interpolation on the distal side). R80 ≈ CSDA range in water.
- **Distal falloff (DFO 80–20)**: R20 − R80.
- **Peak-to-plateau**: D_peak / D(depth = 2 cm).

## Rules for Claude

- Never loosen criteria after seeing the result to make a plan pass; report what failed.
- If the grids differ, say so and resample (don't silently compare misaligned arrays).
- Put a plot (dose profiles + γ map) in any report for humans.
