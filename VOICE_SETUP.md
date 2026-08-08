# Hey Bellamy voice assistant

The first voice-assistant version is local-first:

1. `whisper-stream` stays running and listens for **"Hey Bellamy"**.
2. After the wake phrase is detected, Bellamy says **"Yes?"**.
3. ALSA records one six-second command.
4. `whisper-cli` transcribes the command locally.
5. The Python intent handler calls the same dashboard APIs used by the touchscreen.
6. `espeak-ng` speaks a short confirmation.

No cloud speech API is required.

## Supported commands

Examples:

- `Hey Bellamy` ... `mark dishwasher done`
- `Hey Bellamy` ... `check off vacuum living room`
- `Hey Bellamy` ... `add milk to groceries`
- `Hey Bellamy` ... `add milk and bananas to the grocery list`
- `Hey Bellamy` ... `remind me to change the air filter on September first`
- `Hey Bellamy` ... `remind me tomorrow to take out the trash`
- `Hey Bellamy` ... `add a note maintenance is coming Tuesday`
- `Hey Bellamy` ... `what's on my calendar today`
- `Hey Bellamy` ... `what's on my calendar tomorrow`
- `Hey Bellamy` ... `what chores do I have today`
- `Hey Bellamy` ... `what's the weather`
- `Hey Bellamy` ... `what's on the grocery list`

The first version is intentionally deterministic. It does not send free-form commands to an LLM before changing household data.

## 1. Pull the code

```bash
cd ~/chore_chart
git pull
```

Use the actual project directory if yours is different.

## 2. Install Whisper and microphone dependencies

```bash
bash scripts/setup_bellamy_voice.sh
```

The setup script installs:

- `alsa-utils`
- `libsdl2-dev`
- `espeak-ng`
- build tools
- whisper.cpp v1.9.1
- the `tiny.en` Whisper model

By default whisper.cpp is installed at:

```text
~/.local/share/whisper.cpp
```

## 3. Identify the USB microphone

List ALSA capture devices:

```bash
arecord -l
```

For example, if the microphone is shown as card 2, device 0, test it with:

```bash
arecord -D plughw:2,0 -f S16_LE -r 16000 -c 1 -d 5 /tmp/mic-test.wav
aplay /tmp/mic-test.wav
```

If that recording sounds correct, set:

```ini
VOICE_ALSA_DEVICE=plughw:2,0
```

`whisper-stream` uses SDL capture-device numbering. Start it once manually to see the capture devices it detects:

```bash
~/.local/share/whisper.cpp/build/bin/whisper-stream \
  -m ~/.local/share/whisper.cpp/models/ggml-tiny.en.bin \
  -t 4 --step 2000 --length 5000 -ac 512
```

Its startup output lists capture devices as `#0`, `#1`, etc. Put the correct number in:

```ini
VOICE_CAPTURE_ID=0
```

Press `Ctrl+C` after identifying the microphone.

## 4. Add the voice settings to `.env`

The application now loads `.env` automatically. You no longer need to `source .env` before running `python app.py`.

Add or update:

```ini
VOICE_DASHBOARD_URL=http://127.0.0.1:5000
VOICE_WAKE_ALIASES="hey bellamy,hey belamy,hey bellamy"
VOICE_WHISPER_DIR="~/.local/share/whisper.cpp"
VOICE_WHISPER_MODEL="~/.local/share/whisper.cpp/models/ggml-tiny.en.bin"
VOICE_CAPTURE_ID=0
VOICE_ALSA_DEVICE=default
VOICE_THREADS=4
VOICE_AUDIO_CONTEXT=512
VOICE_WAKE_STEP_MS=2000
VOICE_WAKE_LENGTH_MS=5000
VOICE_COMMAND_SECONDS=6
VOICE_TTS_ENABLED=1
```

If the dashboard runs on port 8080, use:

```ini
VOICE_DASHBOARD_URL=http://127.0.0.1:8080
```

## 5. Test commands without the microphone

Start the dashboard first:

```bash
source .venv/bin/activate
python app.py
```

In another terminal:

```bash
cd ~/chore_chart
source .venv/bin/activate
python -m voice_assistant.service --text "what's the weather"
python -m voice_assistant.service --text "add test milk to groceries"
```

The second command really adds an item to the dashboard, so remove the test item afterward if desired.

## 6. Test the microphone assistant manually

With the dashboard running:

```bash
cd ~/chore_chart
source .venv/bin/activate
python -m voice_assistant.service
```

You should see:

```text
Bellamy voice assistant ready. Wake phrase: 'hey bellamy'
```

Say:

```text
Hey Bellamy
```

Bellamy should reply:

```text
Yes?
```

Then say a command such as:

```text
add milk to groceries
```

## 7. Install the systemd service

From the project directory:

```bash
PROJECT_DIR="$(pwd)"
PROJECT_USER="$(whoami)"

sed \
  -e "s|CHORE_USER|$PROJECT_USER|g" \
  -e "s|CHORE_PATH|$PROJECT_DIR|g" \
  systemd/home-voice.service | \
  sudo tee /etc/systemd/system/home-voice.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now home-voice.service
```

Check it with:

```bash
sudo systemctl status home-voice.service
```

Follow its live log with:

```bash
journalctl -u home-voice.service -f
```

## Tuning wake-word recognition

The first version recognizes "Hey Bellamy" through continuous Whisper transcription rather than a separately trained wake-word neural network. This means it is easy to deploy but will use more CPU than a purpose-built wake-word detector.

If it misses the phrase, first try:

```ini
VOICE_WAKE_STEP_MS=2500
VOICE_WAKE_LENGTH_MS=6000
VOICE_AUDIO_CONTEXT=768
```

If CPU use is too high, try:

```ini
VOICE_WAKE_STEP_MS=4000
VOICE_WAKE_LENGTH_MS=8000
VOICE_AUDIO_CONTEXT=512
```

Once this version is reliable, a later upgrade can replace wake detection with a dedicated custom "Hey Bellamy" model while leaving all command and dashboard code unchanged.
