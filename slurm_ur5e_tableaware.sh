#!/bin/bash
#SBATCH --job-name=clarity_ur5e_ta
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=clarity/evaluation/results/slurm_ur5e_ta_%j.log
set -x
cd "$SLURM_SUBMIT_DIR"
PY=$HOME/.conda/envs/clarity/bin/python
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
$PY scripts/ur5e_retrieval_tableaware.py \
    --out clarity/evaluation/results/ur5e_retrieval_base.json
$PY scripts/ur5e_retrieval_tableaware.py --table-aware \
    --out clarity/evaluation/results/ur5e_retrieval_tableaware.json
exit $?
