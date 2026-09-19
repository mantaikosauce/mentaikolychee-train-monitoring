"""The learning loop: outcomes become labels, uploads are stored, drift is scored,
and the retrain gate runs end to end (dry run) on synthetic outcomes."""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import drift, events  # noqa: E402

# The Door test stream, used to exercise the retrain gate on real signal.
STATIC = ROOT / "repo" / "PS3" / "02_Datasets" / "Door"


def _use_tmp_log(tmp_path):
    events.EVENTS_PATH = tmp_path / "events.jsonl"
    events.ACTIONS_PATH = tmp_path / "events_actions.jsonl"
    events.UPLOADS_DIR = tmp_path / "uploads"


def test_outcome_becomes_a_label_with_its_stored_file(tmp_path):
    _use_tmp_log(tmp_path)
    events.store_upload("Upload test", "Test.csv", b"Datetime,x\n")
    rows = [{"time": events.now().isoformat(), "analysed_at": events.now().isoformat(), "subsystem": "door",
             "subsystem_name": "Door", "state": "alert", "severity": 0.9, "title": "Door cycle 3 (Close) abnormal resistance",
             "detail": "x", "file_id": "Test.csv", "train": None, "line": None, "station": None,
             "source": "run", "dataset": "Upload test"}]
    events.append_unique(rows)
    eid = events.load()["id"].iloc[0]
    events.set_status(eid, "closed", "seal replaced", outcome="confirmed")
    oc = events.outcomes()
    assert len(oc) == 1 and oc["outcome"].iloc[0] == "confirmed"
    assert oc["stored_file"].iloc[0] and Path(oc["stored_file"].iloc[0]).exists()
    with pytest.raises(ValueError):
        events.set_status(eid, "closed", outcome="maybe")


def test_drift_scores_training_like_data_as_low():
    st = drift.load_stats("door")
    assert st and st["n"] == 110
    row = {f: s["median"] for f, s in st["features"].items()}
    d = drift.score("door", row)
    assert d["level"] == "low" and d["score"] == 0.0
    far = {f: s["median"] + 50 * (s["mad"] or 1) for f, s in st["features"].items()}
    assert drift.score("door", far)["level"] == "high"


@pytest.mark.skipif(not (STATIC / "Test.csv").exists() or not (ROOT / "repo" / "PS3" / "02_Datasets").exists(),
                    reason="dataset absent")
def test_retrain_gate_dry_run_on_synthetic_door_outcomes(tmp_path):
    """Ten synthetic outcomes on the stored Door test stream; the gate must run, log a
    decision and never touch the artifact in dry-run mode."""
    _use_tmp_log(tmp_path)
    events.store_upload("Upload test", "Test.csv", (STATIC / "Test.csv").read_bytes())
    rows = []
    for i in range(1, 11):
        rows.append({"time": events.now().isoformat(), "analysed_at": events.now().isoformat(), "subsystem": "door",
                     "subsystem_name": "Door", "state": "alert", "severity": 0.9,
                     "title": f"Door cycle {i} (Close) abnormal resistance", "detail": "x", "file_id": "Test.csv",
                     "train": None, "line": None, "station": None, "source": "run", "dataset": "Upload test"})
    events.append_unique(rows)
    for eid in events.load()["id"]:
        events.set_status(eid, "closed", outcome="confirmed" if int(eid[-1], 16) % 2 else "no_fault_found")
    before = (ROOT / "subsystems" / "door" / "artifacts" / "model.joblib").stat().st_mtime
    env = {"NEBULA_EVENTS_PATH": str(events.EVENTS_PATH), "PYTHONIOENCODING": "utf-8"}
    import os
    r = subprocess.run([sys.executable, "-m", "scripts.retrain", "--dry-run", "--min-outcomes", "5"],
                       capture_output=True, text=True, cwd=ROOT, env={**os.environ, **env})
    assert r.returncode == 0, r.stderr[-1500:]
    assert "door:" in r.stdout and ("kept incumbent" in r.stdout or "PROMOTED" in r.stdout), r.stdout
    assert (ROOT / "subsystems" / "door" / "artifacts" / "model.joblib").stat().st_mtime == before


def test_upload_store_stays_under_its_budget(tmp_path, monkeypatch):
    """A long-lived instance must not fill its disk: the oldest runs are dropped, the
    newest is always kept, and a dropped run just stops offering retrain examples."""
    _use_tmp_log(tmp_path)
    monkeypatch.setattr(events, "UPLOADS_BUDGET_BYTES", 5_000)
    blob = b"x" * 2_000
    for i in range(6):
        p = events.store_upload(f"Run {i:02d}", "Test.csv", blob)
        import os as _os
        _os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))   # run i is older than run i+1
    total = sum(f.stat().st_size for f in events.UPLOADS_DIR.rglob("*") if f.is_file())
    assert total <= 5_000, f"upload store grew to {total} bytes"
    left = sorted(d.name for d in events.UPLOADS_DIR.iterdir() if d.is_dir())
    assert "Run_05" in left, "the newest run must survive"
    assert "Run_00" not in left, "the oldest run should have been dropped"
