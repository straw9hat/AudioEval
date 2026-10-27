"""Synthetic audio fixtures. No confidential call audio is used in tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 16000
LABEL = {
    "emotional_tone": "neutral", "emotional_intensity": "medium", "background_noise_present": False,
    "background_noise_type": "", "background_noise_severity": "none", "audio_quality": "clear",
    "speaker_overlap_present": False, "long_silence_present": False, "confidence": 0.8,
}


def speech_like(seconds: float, sr: int = SR, seed: int = 0, f0: float = 160.0) -> np.ndarray:
    """Harmonic 'syllables' with pitch movement and pauses."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * sr), dtype=np.float32)
    pos = 0
    while pos < len(out):
        syl = int(rng.uniform(0.12, 0.3) * sr)
        t = np.arange(syl) / sr
        pitch = f0 * (1 + 0.15 * np.sin(2 * np.pi * rng.uniform(1, 4) * t))
        phase = 2 * np.pi * np.cumsum(pitch) / sr
        tone = sum(np.sin(k * phase) / k for k in range(1, 8))
        env = np.hanning(syl)
        seg = (0.25 * tone * env).astype(np.float32)
        end = min(len(out), pos + syl)
        out[pos:end] = seg[: end - pos]
        pos = end + int(rng.uniform(0.03, 0.25) * sr)
    return out


def write(path: Path, x: np.ndarray, sr: int = SR, fmt: str | None = None, subtype: str | None = None) -> Path:
    sf.write(str(path), x, sr, format=fmt, subtype=subtype)
    return path


def manifest(names_labels: list[tuple[str, dict | None]], bom: bool = False, crlf: bool = False) -> bytes:
    nl = "\r\n" if crlf else "\n"
    lines = ["name,result_json"]
    for name, label in names_labels:
        cell = "" if label is None else '"' + json.dumps(label).replace('"', '""') + '"'
        lines.append(f"{name},{cell}")
    text = nl.join(lines) + nl
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def wav_bytes(x: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV")
    return buf.getvalue()


@pytest.fixture
def speech_wav(tmp_path) -> Path:
    return write(tmp_path / "speech.wav", speech_like(12.0))
