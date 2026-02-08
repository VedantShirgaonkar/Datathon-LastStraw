from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional


class TTSError(RuntimeError):
    pass


@dataclass
class TTSResult:
    wav_bytes: bytes

    def wav_base64(self) -> str:
        return base64.b64encode(self.wav_bytes).decode("ascii")


class TTSBackend:
    def synthesize_wav(self, text: str) -> TTSResult:
        raise NotImplementedError


class NoTTS(TTSBackend):
    def synthesize_wav(self, text: str) -> TTSResult:
        raise TTSError("TTS is disabled")


class MacOSSayTTS(TTSBackend):
    """Free local TTS on macOS using the built-in `say` command.

    Produces WAV via `afconvert` (also built-in on macOS).
    """

    def synthesize_wav(self, text: str) -> TTSResult:
        t = (text or "").strip()
        if not t:
            raise TTSError("Empty text")

        with tempfile.TemporaryDirectory() as d:
            aiff_path = os.path.join(d, "out.aiff")
            wav_path = os.path.join(d, "out.wav")

            # say -> AIFF
            try:
                subprocess.run(["say", "-o", aiff_path, t], check=True, capture_output=True)
            except FileNotFoundError as e:
                raise TTSError("`say` not found (macOS only)") from e
            except subprocess.CalledProcessError as e:
                raise TTSError(f"say failed: {e.stderr.decode('utf-8', 'ignore')}") from e

            # AIFF -> WAV
            try:
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", aiff_path, wav_path], check=True, capture_output=True)
            except FileNotFoundError as e:
                raise TTSError("`afconvert` not found on this system") from e
            except subprocess.CalledProcessError as e:
                raise TTSError(f"afconvert failed: {e.stderr.decode('utf-8', 'ignore')}") from e

            with open(wav_path, "rb") as f:
                return TTSResult(wav_bytes=f.read())


@dataclass
class PiperTTS(TTSBackend):
    """Free open-source TTS using the `piper` CLI + an `.onnx` voice model."""

    piper_binary: str
    model_path: str
    speaker_id: int = 0

    def synthesize_wav(self, text: str) -> TTSResult:
        t = (text or "").strip()
        if not t:
            raise TTSError("Empty text")
        if not self.model_path:
            raise TTSError("PIPER_MODEL_PATH not configured")

        with tempfile.TemporaryDirectory() as d:
            wav_path = os.path.join(d, "out.wav")
            # Piper reads text from stdin.
            cmd = [
                self.piper_binary,
                "--model",
                self.model_path,
                "--output_file",
                wav_path,
                "--speaker",
                str(int(self.speaker_id)),
            ]
            try:
                subprocess.run(cmd, input=t.encode("utf-8"), check=True, capture_output=True)
            except FileNotFoundError as e:
                raise TTSError(f"piper binary not found: {self.piper_binary}") from e
            except subprocess.CalledProcessError as e:
                err = (e.stderr or b"").decode("utf-8", "ignore")
                raise TTSError(f"piper failed: {err}") from e

            with open(wav_path, "rb") as f:
                return TTSResult(wav_bytes=f.read())


def build_tts_backend(
    *,
    backend_name: str,
    piper_binary: str,
    piper_model_path: str,
    piper_speaker_id: int,
) -> TTSBackend:
    name = (backend_name or "").strip().lower()
    if name in {"", "none", "off", "false", "0"}:
        return NoTTS()
    if name == "piper":
        return PiperTTS(piper_binary=piper_binary, model_path=piper_model_path, speaker_id=piper_speaker_id)
    # Default to macos_say
    return MacOSSayTTS()
