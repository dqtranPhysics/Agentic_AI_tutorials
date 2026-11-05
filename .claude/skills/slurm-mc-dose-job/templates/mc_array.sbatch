#!/bin/bash
#SBATCH --job-name={{JOB_NAME}}
#SBATCH --account={{ACCOUNT}}
#SBATCH --partition={{PARTITION}}
#SBATCH --time={{WALLTIME}}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={{CPUS}}
#SBATCH --mem={{MEM}}
#SBATCH --array=0-{{N_TASKS_MINUS_1}}%{{THROTTLE}}
#SBATCH --output={{OUTDIR}}/logs/%x_%A_%a.out
#SBATCH --error={{OUTDIR}}/logs/%x_%A_%a.err

set -euo pipefail

# ---- environment (pin versions!) ------------------------------------------
{{MODULE_LINES}}

# ---- per-task parameters ---------------------------------------------------
TASK=${SLURM_ARRAY_TASK_ID}
SEED=$(( {{BASE_SEED}} + TASK ))
PARAMS=({{SWEEP_VALUES}})          # one entry per array task, e.g. (70 100 150)
PARAM=${PARAMS[$TASK]}
OUT={{OUTDIR}}/task_${TASK}
mkdir -p "$OUT"

# ---- provenance ------------------------------------------------------------
cat > "$OUT/provenance.json" <<EOF
{"job_id": "${SLURM_ARRAY_JOB_ID}", "task": ${TASK}, "seed": ${SEED},
 "param": "${PARAM}", "host": "$(hostname)", "start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "code_version": "{{CODE_VERSION}}"}
EOF

# ---- run -------------------------------------------------------------------
{{RUN_COMMAND}}

echo "{\"end\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$OUT/done.json"
