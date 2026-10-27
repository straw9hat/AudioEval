# AudioEval Requirements and Delivery Plan

## 1. Purpose and Scope

Build a hosted, authenticated system that analyzes production call audio for
customer emotional tone, background noise, and technical audio issues. Evaluators
must be able to upload a batch, process unseen calls, inspect results, and download
structured predictions without using the command line.

Source of mandatory requirements: the supplied six-page
`voice_tone_background_noise_dashboard_trial.pdf` (AutoAce AI, confidential).
References below use its section numbers. The assessment materials were inspected
in the extracted Downloads folder; confidential audio has not been copied into
this repository or submitted to any analysis service.

**Confidentiality of the brief and this repository:** the brief is marked "AutoAce
AI - Confidential Technical Trial", and this plan restates its contents. The
repository has an Apache 2.0 license, which suggests it may be published. Keep the
repository private until AutoAce confirms otherwise. Add a `.gitignore` for audio,
manifests, uploaded batches, and secrets before adding any data or code.

This document is a plan, not an implementation or a claim of measured performance.
Items marked **Required** come from the brief. **Recommended** items are proposed
implementation choices or improvements, not additional assessment obligations.

### Implementation Status (2026-10-27)

| Deliverable | Status | Where |
| --- | --- | --- |
| D01 Hosted dashboard + login | Built and tested locally; **not deployed** | [audioeval/web.py](audioeval/web.py), README "Deployment" |
| D02 Runnable repo + instructions | Done (venv, CLI, Dockerfile not yet built) | [README.md](README.md) |
| D03 Batch upload workflow | Done: folder/ZIP/multi-ZIP, validation, progress, per-file errors, downloads | [audioeval/batch.py](audioeval/batch.py), [audioeval/jobs.py](audioeval/jobs.py) |
| D04 Predictions for supplied calls | Done for the acoustic baseline | [reports/validation.md](reports/validation.md) |
| D05 Technical memo | Draft; needs model results | [docs/TECHNICAL_MEMO.md](docs/TECHNICAL_MEMO.md) |
| D06 Validation + confusion matrix | Baseline done; model experiments pending | [reports/validation.md](reports/validation.md) |
| D07 Cost analysis | Baseline measured; model stack pending | [reports/cost_latency.md](reports/cost_latency.md) |
| D08 Latency analysis | Baseline measured (RTF 0.0046, desktop CPU) | [reports/cost_latency.md](reports/cost_latency.md) |
| D09 Failure modes and next steps | Done for baseline | [docs/TECHNICAL_MEMO.md](docs/TECHNICAL_MEMO.md) |

Remaining work, in order: download models and run experiments E1-E6
([docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)); build the Docker image; deploy with HTTPS
and evaluator credentials; finalize the memo and reports; prepare the walkthrough.

### Available Evidence

- Three recordings: `call_001.ogg`, `call_002.ogg`, and `call_003.ogg`.
- One CSV with columns `name` and `result_json`, containing nine-field JSON labels.
- Supplied tone labels: upset, neutral, and satisfied, one call each. No examples
  of frustrated or distressed are supplied.
- All three labels use confidence 0.82. Do not copy this value into predictions or
  treat it as evidence that a system's confidence is calibrated.
- Header inspection (local, standard library only): all three files are Ogg Opus,
  2 channels, 48 kHz input rate. Durations: 30.9 s, 35.0 s, and 171.9 s, about
  4.0 audio minutes in total, so the $0.003 ceiling allows roughly $0.012 for the
  whole supplied set. Confirm whether the two channels carry customer and agent
  separately; if so, channel separation may answer the customer-identification question.
- Label coverage gaps: no examples of `frustrated`, `distressed`, `low` intensity,
  `low`/`high` noise severity, impaired audio quality, or long silence. Overlap is
  `true` in two of three calls. Thresholds for these outputs cannot be tuned on the
  supplied calls and need other evidence or explicit, documented defaults.
- Labeling convention to note: `call_003` labels "sharp static" as background
  noise while `audio_quality` stays `clear`, although the brief lists static as an
  audio-quality factor. Treat static as ambiguous between noise and quality, and
  document how the system decides. Noise types use short free text ("TV" rather than
  "television"), so wording varies.
