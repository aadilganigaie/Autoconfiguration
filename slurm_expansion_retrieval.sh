#!/bin/bash
#SBATCH --job-name=clarity_exp_ret
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=clarity/evaluation/results/slurm_expansion_retrieval_%j.log

# CLARITY R1 revision: retrieval evaluation over the FIVE REAL vendor manuals
# (corpus_expansion/). Needs only BGE-M3 + cross-encoder (offline HF cache);
# no Ollama / protocol simulators required for retrieval metrics.
set -x
cd "$SLURM_SUBMIT_DIR"

PY=$HOME/.conda/envs/clarity/bin/python
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

$PY -m clarity.evaluation.retrieval_eval_expansion \
    --out clarity/evaluation/results/retrieval_eval_expansion.json
exit $?
