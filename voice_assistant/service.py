from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from chore_app.env import load_env_file
from .client import DashboardClient
from .intents import IntentHandler, normalize
from .status import write_voice_status


BASE_DIR = Path(__file__).resolve().parents[1]
load_env_file(BASE_DIR / ".env")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class BellamyVoiceService:
    def __init__(self):
        default_dashboard = f"http://127.0.0.1:{os.environ.get('CHORE_PORT', '5000')}"
        self.dashboard_url = os.environ.get("VOICE_DASHBOARD_URL", "").strip() or default_dashboard
        self.timezone = os.environ.get("CHORE_TIMEZONE", "America/Los_Angeles")
        self.model = Path(os.environ.get("VOICE_WHISPER_MODEL", str(Path.home() / ".local/share/whisper.cpp/models/ggml-tiny.en.bin"))).expanduser()
        whisper_root = Path(os.environ.get("VOICE_WHISPER_DIR", str(Path.home() / ".local/share/whisper.cpp"))).expanduser()
        self.whisper_stream = Path(os.environ.get("VOICE_WHISPER_STREAM", str(whisper_root / "build/bin/whisper-stream"))).expanduser()
        self.whisper_cli = Path(os.environ.get("VOICE_WHISPER_CLI", str(whisper_root / "build/bin/whisper-cli"))).expanduser()
        self.capture_id = int(os.environ.get("VOICE_CAPTURE_ID", "0"))
        configured_input = os.environ.get("VOICE_INPUT_DEVICE", "").strip()
        legacy_input = os.environ.get("VOICE_ALSA_DEVICE", "").strip()
        self.input_device_setting = configured_input or (legacy_input if legacy_input.lower() not in {"", "default"} else "")
        self.input_device = self._resolve_input_device(self.input_device_setting)
        self.threads = int(os.environ.get("VOICE_THREADS", "4"))
        self.audio_ctx = int(os.environ.get("VOICE_AUDIO_CONTEXT", "512"))
        self.command_seconds = int(os.environ.get("VOICE_COMMAND_SECONDS", "6"))
        self.wake_step_ms = int(os.environ.get("VOICE_WAKE_STEP_MS", "2000"))
        self.wake_length_ms = int(os.environ.get("VOICE_WAKE_LENGTH_MS", "5000"))
        self.tts_enabled = os.environ.get("VOICE_TTS_ENABLED", "1").lower() not in {"0", "false", "no"}
        aliases = os.environ.get("VOICE_WAKE_ALIASES", "hey bellamy,hey belamy,hey bellamy")
        self.wake_aliases = [normalize(value) for value in aliases.split(",") if normalize(value)]
        self.client = DashboardClient(self.dashboard_url)
        self.intents = IntentHandler(self.client, self.timezone)
        self.running = True
        self._wake_process: subprocess.Popen | None = None

    @staticmethod
    def _resolve_input_device(setting: str):
        if not setting:
            return None
        if setting.isdigit():
            index = int(setting)
            info = sd.query_devices(index)
            if info.get("max_input_channels", 0) <= 0:
                raise RuntimeError(f"Audio device {index} has no input channels")
            return index

        needle = setting.casefold()
        matches = []
        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0 and needle in info.get("name", "").casefold():
                matches.append((index, info.get("name", "")))
        if not matches:
            available = [info.get("name", "") for info in sd.query_devices() if info.get("max_input_channels", 0) > 0]
            raise RuntimeError(f"Input device {setting!r} not found. Available inputs: {', '.join(available)}")
        return matches[0][0]

    def _input_device_info(self) -> dict:
        try:
            return dict(sd.query_devices(self.input_device, "input"))
        except Exception as exc:
            target = self.input_device_setting or "default input"
            raise RuntimeError(f"Could not open {target}: {exc}") from exc

    def set_status(self, state: str, text: str = "") -> None:
        write_voice_status(BASE_DIR, state, text)

    def validate(self) -> None:
        missing = []
        if not self.whisper_stream.is_file(): missing.append(str(self.whisper_stream))
        if not self.whisper_cli.is_file(): missing.append(str(self.whisper_cli))
        if not self.model.is_file(): missing.append(str(self.model))
        if missing:
            raise RuntimeError("Missing voice dependencies: " + ", ".join(missing))
        info = self._input_device_info()
        print(f"Command microphone: {info.get('name', 'unknown')} ({info.get('max_input_channels', 0)} input channels, {info.get('default_samplerate', '?')} Hz default)")

    def stop(self, *_args) -> None:
        self.running = False
        self.set_status("offline", "Bellamy stopped")
        if self._wake_process and self._wake_process.poll() is None:
            self._wake_process.terminate()

    def run(self) -> None:
        self.validate()
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        print(f"Bellamy voice assistant ready. Wake phrase: {self.wake_aliases[0]!r}")
        print(f"Dashboard: {self.dashboard_url}")
        self.set_status("idle", "Say Hey Bellamy")
        while self.running:
            try:
                self._wait_for_wake()
                if not self.running:
                    break
                print("Wake phrase detected")
                self.set_status("listening", "Listening for your command")
                self.speak("Yes?")
                command = self._listen_for_command()
                if not command:
                    self.set_status("error", "I didn't catch that")
                    self.speak("I didn't catch that.")
                    time.sleep(1)
                    self.set_status("idle", "Say Hey Bellamy")
                    continue
                print(f"Command: {command}")
                self.set_status("processing", command)
                result = self.intents.handle(command)
                print(f"Action: {result.action}; success={result.success}; response={result.spoken}")
                self.set_status("done" if result.success else "error", result.spoken)
                self.speak(result.spoken)
                time.sleep(1.25)
                self.set_status("idle", "Say Hey Bellamy")
            except RuntimeError as exc:
                print(f"Voice service error: {exc}")
                self.set_status("error", str(exc))
                self.speak("I ran into a problem.")
                time.sleep(3)
                if self.running:
                    self.set_status("idle", "Say Hey Bellamy")

    def _wait_for_wake(self) -> None:
        command = [
            str(self.whisper_stream),
            "-m", str(self.model),
            "-t", str(self.threads),
            "--step", str(self.wake_step_ms),
            "--length", str(self.wake_length_ms),
            "--keep", "200",
            "-c", str(self.capture_id),
            "-ac", str(self.audio_ctx),
            "-mt", "24",
            "-l", "en",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0)
        self._wake_process = process
        buffer = ""
        try:
            assert process.stdout is not None
            while self.running:
                char = process.stdout.read(1)
                if char == "" and process.poll() is not None:
                    raise RuntimeError(f"whisper-stream exited with code {process.returncode}")
                if char in {"\r", "\n"}:
                    if self._contains_wake_phrase(buffer):
                        return
                    buffer = ""
                elif char:
                    buffer += char
                    if len(buffer) > 1200:
                        buffer = buffer[-600:]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            self._wake_process = None

    def _contains_wake_phrase(self, line: str) -> bool:
        cleaned = normalize(ANSI_RE.sub("", line))
        return any(alias in cleaned for alias in self.wake_aliases)

    def _listen_for_command(self) -> str:
        with tempfile.TemporaryDirectory(prefix="bellamy-") as directory:
            wav_path = Path(directory) / "command.wav"
            info = self._input_device_info()
            channels = 2 if int(info.get("max_input_channels", 1)) >= 2 else 1
            rate = 16000
            try:
                recording = sd.rec(
                    int(self.command_seconds * rate),
                    samplerate=rate,
                    channels=channels,
                    dtype="int16",
                    device=self.input_device,
                )
                sd.wait()
            except Exception as exc:
                raise RuntimeError(f"Microphone recording failed: {exc}") from exc

            if channels > 1:
                mono = recording.astype(np.int32).mean(axis=1).astype(np.int16)
            else:
                mono = recording[:, 0].astype(np.int16)

            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(rate)
                wav_file.writeframes(mono.tobytes())

            return self._transcribe(wav_path)

    def _transcribe(self, wav_path: Path) -> str:
        command = [
            str(self.whisper_cli),
            "-m", str(self.model),
            "-f", str(wav_path),
            "-t", str(self.threads),
            "-l", "en",
            "-nt", "-np",
            "--prompt", "Home assistant command. Chores, groceries, reminders, calendar, weather, household notes.",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if completed.returncode != 0:
            raise RuntimeError("Whisper transcription failed")
        lines = [ANSI_RE.sub("", line).strip() for line in completed.stdout.splitlines() if line.strip()]
        return " ".join(lines).strip()

    def speak(self, text: str) -> None:
        if not self.tts_enabled or not text:
            return
        if shutil.which("espeak-ng"):
            subprocess.run(["espeak-ng", "-s", "165", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("say"):
            subprocess.run(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("TTS unavailable (install espeak-ng)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hey Bellamy household voice assistant")
    parser.add_argument("--text", help="Test an intent without using a microphone")
    args = parser.parse_args()

    service = BellamyVoiceService()
    if args.text:
        result = service.intents.handle(args.text)
        print(result.spoken)
        raise SystemExit(0 if result.success else 1)
    service.run()


if __name__ == "__main__":
    main()
