import numpy as np
import pytest
import soundfile as sf

from audioeval.audio import AudioDecodeError, load_audio
from audioeval.calibration import Calibrator, fit_isotonic
from audioeval.config import Settings
from audioeval.cost import cost_per_audio_minute
from audioeval.features import CallFeatures
from audioeval.models import ModelBundle
from audioeval.pipeline import Analyzer
from audioeval.rules import aggregate_tone, decide_tone
from audioeval.scoring import score
from conftest import LABEL, SR, speech_like, write


@pytest.fixture(scope="module")
def analyzer():
    return Analyzer(Settings(), models=ModelBundle())


def test_speech_prediction_is_schema_valid(analyzer, speech_wav):
    res = analyzer.analyze(speech_wav)
    assert res.prediction["emotional_tone"] == "neutral"  # no valence evidence without models
    assert res.prediction["long_silence_present"] is False
    assert res.prediction["audio_quality"] == "clear"
    assert 0 <= res.prediction["confidence"] <= 1
    assert res.details["method"] == "acoustic_baseline"


def test_analysis_is_deterministic(analyzer, speech_wav):
    assert analyzer.analyze(speech_wav).prediction == analyzer.analyze(speech_wav).prediction


def test_long_silence_detected(analyzer, tmp_path):
    x = np.concatenate([speech_like(5), np.zeros(SR * 15, dtype=np.float32), speech_like(5, seed=1)])
    res = analyzer.analyze(write(tmp_path / "gap.wav", x))
    assert res.prediction["long_silence_present"] is True
    assert res.details["evidence"]["long_silence_present"]["longest_silence_s"] >= 14


def test_impulsive_background_noise_detected(analyzer, tmp_path):
    rng = np.random.default_rng(3)
    parts = []
    for i in range(6):
        parts.append(speech_like(3, seed=i))
        gap = 1e-4 * rng.standard_normal(SR * 3).astype(np.float32)
        for pos in rng.integers(0, len(gap) - 80, 12):
            gap[pos : pos + 40] += 0.3 * rng.standard_normal(40).astype(np.float32)
        parts.append(gap)
    res = analyzer.analyze(write(tmp_path / "static.wav", np.concatenate(parts)))
    assert res.prediction["background_noise_present"] is True
    assert res.prediction["background_noise_type"] == "static"
    assert res.prediction["background_noise_severity"] != "none"


def test_low_volume_is_quality_not_noise(analyzer, tmp_path):
    res = analyzer.analyze(write(tmp_path / "quiet.wav", speech_like(10) * 0.002))
    assert res.prediction["audio_quality"] != "clear"
    assert res.prediction["background_noise_present"] is False


def test_clipping_detected(analyzer, tmp_path):
    x = np.clip(speech_like(10) * 8, -1, 1)
    res = analyzer.analyze(write(tmp_path / "clip.wav", x))
    assert res.prediction["audio_quality"] in ("slightly_impaired", "severely_impaired")


def test_two_channel_overlap(analyzer, tmp_path):
    a, b = speech_like(10, seed=1), speech_like(10, seed=2, f0=220)
    res = analyzer.analyze(write(tmp_path / "stereo.wav", np.stack([a, b], axis=1)))
    assert res.details["audio"]["distinct_channels"] is True
    assert res.details["evidence"]["speaker_overlap_present"]["method"] == "two_channel_vad"
    assert res.prediction["speaker_overlap_present"] is True


def test_dual_mono_is_treated_as_single_channel(analyzer, tmp_path):
    a = speech_like(6)
    res = analyzer.analyze(write(tmp_path / "dual.wav", np.stack([a, a], axis=1)))
    assert res.details["audio"]["distinct_channels"] is False


@pytest.mark.parametrize(
    "ext,fmt,subtype",
    [
        (".ogg", "OGG", "VORBIS"),
        (".ogg", "OGG", "OPUS"),
        (".flac", "FLAC", None),
        (".mp3", "MP3", None),
    ],
)
def test_other_formats_and_rates(analyzer, tmp_path, ext, fmt, subtype):
    sr = 48000 if subtype == "OPUS" else 44100
    x = np.interp(np.arange(int(8 * sr)) * SR / sr, np.arange(8 * SR), speech_like(8)).astype(np.float32)
    try:
        path = write(tmp_path / f"clip{ext}", x, sr=sr, fmt=fmt, subtype=subtype)
    except (sf.LibsndfileError, ValueError, TypeError):
        pytest.skip(f"libsndfile cannot write {fmt}/{subtype}")
    res = analyzer.analyze(path)
    assert abs(res.details["audio"]["duration_s"] - 8) < 0.2


