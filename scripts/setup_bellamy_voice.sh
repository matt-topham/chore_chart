#!/usr/bin/env bash
set -euo pipefail

WHISPER_VERSION="${WHISPER_VERSION:-v1.9.1}"
WHISPER_DIR="${WHISPER_DIR:-$HOME/.local/share/whisper.cpp}"
MODEL_NAME="${MODEL_NAME:-tiny.en}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n==> Installing microphone, build, and speech packages\n'
sudo apt-get update
sudo apt-get install -y git cmake build-essential libsdl2-dev alsa-utils espeak-ng portaudio19-dev python3-dev

if [ -x "$PROJECT_DIR/.venv/bin/pip" ]; then
  printf '\n==> Installing Bellamy Python audio dependencies\n'
  "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
fi

mkdir -p "$(dirname "$WHISPER_DIR")"
if [ ! -d "$WHISPER_DIR/.git" ]; then
  printf '\n==> Cloning whisper.cpp %s\n' "$WHISPER_VERSION"
  git clone --depth 1 --branch "$WHISPER_VERSION" https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
else
  printf '\n==> Updating whisper.cpp checkout to %s\n' "$WHISPER_VERSION"
  git -C "$WHISPER_DIR" fetch --tags --force
  git -C "$WHISPER_DIR" checkout --force "$WHISPER_VERSION"
fi

printf '\n==> Building whisper.cpp with microphone support\n'
cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build" -DWHISPER_SDL2=ON -DCMAKE_BUILD_TYPE=Release
cmake --build "$WHISPER_DIR/build" -j "$(nproc)" --config Release

printf '\n==> Downloading %s model\n' "$MODEL_NAME"
if [ ! -f "$WHISPER_DIR/models/ggml-$MODEL_NAME.bin" ]; then
  (cd "$WHISPER_DIR" && sh ./models/download-ggml-model.sh "$MODEL_NAME")
fi

printf '\n==> Checking expected binaries\n'
test -x "$WHISPER_DIR/build/bin/whisper-cli"
test -x "$WHISPER_DIR/build/bin/whisper-stream"
test -f "$WHISPER_DIR/models/ggml-$MODEL_NAME.bin"

printf '\nBellamy voice dependencies are installed.\n'
printf 'Whisper directory: %s\n' "$WHISPER_DIR"
printf 'Model: %s/models/ggml-%s.bin\n' "$WHISPER_DIR" "$MODEL_NAME"
printf '\nMicrophone capture devices reported by ALSA:\n'
arecord -l || true
printf '\nSounddevice input devices:\n'
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  "$PROJECT_DIR/.venv/bin/python" - <<'PY' || true
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(i, d["name"], "inputs:", d["max_input_channels"])
PY
fi
printf '\nNext: set VOICE_CAPTURE_ID and VOICE_INPUT_DEVICE in .env, then test the service.\n'
