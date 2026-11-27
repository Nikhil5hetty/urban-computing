#!/usr/bin/env bash
#SBATCH --job-name=uc040-apertus
#SBATCH --account=gratis
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --array=0-11%2
#SBATCH --output=slurm-uc040-%A_%a.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
# Use uv from PATH and the prebuilt CUDA-enabled PyTorch from the llm extra.
# Prebuilt PyTorch provides its CUDA libraries, so no CUDA or cuDNN module is needed.
# Stage the model in HF_HOME before submitting, as described in docs/llm.md.
export HF_HUB_OFFLINE=1
export CUBLAS_WORKSPACE_CONFIG=:4096:8
exec uv run --locked --offline --extra llm python scripts/run_llm.py \
    --array-index "${SLURM_ARRAY_TASK_ID:?This job must run as an array}"
