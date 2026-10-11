#!/bin/bash
#SBATCH --job-name=clarity_llmcmp
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=clarity/evaluation/results/slurm_llmcmp_%j.log

# Cross-LLM generator comparison (Reviewer 1, point 5).
# Holds the full retrieval/validation stack fixed; swaps only the generator
# across locally-pulled Ollama models. All models already in ~/.ollama/models.
set -x
cd "$SLURM_SUBMIT_DIR"

PY=$HOME/.conda/envs/clarity/bin/python
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=$HOME/.ollama/models

# --- Ollama server on the GPU node ---
$HOME/ollama_dist/bin/ollama serve &> clarity/evaluation/results/ollama_llmcmp_$SLURM_JOB_ID.log &
OLLAMA_PID=$!
for i in $(seq 1 30); do
  curl -s http://127.0.0.1:11434/api/tags > /dev/null && break
  sleep 2
done
$HOME/ollama_dist/bin/ollama list

# --- cross-LLM evaluation ---
$PY -m clarity.evaluation.llm_comparison_eval --runs 3 \
    --models llama3.1:8b mistral:7b qwen2.5:7b gemma2:9b \
    --out clarity/evaluation/results/llm_comparison_eval.json
STATUS=$?

kill $OLLAMA_PID 2>/dev/null
exit $STATUS
