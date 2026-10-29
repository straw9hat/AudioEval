"""Deterministic frame-level and call-level acoustic features.

Constants here describe framing and signal-processing limits. Decision thresholds
live in `config.py`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .audio import Audio

FRAME = 400  # 25 ms at 16 kHz
HOP = 160  # 10 ms
N_FFT = 512
BLOCK = 4000  # frames per processing block, bounds memory for long calls
MIN_LAG, MAX_LAG = 32, 228  # 500 Hz .. 70 Hz pitch range
DIGITAL_SILENCE_DB = -85.0


@dataclass
class FrameFeatures:
    energy_db: np.ndarray
    flatness: np.ndarray
    centroid_hz: np.ndarray
    rolloff_hz: np.ndarray
    voicing: np.ndarray
    pitch_hz: np.ndarray
    second_pitch: np.ndarray  # strength of a non-harmonic second periodicity

    @property
    def n(self) -> int:
        return len(self.energy_db)


def frame_features(x: np.ndarray, sr: int) -> FrameFeatures:
    x = np.asarray(x, dtype=np.float32)
    if len(x) < FRAME:
        x = np.pad(x, (0, FRAME - len(x)))
    frames_all = sliding_window_view(x, FRAME)[::HOP]
    window = np.hanning(FRAME).astype(np.float32)
    freqs = np.fft.rfftfreq(N_FFT, 1 / sr)
    band = (freqs >= 300) & (freqs <= 4000)
    out = {k: [] for k in FrameFeatures.__dataclass_fields__}
    for start in range(0, len(frames_all), BLOCK):
        fr = frames_all[start : start + BLOCK].astype(np.float32)
        fr = fr - fr.mean(axis=1, keepdims=True)
        out["energy_db"].append(10 * np.log10(np.mean(fr**2, axis=1) + 1e-10))
        spec = np.abs(np.fft.rfft(fr * window, n=N_FFT, axis=1)) ** 2 + 1e-12
        sb = spec[:, band]
        out["flatness"].append(np.exp(np.mean(np.log(sb), axis=1)) / np.mean(sb, axis=1))
        total = spec.sum(axis=1)
        out["centroid_hz"].append((spec * freqs).sum(axis=1) / total)
        cum = np.cumsum(spec, axis=1)
        out["rolloff_hz"].append(freqs[np.argmax(cum >= 0.85 * total[:, None], axis=1)])
        # Normalized autocorrelation for voicing and pitch.
        ac = np.fft.irfft(np.abs(np.fft.rfft(fr, n=1024, axis=1)) ** 2, axis=1)[:, : MAX_LAG + 1]
        ac = ac / (ac[:, :1] + 1e-10)
        seg = ac[:, MIN_LAG:]
        best = np.argmax(seg, axis=1)
        strength = seg[np.arange(len(seg)), best]
        lag = best + MIN_LAG
        out["voicing"].append(np.clip(strength, 0, 1))
        out["pitch_hz"].append(sr / lag)
        # Second periodicity: best peak whose lag is not near a multiple/submultiple of the first.
        lags = np.arange(MIN_LAG, MAX_LAG + 1)
        ratio = lags[None, :] / lag[:, None]
        harmonic = np.abs(ratio - np.round(ratio)) < 0.12
        sub = lag[:, None] / lags[None, :]
        harmonic |= np.abs(sub - np.round(sub)) < 0.12
        masked = np.where(harmonic, -1.0, seg)
        out["second_pitch"].append(np.clip(masked.max(axis=1), 0, 1) / np.maximum(strength, 1e-3))
    return FrameFeatures(**{k: np.concatenate(v).astype(np.float32) for k, v in out.items()})


def mask_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return [start, end) index pairs of True runs."""
    if mask.size == 0:
        return []
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(padded)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    if n <= 0 or not mask.any():
        return mask.copy()
    kernel = np.ones(2 * n + 1)
    return np.convolve(mask.astype(float), kernel, mode="same") > 0


def speech_mask(ff: FrameFeatures) -> tuple[np.ndarray, float]:
    """Energy + voicing VAD with hangover. Returns (mask, quiet floor dB)."""
    # Include digital-zero frames so the floor is not estimated from speech tails when there is no background.
    floor = float(np.percentile(np.maximum(ff.energy_db, -95.0), 10))
    loud = ff.energy_db > max(floor + 12.0, -80.0)
    voiced = loud & (ff.voicing > 0.5)
    # Keep loud frames within 300 ms of voiced frames (consonants, word edges).
    mask = loud & _dilate(voiced, 30)
    # Bridge short pauses (< 250 ms) inside speech.
    gaps = mask_runs(~mask)
    for s, e in gaps:
        if s > 0 and e < len(mask) and e - s < 25:
            mask[s:e] = True
    # Drop isolated blips shorter than 100 ms.
    for s, e in mask_runs(mask):
        if e - s < 10:
            mask[s:e] = False
    return mask, floor


