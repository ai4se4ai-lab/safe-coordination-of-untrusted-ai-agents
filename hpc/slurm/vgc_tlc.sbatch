#!/usr/bin/env bash
# One TLC instance of the SoSyM scaling campaign on a CPU node.
# Required env (sbatch --export): VGC_ROOT ONLY WORKERS HEAP
#SBATCH --job-name=vgc-tlc
#SBATCH --output=%x-%j.out
set -euo pipefail
module load StdEnv/2023 python/3.12.4 java/17.0.6 2>/dev/null || true
echo "host=$(hostname) job=$SLURM_JOB_ID only=$ONLY cpus=$SLURM_CPUS_PER_TASK $(java -version 2>&1 | head -1)"
cd "$VGC_ROOT/repo"
python3 scripts/run_models_sosym.py --only "$ONLY" --workers "$WORKERS" --heap "$HEAP" --timeout 85000 \
    --out "results/processed/sosym/tlc-scaling-$ONLY.json"
echo "done $(date -u +%FT%TZ)"
