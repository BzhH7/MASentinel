#!/usr/bin/env bash
set -e

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}

MODEL_PATH=${MODEL_PATH:-Qwen/Qwen2.5-Coder-7B-Instruct}
SERVED_NAME=${SERVED_NAME:-qwen2.5-coder:7b}
PORT=${PORT:-8001}

vllm serve "$MODEL_PATH" \
  --served-model-name "$SERVED_NAME" \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.75 \
  --enable-prefix-caching \
  --host 0.0.0.0 \
  --port "$PORT"
