# Model Setup and Implementation Guide

Status: **adapters written, not yet executed.** No model weights have been downloaded
and no ML package is installed in this repository's environment. The service runs the
deterministic acoustic baseline until model directories are configured.

This file is written so a person or coding agent can follow it step by step later.
Work through the checklist at the end in order and record results in
[reports/validation.md](../reports/validation.md) and [reports/cost_latency.md](../reports/cost_latency.md).

## 1. Why models are needed

The acoustic baseline cannot do the following (measured on the supplied calls, see reports):

| Gap | Effect today | Model that closes it |
| --- | --- | --- |
| Valence (positive vs negative) | Tone is always `neutral` | Speech emotion recognition (SER) + transcript emotion |
| Noise under speech (e.g. TV) | `call_002` TV noise missed | AudioSet event tagger on all windows |
| Overlap on single-channel audio | Weak heuristic, capped confidence 0.6 | pyannote overlapped-speech detection |
| Noise type wording | Only `static` / `hiss` / `background voices` | AudioSet labels mapped to concise types |

## 2. Candidate models

All run locally on CPU. Verify each model card's license and intended use before use;
licenses are not asserted here. Prefer the first option in each row, then compare.

| Role | Env var | Local dir | Hugging Face repo (first choice / alternative) | Loader in code |
| --- | --- | --- | --- | --- |
| Audio events | `AUDIOEVAL_EVENT_MODEL` | `models/ast` | `MIT/ast-finetuned-audioset-10-10-0.4593` | [audio_events.py](../audioeval/models/audio_events.py) |
| Speech emotion | `AUDIOEVAL_EMOTION_MODEL` | `models/ser` | `superb/wav2vec2-base-superb-er` / `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition` | [emotion_audio.py](../audioeval/models/emotion_audio.py) |
| Transcription | `AUDIOEVAL_ASR_MODEL` | `models/whisper` | `Systran/faster-whisper-small` / `Systran/faster-whisper-base` | [asr_text.py](../audioeval/models/asr_text.py) |
| Transcript emotion | `AUDIOEVAL_TEXT_MODEL` | `models/text` | `SamLowe/roberta-base-go_emotions` / `cardiffnlp/twitter-roberta-base-sentiment-latest` | [asr_text.py](../audioeval/models/asr_text.py) |
| Overlap (optional) | `AUDIOEVAL_OVERLAP_MODEL` | `models/overlap` | `pyannote/overlapped-speech-detection` (gated, needs `pyannote/segmentation`) | [overlap.py](../audioeval/models/overlap.py) |

Label mappings to the required schema live in [labels.py](../audioeval/models/labels.py)
(`SER_LABELS`, `TEXT_LABELS`, `NOISE_LABELS`). The adapters refuse to load a model whose
labels have no mapping, so an unexpected model fails loudly instead of silently.

Language: Whisper detects language automatically, but the text emotion models above are
English. If calls are not English, choose a multilingual text model or disable the text
path and rely on SER.

## 3. Download (on a machine with internet access)

```powershell
python -m pip install -U "huggingface_hub[cli]"
# Use `hf download` (newer CLI) or `huggingface-cli download` (older CLI).
hf download MIT/ast-finetuned-audioset-10-10-0.4593 --local-dir models/ast
hf download superb/wav2vec2-base-superb-er --local-dir models/ser
hf download Systran/faster-whisper-small --local-dir models/whisper
hf download SamLowe/roberta-base-go_emotions --local-dir models/text
```

Overlap model (optional, gated): accept the conditions for `pyannote/segmentation` and
`pyannote/overlapped-speech-detection` on Hugging Face, then download both with a token.
Edit `models/overlap/config.yaml` so the `segmentation` entry points at the local
segmentation checkpoint path instead of a Hub id; the service runs offline.

Copy the `models/` folder to the target machine. Do not commit it (it is git-ignored).
Model downloads are the only network step; call audio is never sent anywhere.

