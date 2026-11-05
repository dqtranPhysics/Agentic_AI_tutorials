# 1 · Claude Code skills for medical physics

A **skill** is a folder with a `SKILL.md` (YAML front matter + instructions) and optional
scripts/templates. Claude reads only the `description` up front; when your request matches,
it loads the full instructions and uses the bundled scripts. Skills are how we turn
"the way our group does X" into something Claude does consistently.

```
.claude/skills/<name>/
  SKILL.md          name + description (when to use) + instructions
  scripts/          deterministic code Claude runs instead of improvising
  templates/        files to fill in
```

## The three skills in this repo

### `dicom-rt-inspector` — what's in this data, and is it safe to move?

Summarizes CT/RTPLAN/RTDOSE/RTSTRUCT (beams, MU, energies, dose grid, ROI names) and
lists populated PHI tags **without printing their values**.

Try in Claude Code:

> *What's in `~/data/phantom_plan/`? Is it OK to copy to the cluster?*

Or run the script yourself:

```bash
uv run python .claude/skills/dicom-rt-inspector/scripts/inspect_dicom.py ~/data/phantom_plan --phi-only
```

Why a skill: everyone needs this, the PHI rule must be applied *every time*, and DICOM
details (`DoseGridScaling`, `DoseSummationType`) are easy to get wrong.

### `slurm-mc-dose-job` — run Monte Carlo the group's way

Encodes conventions for TOPAS/Geant4/EGSnrc/toy jobs: job arrays, unique seeds
(`BASE_SEED + SLURM_ARRAY_TASK_ID`), pilot run → walltime, provenance file, pre-submit
checklist, and *asking before `sbatch`*. Includes `templates/mc_array.sbatch` and a
TOPAS pencil-beam template.

> *Write me a Slurm job to run TOPAS for 100, 150, 200 MeV with 1e7 histories each.*

The LangGraph job agent (tutorial 4) renders the **same template**, so humans, Claude Code
and our agents all produce identical scripts.

### `dose-comparison-qa` — gamma and uncertainty, reported properly

Gamma (global/local, threshold, search radius) for 1D/2D/3D arrays, batch-method MC
uncertainty, R80/R90/DFO, and a TG-218 reporting checklist — including "never loosen the
criteria after seeing the result".

```bash
uv run python .claude/skills/dose-comparison-qa/scripts/compare_dose.py --ref a.npy --eval b.npy --spacing 1 --dd 3 --dta 2
```

> *Compare `film.npy` to `tps_plane.npy` (1 mm grid) at 3%/2mm and summarize.*

## Write your own (10 minutes)

Good candidates are tasks that are **repeated, error-prone, and have a right way**:
e.g. "TG-51 output calculation", "convert TOPAS CSV to npz", "our figure style".

1. `mkdir -p .claude/skills/my-skill/scripts`
2. Write `SKILL.md`:

   ```markdown
   ---
   name: my-skill
   description: <What it does>. Use when <the phrases/situations that should trigger it>.
   ---
   # Title
   ## How to run  (exact commands)
   ## Rules for Claude  (the non-obvious must/never items)
   ```

3. Put the deterministic part in a script; keep `SKILL.md` about *when* and *how to judge*.
4. Test: start a new Claude Code session and ask for the task in your own words. If the
   skill doesn't trigger, make the `description` more specific about *when to use it*.

Tips: keep `SKILL.md` short (it's loaded into context); write rules as reasons, not
shouting; commit skills to the repo so the whole group gets them.
