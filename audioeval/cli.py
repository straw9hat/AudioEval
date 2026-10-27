"""Command-line interface: python -m audioeval <command>."""

from __future__ import annotations

import argparse
import csv
import getpass
import io
import json
import sys
import tempfile
import time
from pathlib import Path

from .audio import AudioDecodeError
from .batch import BatchError, _unwrap, plan_batch, stage_upload
from .calibration import Calibrator, brier_and_ece, fit_isotonic, is_correct
from .config import Settings
from .cost import CEILING_PER_MIN, cost_table
from .export import errors_csv, predictions_csv, results_json
from .schema import SchemaError, parse_label, validate_prediction
from .scoring import score


def _run_batch(input_path: Path, out_dir: Path, settings: Settings) -> dict:
    from .pipeline import Analyzer

    analyzer = Analyzer(settings)
    print(f"method: {analyzer.method}")
    for k, v in analyzer.models.status.items():
        print(f"  model {k}: {v}")
    with tempfile.TemporaryDirectory() as tmp:
        if input_path.is_file():
            with input_path.open("rb") as fh:
                root, skipped, errors = stage_upload([(input_path.name, fh)], Path(tmp), 1 << 40, settings.max_files)
        else:
            root, skipped, errors = _unwrap(input_path), [], []
        plan = plan_batch(root)
        for msg in errors + plan.errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        for msg in plan.warnings:
            print(f"warning: {msg}")
        items = []
        start = time.perf_counter()
        for i, it in enumerate(plan.items, 1):
            row = vars(it) | {"prediction": None, "details": None}
            if it.status == "queued":
                try:
                    res = analyzer.analyze(it.path)
                    row.update(status="done", prediction=res.prediction, details=res.details)
                except AudioDecodeError as exc:
                    row.update(status="failed", error=str(exc))
                except Exception as exc:  # keep going; one bad file must not stop the batch
                    row.update(status="failed", error=f"analysis error: {type(exc).__name__}: {exc}")
            print(f"[{i}/{len(plan.items)}] {it.name}: {row['status']}" + (f" ({row['error']})" if row.get("error") else ""))
            items.append(row)
    pairs = [(r["name"], r["prediction"], r["label"]) for r in items if r["status"] == "done" and r.get("label")]
    audio_s = sum(r["details"]["audio"]["duration_s"] for r in items if r.get("details"))
    proc_s = sum(r["details"]["timings"]["total_s"] for r in items if r.get("details"))
    job = {"id": "cli", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "method": analyzer.method,
           "summary": {"total": len(items), "done": sum(r["status"] == "done" for r in items),
                       "failed": sum(r["status"] == "failed" for r in items), "audio_minutes": round(audio_s / 60, 3),
                       "processing_s": round(proc_s, 3), "wall_s": round(time.perf_counter() - start, 3),
                       "real_time_factor": round(proc_s / audio_s, 4) if audio_s else None},
           "warnings": plan.warnings + errors + plan.errors, "skipped": skipped + plan.skipped, "items": items,
           "score": score(pairs) if pairs else None}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "predictions.csv").write_text(predictions_csv(items), encoding="utf-8", newline="")
    (out_dir / "errors.csv").write_text(errors_csv(items), encoding="utf-8", newline="")
    (out_dir / "results.json").write_text(results_json(job), encoding="utf-8")
    print(json.dumps(job["summary"]))
    print(f"wrote {out_dir / 'predictions.csv'}, results.json, errors.csv")
    return job


def cmd_analyze(args, settings):
    job = _run_batch(Path(args.input), Path(args.out), settings)
    if job["score"]:
        print("NOTE: agreement with supplied labels is descriptive only (not independent validation).")
        for field, m in job["score"]["fields"].items():
            val = m.get("accuracy", m.get("normalized_match"))
            print(f"  {field}: {val:.3f}" if val is not None else f"  {field}: -")
    return 0 if job["summary"]["done"] else 1