## 4. Install the ML packages

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
# Optional: .\.venv\Scripts\python.exe -m pip install "pyannote.audio>=3.1"
```

After a working install, pin exact versions in `requirements-ml.txt` (`pip freeze`).
Docker: `docker build --build-arg INSTALL_ML=true -t audioeval:ml .` and mount `models/`
read-only at `/models`.

## 5. Configure and verify

```powershell
$env:AUDIOEVAL_EVENT_MODEL = "models/ast"
$env:AUDIOEVAL_EMOTION_MODEL = "models/ser"
$env:AUDIOEVAL_ASR_MODEL = "models/whisper"
$env:AUDIOEVAL_TEXT_MODEL = "models/text"
.\.venv\Scripts\python.exe -m audioeval check-models      # every configured model must say "loaded"
.\.venv\Scripts\python.exe -m pytest -q                   # baseline tests must still pass
.\.venv\Scripts\python.exe -m audioeval benchmark "<supplied zip>" --out output/models --hourly-price <USD/h>
```

`check-models` reports `missing package`, `directory not found`, or `failed to load: ...`
per model. The service keeps working with whatever subset loads.

## 6. Experiments to run (record every row)

Run each configuration on the supplied ZIP and on any additional approved labeled data.
The three supplied calls are fixtures, not validation (see [reports/validation.md](../reports/validation.md)).

| ID | Configuration | Purpose |
| --- | --- | --- |
| E0 | Acoustic baseline (done) | Reference |
| E1 | + event model | TV/music/chatter under speech; noise type wording |
| E2 | + SER | Audio-only valence |
| E3 | + ASR + text | Transcript valence; compare with E2 |
| E4 | E1 + E2 + E3 | Full fusion; tune `AUDIOEVAL_TEXT_WEIGHT` on validation data only |
| E5 | E4 + overlap model | Overlap on single-channel audio |
| E6 | E4 with `faster-whisper-base` | Cost/latency vs accuracy trade-off |

For each: per-field accuracy, tone macro F1, confusion matrix (`results.json` → `score`),
real-time factor, and cost from `benchmark.json`. Reject any configuration whose cost at
the expected utilization exceeds $0.003 per audio minute.

## 7. Things likely to need fixing on first run

The adapter code follows the documented `transformers` and `faster-whisper` APIs but has
not been executed. Check these first:

- `AudioEventModel`: AST expects 16 kHz and about 10 s windows; confirm the extractor
  accepts a list of arrays. Tune `AUDIOEVAL_NOISE_EVENT_THRESHOLD` (default 0.15) and
  `AUDIOEVAL_NOISE_EVENT_COVERAGE` (default 0.10) on validation data. Speech-related AudioSet
  labels are deliberately not mapped, so the customer's own voice is not counted as noise.
- `AudioEmotionModel`: confirm `id2label` names match keys in `SER_LABELS` (lower-cased).
- `WhisperASR`: `local_files_only=True` requires a recent faster-whisper; if unsupported,
  pass the local directory path only.
- `TextEmotionModel`: GoEmotions is multi-label; the pipeline returns all scores
  (`top_k=None`) and `map_distribution` renormalizes them.
- `OverlapModel`: pyannote's `Pipeline.from_pretrained` with a local `config.yaml`;
  confirm it returns an `Annotation` with `get_timeline()`.
- Thread safety: `JobManager` shares one analyzer across workers. If a library is not
  thread-safe, set `AUDIOEVAL_WORKERS=1` or add a lock around model calls.

## 8. Customer identification

The supplied calls are dual-mono (identical channels), so customer and agent cannot be
separated by channel. Options in order of effort:

1. If production recordings are stereo with fixed roles, set `AUDIOEVAL_CUSTOMER_CHANNEL=0` or `1`.
2. Diarize (pyannote speaker diarization) and pick the customer by turn order or by an
   agent-voice model. Not implemented; add as a new adapter if needed.
3. Current default: analyze the mix and weight the most emotional 25% of windows
   ([rules.py](../audioeval/rules.py) `aggregate_tone`), because agents are usually neutral.

## 9. Implementation checklist

- [ ] Download models (section 3) and copy `models/` to the target machine.
- [ ] Install ML packages (section 4); pin versions.
- [ ] `check-models` shows every configured model as `loaded`.
- [ ] `pytest` passes.
- [ ] Run E1-E6 and fill in the tables in `reports/validation.md` and `reports/cost_latency.md`.
- [ ] Choose the final configuration under the cost ceiling; set its env vars in deployment.
- [ ] If at least 30 independent labeled clips are available: `python -m audioeval calibrate --results <results.json> --labels <labels.csv>`,
      check calibration on a separate held-out set, then set `AUDIOEVAL_CALIBRATION_PATH`.
- [ ] Update the technical memo with the measured comparison and final choice.
- [ ] Rebuild the Docker image with `INSTALL_ML=true` and confirm `/readyz` lists the models.
