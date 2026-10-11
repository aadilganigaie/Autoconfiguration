#!/bin/bash
#SBATCH --job-name=clarity_eval
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=clarity/evaluation/results/slurm_eval_%j.log

# CLARITY generator + end-to-end evaluation on an H100 node.
# Prereqs (login node): ~/ollama_dist/bin/ollama extracted, llama3.1:8b
# pulled into ~/.ollama/models, HF models cached, clarity conda env built.
set -x
cd "$SLURM_SUBMIT_DIR"

PY=$HOME/.conda/envs/clarity/bin/python
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=$HOME/.ollama/models

# --- Ollama server on the GPU node ---
$HOME/ollama_dist/bin/ollama serve &> clarity/evaluation/results/ollama_$SLURM_JOB_ID.log &
OLLAMA_PID=$!
for i in $(seq 1 30); do
  curl -s http://127.0.0.1:11434/api/tags > /dev/null && break
  sleep 2
done
$HOME/ollama_dist/bin/ollama list

# --- protocol simulators (optional; deployers fall back if absent) ---
$PY scripts/run_modbus_sim.py &> clarity/evaluation/results/modbus_sim_$SLURM_JOB_ID.log &
MODBUS_PID=$!
$PY docker/opcua_server.py &> clarity/evaluation/results/opcua_sim_$SLURM_JOB_ID.log &
OPCUA_PID=$!
sleep 5

# --- evaluation ---
$PY -m clarity.evaluation.generator_eval --runs 3 \
    --out clarity/evaluation/results/generator_eval.json
STATUS=$?

kill $MODBUS_PID $OPCUA_PID $OLLAMA_PID 2>/dev/null
exit $STATUS
