"""Acoustic event tagging (AudioSet vocabulary) via a local Hugging Face model."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .labels import NOISE_LABELS


class AudioEventModel:
    def __init__(self, path: str, device: str = "cpu"):
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self.torch = torch
        self.extractor = AutoFeatureExtractor.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForAudioClassification.from_pretrained(path, local_files_only=True).to(device).eval()
        self.device = device
        self.labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
        self.noise_idx = {i: NOISE_LABELS[lbl] for i, lbl in enumerate(self.labels) if lbl in NOISE_LABELS}
        self.sr = getattr(self.extractor, "sampling_rate", 16000)
        self.name = Path(path).name
        if not self.noise_idx:
            raise ValueError("model has no AudioSet labels that map to noise types")

    def predict(self, windows: list[np.ndarray], sr: int) -> list[dict[str, float]]:
        """Return per-window {noise_type: max probability} using multi-label sigmoid scores."""
        if sr != self.sr:
            raise ValueError(f"event model expects {self.sr} Hz audio")
        results = []
        for start in range(0, len(windows), 8):
            batch = windows[start : start + 8]
            inputs = self.extractor(batch, sampling_rate=sr, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with self.torch.inference_mode():
                probs = self.torch.sigmoid(self.model(**inputs).logits).cpu().numpy()
            for row in probs:
                scores: dict[str, float] = {}
                for i, noise in self.noise_idx.items():
                    scores[noise] = max(scores.get(noise, 0.0), float(row[i]))
                results.append(scores)
        return results
