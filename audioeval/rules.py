"""Decision rules that turn acoustic features and optional model evidence into schema fields."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .config import Settings
from .features import CallFeatures
from .models.labels import TONES

TONE_MIN_EVIDENCE = 0.35  # non-neutral tone must reach this aggregated probability


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _margin_conf(value: float, threshold: float, scale: float, cap: float = 0.95) -> float:
    """Confidence that a thresholded decision is right, from distance to the threshold."""
    return min(cap, _sigmoid(abs(value - threshold) / max(scale, 1e-6)))


@dataclass
class Decision:
    value: object
    confidence: float
    evidence: dict = field(default_factory=dict)


def arousal_score(cf: CallFeatures) -> float:
    """Prosodic activation (not valence). Reference values are generic adult-speech norms."""
    parts = [
        (cf.pitch_std_semitones - 4.0) / 1.5,
        (cf.energy_std_db - 12.0) / 4.0,
        (cf.voiced_onset_rate - 5.0) / 2.0,
    ]
    return float(np.mean(parts))


def intensity_from_arousal(a: float) -> str:
    return "high" if a > 1.0 else "low" if a < -1.0 else "medium"


def aggregate_tone(dists: list[dict[str, float]], weights: list[float] | None = None) -> dict[str, float]:
    """Blend the mean distribution with the most emotional 25% of windows.

    Calls mix customer and agent speech, and emotion is often localized, so a plain
    mean dilutes short but clear customer emotion.
    """
    if not dists:
        return {}
    m = np.array([[d.get(t, 0.0) for t in TONES] for d in dists])
    w = np.ones(len(m)) if weights is None else np.asarray(weights, dtype=float)
    mean = (m * w[:, None]).sum(axis=0) / w.sum()
    non_neutral = m[:, 1:].max(axis=1)
    k = max(1, int(math.ceil(len(m) * 0.25)))
    top = m[np.argsort(non_neutral)[-k:]].mean(axis=0)
    agg = 0.5 * mean + 0.5 * top
    return {t: float(v) for t, v in zip(TONES, agg / agg.sum())}


def decide_tone(cf: CallFeatures, audio_dist: dict | None, text_dist: dict | None, s: Settings) -> tuple[Decision, Decision]:
    arousal = arousal_score(cf)
    if audio_dist and text_dist:
        dist = {t: (1 - s.text_weight) * audio_dist[t] + s.text_weight * text_dist[t] for t in TONES}
        source = "audio_emotion+transcript"
    else:
        dist = audio_dist or text_dist
        source = "audio_emotion" if audio_dist else "transcript" if text_dist else "acoustic_prior"
    if not dist:
        # No valence evidence: prosody alone cannot separate frustrated from satisfied,
        # and the brief forbids inferring frustration/distress from loudness.
        tone = Decision("neutral", 0.35, {"source": source, "arousal": round(arousal, 3)})
        intensity = Decision(intensity_from_arousal(arousal), 0.4, {"arousal": round(arousal, 3)})
        return tone, intensity
    best = max((t for t in TONES if t != "neutral"), key=lambda t: dist[t])
    label = best if dist[best] >= TONE_MIN_EVIDENCE and dist[best] > dist["neutral"] else "neutral"
    p = dist[label]
    ev = {"source": source, "distribution": {t: round(v, 3) for t, v in dist.items()}, "arousal": round(arousal, 3)}
    if label == "neutral":
        level = intensity_from_arousal(arousal)
    elif p >= 0.7 or (label in ("upset", "distressed") and arousal > 1.0):
        level = "high"
    elif p < 0.45:
        level = "low"
    else:
        level = "medium"
    return Decision(label, float(p), ev), Decision(level, float(min(0.9, 0.5 + 0.4 * p)), {"arousal": round(arousal, 3)})


def decide_noise(cf: CallFeatures, event_cov: dict[str, float] | None, s: Settings) -> tuple[Decision, Decision, Decision]:
    """Return (present, type, severity). Poor technical quality alone is not noise."""
    enough_bg = cf.background_seconds >= s.min_background_s
    sustained = enough_bg and cf.bg_active_ratio >= s.noise_active_ratio
    impulsive = cf.bg_transient_rate >= s.noise_transient_rate
    low_snr = enough_bg and cf.snr_db < s.noise_snr_db and cf.bg_active_ratio >= s.noise_active_ratio / 2
    acoustic_present = sustained or impulsive or low_snr
    ev = {
        "bg_active_ratio": round(cf.bg_active_ratio, 3), "bg_transient_rate_per_min": round(cf.bg_transient_rate, 2),
        "background_seconds": round(cf.background_seconds, 1),
        "snr_db": round(cf.snr_db, 1), "acoustic_present": acoustic_present,
    }
    if impulsive and cf.bg_voicing <= 0.5:
        acoustic_type = "static"
    elif cf.bg_voicing > 0.5:
        acoustic_type = "background voices"
    elif cf.bg_flatness > 0.5 and cf.bg_stationarity_db < 4:
        acoustic_type = "hiss"
    else:
        acoustic_type = "background noise"

    model_type, model_cov = None, 0.0
    if event_cov:
        ev["event_coverage"] = {k: round(v, 3) for k, v in sorted(event_cov.items(), key=lambda kv: -kv[1])[:5]}
        model_type, model_cov = max(event_cov.items(), key=lambda kv: kv[1])
        if model_cov < s.noise_event_coverage:
            model_type = None
    present = acoustic_present or model_type is not None

    if not present:
        margins = [
            _margin_conf(cf.bg_active_ratio, s.noise_active_ratio, 0.05),
            _margin_conf(cf.bg_transient_rate, s.noise_transient_rate, 2.0),
        ]
        conf = min(margins) * (0.9 if event_cov is not None else 0.75)
        if not enough_bg and event_cov is None:
            conf = min(conf, 0.5)  # little non-speech audio to judge from
        return Decision(False, conf, ev), Decision("", conf), Decision("none", conf)

    noise_type = model_type or acoustic_type
    if cf.snr_db < 10 or cf.bg_active_ratio > 0.6 or model_cov > 0.6:
        severity = "high"
    elif cf.snr_db < 20 or cf.bg_active_ratio > 0.3 or cf.bg_transient_rate > 12 or model_cov > 0.3:
        severity = "medium"
    else:
        severity = "low"
    agree = acoustic_present and model_type is not None
    conf = 0.8 if agree else (0.65 if model_type else 0.6)
    if impulsive:
        conf = max(conf, _margin_conf(cf.bg_transient_rate, s.noise_transient_rate, 3.0, cap=0.85))
    return Decision(True, conf, ev), Decision(noise_type, 0.5 if model_type else 0.35), Decision(severity, 0.45)


def decide_quality(cf: CallFeatures, s: Settings) -> Decision:
    issues: dict[str, str] = {}
    if cf.clip_fraction >= s.clip_severe:
        issues["clipping"] = "severe"
    elif cf.clip_fraction >= s.clip_slight:
        issues["clipping"] = "slight"
    if cf.dropout_rate >= s.dropout_severe:
        issues["dropouts"] = "severe"
    elif cf.dropout_rate >= s.dropout_slight:
        issues["dropouts"] = "slight"
    if cf.speech_level_db < s.low_volume_db - 10:
        issues["low_volume"] = "severe"
    elif cf.speech_level_db < s.low_volume_db:
        issues["low_volume"] = "slight"
    if 0 < cf.speech_rolloff_hz < s.muffled_rolloff_hz:
        issues["muffled"] = "slight"
    if cf.speech_ratio < 0.02:
        issues["no_detectable_speech"] = "severe"
    if "severe" in issues.values() or len(issues) >= 3:
        value = "severely_impaired"
    elif issues:
        value = "slightly_impaired"
    else:
        value = "clear"
    margins = [
        _margin_conf(cf.clip_fraction, s.clip_slight, 0.0005),
        _margin_conf(cf.dropout_rate, s.dropout_slight, 1.0),
        _margin_conf(cf.speech_level_db, s.low_volume_db, 4.0),
    ]
    ev = {"issues": issues, "clip_fraction": round(cf.clip_fraction, 5), "dropouts_per_min": round(cf.dropout_rate, 2),
          "speech_level_dbfs": round(cf.speech_level_db, 1), "speech_rolloff_hz": round(cf.speech_rolloff_hz, 0)}
    # Robotic audio, echo, and codec artifacts are not measured by the baseline.
    return Decision(value, min(margins) * 0.85, ev)


def decide_overlap(cf: CallFeatures, overlap_s: float | None, s: Settings) -> Decision:
    if overlap_s is not None:
        speech_s = max(cf.speech_ratio * cf.duration_s, 1e-6)
        ratio = overlap_s / speech_s
        present = overlap_s >= 1.0 and ratio >= 0.02
        return Decision(present, _margin_conf(ratio, 0.02, 0.01, cap=0.9),
                        {"method": "overlap_model", "overlap_s": round(overlap_s, 2), "ratio": round(ratio, 4)})
    if cf.overlap_method == "two_channel_vad":
        thr, cap = s.overlap_ratio_two_channel, 0.9
    else:
        thr, cap = s.overlap_ratio_single, 0.6  # weak heuristic on mixed single-channel audio
    return Decision(cf.overlap_ratio >= thr, _margin_conf(cf.overlap_ratio, thr, 0.02, cap=cap),
                    {"method": cf.overlap_method, "ratio": round(cf.overlap_ratio, 4)})


def decide_silence(cf: CallFeatures, s: Settings) -> Decision:
    return Decision(cf.longest_silence_s >= s.long_silence_s,
                    _margin_conf(cf.longest_silence_s, s.long_silence_s, 1.5),
                    {"longest_silence_s": round(cf.longest_silence_s, 2), "threshold_s": s.long_silence_s})


def overall_confidence(decisions: dict[str, Decision]) -> float:
    """Raw overall confidence: geometric mean of per-field confidences for scored fields."""
    keys = ("emotional_tone", "background_noise_present", "audio_quality", "speaker_overlap_present", "long_silence_present")
    vals = [max(1e-3, decisions[k].confidence) for k in keys]
    return float(np.exp(np.mean(np.log(vals))))