- Speaker roles and actual audio content still need listening review. No accuracy,
  latency, or cost measurements exist.

## 2. Success Criteria and Scoring

| Evaluation category | Weight | Planning consequence |
| --- | --- | --- |
| Hidden-set performance | 45% | Prioritize generalization and task-appropriate validation. |
| Cost efficiency | 15% | Enforce the $0.003/audio-minute ceiling and disclose assumptions. |
| Technical rigor | 15% | Preserve evaluation independence, record experiments, and justify confidence. |
| Production practicality | 10% | Measure runtime and provide reliable, private batch processing. |
| Communication | 5% | Explain setup, choices, tradeoffs, limitations, and next steps. |
| Hosted dashboard and upload experience | 10% | Deliver the complete browser-based workflow, not a local-only demo. |

**Required:** target submission within three business days of receipt; earlier
completion is appreciated. Confirm the receipt date, time zone, submission time,
and how long the deployment must remain available. No calendar deadline is assumed.

## 3. Required Prediction Contract

Every successful clip must produce this exact nine-field object (brief section 2).
Filename and processing status belong in a surrounding result record, not as
substitutes for the required prediction fields.

| Field | Type / allowed values | Required interpretation |
| --- | --- | --- |
| `emotional_tone` | Enum: `neutral`, `satisfied`, `frustrated`, `upset`, `distressed` | Primary emotion expressed by the customer, not the agent. Neutral: no clear positive/negative emotion; satisfied: pleased, relieved, appreciative, positive; frustrated: annoyed, impatient, dissatisfied without strong anger/distress; upset: clearly angry, agitated, strongly dissatisfied; distressed: overwhelmed, panicked, crying, or emotionally escalated. |
| `emotional_intensity` | Enum: `low`, `medium`, `high` | Strength of emotion: subtle/mild, clear/sustained, or strong/escalated respectively. |
| `background_noise_present` | Boolean | Meaningful audible non-speech background sound; barely perceptible artifacts do not automatically qualify. |
| `background_noise_type` | String | Concise dominant noise description, such as television, chatter, static, or wind; empty string when no noise is present. |
| `background_noise_severity` | Enum: `none`, `low`, `medium`, `high` | None: no meaningful noise; low: audible without interference; medium: occasionally interferes with understanding; high: materially impairs conversation or analysis. |
| `audio_quality` | Enum: `clear`, `slightly_impaired`, `severely_impaired` | Technical quality independent of emotion; consider clipping, distortion, echo, static, low volume, muffling, robotic audio, and packet loss. |
| `speaker_overlap_present` | Boolean | Simultaneous speakers overlap enough to affect understanding or analysis. |
| `long_silence_present` | Boolean | Unusually long silence/dead air that may indicate an audio or call-flow problem; the brief supplies no numeric threshold. |
| `confidence` | Number in [0.0, 1.0] | Confidence in the overall result, not a fabricated constant or unsupported probability claim. |

Acceptance checks: exact enum spelling, genuine JSON booleans and numeric
confidence, all fields present, and no fabricated prediction for failed audio.
When noise is absent, its type must be empty and its severity `none`. Document
how conflicting outputs are resolved without hiding model failures.

**Required interpretation safeguards:** emotional tone, noise, and technical
quality are scored separately. Loudness alone is not frustration/distress, and
poor technical quality alone is not evidence of background noise.

## 4. Functional Requirements and Acceptance Criteria

