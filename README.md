# AudioEval

Voice tone and background noise analysis for call audio (AutoAce AI technical trial).
Upload a batch of calls in the browser, get the required nine-field JSON per file, and
download the results as CSV or JSON.

> **Confidential.** The trial brief and call audio are confidential. Keep this repository
> private. Audio, ZIPs, PDFs, `labels.csv`, models, and `.env` files are git-ignored.

| Document | Contents |
| --- | --- |
| [PLAN.md](PLAN.md) | Requirements, acceptance criteria, delivery plan |
| [docs/TECHNICAL_MEMO.md](docs/TECHNICAL_MEMO.md) | Approaches, architecture, ambiguity handling, limitations, production path |
| [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md) | Pinned local model setup and experiment commands |
| [reports/validation.md](reports/validation.md) | Predictions for supplied calls, metrics, confusion matrix |
| [reports/cost_latency.md](reports/cost_latency.md) | Measured runtime and cost per audio minute |
| [predictions/supplied_calls.csv](predictions/supplied_calls.csv) | Baseline predictions for all supplied calls |

## Status

- Working now: acoustic baseline, CLI, authenticated dashboard, batch validation, background
  processing, downloads, scoring, optional local models, Docker image definition, 54 tests.
- Model experiments E1-E4 and E6 ran locally; these are fixture comparisons on only three
  calls, not independent validation. The default remains the inexpensive acoustic baseline.
- Not done yet: Docker image build, hosted deployment, independent validation data, gated E5,
  and confidence calibration. See [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md).

## Output schema

Each successful file produces exactly:

```json
{"emotional_tone": "neutral", "emotional_intensity": "medium", "background_noise_present": false,
 "background_noise_type": "", "background_noise_severity": "none", "audio_quality": "clear",
 "speaker_overlap_present": false, "long_silence_present": false, "confidence": 0.63}
```

Enums: tone `neutral|satisfied|frustrated|upset|distressed`; intensity `low|medium|high`;
severity `none|low|medium|high`; quality `clear|slightly_impaired|severely_impaired`.

## Setup (Windows PowerShell)

```powershell
py -3.14 -m venv .venv            # Python 3.11+ should work; 3.14.2 was tested
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python`.
WAV, MP3, OGG (Vorbis/Opus), and FLAC decode without extra tools. Install `ffmpeg` to also
accept M4A, AAC, WMA, WebM, and AMR.

## Command line

```powershell
# Analyze a batch folder or ZIP (wrapper folders and OS junk files are handled)
.\.venv\Scripts\python.exe -m audioeval analyze "path\to\batch.zip" --out output

# Score predictions against a labels CSV
.\.venv\Scripts\python.exe -m audioeval evaluate --predictions output\predictions.csv --labels path\to\labels.csv

# Measure runtime and estimate cost (state where the hourly price comes from)
.\.venv\Scripts\python.exe -m audioeval benchmark "path\to\batch.zip" --out output --hourly-price 0.10
.\.venv\Scripts\python.exe -m audioeval cost --rtf 0.02 --hourly-price 0.10

# Show which optional models load
.\.venv\Scripts\python.exe -m audioeval check-models
```

Outputs: `predictions.csv` (`name,result_json`, successful files only), `errors.csv`
(failed files and warnings), and `results.json` (everything, including per-field
confidence, evidence, timings, and scores when labels are present).

## Web dashboard

### Batch format

A folder or ZIP with audio files at the root and one CSV manifest (any name):

```
evaluation_batch/
  call_001.wav
  call_002.mp3
  labels.csv        # columns: name, result_json (result_json optional or empty)
```

One outer folder is unwrapped automatically. You can also upload several ZIPs as one batch.
Validation reports missing files, files not in the manifest (still processed, with a
warning), duplicate rows, unsupported or corrupt files, invalid label JSON, and multiple
CSVs. One bad file never stops the batch.

### Run locally

```powershell
.\.venv\Scripts\python.exe -m audioeval hash-password      # prompts; prints a hash
$env:AUDIOEVAL_USERS = 'evaluator:<hash from above>'
$env:AUDIOEVAL_SECRET_KEY = '<long random string>'
$env:AUDIOEVAL_COOKIE_SECURE = 'false'                      # plain-HTTP localhost only
.\.venv\Scripts\python.exe -m audioeval serve --port 8000
```

Open http://127.0.0.1:8000, sign in, choose a folder or ZIP, and select **Upload and analyze**.
The dashboard has an overview with prediction and confidence charts plus label agreement, and
a separate file-results table with per-file status, duration, and estimated inference cost.
Cost estimates use editable hourly-price and utilization assumptions for measured processing
time only; they are not Azure bills and exclude idle hosting and other platform charges.

### Short review walkthrough

1. Sign in with the dedicated evaluator account; do not show or record the password.
2. Upload an approved batch containing audio files and its CSV manifest.
3. Show validation, per-file progress, and the difference between successful predictions
   and file errors.
4. Open a result and point out the nine-field schema, evidence, and confidence caveat.
   Label comparisons are scoring output; labels are not inference input.
5. Download the predictions CSV and errors report. Explain that model comparisons on the
   three supplied calls are descriptive only and that the acoustic baseline remains default.
6. If the hosted app is unavailable, use the local CLI command and the saved
   [validation report](reports/validation.md) and [baseline export](predictions/supplied_calls.csv).

