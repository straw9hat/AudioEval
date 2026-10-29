## Deliverable details

### 1. Hosted dashboard and login

The application provides an authenticated dashboard and job APIs. Authentication uses hashed passwords, login rate limiting, signed session cookies, and CSRF protection. **The service is not hosted yet**, so a working AutoAce URL and login credentials still need to be provisioned and delivered privately. Do not put credentials in the repository.

Before evaluation, build and deploy the container, configure HTTPS and persistent storage, set deployment secrets, and verify login and availability for the evaluation period. Deployment requirements and an example host setup are in the `README deployment section`. Authentication is implemented in `auth.py` and the dashboard/API in `web.py`.

### 2. Runnable implementation

The repository includes Windows setup instructions, a CLI for analysis and evaluation, environment-based configuration, and container deployment guidance. The implementation uses local inference; the technical memo reports that call audio is not sent to an external inference API.

The Docker image is provided but has not been built or deployed. A fresh setup and deployment smoke test remain necessary. See `README.md`, `MODEL_SETUP.md`, and `config.py`.

### 3. Batch upload workflow

The dashboard accepts folder and ZIP uploads, including multiple ZIPs in one batch. The workflow validates the manifest and file mapping, reports warnings and errors, processes valid files independently, and makes predictions, errors, and full JSON results downloadable. A failed file does not prevent other valid files from being analyzed.

The main workflow is implemented in `batch.py`, `jobs.py`, `web.py`, and `export.py`. Batch, web, and schema behavior has test coverage in `test_batch.py`, `test_web.py`, and `test_schema.py`.

### 4. Predictions for supplied calls

Each successful clip produces exactly nine fields: emotional tone, emotional intensity, background-noise presence, noise type, noise severity, audio quality, speaker overlap, long silence, and confidence. The allowed values and validation rules are defined in `schema.py`.

The baseline predictions are available in `supplied_calls.csv` and summarized in `validation.md`:

| File | Tone | Intensity | Noise | Noise type | Severity | Quality | Overlap | Long silence | Confidence |
|---|---|---|---|---|---|---|---|---|---:|
| call_001.ogg | neutral | medium | false | — | none | clear | false | false | 0.635 |
| call_002.ogg | neutral | medium | false | — | none | clear | true | false | 0.606 |
| call_003.ogg | neutral | medium | true | static | medium | clear | false | false | 0.617 |

Predictions are generated independently of labels; scoring occurs after inference.

### 5. Technical memo and selected architecture

The technical memo compares a deterministic acoustic baseline (E0), optional AudioSet event tagging (E1), speech-emotion recognition (E2), Whisper-small plus text emotion (E3), full fusion (E4), and full fusion with Whisper-base (E6). E5, a gated overlap model, was not run.

The selected default is E0: interpretable acoustic features and rules, with optional local models retained as experiments rather than enabled by default. On the three supplied calls, model additions did not improve full-fusion tone accuracy; the sample is too small to select or calibrate a model reliably.

The architecture covers authenticated upload, batch validation, background jobs, audio decoding, acoustic analysis and optional local models, schema validation, scoring, and result downloads. See `TECHNICAL_MEMO.md` and `MODEL_SETUP.md`.

### 6. Validation

The `validation report` describes three supplied calls and synthetic tests. For baseline tone, accuracy is **1/3 (0.333)** and macro F1 is **0.167**. The report includes per-class results and a five-class tone confusion matrix; only neutral, satisfied, and upset occur in the labels, one example each. The baseline predicts neutral for all three calls.

These results are descriptive fixture agreement, **not evidence of generalization**. Some thresholds were set after examining these same calls, and several classes and conditions have no labeled examples. Independent, representative labeled data and a grouped holdout are needed before making accuracy or confidence-calibration claims.

### 7–8. Cost and latency

The `cost and latency report` uses local CPU measurements on an AMD Ryzen 7 5800XT and an **assumed**, not quoted, compute price of **$0.05 per instance-hour**. The baseline E0 measured approximately **0.0070 RTF** (processing time divided by audio duration); E6 measured **0.2527 RTF**.

At 10% utilization, the report estimates **$0.0000583 per audio minute for E0** and **$0.0021058 for E6**. The estimates exclude idle hosting, storage, egress, monitoring, and other platform charges. The actual deployment’s cost and latency remain unverified; they depend on the selected host, workload, utilization, and configuration.

### 9. Limitations and next steps

Known limitations include weak tone results on the tiny fixture set, noise under continuous speech, unreliable single-channel overlap detection, lack of customer/agent separation for mono or dual-mono audio, and uncalibrated confidence. Language coverage and audio-quality conditions also require broader evaluation.

Recommended next steps:

1. Build and test the Docker image, then deploy over HTTPS with persistent job storage.
2. Provide an evaluator account through an approved private channel and verify the hosted workflow.
3. Obtain approved, independently labeled calls covering all required classes and relevant noise conditions; use a grouped holdout for evaluation.
4. Measure latency and cost on the actual deployment at expected workload and utilization.
5. Reassess model selection and confidence calibration using independent data.
6. Confirm data-retention, model-license, and recording/sharing approvals before production use.

Detailed acceptance criteria and remaining tasks are tracked in `PLAN.md`; the project runbook is in `README.md`.