| ID | Required behavior | Acceptance evidence | Source |
| --- | --- | --- | --- |
| F01 | Publicly accessible hosted web dashboard with login. | Evaluator can use supplied credentials at a working URL; deployment remains available throughout evaluation. Send credentials privately, never in the repository. | 6-7, 12 |
| F02 | Upload a folder or ZIP containing multiple audio files and one CSV manifest. | Browser supports folder selection and ZIP upload. Accept at least OGG (Opus and Vorbis), WAV, and MP3: supplied calls are OGG/Opus, while the brief's example batch uses WAV and MP3. Mixed formats in one batch work. Test each advertised format. | 3, 7 |
| F03 | Validate the root-level batch structure and exact filename mapping. | Report missing audio, unlisted/unmatched files, duplicate names/rows, malformed CSV/JSON, unsupported files, and missing/ambiguous manifests. Do not silently pair approximate filenames. | 7 |
| F04 | Support labeled and unlabeled batches. | `name` identifies each exact filename including extension; parse `result_json` when populated. Permit empty labels and a name-only scoring input as described for hidden tests. Confirm any evaluator-specific interpretation. | 7 |
| F05 | Process each valid supported audio file and show progress/completion. | Dashboard distinguishes queued, running, completed, and failed files; progress and error messages remain understandable for a mixed-validity batch. | 6-7 |
| F06 | Isolate per-file failures. | A corrupt or unsupported file reports a useful reason while other valid files finish; structural errors identify whether the batch can proceed. | 7 |
| F07 | Display schema-compliant predictions per file. | Every successful file has all nine fields; failed files are distinguishable from low-confidence successes. | 2, 6-7 |
| F08 | Download structured results with original filenames. | At least CSV or JSON is downloadable; recommended CSV shape is `name,result_json`, with failures available separately. Verify filenames and JSON survive export/re-import. | 6-7 |
| F09 | Produce predictions for all three supplied calls. | Export generated predictions independently of labels and retain reproducible commands/configuration. Labels must never be used as inference input. | 6 |

Recommended upload policy: accept flat root-level batches as specified. Treat a
single outer folder as a practical requirement: the supplied ZIP itself wraps
everything in `Voice Analyzer Assessment/`. Unwrap exactly one directory, then
validate the same structure. Ignore OS artifacts (`__MACOSX/`, `.DS_Store`,
`Thumbs.db`, `desktop.ini`) and report them as skipped, not as errors. Reject unsafe
paths, archive bombs, excessive file counts, and excessive expanded size. Define
and disclose limits rather than silently truncate.

Manifest robustness: do not require the filename `labels.csv`, because the brief
only says "one CSV manifest". Handle UTF-8 BOM, CRLF line endings, quoted JSON,
spaces and Unicode in filenames, and trailing whitespace. Match filenames exactly
by default; if case-insensitive matching is added, report it rather than applying
it silently. Reject multiple CSVs at the root as ambiguous.

## 5. Constraints and Required Deliverables

| ID | Required constraint | Acceptance evidence |
| --- | --- | --- |
| C01 | Final production inference costs at most $0.003 per audio minute. | Reproducible cost calculation with measured usage or clearly marked estimates; include every enabled inference stage, retries, and external services. |
| C02 | Runtime is reasonable for production batch analysis. | Report measured or estimated clip runtime and processing time per audio minute; the brief gives no numeric latency SLA. |
| C03 | System is reproducible and runnable on new audio. | Setup, deployment, execution, dependencies/model versions, configuration, and evaluation instructions permit a fresh run. |
| C04 | Generalize to unseen audio; hidden test data is unavailable. | No hidden-set assumptions, filename-based predictions, label leakage, or training-only accuracy claims. |
| C05 | Production calls are confidential. | No upload to unapproved public services; use approved infrastructure and documented data flows. |
| C06 | Disclose every external paid API. | State provider/model, pricing assumptions, retention policy, and whether customer audio leaves AutoAce-controlled infrastructure. |

The submission checklist maps to all nine deliverables in brief section 6:

- [ ] D01: Hosted dashboard, URL, and working evaluator login.
- [ ] D02: Runnable implementation/repository with setup, deployment, and execution instructions.
- [ ] D03: Batch folder/ZIP upload, validation, progress/errors, and structured downloads.
- [ ] D04: Schema-compliant predictions for the three supplied calls.
- [ ] D05: Short technical memo covering approaches tested, final architecture, and rationale.
- [ ] D06: Validation results, metric definitions, per-class results where possible, and confusion matrix.
- [ ] D07: Cost per audio minute with assumptions and ceiling compliance.
- [ ] D08: Latency per audio minute or clip, distinguishing measurements from estimates.
- [ ] D09: Failure modes, limitations, and next steps for accuracy improvements.

