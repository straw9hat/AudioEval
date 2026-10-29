"""Audio decoding and normalization to analysis sample rate."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ANALYSIS_SR = 16000
NATIVE_EXTENSIONS = {".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".aif", ".aiff"}
FFMPEG_EXTENSIONS = {".m4a", ".aac", ".wma", ".webm", ".amr", ".mp4", ".3gp"}


class AudioDecodeError(Exception):
    pass


@dataclass
class Audio:
    channels: np.ndarray  # (samples, n_channels) float32 at ANALYSIS_SR
    sr: int
    original_sr: int
    original_channels: int
    duration_s: float
    distinct_channels: bool  # False for mono or dual-mono (identical channels)

    @property
    def mono(self) -> np.ndarray:
        return self.channels.mean(axis=1)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def supported_extensions() -> set[str]:
    return NATIVE_EXTENSIONS | (FFMPEG_EXTENSIONS if ffmpeg_available() else set())


def _resample(x: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target:
        return x
    g = gcd(sr, target)
    return resample_poly(x, target // g, sr // g, axis=0)


def _decode_ffmpeg(path: Path, max_duration_s: float) -> tuple[np.ndarray, int]:
    if not ffmpeg_available():
        raise AudioDecodeError("format not supported without ffmpeg")
    # Decode one second past the limit so over-long files are detected without reading them fully.
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-t",
        str(max_duration_s + 1),
        "-ac",
        "1",
        "-ar",
        str(ANALYSIS_SR),
        "-f",
        "f32le",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AudioDecodeError("ffmpeg decode timed out") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip().splitlines()
        raise AudioDecodeError(f"ffmpeg could not decode file: {msg[-1] if msg else 'unknown error'}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data.reshape(-1, 1), ANALYSIS_SR


def load_audio(path: str | Path, max_duration_s: float = 3 * 3600, min_duration_s: float = 0.5) -> Audio:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in supported_extensions():
        raise AudioDecodeError(f"unsupported file type '{ext or '(none)'}'")
    try:
        info = sf.info(str(path))
        if info.duration > max_duration_s:
            raise AudioDecodeError(f"audio longer than limit ({info.duration:.0f}s > {max_duration_s:.0f}s)")
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except AudioDecodeError:
        raise
    except Exception:  # libsndfile cannot read it; ffmpeg may
        try:
            data, sr = _decode_ffmpeg(path, max_duration_s)
        except AudioDecodeError as exc:
            raise AudioDecodeError(f"could not decode audio ({exc})") from None
        if len(data) / sr > max_duration_s:
            raise AudioDecodeError(f"audio longer than limit ({max_duration_s:.0f}s)") from None
    if data.size == 0:
        raise AudioDecodeError("audio contains no samples")
    if not np.all(np.isfinite(data)):
        raise AudioDecodeError("audio contains invalid sample values")
    original_channels = data.shape[1]
    distinct = False
    if original_channels >= 2:
        diff = np.sqrt(np.mean((data[:, 0] - data[:, 1]) ** 2))
        level = np.sqrt(np.mean(data[:, :2] ** 2)) + 1e-9
        distinct = bool(diff / level > 0.05)
        data = data[:, :2] if distinct else data[:, :2].mean(axis=1, keepdims=True)
    resampled = _resample(data.astype(np.float64), sr, ANALYSIS_SR).astype(np.float32)
    duration = len(resampled) / ANALYSIS_SR
    if duration < min_duration_s:
        raise AudioDecodeError(f"audio too short ({duration:.2f}s)")
    if duration > max_duration_s:
        raise AudioDecodeError(f"audio longer than limit ({duration:.0f}s > {max_duration_s:.0f}s)")
    return Audio(resampled, ANALYSIS_SR, sr, original_channels, duration, distinct)
