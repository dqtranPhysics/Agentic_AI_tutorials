---
name: slurm-mc-dose-job
description: Write, check, and submit Monte Carlo dose-calculation jobs (TOPAS, Geant4, EGSnrc, or the toy pencil-beam workload in this repo) to a Slurm cluster as job arrays with unique seeds, sensible walltime, and provenance. Use when the user wants to run a simulation on HPC, split histories across nodes, sweep energies/field sizes, or asks for an sbatch script.
---

# Slurm Monte Carlo dose job

MC dose calculations are embarrassingly parallel: split the histories (or the parameter
sweep) into a **Slurm job array**, give each task a **unique random seed**, and merge the
results afterwards. This skill encodes the conventions our group uses.

## Workflow

1. **Collect the spec** (ask only for what is missing):
   - code: `toy` | `topas` | `geant4` | `egsnrc`
   - what varies across array tasks: seeds only, or a sweep (energies, field sizes …)
   - histories per task, account/allocation, partition, walltime
2. **Pilot run first.** Run 1 task with ~1% of the histories (or `--qos=debug`). Use the
   measured time to set `--time` = pilot time × (N / N_pilot) × 1.5 safety factor.
3. **Render the script** from `templates/mc_array.sbatch` (fill every `{{…}}`). For TOPAS
   also render `templates/topas_beam.txt`.
4. **Run the pre-submit checklist** below, show the script to the user, and get an explicit
   OK before `sbatch` — submissions spend allocation hours.
5. Submit with `sbatch --parsable script.sbatch` and record the job ID in `runs/<job_id>/`.
6. Monitor with `squeue -j <id> -h -o "%i %T %M"`; after completion check
   `sacct -j <id> -X -o JobID,State,Elapsed,MaxRSS,ExitCode`.
7. Merge: sum dose tallies; combine variances (batch method — see `dose-comparison-qa`).

## Pre-submit checklist

- [ ] **No PHI on the cluster** — CT/RT inputs de-identified (use `dicom-rt-inspector`).
- [ ] Seeds are unique per task: `SEED = BASE_SEED + SLURM_ARRAY_TASK_ID`.
- [ ] Outputs go to `$SCRATCH`/project space, *not* `$HOME`; file names contain the array index.
- [ ] `--time` comes from a pilot run, not a guess.
- [ ] `--array` uses a throttle (`%20`) on large sweeps to be a good citizen.
- [ ] Provenance written: code version, input file hash, seed, host, start/end time.
- [ ] Modules/containers pinned (e.g. `module load topas/3.9` not `topas`).

## Code-specific notes

| Code | Seed parameter | Histories parameter |
|---|---|---|
| toy (this repo) | `--seed` | `--histories` |
| TOPAS | `i:Ts/Seed` | `i:So/<source>/NumberOfHistoriesInRun` |
| Geant4 macro | `/random/setSeeds a b` | `/run/beamOn N` |
| EGSnrc | `rng seeds` in input | `ncase` |

## Templates

- `templates/mc_array.sbatch` — generic array job with provenance block
- `templates/topas_beam.txt` — minimal TOPAS proton pencil beam in water phantom

The LangGraph job agent in `src/medphys_agents/agents/job_agent.py` implements this same
workflow programmatically (render → human approval → submit → monitor → collect).
