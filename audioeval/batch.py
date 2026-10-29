"""Batch ingestion: safe upload/ZIP handling, manifest parsing, and file matching (brief section 7)."""

from __future__ import annotations

import csv
import io
import shutil
import stat
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from .audio import supported_extensions
from .schema import SchemaError, parse_label

ARTIFACT_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
ARTIFACT_DIRS = {"__macosx"}
COPY_CHUNK = 1 << 20


class BatchError(Exception):
    pass


@dataclass
class Item:
    name: str
    path: str | None = None
    label: dict | None = None
    in_manifest: bool = False
    status: str = "queued"  # queued | running | done | failed
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class BatchPlan:
    items: list[Item] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # batch-level, processing cannot start
    warnings: list[str] = field(default_factory=list)
    manifest_name: str | None = None
    has_labels: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def is_artifact(rel: PurePosixPath) -> bool:
    parts = [p.lower() for p in rel.parts]
    return any(p in ARTIFACT_DIRS for p in parts[:-1]) or parts[-1] in ARTIFACT_NAMES or parts[-1].startswith("._")


def safe_relpath(name: str) -> PurePosixPath:
    """Normalize an uploaded/archived path; reject traversal, absolute paths and drive letters."""
    cleaned = name.replace("\\", "/")
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise BatchError(f"unsafe path rejected: {name!r}")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise BatchError(f"unsafe path rejected: {name!r}")
    if any(ord(c) < 32 for p in parts for c in p):
        raise BatchError(f"invalid characters in path: {name!r}")
    return PurePosixPath(*parts)


def _copy_limited(src: BinaryIO, dst: Path, budget: list[int]) -> None:
    with dst.open("wb") as out:
        while chunk := src.read(COPY_CHUNK):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise BatchError("upload exceeds the maximum allowed size")
            out.write(chunk)


