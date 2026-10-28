# Model Setup and Implementation Guide

Status: **pinned E1-E4/E6 models downloaded, loaded, and run locally.** The model
directories are git-ignored; a fresh machine must download them again. The service
continues to use the acoustic baseline unless model paths are configured.

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

All selected candidates run locally on CPU. The model cards at the pinned revisions
declare the licenses listed below; review the complete license and intended-use terms
before deployment. In particular, model training datasets and their limitations are
not covered by the weight license.

| Role | Env var | Local dir | Hugging Face repo (first choice / alternative) | Loader in code |
| --- | --- | --- | --- | --- |
| Audio events | `AUDIOEVAL_EVENT_MODEL` | `models/ast` | [MIT/ast-finetuned-audioset-10-10-0.4593](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593/tree/f826b80d28226b62986cc218e5cec390b1096902) (BSD-3-Clause) | [audio_events.py](../audioeval/models/audio_events.py) |
| Speech emotion | `AUDIOEVAL_EMOTION_MODEL` | `models/ser` | [superb/wav2vec2-base-superb-er](https://huggingface.co/superb/wav2vec2-base-superb-er/tree/441a7599c3b22107314dcbd9166621c5c83f2cc5) (Apache-2.0) | [emotion_audio.py](../audioeval/models/emotion_audio.py) |
| Transcription | `AUDIOEVAL_ASR_MODEL` | `models/whisper` | [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120) (MIT); base is the E6 comparison | [asr_text.py](../audioeval/models/asr_text.py) |
| Transcript emotion | `AUDIOEVAL_TEXT_MODEL` | `models/text` | [SamLowe/roberta-base-go_emotions](https://huggingface.co/SamLowe/roberta-base-go_emotions/tree/d75048347613a25d77de8cf6412eaae9fa7b26be) (MIT) | [asr_text.py](../audioeval/models/asr_text.py) |
| Overlap (optional) | `AUDIOEVAL_OVERLAP_MODEL` | `models/overlap` | `pyannote/overlapped-speech-detection` (gated, needs `pyannote/segmentation`) | [overlap.py](../audioeval/models/overlap.py) |

Label mappings to the required schema live in [labels.py](../audioeval/models/labels.py)
(`SER_LABELS`, `TEXT_LABELS`, `NOISE_LABELS`). The adapters refuse to load a model whose
labels have no mapping, so an unexpected model fails loudly instead of silently.

Language: Whisper detects language automatically, but the text emotion models above are
English. If calls are not English, choose a multilingual text model or disable the text
path and rely on SER.

## 3. Download (on a machine with internet access)

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='MIT/ast-finetuned-audioset-10-10-0.4593', revision='f826b80d28226b62986cc218e5cec390b1096902', local_dir='models/ast', allow_patterns=['config.json','preprocessor_config.json','model.safetensors'])"
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='superb/wav2vec2-base-superb-er', revision='441a7599c3b22107314dcbd9166621c5c83f2cc5', local_dir='models/ser', allow_patterns=['config.json','preprocessor_config.json','pytorch_model.bin'])"
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-small', revision='536b0662742c02347bc0e980a01041f333bce120', local_dir='models/whisper', allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'])"
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='SamLowe/roberta-base-go_emotions', revision='d75048347613a25d77de8cf6412eaae9fa7b26be', local_dir='models/text', allow_patterns=['config.json','merges.txt','model.safetensors','special_tokens_map.json','tokenizer.json','tokenizer_config.json','vocab.json'])"
```

For the E6 size comparison, download the pinned base model:

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-base', revision='ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66', local_dir='models/whisper-base', allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'])"
$env:AUDIOEVAL_ASR_MODEL = "models/whisper-base"
```

These are immutable Hugging Face commit revisions. Check the upstream model cards
again before deployment; a declared weight license does not establish that the model
is suitable for every jurisdiction, purpose, or dataset.

Overlap model (optional, gated): accept the conditions for `pyannote/segmentation` and
`pyannote/overlapped-speech-detection` on Hugging Face, then download both with a token.
Edit `models/overlap/config.yaml` so the `segmentation` entry points at the local
segmentation checkpoint path instead of a Hub id; the service runs offline.

Copy the `models/` folder to the target machine. Do not commit it (it is git-ignored).
Model downloads are the only network step; call audio is never sent anywhere.

## 4. Install the ML packages

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.11.0+cpu torchaudio==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
# Optional: .\.venv\Scripts\python.exe -m pip install "pyannote.audio>=3.1"
```

The tested CPU stack pins matching PyTorch/torchaudio versions; Transformers and
faster-whisper are pinned in `requirements-ml.txt`. The pinned E1-E4/E6 model files
loaded successfully and were exercised in the reported experiments.
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

## 6. Experiment status and reproduction

The measured results below use the three supplied calls as fixtures, not validation.
Run on additional approved labeled data before selecting a model
(see [reports/validation.md](../reports/validation.md)).

| ID | Configuration | Purpose | Status |
| --- | --- | --- | --- |
| E0 | Acoustic baseline | Reference | Run |
| E1 | + event model | TV/music/chatter under speech; noise type wording | Run |
| E2 | + SER | Audio-only valence | Run |
| E3 | + ASR + text | Transcript valence; compare with E2 | Run |
| E4 | E1 + E2 + E3 | Full fusion | Run; no independent tuning |
| E5 | E4 + overlap model | Overlap on single-channel audio | Not run; gated access required |
| E6 | E4 with `faster-whisper-base` | Cost/latency vs accuracy trade-off | Run |

For each: per-field accuracy, tone macro F1, confusion matrix (`results.json` → `score`),
real-time factor, and cost from `benchmark.json`. Reject any configuration whose cost at
the expected utilization exceeds $0.003 per audio minute.

Reproduce the measured CPU experiments with the same local batch and assumed $0.05/hour
price. Use a fresh PowerShell session or remove the listed model variables between runs:

```powershell
$batch = 'C:\path\to\Voice Analyzer Assessment'
$py = '.\.venv\Scripts\python.exe'