@dataclass
class CallFeatures:
    duration_s: float
    distinct_channels: bool
    speech_ratio: float
    speech_level_db: float
    quiet_floor_db: float
    background_level_db: float
    background_seconds: float  # non-speech audio available as background evidence
    snr_db: float
    bg_active_ratio: float
    bg_voicing: float
    bg_flatness: float
    bg_transient_rate: float  # impulsive events per minute in non-speech regions
    bg_stationarity_db: float  # std of background energy (low = steady hiss/hum)
    longest_silence_s: float
    longest_internal_silence_s: float
    overlap_ratio: float
    overlap_method: str
    clip_fraction: float
    dropout_rate: float  # abrupt digital-silence gaps inside speech, per minute
    speech_rolloff_hz: float
    pitch_median_hz: float
    pitch_std_semitones: float
    energy_std_db: float
    voiced_onset_rate: float  # syllable-rate proxy, per second of speech
    loud_speech_ratio: float

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _clip_fraction(x: np.ndarray) -> float:
    """Fraction of samples in runs of >=3 consecutive near-peak samples, for near-full-scale peaks."""
    a = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    peak = float(a.max()) if a.size else 0.0
    if peak < 0.89:  # peaks below -1 dBFS are not treated as clipping
        return 0.0
    near = a >= 0.995 * peak
    run3 = near[2:] & near[1:-1] & near[:-2]
    return float(run3.mean())


def call_features(audio: Audio) -> tuple[CallFeatures, FrameFeatures, np.ndarray]:
    sr = audio.sr
    mono = audio.mono
    ff = frame_features(mono, sr)
    mask, floor = speech_mask(ff)
    fps = sr / HOP
    minutes = max(audio.duration_s / 60.0, 1e-6)

    speech_db = ff.energy_db[mask]
    near_speech = _dilate(mask, 20)
    bg = ~near_speech & (ff.energy_db > DIGITAL_SILENCE_DB)
    speech_level = float(np.median(speech_db)) if speech_db.size else -100.0
    bg_level = float(np.median(ff.energy_db[bg])) if bg.any() else floor
    bg_active = bg & (ff.energy_db > floor + 10.0)
    bg_active_ratio = float(bg_active.sum() / max(bg.sum(), 1))
    bg_voicing = float(np.mean(ff.voicing[bg_active])) if bg_active.any() else 0.0
    bg_flatness = float(np.mean(ff.flatness[bg])) if bg.any() else 0.0
    bg_std = float(np.std(ff.energy_db[bg])) if bg.sum() > 10 else 0.0
    jumps = np.diff(ff.energy_db, prepend=ff.energy_db[:1]) > 15.0
    transients = jumps & bg
    bg_minutes = max(bg.sum() / fps / 60.0, 1e-6)
    bg_transient_rate = float(transients.sum() / bg_minutes) if bg.sum() > fps * 5 else 0.0

    silent = ~mask
    silent_runs = mask_runs(silent)
    longest = max(((e - s) / fps for s, e in silent_runs), default=0.0)
    internal = max(((e - s) / fps for s, e in silent_runs if s > 0 and e < len(mask)), default=0.0)

    if audio.distinct_channels:
        m0, _ = speech_mask(frame_features(audio.channels[:, 0], sr))
        m1, _ = speech_mask(frame_features(audio.channels[:, 1], sr))
        n = min(len(m0), len(m1))
        both = m0[:n] & m1[:n]
        overlap_ratio = float(both.sum() / max((m0[:n] | m1[:n]).sum(), 1))
        overlap_method = "two_channel_vad"
    else:
        voiced = mask & (ff.voicing > 0.5)
        multi = voiced & (ff.second_pitch > 0.85)
        overlap_ratio = float(multi.sum() / max(voiced.sum(), 1))
        overlap_method = "single_channel_multipitch_heuristic"

    digital = ff.energy_db <= DIGITAL_SILENCE_DB
    dropouts = 0
    abrupt = speech_level - 10.0
    for s, e in mask_runs(digital):
        # Packet loss cuts speech off abruptly; natural pauses and DTX decay first.
        if 2 <= e - s <= 20 and s > 0 and e < len(mask) and ff.energy_db[s - 1] >= abrupt and ff.energy_db[e] >= abrupt:
            dropouts += 1

    voiced_speech = mask & (ff.voicing > 0.5)
    pitches = ff.pitch_hz[voiced_speech]
    if pitches.size > 20:
        semis = 12 * np.log2(pitches / np.median(pitches))
        pitch_std = float(np.std(np.clip(semis, -12, 12)))
        pitch_med = float(np.median(pitches))
    else:
        pitch_std, pitch_med = 0.0, 0.0
    onsets = np.sum(voiced_speech[1:] & ~voiced_speech[:-1])
    speech_seconds = max(mask.sum() / fps, 1e-6)

    cf = CallFeatures(
        duration_s=audio.duration_s,
        distinct_channels=audio.distinct_channels,
        speech_ratio=float(mask.mean()),
        speech_level_db=speech_level,
        quiet_floor_db=floor,
        background_level_db=bg_level,
        background_seconds=float(bg.sum() / fps),
        snr_db=speech_level - bg_level,
        bg_active_ratio=bg_active_ratio,
        bg_voicing=bg_voicing,
        bg_flatness=bg_flatness,
        bg_transient_rate=bg_transient_rate,
        bg_stationarity_db=bg_std,
        longest_silence_s=float(longest),
        longest_internal_silence_s=float(internal),
        overlap_ratio=overlap_ratio,
        overlap_method=overlap_method,
        clip_fraction=_clip_fraction(audio.channels),
        dropout_rate=dropouts / minutes,
        speech_rolloff_hz=float(np.median(ff.rolloff_hz[mask])) if mask.any() else 0.0,
        pitch_median_hz=pitch_med,
        pitch_std_semitones=pitch_std,
        energy_std_db=float(np.std(ff.energy_db[voiced_speech])) if voiced_speech.sum() > 20 else 0.0,
        voiced_onset_rate=float(onsets / speech_seconds),
        loud_speech_ratio=float(np.mean(speech_db > speech_level + 6.0)) if speech_db.size else 0.0,
    )
    return cf, ff, mask
