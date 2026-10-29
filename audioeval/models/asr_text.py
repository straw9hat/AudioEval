"""Local transcription (faster-whisper) and transcript emotion classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .labels import TEXT_LABELS, map_distribution


@dataclass
class Segment:
    start: float
    end: float
    text: str


class WhisperASR:
    def __init__(self, path: str, device: str = "cpu"):
        from faster_whisper import WhisperModel

        compute_type = "int8" if device == "cpu" else "float16"
        self.model = WhisperModel(path, device=device, compute_type=compute_type, local_files_only=True)
        self.name = Path(path).name

    def transcribe(self, audio: np.ndarray, sr: int) -> tuple[list[Segment], str]:
        if sr != 16000:
            raise ValueError("ASR expects 16 kHz audio")
        segments, info = self.model.transcribe(audio.astype(np.float32), vad_filter=True, beam_size=1)
        return [Segment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()], info.language


class TextEmotionModel:
    def __init__(self, path: str, device: str = "cpu"):
        from transformers import pipeline

        self.pipe = pipeline(
            "text-classification", model=path, tokenizer=path, top_k=None, device=-1 if device == "cpu" else 0, truncation=True
        )
        self.name = Path(path).name
        labels = [lbl.lower() for lbl in self.pipe.model.config.id2label.values()]
        if not any(lbl in TEXT_LABELS for lbl in labels):
            raise ValueError(f"text model labels {labels} have no mapping in TEXT_LABELS")

    def predict(self, texts: list[str]) -> list[dict[str, float] | None]:
        if not texts:
            return []
        outputs = self.pipe(texts, batch_size=16)
        results = []
        for out in outputs:
            scores = {d["label"]: float(d["score"]) for d in out}
            # Multi-label models (e.g. GoEmotions) are not normalized; map_distribution renormalizes.
            results.append(map_distribution(scores, TEXT_LABELS))
        return results