# E0
& $py -m audioeval benchmark $batch --out output\E0 --hourly-price 0.05

# E1
$env:AUDIOEVAL_EVENT_MODEL = 'models\ast'
& $py -m audioeval benchmark $batch --out output\E1 --hourly-price 0.05
Remove-Item Env:AUDIOEVAL_EVENT_MODEL

# E2
$env:AUDIOEVAL_EMOTION_MODEL = 'models\ser'
& $py -m audioeval benchmark $batch --out output\E2 --hourly-price 0.05
Remove-Item Env:AUDIOEVAL_EMOTION_MODEL

# E3
$env:AUDIOEVAL_ASR_MODEL = 'models\whisper'
$env:AUDIOEVAL_TEXT_MODEL = 'models\text'
& $py -m audioeval benchmark $batch --out output\E3 --hourly-price 0.05
Remove-Item Env:AUDIOEVAL_ASR_MODEL,Env:AUDIOEVAL_TEXT_MODEL

# E4
$env:AUDIOEVAL_EVENT_MODEL = 'models\ast'
$env:AUDIOEVAL_EMOTION_MODEL = 'models\ser'
$env:AUDIOEVAL_ASR_MODEL = 'models\whisper'
$env:AUDIOEVAL_TEXT_MODEL = 'models\text'
& $py -m audioeval benchmark $batch --out output\E4 --hourly-price 0.05
Remove-Item Env:AUDIOEVAL_EVENT_MODEL,Env:AUDIOEVAL_EMOTION_MODEL,Env:AUDIOEVAL_ASR_MODEL,Env:AUDIOEVAL_TEXT_MODEL

# E6: same as E4, with the smaller Whisper-base model
$env:AUDIOEVAL_EVENT_MODEL = 'models\ast'
$env:AUDIOEVAL_EMOTION_MODEL = 'models\ser'
$env:AUDIOEVAL_ASR_MODEL = 'models\whisper-base'
$env:AUDIOEVAL_TEXT_MODEL = 'models\text'
& $py -m audioeval benchmark $batch --out output\E6 --hourly-price 0.05
Remove-Item Env:AUDIOEVAL_EVENT_MODEL,Env:AUDIOEVAL_EMOTION_MODEL,Env:AUDIOEVAL_ASR_MODEL,Env:AUDIOEVAL_TEXT_MODEL
```

## 7. Verified behavior and remaining checks

The pinned AST, SER, Whisper-small/base, and GoEmotions adapters loaded and completed
inference on the three supplied calls. This verifies those model files and current
package versions only; it does not validate generalization, concurrency, or other model
revisions. The gated overlap adapter remains untested.

- `AudioEventModel`: AST inference on 16 kHz, about 10 s windows succeeded. Tune
  `AUDIOEVAL_NOISE_EVENT_THRESHOLD` (default 0.15) and
  `AUDIOEVAL_NOISE_EVENT_COVERAGE` (default 0.10) only on independent validation data.
  Speech-related AudioSet labels are deliberately not mapped.
- `AudioEmotionModel`: the selected model's `id2label` values mapped through `SER_LABELS`
  and produced predictions.
- `WhisperASR`: `local_files_only=True` worked with faster-whisper 1.2.1 for both local
  model sizes; transcription quality still requires independent review.
- `TextEmotionModel`: GoEmotions inference ran; its addition did not improve aggregate
  tone agreement on these three calls.
- `OverlapModel`: not tested; verify the gated model and local `config.yaml` output before
  enabling it.
- Thread safety: model inference was benchmarked sequentially, not under concurrent job
  load. Keep `AUDIOEVAL_WORKERS=1` until concurrency safety and resource use are measured.

## 8. Customer identification

The supplied calls are dual-mono (identical channels), so customer and agent cannot be
separated by channel. Options in order of effort:

1. If production recordings are stereo with fixed roles, set `AUDIOEVAL_CUSTOMER_CHANNEL=0` or `1`.
2. Diarize (pyannote speaker diarization) and pick the customer by turn order or by an
   agent-voice model. Not implemented; add as a new adapter if needed.
3. Current default: analyze the mix and weight the most emotional 25% of windows
   ([rules.py](../audioeval/rules.py) `aggregate_tone`), because agents are usually neutral.

## 9. Implementation checklist

- [x] Download the pinned E1-E4/E6 models (section 3); weights remain git-ignored.
- [x] Install the pinned CPU ML packages (section 4).
- [x] `check-models` reports emotion, events, ASR, and text as `loaded`.
- [x] `pytest` passes with the optional ML packages installed.
- [x] Run E1-E4 and E6 and record descriptive results in the validation and cost reports.
- [ ] Run E5 only if gated model access and its license are approved.
- [ ] Select a production configuration after independent validation and actual host
      cost/utilization are known; do not infer generalization from three supplied calls.
- [ ] If at least 30 independent labeled clips are available: `python -m audioeval calibrate --results <results.json> --labels <labels.csv>`,
      check calibration on a separate held-out set, then set `AUDIOEVAL_CALIBRATION_PATH`.
- [x] Update the technical memo with the measured comparison and current conservative
      default.
- [ ] Build/test the Docker image with `INSTALL_ML=true` and confirm `/readyz` on a
      machine with Docker installed.