Additional required content, drawn from other sections of the brief:

- [ ] Memo explains how ambiguous emotional tone and low-level background noise are
      handled (section 9).
- [ ] Memo describes how confidence was calibrated (section 9).
- [ ] Memo gives a reasonable path to production integration (section 12, success
      definition): batch API or storage-triggered processing, authentication, data
      retention, scaling, and monitoring. This is not only an optional backlog item.
- [ ] Memo discloses any external paid API, model, pricing, retention, and data
      location (section 11).
- [ ] Walkthrough prepared on methodology, experiments, tradeoffs, and what would
      change with more data or time (section 10). Have a short live demo script and
      a fallback recording of the dashboard in case hosting fails during review.

Recommended repository layout for the deliverables, so they are easy to find:
`docs/memo.md`, `reports/validation.md`, `reports/cost.md`, `reports/latency.md`,
`predictions/supplied_calls.csv`, and setup/deploy/run instructions in `README.md`.

## 6. Proposed Architecture (Recommended)

Start with one deployable application and a bounded background worker rather than
multiple independent services. Hosting provider and model choice remain undecided.

1. Authenticated dashboard accepts the batch and presents validation feedback.
2. Isolated temporary storage holds uploaded audio and the parsed manifest.
3. Validator creates a job containing valid files and independent error records.
4. Audio adapter decodes files using a proven audio library/toolchain, records
   duration/channel metadata, and creates model-specific working copies. Preserve
   the original signal for quality/noise measurements; aggressive denoising can
   erase evidence that the assessment expects the system to detect.
5. Inference service receives audio only, never expected labels. It combines the
   selected emotion/noise models and validated acoustic checks as appropriate.
6. Output validator enforces the schema; aggregator combines chunk-level evidence
   into a call-level result using a documented rule.
7. Results view/export exposes predictions and errors. A separate scoring module
   compares completed predictions with labels only when labels are available.
8. Retention cleanup removes raw audio, temporary files, and results according to
   the agreed policy; logs exclude audio, credentials, and sensitive content.

Candidate rapid-delivery stack: Python audio/model libraries with Streamlit for a
small dashboard, or FastAPI plus a small frontend if job control/authentication
needs justify the extra work. Verify secure login and hosting support before
committing. Do not build an elaborate UI ahead of the working evaluation path.

Customer identification is a critical design decision: inspect channel roles and
speaker structure first. Use channel separation when reliable, or evaluate
diarization/role attribution when necessary. Do not assume the first or loudest
speaker is the customer. Define an uncertainty policy for unresolved roles.
Because the supplied calls are stereo, check this first; it can also make overlap
detection simpler (simultaneous speech on both channels). Mono hidden-set files
must still work.

Hosting practicalities to verify before choosing a platform:

- Upload size and request limits. The supplied ZIP is about 4 MB for 4 minutes of
  audio, but a hidden batch may be much larger. Test a realistic large batch.
- Request timeouts. Run analysis as a background job, not inside the upload request,
  so long batches do not hit gateway timeouts. The dashboard polls job status.
- Cold starts and scale-to-zero. Keep at least one warm instance during evaluation,
  or show a clear "starting up" state. Model download time must not cause failures.
- HTTPS only, credentials stored as platform secrets, sessions that expire, and a
  login attempt limit. Use a dedicated evaluator account that can be revoked.

## 7. Modeling and Validation Strategy

### Establish a Baseline

The brief recommends comparing at least two materially different approaches
(section 9). Plan for this comparison, but do not assume any candidate will meet
the accuracy or cost requirements before testing.

- Candidate A: pretrained speech-emotion and acoustic-event models, supported by
  signal-processing checks for silence, overlap, and technical quality. Confirm
  model licenses, supported languages, compute requirements, and label mappings.
- Candidate B: an approved audio-capable foundation model with a fixed schema and
  prompt. Only run confidential calls after provider/retention approval and a
  preliminary cost check. If approval or pricing fails, compare a materially
  different local model/feature-based approach instead.