def _read_csv(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    return {r["name"].strip(): (r.get("result_json") or "") for r in csv.DictReader(io.StringIO(text))}


def cmd_evaluate(args, _settings):
    preds = _read_csv(Path(args.predictions))
    labels = _read_csv(Path(args.labels))
    pairs, problems = [], []
    for name, label_text in labels.items():
        if not label_text.strip():
            continue
        if name not in preds:
            problems.append(f"{name}: no prediction")
            continue
        try:
            pairs.append((name, validate_prediction(json.loads(preds[name])), parse_label(label_text)))
        except (SchemaError, json.JSONDecodeError) as exc:
            problems.append(f"{name}: {exc}")
    report = score(pairs) | {"problems": problems}
    out = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    print(out)
    return 0


def cmd_benchmark(args, settings):
    job = _run_batch(Path(args.input), Path(args.out), settings)
    rtf = job["summary"]["real_time_factor"]
    if not rtf:
        print("no audio processed", file=sys.stderr)
        return 1
    per_file = [{"name": r["name"], "duration_s": r["details"]["audio"]["duration_s"],
                 "timings": r["details"]["timings"], "rtf": r["details"]["real_time_factor"]}
                for r in job["items"] if r.get("details")]
    report = {"method": job["method"], "summary": job["summary"], "per_file": per_file,
              "hourly_price_assumed": args.hourly_price, "concurrency": args.concurrency,
              "cost": cost_table(rtf, args.hourly_price, args.concurrency), "ceiling_per_audio_minute": CEILING_PER_MIN}
    (Path(args.out) / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def cmd_cost(args, _settings):
    for row in cost_table(args.rtf, args.hourly_price, args.concurrency):
        flag = "OK" if row["within_ceiling"] else "OVER CEILING"
        print(f"utilization {row['utilization']:>4.0%}: ${row['cost_per_audio_minute']:.6f}/audio-min  {flag}")
    return 0


def cmd_calibrate(args, _settings):
    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    labels = {n: parse_label(t) for n, t in _read_csv(Path(args.labels)).items() if t.strip()}
    raw, correct = [], []
    for r in data["results"]:
        if r["status"] == "done" and r["name"] in labels:
            raw.append(r["details"]["raw_confidence"])
            correct.append(is_correct(r["prediction"], labels[r["name"]]))
    print("before:", brier_and_ece([Calibrator()(x) for x in raw], correct))
    try:
        params = fit_isotonic(raw, correct)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(params, indent=2), encoding="utf-8")
    print("in-sample after:", brier_and_ece([Calibrator(params)(x) for x in raw], correct))
    print(f"wrote {args.out}; evaluate on a separate held-out set before relying on it")
    return 0


def cmd_hash_password(_args, _settings):
    from .auth import hash_password

    pw = getpass.getpass("Password: ")
    if len(pw) < 12:
        print("ERROR: use at least 12 characters", file=sys.stderr)
        return 1
    if pw != getpass.getpass("Repeat: "):
        print("ERROR: passwords differ", file=sys.stderr)
        return 1
    print(hash_password(pw))
    return 0


def cmd_check_models(_args, settings):
    from .models import load_models

    bundle = load_models(settings)
    for k, v in bundle.status.items():
        print(f"{k:8s} {v}")
    return 0


def cmd_serve(args, _settings):
    import uvicorn

    uvicorn.run("audioeval.web:create_app", factory=True, host=args.host, port=args.port, proxy_headers=True)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="audioeval", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze a batch folder or ZIP")
    a.add_argument("input")
    a.add_argument("--out", default="output")
    a.set_defaults(fn=cmd_analyze)
    e = sub.add_parser("evaluate", help="score predictions.csv against a labels CSV")
    e.add_argument("--predictions", required=True)
    e.add_argument("--labels", required=True)
    e.add_argument("--out")
    e.set_defaults(fn=cmd_evaluate)
    b = sub.add_parser("benchmark", help="measure runtime and estimate cost")
    b.add_argument("input")
    b.add_argument("--out", default="output")
    b.add_argument("--hourly-price", type=float, required=True, help="USD per instance-hour (state your source)")
    b.add_argument("--concurrency", type=int, default=1)
    b.set_defaults(fn=cmd_benchmark)
    c = sub.add_parser("cost", help="cost per audio minute from a real-time factor")
    c.add_argument("--rtf", type=float, required=True)
    c.add_argument("--hourly-price", type=float, required=True)
    c.add_argument("--concurrency", type=int, default=1)
    c.set_defaults(fn=cmd_cost)
    k = sub.add_parser("calibrate", help="fit confidence calibration (needs >=30 independent labeled clips)")
    k.add_argument("--results", required=True)
    k.add_argument("--labels", required=True)
    k.add_argument("--out", default="calibration.json")
    k.set_defaults(fn=cmd_calibrate)
    sub.add_parser("hash-password", help="create a password hash for AUDIOEVAL_USERS").set_defaults(fn=cmd_hash_password)
    sub.add_parser("check-models", help="show which optional models load").set_defaults(fn=cmd_check_models)
    s = sub.add_parser("serve", help="run the web dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    args = p.parse_args(argv)
    try:
        return args.fn(args, Settings.from_env())
    except BatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
