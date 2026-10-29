"""Runtime settings, read from AUDIOEVAL_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path


def _env(name: str, default):
    raw = os.environ.get(f"AUDIOEVAL_{name.upper()}")
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


@dataclass(frozen=True)
class Settings:
    # Decision thresholds. Hand-set starting points, not fitted; they were chosen with the
    # supplied calls in view, so agreement on those calls is not independent validation.
    long_silence_s: float = 10.0
    overlap_ratio_single: float = 0.10
    overlap_ratio_two_channel: float = 0.05
    noise_active_ratio: float = 0.15
    min_background_s: float = 3.0
    noise_transient_rate: float = 6.0
    noise_snr_db: float = 15.0
    noise_event_threshold: float = 0.15
    noise_event_coverage: float = 0.10
    low_volume_db: float = -45.0
    clip_slight: float = 0.001
    clip_severe: float = 0.01
    dropout_slight: float = 2.0
    dropout_severe: float = 10.0
    muffled_rolloff_hz: float = 300.0
    customer_channel: str = "auto"  # auto | 0 | 1 when channels carry separate speakers
    text_weight: float = 0.6  # weight of transcript evidence vs audio emotion model

    # Optional local model directories (never downloaded at runtime).
    emotion_model: str = ""
    event_model: str = ""
    asr_model: str = ""
    text_model: str = ""
    overlap_model: str = ""
    device: str = "cpu"
    calibration_path: str = ""

    # Service limits.
    max_duration_s: float = 3 * 3600.0
    max_upload_mb: int = 2048
    max_files: int = 2000
    workers: int = 2
    retention_hours: float = 72.0
    keep_audio: bool = False
    data_dir: str = "jobs"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(**{f.name: _env(f.name, f.default) for f in fields(cls)})

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)