Do not record supplied confidential calls, credentials, or evaluator data unless the
recipient, storage, and retention are approved. A dashboard fallback recording still
needs to be made after an approved deployment, preferably with approved synthetic audio.

## Deployment

The app is one container. It has not been deployed or built with Docker yet. Any container
host with HTTPS works.

```powershell
docker build -t audioeval .                                  # baseline image
docker build --build-arg INSTALL_ML=true -t audioeval:ml .   # with model packages
docker run -p 8000:8000 --env-file .env -v audioeval-data:/data audioeval
```

Requirements for the host:

- **HTTPS** terminated by the platform; keep `AUDIOEVAL_COOKIE_SECURE=true`.
- **Secrets** `AUDIOEVAL_USERS` and `AUDIOEVAL_SECRET_KEY` from the platform's secret store.
  Keep the secret key stable, or sessions end on every restart.
- **Exactly one replica.** Job state lives on the instance's disk; mount a persistent volume
  at `/data`. More replicas need shared storage and a shared queue (see memo).
- **Always on during evaluation** (minimum one instance) so the first request does not hit a
  cold start or model loading delay. Probes: `/healthz` (liveness), `/readyz` (readiness).
- **Upload size and timeouts**: check the platform's request-body limit and ingress timeout
  against the largest expected batch (`AUDIOEVAL_MAX_UPLOAD_MB`, default 2048). Analysis
  runs in the background, so only the upload itself must fit within the timeout.
- **Proxy headers**: the image sets `AUDIOEVAL_TRUST_PROXY=true`, so login rate limiting uses
  the rightmost `X-Forwarded-For` hop (the one the platform proxy appends; earlier hops are
  client-controlled). Do not expose the container directly without a proxy.
- **Models**: mount `models/` read-only and set the `AUDIOEVAL_*_MODEL` paths.

Example for Azure Container Apps (not run; review names, region, and cost first):

```powershell
az group create -n rg-audioeval -l <region>
az acr create -g rg-audioeval -n <acrname> --sku Basic
az acr build -r <acrname> -t audioeval:1 .
az containerapp env create -g rg-audioeval -n audioeval-env -l <region>
az containerapp create -g rg-audioeval -n audioeval --environment audioeval-env `
  --image <acrname>.azurecr.io/audioeval:1 --registry-server <acrname>.azurecr.io `
  --ingress external --target-port 8000 --min-replicas 1 --max-replicas 1 --cpu 2 --memory 4Gi `
  --secrets users='<user:hash>' secret-key='<random>' `
  --env-vars AUDIOEVAL_USERS=secretref:users AUDIOEVAL_SECRET_KEY=secretref:secret-key
```

Add an Azure Files (SMB) volume at `/data` for job persistence across restarts. The container
runs as uid 10001, so set the volume's mount options to
`uid=10001,gid=10001,dir_mode=0700,file_mode=0600`, or the app cannot write to the share.
Container Apps ingress times out requests after 240 seconds, which bounds upload size.

## Configuration

All settings are `AUDIOEVAL_*` environment variables; see [.env.example](.env.example) and
[audioeval/config.py](audioeval/config.py). Main ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOEVAL_USERS` | (none) | `user:hash` pairs; nobody can log in if empty |
| `AUDIOEVAL_SECRET_KEY` | random | Session signing key |
| `AUDIOEVAL_LONG_SILENCE_S` | 10 | Silence length that counts as long |
| `AUDIOEVAL_CUSTOMER_CHANNEL` | auto | `0`/`1` if stereo channels carry customer/agent separately |
| `AUDIOEVAL_WORKERS` | 2 | Files processed in parallel |
| `AUDIOEVAL_RETENTION_HOURS` | 72 | Jobs and results deleted after this |
| `AUDIOEVAL_KEEP_AUDIO` | false | Keep raw audio after a job finishes |
| `AUDIOEVAL_TRUST_PROXY` | false (true in image) | Take client IP from the rightmost `X-Forwarded-For` hop |
| `AUDIOEVAL_*_MODEL` | (none) | Local model directories |

## Security and privacy

- Login with PBKDF2-hashed passwords, rate limiting (5 failures per 15 minutes per user and
  per IP), signed `SameSite=Strict` session cookies, CSRF tokens on all changes.
- Users see only their own jobs. Strict Content-Security-Policy; the UI never renders
  uploaded text as HTML.
- ZIP handling rejects path traversal, symlinks, encrypted entries, and oversized or
  suspicious archives; sizes are counted from real bytes, not headers.
- Raw audio is deleted when a job finishes; jobs expire after the retention period.
- No external API calls; models load offline from local directories.

## Project layout

```
audioeval/
  audio.py         decode + resample (libsndfile, ffmpeg fallback)
  features.py      frame and call-level acoustic features
  rules.py         decisions, fusion, confidence
  pipeline.py      per-file analysis
  models/          optional pretrained-model adapters and label mappings
  batch.py         safe upload staging, manifest parsing, matching
  jobs.py          background jobs, persistence, retention
  scoring.py       accuracy, macro F1, confusion matrices
  calibration.py   isotonic confidence calibration
  web.py, auth.py  dashboard, API, login
  cli.py           command line
tests/             synthetic-audio tests (no confidential data)
```

## License

Apache 2.0 (see [LICENSE](LICENSE)). Confirm with AutoAce before publishing.