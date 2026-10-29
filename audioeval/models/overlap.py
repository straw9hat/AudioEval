"""Overlapped speech detection via a local pyannote.audio pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np


class OverlapModel:
    def __init__(self, path: str, device: str = "cpu"):
        import torch
        from pyannote.audio import Pipeline

        self.pipeline = Pipeline.from_pretrained(str(Path(path) / "config.yaml"))
        self.pipeline.to(torch.device(device))
        self.torch = torch
        self.name = Path(path).name

    def overlap_seconds(self, audio: np.ndarray, sr: int) -> float:
        waveform = self.torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        result = self.pipeline({"waveform": waveform, "sample_rate": sr})
        return float(sum(seg.duration for seg in result.get_timeline().support()))
