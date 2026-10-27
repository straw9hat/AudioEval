"""Background batch jobs with on-disk state, resume after restart, and retention cleanup."""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Iterable

from .audio import AudioDecodeError
from .batch import BatchError, plan_batch, stage_upload
from .config import Settings
from .pipeline import Analyzer
from .scoring import score

log = logging.getLogger("audioeval.jobs")
JOB_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobManager:
    def __init__(self, settings: Settings, analyzer_factory: Callable[[], Analyzer]):
        self.settings = settings
        self.root = settings.data_path.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._analyzer_factory = analyzer_factory
        self._analyzer: Analyzer | None = None
        self._analyzer_lock = threading.Lock()
        self._lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.workers), thread_name_prefix="audioeval")
        self.cleanup()
        self._load_existing()

    @property
    def analyzer(self) -> Analyzer:
        with self._analyzer_lock:
            if self._analyzer is None:
                self._analyzer = self._analyzer_factory()
            return self._analyzer

    # ---- persistence -------------------------------------------------
    def _job_dir(self, job_id: str) -> Path:
        if not job_id or set(job_id) - JOB_ID_CHARS:
            raise KeyError(job_id)
        return self.root / job_id

    def _save(self, job: dict) -> None:
        path = self._job_dir(job["id"]) / "state.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _load_existing(self) -> None:
        for state in self.root.glob("*/state.json"):
            try:
                job = json.loads(state.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                log.warning("unreadable job state %s", state.parent.name)
                continue
            if job.get("status") == "running":
                job["status"] = "interrupted"
                for it in job["items"]:
                    if it["status"] == "running":
                        it["status"] = "queued"
                self._save(job)
            self.jobs[job["id"]] = job

    def cleanup(self) -> int:
        """Delete jobs (audio and results) older than the retention period."""
        cutoff = time.time() - self.settings.retention_hours * 3600
        removed = 0
        for d in self.root.iterdir() if self.root.exists() else []:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                with self._lock:
                    self.jobs.pop(d.name, None)
                removed += 1
        return removed

    # ---- lifecycle ---------------------------------------------------
    def create(self, owner: str, uploads: Iterable[tuple[str, BinaryIO]]) -> dict:
        self.cleanup()
        job_id = secrets.token_urlsafe(12)
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True)
        job = {"id": job_id, "owner": owner, "created": _now(), "status": "validating", "errors": [],
               "warnings": [], "skipped": [], "items": [], "manifest": None, "has_labels": False}
        try:
            root, skipped, errors = stage_upload(uploads, job_dir, self.settings.max_upload_mb * 1024 * 1024, self.settings.max_files)
            plan = plan_batch(root)
            job.update(errors=errors + plan.errors, warnings=plan.warnings, skipped=skipped + plan.skipped,
                       manifest=plan.manifest_name, has_labels=plan.has_labels,
                       items=[vars(it) | {"prediction": None, "details": None} for it in plan.items])
        except BatchError as exc:
            job["errors"].append(str(exc))
        job["status"] = "invalid" if job["errors"] and not any(i["status"] == "queued" for i in job["items"]) else "running"
        if job["status"] == "invalid":
            self._purge_audio(job_dir)
        self._summarize(job)
        with self._lock:
            self.jobs[job_id] = job
            self._save(job)
        if job["status"] == "running":
            self._submit(job)
        log.info("job %s created: %d items, status %s", job_id, len(job["items"]), job["status"])
        return job

    def _submit(self, job: dict) -> None:
        for idx, it in enumerate(job["items"]):
            if it["status"] == "queued":
                self.executor.submit(self._process, job["id"], idx)

    def resume(self, job_id: str, owner: str) -> dict:
        job = self.get(job_id, owner)
        with self._lock:
            if job["status"] != "interrupted":
                return job
            for it in job["items"]:
                if it["status"] == "queued" and not (it.get("path") and Path(it["path"]).exists()):
                    it["status"], it["error"] = "failed", "audio no longer available; re-upload the batch"
            job["status"] = "running"
            self._summarize(job)
            self._save(job)
        self._submit(job)
        self._maybe_finish(job_id)
        return job

    def _process(self, job_id: str, idx: int) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            item = job["items"][idx]
            item["status"] = "running"
            self._summarize(job)
            self._save(job)
        try:
            result = self.analyzer.analyze(item["path"])
            update = {"status": "done", "prediction": result.prediction, "details": result.details}
        except AudioDecodeError as exc:
            update = {"status": "failed", "error": str(exc)}
        except Exception as exc:  # isolate per-file failures (brief section 7)
            log.exception("analysis failed for item %d of job %s", idx, job_id)
            update = {"status": "failed", "error": f"analysis error: {type(exc).__name__}"}
        with self._lock:
            item.update(update)
            self._summarize(job)
            self._save(job)
        self._maybe_finish(job_id)

    def _maybe_finish(self, job_id: str) -> None:
        with self._lock:
            job = self.jobs[job_id]
            if job["status"] != "running" or any(i["status"] in ("queued", "running") for i in job["items"]):
                return
            failed = any(i["status"] == "failed" for i in job["items"])
            job["status"] = "completed_with_errors" if failed or job["errors"] else "completed"
            job["finished"] = _now()
            pairs = [(i["name"], i["prediction"], i["label"]) for i in job["items"]
                     if i["status"] == "done" and i.get("label")]
            job["score"] = score(pairs) if pairs else None
            job["method"] = self.analyzer.method
            self._summarize(job)
            self._save(job)
            if not self.settings.keep_audio:
                self._purge_audio(self._job_dir(job_id))

    @staticmethod
    def _purge_audio(job_dir: Path) -> None:
        shutil.rmtree(job_dir / "batch", ignore_errors=True)

    @staticmethod
    def _summarize(job: dict) -> None:
        counts = {s: 0 for s in ("queued", "running", "done", "failed")}
        audio_s = proc_s = 0.0
        for it in job["items"]:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
            if it.get("details"):
                audio_s += it["details"]["audio"]["duration_s"]
                proc_s += it["details"]["timings"]["total_s"]
        job["summary"] = counts | {"total": len(job["items"]), "audio_minutes": round(audio_s / 60, 3),
                                   "processing_s": round(proc_s, 3),
                                   "real_time_factor": round(proc_s / audio_s, 4) if audio_s else None}

    # ---- queries -----------------------------------------------------
    def get(self, job_id: str, owner: str) -> dict:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None or job["owner"] != owner:
                raise KeyError(job_id)
            return job

    def list(self, owner: str) -> list[dict]:
        with self._lock:
            jobs = [j for j in self.jobs.values() if j["owner"] == owner]
        return sorted(jobs, key=lambda j: j["created"], reverse=True)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