- Candidate C, only if justified: hybrid/conditional ensemble. Measure every added
  stage's incremental benefit, latency, and cost before enabling it.

Pretrained emotion labels may not match the five required classes. Document and
test mappings explicitly, especially frustrated versus upset versus distressed.
Do not train or fine-tune a five-class classifier on only these three calls.

### Honest Evaluation With Three Calls

- Use supplied calls for schema/integration checks, qualitative error analysis,
  and clearly labeled descriptive results. They cannot establish generalization.
- Tone has only three observed classes with one example each. Stratified
  cross-validation across five classes is not feasible; leave-one-call-out on
  three calls cannot validate missing classes or justify strong accuracy claims.
- Prefer an additional approved, representative, independently labeled dataset.
  Group by original call/caller; keep duplicates, channels, and derived chunks
  together. Prevent preprocessing and threshold tuning from leaking across splits.
- Keep a frozen holdout when sufficient data exists. Use grouped validation for
  development and record every prompt/model/threshold decision. Do not tune on the
  final holdout or claim post-tuning fixture agreement as independent validation.
- Public/licensed or synthetic data may support development if permitted, but
  report it separately from real production-call evaluation and disclose mismatch.

### Metrics and Reporting

| Output | Proposed report |
| --- | --- |
| Emotional tone | Accuracy, macro F1 with an explicit label/zero-division policy, five-class confusion matrix, per-class precision/recall/F1 and support. Mark unsupported classes; do not imply they were tested. |
| Intensity, noise severity, audio quality | Accuracy, per-class support/confusion matrices; optionally ordinal error as a secondary metric. |
| Noise present, overlap, long silence | Precision/recall/F1 and confusion counts; accuracy alone can hide class imbalance. |
| Noise type | Human-reviewed semantic agreement or a declared normalization rubric; report exact string match separately because valid synonyms exist. |
| Confidence | Calibration/reliability analysis and Brier score/ECE only with sufficient independent labeled data and a defined correctness event; otherwise disclose heuristic confidence and insufficient evidence. |
| Operational validity | Schema pass rate, file failure rate, completed/failed counts, runtime, throughput, and cost. |

These are proposed reporting metrics beyond the explicitly stated tone accuracy
and macro F1. The hidden scoring formula for every field is not specified.
Report noise, emotion, and quality separately, not only one aggregate score.

Define the overall-confidence event before calibration, for example correctness
of all specified categorical/boolean fields under a declared rubric. Do not average
unrelated raw model scores and label the result a calibrated probability.

## 8. Cost and Latency Verification

**Required inference gate:** total attributable inference cost divided by audio
minutes analyzed must be at most $0.003. Use actual decoded duration, not upload
size, and define billing rounding/minimums. Do not hide failed attempts or retries.

- Hosted model estimate: billed audio/text units at disclosed provider rates plus
  any transcription, event-detection, retry, and ensemble stages.
- Self-hosted estimate: compute price per hour multiplied by processing hours,
  divided by audio minutes processed; state utilization, batching, idle-time
  assumptions, hardware, and model size. Local inference is not automatically free.
- At real-time factor 0.1, the inference-only compute budget is $1.80/hour at full
  utilization: $0.003 * 60 / 0.1. This is illustrative, not a measured result.
- Report low- and expected-utilization scenarios. Separately disclose total hosting,
  storage, networking, and monitoring costs; clarify whether the evaluator includes
  these in the ceiling, and do not claim compliance by omitting material costs.
- Time decoding, inference, aggregation, and export. Distinguish cold/warm runs,
  queue wait, per-clip runtime, total batch runtime, and concurrency settings.
- Report real-time factor as processing seconds / audio seconds. Add median and
  tail latency only when the sample size supports them.

Choose the final system using validation quality subject to cost, privacy, and
operability gates. Disable an optional expensive fallback if it can breach the
ceiling; provide a documented bounded policy rather than an unrestricted cascade.

## 9. Three-Business-Day Delivery Plan

Suggested allocation, conditional on prompt hosting/data-access decisions. It is
not a promise that unapproved services or hardware will be available immediately.

