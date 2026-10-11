#!/bin/bash
#SBATCH --job-name=ur5e_case
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=clarity/evaluation/results/slurm_ur5e_%j.log

# CLARITY UR5e real-device case study on an H100 node.
# Prereqs (login node): ~/ollama_dist/bin/ollama extracted, llama3.1:8b
# pulled into ~/.ollama/models, HF models cached, clarity conda env built.
set -x
cd "$SLURM_SUBMIT_DIR"

PY=$HOME/.conda/envs/clarity/bin/python
RESULTS=clarity/evaluation/results
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=$HOME/.ollama/models

# --- Ollama server on the GPU node ---
$HOME/ollama_dist/bin/ollama serve &> $RESULTS/ollama_ur5e_$SLURM_JOB_ID.log &
OLLAMA_PID=$!
for i in $(seq 1 30); do
  curl -s http://127.0.0.1:11434/api/tags > /dev/null && break
  sleep 2
done
$HOME/ollama_dist/bin/ollama list

# --- MuJoCo UR5e Modbus TCP bridge on port 5021 ---
$PY scripts/run_ur5e_mujoco_bridge.py &> $RESULTS/ur5e_bridge_$SLURM_JOB_ID.log &
BRIDGE_PID=$!
for i in $(seq 1 60); do
  $PY -c "import socket; socket.create_connection(('127.0.0.1', 5021), timeout=1).close()" 2>/dev/null && break
  sleep 1
done

# --- case study ---
$PY -m clarity.evaluation.ur5e_case_study --runs 3 \
    --out $RESULTS/ur5e_case_study.json
STATUS=$?

kill $BRIDGE_PID $OLLAMA_PID 2>/dev/null
exit $STATUS
