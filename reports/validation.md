# Validation Report

## Data and method

- Three supplied production calls (Ogg Opus, dual-mono, 48 kHz; 30.9 s, 35.0 s, 171.9 s).
- Configuration E0: deterministic acoustic baseline, no learned models (`method: acoustic_baseline`).
- Command: `python -m audioeval analyze "<supplied zip>" --out <dir>`.
- Labels were read only by the scoring step after prediction; inference never sees them.
- Model experiments E1-E4 and E6 were run locally on CPU with the pinned revisions in
  [MODEL_SETUP.md](../docs/MODEL_SETUP.md); labels were again used only for scoring.
- The test machine was an AMD Ryzen 7 5800XT, Python 3.14.2, PyTorch 2.11.0+cpu,
  Transformers 5.21.0, and faster-whisper 1.2.1.

**These results are not a validation of generalization.** There are three clips, one per
observed tone, no examples of `frustrated` or `distressed`, and several thresholds were
set after looking at the feature values of these same calls. Treat the numbers as
descriptive fixture agreement. Leave-one-call-out validation is not meaningful for a
system with no fitted parameters and three examples.

## Predictions for the supplied calls (deliverable D04)

| File | Tone | Intensity | Noise | Noise type | Severity | Quality | Overlap | Long silence | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| call_001.ogg | neutral | medium | false | "" | none | clear | false | false | 0.635 |
| call_002.ogg | neutral | medium | false | "" | none | clear | true | false | 0.606 |
| call_003.ogg | neutral | medium | true | static | medium | clear | false | false | 0.617 |

Reproducible baseline export: [supplied_calls.csv](../predictions/supplied_calls.csv).

Labels for comparison: call_001 upset/high, no noise, no overlap; call_002 neutral/medium,
TV noise (medium), overlap; call_003 satisfied/medium, "sharp static" noise (medium), overlap.

## Field agreement (E0, n = 3)

| Field | Accuracy | Macro F1 | Notes |
| --- | --- | --- | --- |
| emotional_tone | 1/3 (0.333) | 0.167 | Baseline always predicts neutral (no valence evidence) |
| emotional_intensity | 2/3 | 0.400 | Missed `high` on call_001 |
| background_noise_present | 2/3 | 0.667 | Missed TV under speech on call_002 |
| background_noise_type | 2/3 normalized | - | "static" vs "sharp static" counts as a match after normalization; exact match 1/3 |
| background_noise_severity | 2/3 | 0.667 | |
| audio_quality | 3/3 | 1.000 | Only `clear` present in labels |
| speaker_overlap_present | 2/3 | 0.667 | Single-channel heuristic; missed call_003 |
| long_silence_present | 3/3 | 1.000 | No positive examples in labels |

Macro F1 averages over the union of true and predicted classes (as in scikit-learn).
Tone classes `frustrated` and `distressed` have no support and are reported, not averaged.

## Emotional tone confusion matrix (rows = true, columns = predicted)

| true \ pred | neutral | satisfied | frustrated | upset | distressed |
| --- | --- | --- | --- | --- | --- |
| neutral | 1 | 0 | 0 | 0 | 0 |
| satisfied | 1 | 0 | 0 | 0 | 0 |
| frustrated | 0 | 0 | 0 | 0 | 0 |
| upset | 1 | 0 | 0 | 0 | 0 |
| distressed | 0 | 0 | 0 | 0 | 0 |

Per-class tone results: neutral precision 0.33 / recall 1.0; satisfied and upset recall 0.
Full per-class metrics and confusion matrices for every field are in `results.json` → `score`.

## Error analysis

- **Tone**: prosody measures activation, not valence; the baseline deliberately does not map
  loudness to frustration (brief section 2). Needs SER and/or transcript emotion (E2-E4).
- **call_002 TV noise**: background energy in pauses is near the floor (active ratio 0.01);
  the TV sits under speech. Needs the event tagger on all windows (E1).
- **call_003 overlap**: multi-pitch ratio 0.066 vs threshold 0.10. The single-channel
  heuristic cannot separate overlap reliably; needs a dedicated model (E5) or stereo audio.