| Stage | Work and dependencies | Exit evidence |
| --- | --- | --- |
| Day 1, first half | Resolve critical questions; inspect metadata/audio locally; define schema, validation fixtures, privacy boundary, candidate models, and preliminary cost. | Written decisions; decodable inputs; independent inference/scoring interfaces. |
| Day 1, second half | Build baseline and batch runner; generate three-call predictions; record initial runtime and cost. Reserve hosting and verify login path early. | Reproducible baseline, validated JSON, and a first deployed access check. |
| Day 2, first half | Compare a materially different approach; review errors; test customer-role handling and chunk aggregation; select a cost-compliant candidate. | Experiment table and defensible selection, with small-data limitations. |
| Day 2, second half | Integrate folder/ZIP upload, manifest validation, progress, per-file failures, review, exports, and label-optional scoring. | End-to-end mixed-validity labeled and unlabeled batch tests. |
| Day 3, first half | Harden upload/auth/retention; measure deployed runtime/cost; check clean setup and browser workflow. Freeze candidate/configuration. | Deployment smoke tests and reproducibility evidence. |
| Day 3, second half | Finish memo, metrics/confusion matrix, predictions, cost/latency reports, limitations, production integration path, and submission audit. Prepare the walkthrough and demo fallback. | All D01-D09 artifacts and section 5 memo items; verified URL and privately delivered login. |

Core dependency: contract/data review -> baseline -> comparison/selection -> final
evaluation. Dashboard work can proceed after result/job contracts are stable.
Do not spend the accuracy budget on cosmetic UI work; do not postpone hosting
until the final hours. Defer custom training and extra infrastructure if they
threaten mandatory deliverables.

## 10. Verification Checklist

- [ ] Every successful result passes the exact nine-field schema and invariants.
- [ ] Supplied OGG/Opus files decode; WAV, MP3, OGG/Vorbis, mono, and other sample
      rates each have a fixture, plus one batch that mixes formats.
- [ ] Uploading the original supplied ZIP unchanged (with its outer folder) works.
- [ ] ZIPs containing `__MACOSX/` or `.DS_Store` entries, a CSV with BOM/CRLF, and
      filenames with spaces process correctly.
- [ ] Valid labeled, empty-label, and name-only manifests work without label leakage.
- [ ] Missing files, unmatched names, duplicates, malformed JSON/CSV, unsupported
      audio, corrupt audio, and all-invalid batches produce clear outcomes.
- [ ] One corrupt file does not prevent valid files from completing.
- [ ] ZIP traversal, oversized expansion, excessive duration/file counts, and
      unauthorized access are rejected safely; upload content is never executed.
- [ ] Predictions are unchanged when labels are altered or removed for the same
      audio. Scoring is a separate operation and never influences inference.
- [ ] Customer/agent attribution and unresolved-role behavior are tested.
- [ ] Loud neutral speech, poor-quality clean audio, meaningful background noise,
      overlapping speech, and long silence have targeted checks where approved
      examples exist; record untested cases rather than fabricate coverage.
- [ ] Whole-call processing/chunk aggregation does not silently omit late events;
      chunk boundaries and silence durations are handled consistently.
- [ ] Download/re-import preserves exact filenames, fields, and JSON types.
- [ ] Logged-out users cannot access batches/results; users cannot read other
      batches unless explicitly authorized; credentials are not committed.
- [ ] Hosted browser workflow works on desktop and a narrow/mobile viewport,
      including progress, long filenames, failures, and downloads.
- [ ] Clean-environment run follows documentation and reproduces stored predictions
      within declared model nondeterminism.
- [ ] Measured/estimated cost and runtime include all enabled pipeline stages;
      $0.003/audio-minute compliance is supported, not assumed.
- [ ] A large batch completes without request timeouts; the first request after
      idle does not fail because of cold start or model download.
- [ ] When labels are present, the dashboard can show expected versus predicted per
      file, and inference output is identical with labels removed.
- [ ] Repository contains no confidential audio, labels, brief, or credentials, and
      its visibility matches the confidentiality decision in section 1.
- [ ] Deployment URL/login work and evaluation-period availability has an owner.

## 11. Prioritized Improvement Backlog (Optional)

