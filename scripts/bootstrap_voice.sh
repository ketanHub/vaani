#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

EXTRAS=(--extra voice-local)
if [[ "${VAANI_VOICE_GPU:-0}" == "1" ]]; then
  EXTRAS+=(--extra voice-gpu)
fi

uv sync --dev "${EXTRAS[@]}"

mkdir -p models/piper models/whisper

for voice in en_US-lessac-medium hi_IN-priyamvada-medium; do
  if [[ ! -f "models/piper/${voice}.onnx" ]]; then
    uv run --extra voice-local python -m piper.download_voices       --data-dir models/piper       "$voice"
  fi
done

uv run --extra voice-local python - <<'PY'
from faster_whisper import WhisperModel

WhisperModel(
    "small",
    device="cpu",
    compute_type="int8",
    download_root="models/whisper",
)
print("Local voice models are ready.")
PY