- **call_003 static**: detected from impulsive transients in pauses (14.8 per minute).
  Treated as background noise, not audio quality, following the supplied label convention.

## Synthetic tests

`pytest` (54 tests) checks behavior the supplied calls cannot: long silence, clipping, low
volume (quality issue, not noise), impulsive noise, two-channel overlap, dual-mono handling,
WAV/MP3/OGG Vorbis/OGG Opus/FLAC at 16/44.1/48 kHz, corrupt files, and loudness without
valence evidence staying `neutral`.

## Confidence

Confidence is the geometric mean of per-field heuristic confidences, bounded to [0.05, 0.95].
It is **not calibrated**: calibration needs at least 30 independent labeled clips
(`python -m audioeval calibrate`). The correctness event used for calibration is: tone,
noise presence, and audio quality all correct.

## Model experiments (descriptive fixtures only)

Macro F1 uses the union of true/predicted classes, with undefined class F1 counted as
zero. Only three of the five tone classes have support. Costs use an assumed (not quoted)
$0.05/instance-hour; see [cost and latency report](cost_latency.md). These figures are
not independent accuracy evidence.

| ID | Configuration | Tone acc | Tone macro F1 | Noise-present acc | Overlap acc | RTF | Cost/audio-min at 10% | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| E0 | Acoustic baseline | 0.333 | 0.167 | 0.667 | 0.667 | 0.0070 | $0.0000583 | Keep default; lowest cost |
| E1 | E0 + AudioSet events | 0.333 | 0.167 | 1.000 | 0.667 | 0.0763 | $0.0006358 | Finds call_002 noise; type/severity wrong |
| E2 | E0 + speech emotion | 0.333 | 0.222 | 0.667 | 0.667 | 0.0669 | $0.0005575 | Call_001 corrected, call_002 becomes false upset |
| E3 | E0 + Whisper-small + GoEmotions | 0.333 | 0.167 | 0.667 | 0.667 | 0.1592 | $0.0013267 | No aggregate fixture improvement |
| E4 | E1 + E2 + E3 | 0.333 | 0.167 | 1.000 | 0.667 | 0.3595 | $0.0029958 | No tone gain; cost has almost no 10% headroom |
| E6 | E4 with Whisper-base | 0.333 | 0.167 | 1.000 | 0.667 | 0.2527 | $0.0021058 | Faster than E4 here, but not validated for adoption |

E1, E4, and E6 called call_002 noise present but labeled its type `background chatter`
and severity `low`, versus the reference `TV` and `medium`. E2 predicted call_001 as
`upset` correctly, but changed the neutral call_002 to `upset`; call_003 stayed neutral
instead of satisfied. E3's transcript path did not change aggregate tone agreement.
E4/E6 full-fusion tone predictions and confusion matrix match E0; confidence changes
are not calibration evidence. Full-fusion E6 predictions are saved separately in
[supplied_calls_e6_full_fusion.csv](../predictions/supplied_calls_e6_full_fusion.csv).

Across E1-E6, intensity accuracy remained 2/3, noise-severity accuracy 2/3,
audio-quality accuracy 3/3, overlap accuracy 2/3, and long-silence accuracy 3/3.
Normalized noise-type agreement remained 2/3. E1, E3, E4, and E6 have the same tone
confusion matrix as E0; the E2 matrix and per-class results are:

| True \ Predicted | neutral | satisfied | frustrated | upset | distressed |
| --- | ---: | ---: | ---: | ---: | ---: |
| neutral | 0 | 0 | 0 | 1 | 0 |
| satisfied | 1 | 0 | 0 | 0 | 0 |
| frustrated | 0 | 0 | 0 | 0 | 0 |
| upset | 0 | 0 | 0 | 1 | 0 |
| distressed | 0 | 0 | 0 | 0 | 0 |

E2 per-class tone: neutral precision/recall 0/0; satisfied undefined precision and
recall 0; upset precision/recall 0.50/1.00 (F1 0.667); `frustrated` and `distressed`
have zero support. Undefined F1 values count as zero in the reported macro F1.

E5 (pyannote overlap detection) was not run: it is gated and requires approved account
access and additional local weights. No credentials were available or placed in the repo.