def extract_zip(src: BinaryIO, dest: Path, budget: list[int], max_files: int) -> list[str]:
    skipped = []
    try:
        zf = zipfile.ZipFile(src)
    except zipfile.BadZipFile as exc:
        raise BatchError("file is not a valid ZIP archive") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > max_files * 2:
            raise BatchError(f"ZIP contains too many entries ({len(infos)})")
        for info in infos:
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise BatchError("encrypted ZIP archives are not supported")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                skipped.append(f"{info.filename} (symbolic link)")
                continue
            rel = safe_relpath(info.filename)
            if is_artifact(rel):
                skipped.append(f"{rel} (system file)")
                continue
            if info.compress_size and info.file_size / info.compress_size > 200 and info.file_size > 50 * COPY_CHUNK:
                raise BatchError(f"suspicious compression ratio in {rel}")
            target = dest.joinpath(*rel.parts)
            if not target.resolve().is_relative_to(dest.resolve()):
                raise BatchError(f"unsafe path rejected: {info.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fh:
                _copy_limited(fh, target, budget)  # counts real bytes, not header claims
    return skipped


def unwrap_single_folder(source: Path) -> Path:
    """Descend into a single wrapper folder (e.g. 'Voice Analyzer Assessment/')."""
    entries = [p for p in source.iterdir()]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return source


def stage_upload(
    uploads: Iterable[tuple[str, BinaryIO]], staging: Path, max_bytes: int, max_files: int
) -> tuple[Path, list[str], list[str]]:
    """Write uploaded files/ZIPs to disk and merge their root level into one batch folder.

    Returns (batch_root, skipped, errors).
    """
    raw = staging / "raw"
    root = staging / "batch"
    raw.mkdir(parents=True)
    root.mkdir()
    budget = [max_bytes]
    skipped: list[str] = []
    errors: list[str] = []
    loose = raw / "files"
    sources: list[Path] = []
    count = 0
    for index, (name, fh) in enumerate(uploads):
        count += 1
        if count > max_files:
            raise BatchError(f"too many files uploaded (limit {max_files})")
        rel = safe_relpath(name or f"upload_{index}")
        if is_artifact(rel):
            skipped.append(f"{rel} (system file)")
            continue
        if rel.suffix.lower() == ".zip":
            dest = raw / f"zip_{index}"
            dest.mkdir()
            try:
                skipped += extract_zip(fh, dest, budget, max_files)
            except BatchError as exc:
                errors.append(f"{rel}: {exc}")
                continue
            sources.append(dest)
        else:
            target = loose.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_limited(fh, target, budget)
    if loose.exists():
        sources.insert(0, loose)
    for source in sources:
        base = unwrap_single_folder(source)
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(base)
            if len(rel.parts) > 1:
                skipped.append(f"{rel.as_posix()} (not at batch root)")
                continue
            target = root / p.name
            if target.exists():
                errors.append(f"duplicate file name across uploads: {p.name}")
                continue
            shutil.move(str(p), target)
    shutil.rmtree(raw, ignore_errors=True)
    return root, skipped, errors


def _read_manifest(path: Path) -> tuple[list[dict], list[str], bool]:
    data = path.read_bytes()
    warnings = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
        warnings.append(f"{path.name} is not UTF-8; decoded as Windows-1252")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise BatchError(f"manifest {path.name} is empty")
    headers = {h: (h or "").strip().lower() for h in reader.fieldnames}
    if "name" not in headers.values():
        raise BatchError(f"manifest {path.name} has no 'name' column (found: {', '.join(headers.values())})")
    has_labels_col = "result_json" in headers.values()
    rows = []
    try:
        for row in reader:
            rows.append({headers.get(k, k): (v or "") for k, v in row.items() if k is not None})
    except csv.Error as exc:
        raise BatchError(f"manifest {path.name} could not be parsed: {exc}") from exc
    return rows, warnings, has_labels_col


def plan_batch(root: Path) -> BatchPlan:
    plan = BatchPlan()
    exts = supported_extensions()
    files = {p.name: p for p in root.iterdir() if p.is_file()}
    csvs = sorted(n for n in files if n.lower().endswith(".csv"))
    audio = {n: p for n, p in files.items() if Path(n).suffix.lower() in exts}
    for n in sorted(files):
        if n not in audio and n not in csvs:
            plan.warnings.append(f"{n}: ignored (not a supported audio file or CSV)")

    if len(csvs) > 1:
        plan.errors.append(f"multiple CSV files at batch root ({', '.join(csvs)}); include exactly one manifest")
        return plan
    rows: list[dict] = []
    if not csvs:
        plan.warnings.append("no CSV manifest found; all supported audio files will be processed")
    else:
        plan.manifest_name = csvs[0]
        try:
            rows, warns, has_col = _read_manifest(files[csvs[0]])
        except BatchError as exc:
            plan.errors.append(str(exc))
            return plan
        plan.warnings += warns
        if not has_col:
            plan.warnings.append("manifest has no result_json column; batch treated as unlabeled")

    items: dict[str, Item] = {}
    lower_audio = {n.lower().strip(): n for n in audio}
    for i, row in enumerate(rows, start=2):  # header is line 1
        name = row.get("name", "").strip()
        if not name:
            plan.warnings.append(f"manifest line {i}: empty name, row ignored")
            continue
        if "/" in name or "\\" in name:
            plan.warnings.append(f"manifest line {i}: '{name}' must be a file name at the batch root")
        if name in items:
            items[name].warnings.append(f"duplicate manifest row (line {i}); first row used")
            continue
        item = Item(name=name, in_manifest=True)
        label_text = row.get("result_json", "").strip()
        if label_text:
            try:
                item.label = parse_label(label_text)
            except SchemaError as exc:
                item.warnings.append(f"label ignored: {exc}")
        if name in audio:
            item.path = str(audio[name])
        elif name in files:
            item.status, item.error = "failed", f"unsupported file type '{Path(name).suffix or '(none)'}'"
        else:
            hint = lower_audio.get(name.lower())
            item.status = "failed"
            item.error = "file listed in manifest but not found in batch" + (f" (similar file: '{hint}')" if hint else "")
        items[name] = item

    for name, path in sorted(audio.items()):
        if name not in items:
            item = Item(name=name, path=str(path))
            if plan.manifest_name:
                item.warnings.append("audio file not listed in manifest; processed anyway")
            items[name] = item

    plan.items = list(items.values())
    plan.has_labels = any(it.label for it in plan.items)
    if not any(it.status == "queued" for it in plan.items):
        plan.errors.append("no processable audio files found in batch")
    return plan
