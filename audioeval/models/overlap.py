"""Overlapped speech detection via a local pyannote.audio pipeline."""

from __future__ import annotations

import numpy as np


class OverlapModel:
    def __init__(self, path: str, device: str = "cpu"):
        import os

        import torch
        from pyannote.audio import Pipeline

        config = os.path.join(path, "config.yaml")
        self.pipeline = Pipeline.from_pretrained(config)
        self.pipeline.to(torch.device(device))
        self.torch = torch
        self.name = path.replace("\\", "/").rstrip("/").split("/")[-1]

    def overlap_seconds(self, audio: np.ndarray, sr: int) -> float:
        waveform = self.torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        result = self.pipeline({"waveform": waveform, "sample_rate": sr})
        return float(sum(seg.duration for seg in result.get_timeline().support()))
