"""End-to-end analysis of one audio file."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import __version__
from .audio import Audio, load_audio
from .calibration import Calibrator
from .config import Settings
from .features import HOP, call_features, frame_features, mask_runs, speech_mask
from .models import ModelBundle, load_models
from .rules import (
    aggregate_tone,
    decide_noise,
    decide_overlap,
    decide_quality,
    decide_silence,
    decide_tone,
    overall_confidence,
)
from .schema import validate_prediction


@dataclass
class AnalysisResult:
    prediction: dict
    details: dict


def speech_windows(
    x: np.ndarray, sr: int, mask: np.ndarray, min_s: float = 2.0, max_s: float = 8.0
) -> tuple[list[np.ndarray], list[float]]:
    """Cut VAD speech regions into windows of 2-8 s for window-level models."""
    windows, weights = [], []
    for s, e in mask_runs(mask):
        a, b = s * HOP, min(len(x), e * HOP)
        while b - a >= int(min_s * sr) // 2:
            end = min(b, a + int(max_s * sr))
            seg = x[a:end]
            if len(seg) < min_s * sr:
                seg = np.pad(seg, (0, int(min_s * sr) - len(seg)))
            windows.append(seg.astype(np.float32))
            weights.append((end - a) / sr)
            a = end
    return windows, weights


def fixed_windows(x: np.ndarray, sr: int, size_s: float = 10.0) -> list[np.ndarray]:
    n = int(size_s * sr)
    return [x[i : i + n] for i in range(0, max(len(x) - n // 4, 1), n)]


class Analyzer:
    def __init__(self, settings: Settings | None = None, models: ModelBundle | None = None):
        self.settings = settings or Settings.from_env()
        self.models = models if models is not None else load_models(self.settings)
        self.calibrator = Calibrator.load(self.settings.calibration_path)

    @property
    def method(self) -> str:
        used = [k for k, v in self.models.names.items() if v]
        return "acoustic_baseline" + (f"+{'+'.join(used)}" if used else "")

    def describe(self) -> dict:
        return {"version": __version__, "method": self.method, "models": self.models.status, "calibrated": self.calibrator.active}

    def _customer_signal(self, audio: Audio) -> tuple[np.ndarray, str]:
        ch = self.settings.customer_channel
        if audio.distinct_channels and ch in ("0", "1"):
            return audio.channels[:, int(ch)], f"channel_{ch}"
        # Mono, dual-mono, or unknown channel roles: analyze the mix (customer and agent).
        return audio.mono, "mixed_unresolved"

    def analyze(self, path: str | Path) -> AnalysisResult:
        t0 = time.perf_counter()
        s = self.settings
        audio = load_audio(path, max_duration_s=s.max_duration_s)
        t_decode = time.perf_counter()
        cf, _, mask = call_features(audio)
        t_feat = time.perf_counter()
        timings: dict[str, float] = {}

        customer, role = self._customer_signal(audio)
        if role.startswith("channel_"):
            cust_mask, _ = speech_mask(frame_features(customer, audio.sr))
        else:
            cust_mask = mask

        audio_dist = text_dist = None
        transcript_chars = 0
        if self.models.emotion is not None:
            t = time.perf_counter()
            windows, weights = speech_windows(customer, audio.sr, cust_mask)
            dists = self.models.emotion.predict(windows, audio.sr) if windows else []
            pairs = [(d, w) for d, w in zip(dists, weights) if d]
            if pairs:
                audio_dist = aggregate_tone([d for d, _ in pairs], [w for _, w in pairs])
            timings["emotion_s"] = time.perf_counter() - t
        if self.models.asr is not None and self.models.text is not None:
            t = time.perf_counter()
            segments, _ = self.models.asr.transcribe(customer, audio.sr)
            texts = [seg.text for seg in segments]
            transcript_chars = sum(len(x) for x in texts)
            dists = [d for d in self.models.text.predict(texts) if d]
            if dists:
                text_dist = aggregate_tone(dists, [max(seg.end - seg.start, 0.5) for seg in segments][: len(dists)])
            timings["asr_text_s"] = time.perf_counter() - t

        event_cov = None
        if self.models.events is not None:
            t = time.perf_counter()
            windows = fixed_windows(audio.mono, audio.sr)
            scores = self.models.events.predict(windows, audio.sr)
            thr = s.noise_event_threshold
            types = {k for sc in scores for k in sc}
            event_cov = {k: float(np.mean([sc.get(k, 0.0) >= thr for sc in scores])) for k in types}
            timings["events_s"] = time.perf_counter() - t

        overlap_s = None
        if self.models.overlap is not None:
            t = time.perf_counter()
            overlap_s = self.models.overlap.overlap_seconds(audio.mono, audio.sr)
            timings["overlap_s"] = time.perf_counter() - t

        tone, intensity = decide_tone(cf, audio_dist, text_dist, s)
        present, ntype, severity = decide_noise(cf, event_cov, s)
        decisions = {
            "emotional_tone": tone,
            "emotional_intensity": intensity,
            "background_noise_present": present,
            "background_noise_type": ntype,
            "background_noise_severity": severity,
            "audio_quality": decide_quality(cf, s),
            "speaker_overlap_present": decide_overlap(cf, overlap_s, s),
            "long_silence_present": decide_silence(cf, s),
        }
        raw_conf = overall_confidence(decisions)
        pred = {k: d.value for k, d in decisions.items()}
        pred["confidence"] = round(self.calibrator(raw_conf), 3)
        pred = validate_prediction(pred)

        total = time.perf_counter() - t0
        timings.update({"decode_s": t_decode - t0, "features_s": t_feat - t_decode, "total_s": total})
        details = {
            "method": self.method,
            "version": __version__,
            "customer_audio": role,
            "audio": {
                "duration_s": round(audio.duration_s, 2),
                "original_sr": audio.original_sr,
                "channels": audio.original_channels,
                "distinct_channels": audio.distinct_channels,
            },
            "field_confidence": {k: round(d.confidence, 3) for k, d in decisions.items()},
            "raw_confidence": round(raw_conf, 3),
            "calibrated": self.calibrator.active,
            "evidence": {k: d.evidence for k, d in decisions.items() if d.evidence},
            "features": cf.to_dict(),
            "transcript_chars": transcript_chars,
            "timings": {k: round(v, 3) for k, v in timings.items()},
            "real_time_factor": round(total / max(audio.duration_s, 1e-6), 4),
        }
        return AnalysisResult(pred, details)
