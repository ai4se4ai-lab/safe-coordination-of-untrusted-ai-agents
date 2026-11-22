#!/usr/bin/env bash
# One model on one GPU with a node-local Ollama server, running one study of this project.
# Required env (sbatch --export): VGC_ROOT MODEL STUDY ARGS OUT PARALLEL
#   STUDY=benchmark -> experiments/benchmark_study.py --model $MODEL $ARGS --out $OUT
#   STUDY=llm       -> experiments/llm_study.py       --models $MODEL $ARGS (results under $VGC_ROOT/results/raw)
# ARGS uses ';' instead of spaces (sbatch --export splits on commas).
#SBATCH --job-name=vgc-llm
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=%x-%j.out
set -euo pipefail
module load StdEnv/2023 python/3.12.4 2>/dev/null || true
echo "host=$(hostname) job=$SLURM_JOB_ID model=$MODEL study=$STUDY gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
mkdir -p "$OUT" "$VGC_ROOT/logs"
LOG="$VGC_ROOT/logs/ollama_${SLURM_JOB_ID}.log"

# Stage this project's Ollama runtime on node-local disk.
runtime_local="${SLURM_TMPDIR:-/tmp}/vgc-ollama"
mkdir -p "$runtime_local"
rsync -a --exclude=vulkan "$VGC_ROOT/ollama/runtime/" "$runtime_local/"
export OLLAMA_VULKAN=0 OLLAMA_LOAD_TIMEOUT=10m OLLAMA_NOPRUNE=1 OLLAMA_NO_CLOUD=1
export OLLAMA_HOST="127.0.0.1:$((20000 + SLURM_JOB_ID % 30000))"
export OLLAMA_NUM_PARALLEL="${PARALLEL:-4}" OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=60m
export OLLAMA_MODELS="$VGC_ROOT/ollama/models" OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_FLASH_ATTENTION=1
"$runtime_local/bin/ollama" serve > "$LOG" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
curl --fail --silent --retry 30 --retry-connrefused --retry-delay 2 --retry-max-time 90 "http://$OLLAMA_HOST/api/version"; echo

# Preload and require full GPU residency before any task prompt.
curl -s "http://$OLLAMA_HOST/api/generate" -d "{\"model\":\"$MODEL\",\"prompt\":\"\",\"keep_alive\":\"60m\",\"options\":{\"num_ctx\":8192}}" > /dev/null
python3 - "$OLLAMA_HOST" "$MODEL" <<'EOF'
import json, sys, urllib.request
ps = json.load(urllib.request.urlopen(f"http://{sys.argv[1]}/api/ps"))
m = [x for x in ps.get("models", []) if x["name"].startswith(sys.argv[2])]
assert m, f"model not loaded: {ps}"
size, vram = m[0]["size"], m[0].get("size_vram", 0)
print(f"residency size={size} vram={vram} ratio={vram/size:.3f} digest={m[0].get('digest','')[:16]}")
assert vram >= 0.98 * size, "model not fully GPU resident"
EOF

cd "$VGC_ROOT/repo"
args=${ARGS//;/ }
if [[ "$STUDY" == "benchmark" ]]; then
  python3 experiments/benchmark_study.py --model "$MODEL" --host "http://$OLLAMA_HOST" \
      --parallel "${PARALLEL:-4}" --out "$OUT" $args
else
  VGC_OLLAMA="http://$OLLAMA_HOST" python3 experiments/llm_study.py --models "$MODEL" $args
fi
nvidia-smi --query-gpu=name,utilization.gpu,memory.used --format=csv,noheader
echo "done $(date -u +%FT%TZ)"
