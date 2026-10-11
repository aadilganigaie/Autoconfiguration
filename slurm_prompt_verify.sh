#!/bin/bash
#SBATCH --job-name=clarity_promptv
#SBATCH --partition=gpu_x450
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=clarity/evaluation/results/slurm_promptv_%j.log
set -x
cd "$SLURM_SUBMIT_DIR"
PY=$HOME/.conda/envs/clarity/bin/python
RESULTS=clarity/evaluation/results
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=$HOME/.ollama/models
$HOME/ollama_dist/bin/ollama serve &> $RESULTS/ollama_promptv_$SLURM_JOB_ID.log &
OLLAMA_PID=$!
for i in $(seq 1 30); do curl -s http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 2; done
$PY scripts/run_modbus_sim.py &> $RESULTS/modbus_promptv_$SLURM_JOB_ID.log &
MODBUS_PID=$!
$PY docker/opcua_server.py &> $RESULTS/opcua_promptv_$SLURM_JOB_ID.log &
OPCUA_PID=$!
$PY scripts/run_ur5e_mujoco_bridge.py &> $RESULTS/bridge_promptv_$SLURM_JOB_ID.log &
BRIDGE_PID=$!
sleep 8

# 1) benchmark generator (integrity: must not regress vs R0 0.867)
$PY -m clarity.evaluation.generator_eval --runs 3 \
    --out $RESULTS/generator_eval_promptfix.json
# 2) UR5e handed-in (must stay ~1.0)
$PY -m clarity.evaluation.ur5e_case_study --runs 3 --table-aware \
    --out $RESULTS/ur5e_handed_promptfix.json
# 3) UR5e high-level (improvement vs 0.0)
$PY -m clarity.evaluation.ur5e_case_study --runs 3 --table-aware --high-level \
    --out $RESULTS/ur5e_highlevel_promptfix.json
STATUS=$?
kill $MODBUS_PID $OPCUA_PID $BRIDGE_PID $OLLAMA_PID 2>/dev/null
exit $STATUS
