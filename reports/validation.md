# Validation Report

## Data and method

- Three supplied production calls (Ogg Opus, dual-mono, 48 kHz; 30.9 s, 35.0 s, 171.9 s).
- Configuration E0: deterministic acoustic baseline, no learned models (`method: acoustic_baseline`).
- Command: `python -m audioeval analyze "<supplied zip>" --out <dir>`.
- Labels were read only by the scoring step after prediction; inference never sees them.

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

`pytest` (53 tests) checks behavior the supplied calls cannot: long silence, clipping, low
volume (quality issue, not noise), impulsive noise, two-channel overlap, dual-mono handling,
WAV/MP3/OGG Vorbis/OGG Opus/FLAC at 16/44.1/48 kHz, corrupt files, and loudness without
valence evidence staying `neutral`.

## Confidence

Confidence is the geometric mean of per-field heuristic confidences, bounded to [0.05, 0.95].
It is **not calibrated**: calibration needs at least 30 independent labeled clips
(`python -m audioeval calibrate`). The correctness event used for calibration is: tone,
noise presence, and audio quality all correct.

## Model experiments (to fill in, see docs/MODEL_SETUP.md section 6)

| ID | Tone acc | Tone macro F1 | Noise present acc | Overlap acc | RTF | Cost/audio-min | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0 | 0.333 | 0.167 | 0.667 | 0.667 | 0.0046 | see cost report | baseline |
| E1-E6 | not run | | | | | | |
