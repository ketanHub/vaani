#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export VAANI_LOCAL_VOICE_ENABLED=true
export VAANI_LOCAL_VOICE_WARMUP=true
export VAANI_WHISPER_MODEL="${VAANI_WHISPER_MODEL:-small}"
export VAANI_WHISPER_DEVICE=cuda
export VAANI_WHISPER_COMPUTE_TYPE="${VAANI_WHISPER_COMPUTE_TYPE:-float16}"
export VAANI_WHISPER_NUM_WORKERS="${VAANI_WHISPER_NUM_WORKERS:-3}"
export VAANI_WHISPER_DOWNLOAD_ROOT="${VAANI_WHISPER_DOWNLOAD_ROOT:-models/whisper}"
export VAANI_PIPER_ENGLISH_MODEL="${VAANI_PIPER_ENGLISH_MODEL:-models/piper/en_US-lessac-medium.onnx}"
export VAANI_PIPER_HINDI_MODEL="${VAANI_PIPER_HINDI_MODEL:-models/piper/hi_IN-priyamvada-medium.onnx}"
export VAANI_PIPER_USE_CUDA=false
export VAANI_PIPER_NUM_WORKERS="${VAANI_PIPER_NUM_WORKERS:-1}"

exec uv run --extra voice-local --extra voice-gpu uvicorn app.main:app   --host 127.0.0.1   --port "${VAANI_PORT:-8010}"