def test_decode_errors(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"RIFF....garbage")
    with pytest.raises(AudioDecodeError):
        load_audio(bad)
    with pytest.raises(AudioDecodeError, match="unsupported"):
        load_audio(tmp_path / "x.txt")
    with pytest.raises(AudioDecodeError, match="too short"):
        load_audio(write(tmp_path / "short.wav", np.zeros(100, dtype=np.float32)))


def _cf(**kw):
    base = dict(
        duration_s=60,
        distinct_channels=False,
        speech_ratio=0.6,
        speech_level_db=-20,
        quiet_floor_db=-70,
        background_level_db=-65,
        background_seconds=20,
        snr_db=45,
        bg_active_ratio=0,
        bg_voicing=0,
        bg_flatness=0.2,
        bg_transient_rate=0,
        bg_stationarity_db=5,
        longest_silence_s=2,
        longest_internal_silence_s=2,
        overlap_ratio=0,
        overlap_method="x",
        clip_fraction=0,
        dropout_rate=0,
        speech_rolloff_hz=900,
        pitch_median_hz=180,
        pitch_std_semitones=4,
        energy_std_db=12,
        voiced_onset_rate=5,
        loud_speech_ratio=0.2,
    )
    return CallFeatures(**(base | kw))


def test_loudness_alone_does_not_imply_frustration():
    loud = _cf(pitch_std_semitones=9, energy_std_db=25, voiced_onset_rate=9, loud_speech_ratio=0.6)
    tone, intensity = decide_tone(loud, None, None, Settings())
    assert tone.value == "neutral" and intensity.value == "high"


def test_tone_fusion_and_aggregation():
    s = Settings()
    upset = {"neutral": 0.1, "satisfied": 0.0, "frustrated": 0.2, "upset": 0.7, "distressed": 0.0}
    neutral = {"neutral": 0.9, "satisfied": 0.05, "frustrated": 0.05, "upset": 0.0, "distressed": 0.0}
    agg = aggregate_tone([neutral] * 3 + [upset])
    assert agg["upset"] > 0.3  # short, clear emotion is not drowned out by agent speech
    tone, _ = decide_tone(_cf(), upset, upset, s)
    assert tone.value == "upset"
    tone, _ = decide_tone(_cf(), neutral, None, s)
    assert tone.value == "neutral"


def test_scoring_metrics():
    labels = [LABEL | {"emotional_tone": t} for t in ("upset", "neutral", "satisfied")]
    preds = [LABEL | {"emotional_tone": t} for t in ("upset", "neutral", "neutral")]
    rep = score([(str(i), pred, label) for i, (pred, label) in enumerate(zip(preds, labels))])
    tone = rep["fields"]["emotional_tone"]
    assert tone["accuracy"] == pytest.approx(2 / 3)
    assert tone["confusion_matrix"]["satisfied"]["neutral"] == 1
    assert "frustrated" in tone["unsupported_classes"]
    assert tone["macro_f1"] == pytest.approx((1 + 2 / 3 + 0) / 3)


def test_noise_type_synonyms():
    noisy = LABEL | {"background_noise_present": True, "background_noise_severity": "low"}
    rep = score([("a", noisy | {"background_noise_type": "television"}, noisy | {"background_noise_type": "TV"})])
    assert rep["fields"]["background_noise_type"]["normalized_match"] == 1.0


def test_calibration_requires_enough_data_and_is_monotonic():
    with pytest.raises(ValueError, match="at least"):
        fit_isotonic([0.5] * 3, [True] * 3)
    rng = np.random.default_rng(0)
    raw = rng.uniform(0, 1, 200).tolist()
    correct = (rng.uniform(0, 1, 200) < np.asarray(raw) * 0.8).tolist()
    cal = Calibrator(fit_isotonic(raw, correct))
    vals = [cal(x) for x in np.linspace(0, 1, 11)]
    assert all(a <= b for a, b in zip(vals, vals[1:]))


def test_cost_formula():
    # RTF 0.1 at $1.80/h and full utilization is exactly the $0.003 ceiling.
    assert cost_per_audio_minute(0.1, 1.80) == pytest.approx(0.003)
    assert cost_per_audio_minute(0.1, 1.80, utilization=0.5) == pytest.approx(0.006)
