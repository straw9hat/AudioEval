"""Result export: CSV (name,result_json), full JSON, and errors."""

from __future__ import annotations

import csv
import io
import json

from .schema import to_json


def predictions_csv(items: list[dict]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["name", "result_json"])
    for it in items:
        if it.get("status") == "done" and it.get("prediction"):
            w.writerow([it["name"], to_json(it["prediction"])])
    return buf.getvalue()


def errors_csv(items: list[dict]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["name", "status", "error", "warnings"])
    for it in items:
        if it.get("status") != "done" or it.get("warnings"):
            w.writerow([it["name"], it.get("status"), it.get("error") or "", "; ".join(it.get("warnings") or [])])
    return buf.getvalue()


def results_json(job: dict) -> str:
    out = {
        "job_id": job["id"],
        "created": job["created"],
        "method": job.get("method"),
        "summary": job.get("summary"),
        "batch_warnings": job.get("warnings", []),
        "skipped": job.get("skipped", []),
        "results": [
            {"name": it["name"], "status": it["status"], "error": it.get("error"), "warnings": it.get("warnings", []),
             "prediction": it.get("prediction"), "details": it.get("details")}
            for it in job["items"]
        ],
        "score": job.get("score"),
    }
    return json.dumps(out, indent=2, ensure_ascii=False)