| Priority | Suggestion | Benefit and evidence needed |
| --- | --- | --- |
| P1: accuracy | Acquire approved labels covering all five tones, multiple speakers/languages/devices, noise types, and ambiguous boundaries. Use a written rubric and reviewer adjudication. | Addresses the largest validation gap; measure grouped holdout improvements and label agreement. |
| P1: accuracy | Strengthen customer-role attribution and time-localized emotion/noise aggregation. | Reduces agent/customer confusion and missed short events; assess on annotated calls. |
| P1: confidence | Calibrate on independent data and show uncertainty to reviewers without altering the required schema. | Makes confidence useful; verify calibration and review workload, not just apparent certainty. |
| P1: demo | Add audio playback and optional evidence timestamps, a compact results table, filters, and per-file retries. | Makes inspection faster; timestamps must come from real analysis and respect permissions. |
| P1: reliability | Persist job state and implement bounded retries, cancellation, and resumable processing. | Survives refreshes/restarts and avoids duplicate paid work; verify idempotency and isolation. |
| P2: efficiency | Benchmark shorter windows, smaller models, quantization, batching, and tightly bounded conditional inference. | Improve throughput/cost only if held-out quality and rare-event recall remain acceptable. |
| P2: operations | Add queue/latency/failure/cost monitoring, versioned artifacts, retention enforcement, rollback, and deployment health checks. | Supports production readiness without exposing confidential content in telemetry. |
| P2: integration | Publish a versioned batch API/webhook after the dashboard contract is stable. | Provides a production integration path; not a substitute for the required browser workflow. |
| P3: adaptation | Consider fine-tuning, domain adaptation, and drift monitoring once enough approved representative data exists. | Validate out-of-sample benefit before paying for training or maintaining added complexity. |

Do not prioritize a bespoke model, large ensemble, decorative dashboard, or
microservice architecture before the mandatory submission is complete.

## 12. Decisions and Clarifications

Resolve the first four items early because they affect feasibility:

1. What is the exact deadline and evaluation availability period?
2. Which hosting environments, external providers, model licenses, and data flows
   are approved? Who funds hosting and supplies access? No provider is assumed.
3. What compute is available, and what expected batch size, maximum clip duration,
   concurrency, and acceptable turnaround should the deployment support?
4. How can the customer be identified (channels, metadata, speaker conventions),
   and which languages are expected? What should happen when roles are ambiguous?
5. What numeric definition should apply to long silence? Establish a documented,
   configurable threshold and distinguish hold/dead air from natural pauses.
6. Does the cost ceiling include idle hosting and related infrastructure? What
   pricing region, currency, utilization, and billing rounding should be used?
7. Is additional approved labeled data available? What is the preferred noise-type
   matching rubric and confidence interpretation?
8. What retention/deletion policy, authentication expectations, and evaluator
   credential-delivery channel apply?
9. Should a missing `result_json` column be accepted directly for hidden batches,
   and are any formats beyond supplied OGG and the brief's WAV/MP3 examples needed?
10. Should static and similar line noise count as background noise, an audio-quality
    issue, or both? The supplied label for `call_003` suggests background noise.
11. Will the hidden batch arrive as one ZIP, or possibly as several parts (cloud
    storage downloads often split large archives)? Should several ZIPs be merged
    into one batch?
12. Is the repository allowed to be public? If not, keep it private and share it
    with AutoAce directly.

Pending answers, keep these as explicit assumptions in the technical memo; never
present a locally chosen threshold or unsupported accuracy target as a requirement.

## 13. Experiment and Change Log Templates

Record one row per candidate before selecting the final pipeline:

| Experiment | Model/version and configuration | Data/split | Metrics and support | Cost/audio minute | Runtime/audio minute | Privacy approval | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | TBD | Supplied fixtures; not independent validation | Not measured | Not measured | Not measured | TBD | Pending |

For each later improvement, record: hypothesis, affected requirement, dataset and
split, expected benefit, measured result, cost/latency impact, decision, and rollback
path. Update the requirements checklist when scope changes; keep optional work
visibly separate from acceptance gates.