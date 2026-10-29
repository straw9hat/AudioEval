import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from audioeval.auth import hash_password
from audioeval.config import Settings
from audioeval.models import ModelBundle
from audioeval.pipeline import Analyzer
from audioeval.web import create_app
from conftest import LABEL, make_zip, manifest, speech_like, wav_bytes

BASE = "https://testserver"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOEVAL_USERS", f"eval:{hash_password('correct horse battery', 1000)},other:{hash_password('another password!', 1000)}")
    monkeypatch.setenv("AUDIOEVAL_SECRET_KEY", "test-secret")
    settings = Settings(data_dir=str(tmp_path / "jobs"), workers=2)
    app = create_app(settings, analyzer_factory=lambda: Analyzer(settings, models=ModelBundle()))
    with TestClient(app, base_url=BASE) as c:
        yield c


def login(c, user="eval", pw="correct horse battery"):
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return c.get("/api/me").json()["csrf"]


def wait(c, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        job = c.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("running", "validating"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def batch_zip():
    wav = wav_bytes(speech_like(6))
    return make_zip({
        "evaluation_batch/call_001.wav": wav,
        "evaluation_batch/call_002.wav": wav_bytes(speech_like(6, seed=4)),
        "evaluation_batch/broken.wav": b"RIFF not really audio",
        "evaluation_batch/labels.csv": manifest([
            ("call_001.wav", LABEL), ("call_002.wav", LABEL | {"emotional_tone": "upset"}),
            ("broken.wav", None), ("missing.wav", None),
        ]),
    })


def test_requires_login(client):
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/healthz").json() == {"status": "ok"}


def test_security_headers(client):
    r = client.get("/login")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_bad_login_and_rate_limit(client):
    for _ in range(5):
        assert client.post("/api/login", json={"username": "eval", "password": "nope"}).status_code == 401
    assert client.post("/api/login", json={"username": "eval", "password": "correct horse battery"}).status_code == 429


def test_rate_limit_ignores_spoofed_forwarded_for(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOEVAL_USERS", f"eval:{hash_password('correct horse battery', 1000)}")
    monkeypatch.setenv("AUDIOEVAL_TRUST_PROXY", "true")
    settings = Settings(data_dir=str(tmp_path / "jobs"))
    with TestClient(create_app(settings, analyzer_factory=lambda: None), base_url=BASE) as c:
        for i in range(5):
            headers = {"x-forwarded-for": f"10.0.0.{i}, 203.0.113.9"}
            assert c.post("/api/login", json={"username": f"u{i}", "password": "x"}, headers=headers).status_code == 401
        headers = {"x-forwarded-for": "10.9.9.9, 203.0.113.9"}
        assert c.post("/api/login", json={"username": "eval", "password": "correct horse battery"}, headers=headers).status_code == 429
        headers = {"x-forwarded-for": "198.51.100.1"}
        assert c.post("/api/login", json={"username": "eval", "password": "correct horse battery"}, headers=headers).status_code == 200


def test_login_requires_json(client):
    assert client.post("/api/login", data={"username": "eval", "password": "x"}).status_code == 415


def test_upload_requires_csrf(client):
    login(client)
    r = client.post("/api/jobs", files=[("files", ("b.zip", batch_zip(), "application/zip"))])
    assert r.status_code == 403


def test_full_batch_workflow(client):
    csrf = login(client)
    r = client.post("/api/jobs", headers={"X-CSRF-Token": csrf},
                    files=[("files", ("batch.zip", batch_zip(), "application/zip"))], data={"paths": "batch.zip"})
    assert r.status_code == 200, r.text
    job = wait(client, r.json()["id"])
    assert job["status"] == "completed_with_errors"
    items = {i["name"]: i for i in job["items"]}
    assert items["call_001.wav"]["status"] == "done"
    assert items["call_001.wav"]["duration_s"] > 0
    assert items["call_001.wav"]["processing_s"] >= 0
    assert items["broken.wav"]["status"] == "failed" and items["broken.wav"]["error"]
    assert "not found" in items["missing.wav"]["error"]
    assert job["score"]["n_scored"] == 2
    # Labels never influence inference: identical audio inputs differ only in label.
    assert items["call_001.wav"]["prediction"]["emotional_tone"] == "neutral"

    csv_text = client.get(f"/api/jobs/{job['id']}/download/predictions.csv").text
    assert csv_text.splitlines()[0] == "name,result_json"
    assert "call_001.wav" in csv_text and "broken.wav" not in csv_text
    err = client.get(f"/api/jobs/{job['id']}/download/errors.csv").text
    assert "broken.wav" in err and "missing.wav" in err
    results = client.get(f"/api/jobs/{job['id']}/download/results.json").json()
    assert {r["name"] for r in results["results"]} == {"call_001.wav", "call_002.wav", "broken.wav", "missing.wav"}

    # Another user cannot see the job.
    client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    login(client, "other", "another password!")
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/download/results.json").status_code == 404


def test_folder_upload_and_invalid_batch(client):
    csrf = login(client)
    wav = wav_bytes(speech_like(4))
    files = [("files", ("a.wav", wav, "audio/wav")), ("files", ("labels.csv", b"name\na.wav\n", "text/csv"))]
    r = client.post("/api/jobs", headers={"X-CSRF-Token": csrf}, files=files,
                    data={"paths": ["my batch/a.wav", "my batch/labels.csv"]})
    job = wait(client, r.json()["id"])
    assert job["status"] == "completed" and job["items"][0]["prediction"]

    r = client.post("/api/jobs", headers={"X-CSRF-Token": csrf},
                    files=[("files", ("notes.txt", b"hello", "text/plain"))], data={"paths": "notes.txt"})
    job = r.json()
    assert job["status"] == "invalid" and job["errors"]


def test_label_independence(tmp_path):
    settings = Settings(data_dir=str(tmp_path))
    analyzer = Analyzer(settings, models=ModelBundle())
    x = speech_like(6, seed=9)
    p = tmp_path / "a.wav"
    import soundfile as sf
    sf.write(p, x, 16000)
    assert analyzer.analyze(p).prediction == analyzer.analyze(p).prediction
    assert np.isfinite(analyzer.analyze(p).prediction["confidence"])
