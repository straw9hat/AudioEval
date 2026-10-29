"""Confidence calibration with isotonic regression (pool-adjacent-violators).

Correctness event (declared): a prediction counts as correct when emotional_tone,
background_noise_present, and audio_quality all match the label.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

MIN_SAMPLES = 30
CORRECTNESS_FIELDS = ("emotional_tone", "background_noise_present", "audio_quality")


def is_correct(pred: dict, label: dict) -> bool:
    return all(pred.get(f) == label.get(f) for f in CORRECTNESS_FIELDS)


def fit_isotonic(raw: list[float], correct: list[bool]) -> dict:
    if len(raw) < MIN_SAMPLES:
        raise ValueError(f"need at least {MIN_SAMPLES} labeled independent clips to calibrate, got {len(raw)}")
    order = np.argsort(raw)
    x = np.asarray(raw, dtype=float)[order]
    y = np.asarray(correct, dtype=float)[order]
    blocks = [[v, 1.0, xv, xv] for v, xv in zip(y, x)]  # mean, weight, x_min, x_max
    merged: list[list[float]] = []
    for b in blocks:
        merged.append(b)
        while len(merged) > 1 and merged[-2][0] > merged[-1][0]:
            b2, b1 = merged.pop(), merged.pop()
            w = b1[1] + b2[1]
            merged.append([(b1[0] * b1[1] + b2[0] * b2[1]) / w, w, b1[2], b2[3]])
    xs = [(b[2] + b[3]) / 2 for b in merged]
    ys = [min(0.99, max(0.01, b[0])) for b in merged]
    return {"method": "isotonic", "correctness_fields": list(CORRECTNESS_FIELDS), "n": len(raw), "x": xs, "y": ys}


class Calibrator:
    def __init__(self, params: dict | None = None):
        self.params = params

    @classmethod
    def load(cls, path: str) -> Calibrator:
        if not path:
            return cls(None)
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def active(self) -> bool:
        return self.params is not None

    def __call__(self, raw: float) -> float:
        if not self.params:
            # Uncalibrated: keep raw heuristic value, bounded away from certainty.
            return float(min(0.95, max(0.05, raw)))
        return float(np.interp(raw, self.params["x"], self.params["y"]))


def brier_and_ece(conf: list[float], correct: list[bool], bins: int = 10) -> dict:
    c = np.asarray(conf, dtype=float)
    y = np.asarray(correct, dtype=float)
    if c.size == 0:
        return {"brier": None, "ece": None, "n": 0}
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(c, edges) - 1, 0, bins - 1)
    ece = sum(abs(c[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean() for b in range(bins) if (idx == b).any())
    return {"brier": float(np.mean((c - y) ** 2)), "ece": float(ece), "n": int(c.size)}
