"""Speech emotion recognition via a local Hugging Face audio-classification model."""

from __future__ import annotations

import numpy as np

from .labels import SER_LABELS, map_distribution


class AudioEmotionModel:
    def __init__(self, path: str, device: str = "cpu"):
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self.torch = torch
        self.extractor = AutoFeatureExtractor.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForAudioClassification.from_pretrained(path, local_files_only=True).to(device).eval()
        self.device = device
        self.labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
        self.sr = getattr(self.extractor, "sampling_rate", 16000)
        self.name = path.replace("\\", "/").rstrip("/").split("/")[-1]
        if not any(lbl.strip().lower() in SER_LABELS for lbl in self.labels):
            raise ValueError(f"model labels {self.labels} have no mapping in SER_LABELS")

    def predict(self, windows: list[np.ndarray], sr: int) -> list[dict[str, float] | None]:
        """Return per-window tone distributions (schema tones), or None if unmappable."""
        if sr != self.sr:
            raise ValueError(f"emotion model expects {self.sr} Hz audio")
        results = []
        for start in range(0, len(windows), 8):
            batch = windows[start:start + 8]
            inputs = self.extractor(batch, sampling_rate=sr, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with self.torch.inference_mode():
                probs = self.torch.softmax(self.model(**inputs).logits, dim=-1).cpu().numpy()
            for row in probs:
                results.append(map_distribution(dict(zip(self.labels, row.tolist())), SER_LABELS))
        return results
