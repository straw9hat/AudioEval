import io

import pytest

from audioeval.batch import BatchError, plan_batch, safe_relpath, stage_upload
from conftest import LABEL, make_zip, manifest, speech_like, wav_bytes


def stage(tmp_path, uploads, max_bytes=50 << 20):
    return stage_upload([(n, io.BytesIO(b)) for n, b in uploads], tmp_path / "job", max_bytes, 100)


@pytest.fixture(scope="module")
def wav():
    return wav_bytes(speech_like(3.0))


def by_name(plan):
    return {it.name: it for it in plan.items}


def test_wrapped_zip_with_os_artifacts(tmp_path, wav):
    z = make_zip({
        "Voice Analyzer Assessment/a.wav": wav,
        "Voice Analyzer Assessment/b.wav": wav,
        "Voice Analyzer Assessment/labels.csv": manifest([("a.wav", LABEL), ("b.wav", None)], bom=True, crlf=True),
        "__MACOSX/Voice Analyzer Assessment/._a.wav": b"junk",
        "Voice Analyzer Assessment/.DS_Store": b"junk",
    })
    root, skipped, errors = stage(tmp_path, [("batch.zip", z)])
    plan = plan_batch(root)
    assert not errors and not plan.errors
    items = by_name(plan)
    assert set(items) == {"a.wav", "b.wav"}
    assert items["a.wav"].label["emotional_tone"] == "neutral"
    assert items["b.wav"].label is None
    assert plan.has_labels and plan.manifest_name == "labels.csv"
    assert any("system file" in s for s in skipped)


def test_folder_upload_with_relative_paths(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("eval batch/x y.wav", wav), ("eval batch/manifest.csv", manifest([("x y.wav", None)]))])
    plan = plan_batch(root)
    assert [it.name for it in plan.items] == ["x y.wav"]
    assert plan.items[0].status == "queued"


def test_missing_unmatched_duplicate_unsupported(tmp_path, wav):
    csv_bytes = manifest([("a.wav", None), ("a.wav", None), ("missing.wav", None), ("notes.txt", None), ("B.WAV", None)])
    root, _, _ = stage(tmp_path, [("a.wav", wav), ("b.wav", wav), ("extra.wav", wav), ("notes.txt", b"hi"), ("m.csv", csv_bytes)])
    items = by_name(plan_batch(root))
    assert any("duplicate" in w for w in items["a.wav"].warnings)
    assert items["missing.wav"].status == "failed" and "not found" in items["missing.wav"].error
    assert items["notes.txt"].status == "failed" and "unsupported" in items["notes.txt"].error
    assert "similar file: 'b.wav'" in items["B.WAV"].error
    assert items["extra.wav"].status == "queued" and "not listed" in items["extra.wav"].warnings[0]
    assert items["b.wav"].status == "queued"


def test_name_only_manifest_is_unlabeled(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("a.wav", wav), ("m.csv", b"name\na.wav\n")])
    plan = plan_batch(root)
    assert not plan.has_labels and plan.items[0].status == "queued"
    assert any("no result_json column" in w for w in plan.warnings)


def test_multiple_csv_is_batch_error(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("a.wav", wav), ("one.csv", b"name\na.wav\n"), ("two.csv", b"name\na.wav\n")])
    assert "multiple CSV" in plan_batch(root).errors[0]


def test_manifest_without_name_column(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("a.wav", wav), ("m.csv", b"file,result_json\na.wav,\n")])
    assert "no 'name' column" in plan_batch(root).errors[0]


def test_no_manifest_processes_audio(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("a.wav", wav)])
    plan = plan_batch(root)
    assert not plan.errors and plan.items[0].status == "queued"


def test_invalid_label_json_is_warning_not_failure(tmp_path, wav):
    root, _, _ = stage(tmp_path, [("a.wav", wav), ("m.csv", b'name,result_json\na.wav,"{bad"\n')])
    item = plan_batch(root).items[0]
    assert item.status == "queued" and item.label is None and "label ignored" in item.warnings[0]


@pytest.mark.parametrize("name", ["../evil.wav", "/etc/passwd", "C:/x.wav", "a/../../b.wav"])
def test_unsafe_paths_rejected(name):
    with pytest.raises(BatchError):
        safe_relpath(name)


def test_zip_slip_reported(tmp_path, wav):
    z = make_zip({"../../evil.wav": wav})
    _, _, errors = stage(tmp_path, [("bad.zip", z)])
    assert errors and "unsafe path" in errors[0]


def test_upload_size_limit(tmp_path, wav):
    with pytest.raises(BatchError, match="maximum allowed size"):
        stage(tmp_path, [("a.wav", wav)], max_bytes=1000)


def test_corrupt_zip_reported(tmp_path, wav):
    _, _, errors = stage(tmp_path, [("bad.zip", b"not a zip"), ("a.wav", wav)])
    assert "not a valid ZIP" in errors[0]


def test_multiple_zips_merged_and_conflicts_reported(tmp_path, wav):
    z1 = make_zip({"part1/a.wav": wav, "part1/labels.csv": manifest([("a.wav", None), ("b.wav", None)])})
    z2 = make_zip({"part2/b.wav": wav, "part2/a.wav": wav})
    root, _, errors = stage(tmp_path, [("p1.zip", z1), ("p2.zip", z2)])
    assert set(by_name(plan_batch(root))) == {"a.wav", "b.wav"}
    assert any("duplicate file name" in e for e in errors)
