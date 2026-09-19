"""Press every button and change every input on every page, and fail on any exception.

test_pages.py proves each page RENDERS; this proves each page survives being USED.
With the cached competition run in session and a fleet log built from it, every
widget on every page is exercised: each selectbox / radio / pill / segmented option,
both ends of every slider, every toggle and checkbox flipped, a date and a text value
typed, every button clicked. After each action the page reruns and any exception is
recorded with the page, the widget and the value that caused it.

Slow (several minutes), so it only runs when asked:

    NEBULA_FULL_UI=1 python -m pytest tests/test_interactions.py -q
    python tests/test_interactions.py          # prints a report and per-page timings

Buttons that start a full re-analysis of the heaviest data (Rail, Run all) are skipped:
they are the same code paths the cached run already executed.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest  # noqa: E402

from core import cache, events  # noqa: E402

PAGES = ["", "fleet", "live", "door", "shm", "rail", "acv", "monitor", "validation", "submission", "method"]
SKIP_BUTTON_LABELS = ("Run all", "Classify recordings")
MAX_OPTIONS = 5
# Streamlit's AppTest cannot drive these (a selectbox with a format_func, a datetime range
# slider): verified by hand in the browser instead.
SKIP_KEYS_CONTAINING = ("_ctx_station",)


def _app(page: str, log_path: Path) -> AppTest:
    os.environ["NEBULA_TEST_PAGE"] = page
    os.environ["NEBULA_EVENTS_PATH"] = str(log_path)
    events.EVENTS_PATH = log_path
    events.ACTIONS_PATH = log_path.with_name(log_path.stem + "_actions.jsonl")
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=300)
    for k, v in (cache.load() or {}).items():
        at.session_state[f"{k}_result"] = v
    return at


def _seed_log(log_path: Path) -> None:
    events.EVENTS_PATH = log_path
    events.ACTIONS_PATH = log_path.with_name(log_path.stem + "_actions.jsonl")
    rows = []
    for k, res in (cache.load() or {}).items():
        rows += events.events_from_result(k, res, {"source": "run", "dataset": "Competition test data",
                                                   "train": "NSL-01", "line": "NSL", "station": "BISHAN"})
    events.append(rows)


def _values(w) -> list:
    """Alternative values worth trying for one widget."""
    kind = type(w).__name__
    opts = list(getattr(w, "options", []) or [])
    if kind in ("Selectbox", "Radio", "SegmentedControl", "Pills", "ButtonGroup"):
        return opts[:MAX_OPTIONS]
    if kind == "Multiselect":
        return [opts[:1], opts[:2], []] if opts else []
    if kind in ("Toggle", "Checkbox"):
        return [not w.value, w.value]
    if kind == "Slider":
        lo, hi = w.min, w.max
        if isinstance(w.value, (tuple, list)):
            mid = lo + (hi - lo) / 2 if not isinstance(lo, (dt.date, dt.datetime)) else lo + (hi - lo) / 2
            return [(lo, mid), (mid, hi), (lo, hi)]
        return [lo, hi]
    if kind == "SelectSlider":
        return opts[:1] + opts[-1:]
    if kind == "DateInput":
        v = w.value
        return [v] if v else [dt.date.today()]
    if kind in ("TextInput", "TextArea"):
        return ["test", ""]
    if kind == "NumberInput":
        return [w.min if w.min is not None else 0]
    return []


def _widgets(at: AppTest) -> list:
    out = []
    for acc in ("selectbox", "radio", "segmented_control", "pills", "multiselect", "toggle", "checkbox",
                "slider", "select_slider", "date_input", "text_input", "text_area", "number_input", "button"):
        try:
            out += list(getattr(at, acc))
        except Exception:
            pass
    return out


def _ident(w) -> str:
    """A widget's stable identity: its key, or for an unkeyed widget its element id
    (derived from type and label, so it survives reruns)."""
    return getattr(w, "key", None) or f"id:{w.id}"


def _find(at: AppTest, key: str):
    for w in _widgets(at):
        if _ident(w) == key:
            return w
    return None


def exercise(page: str, workdir: Path) -> tuple[list[str], dict]:
    log_path = workdir / f"events_{page or 'home'}.jsonl"
    _seed_log(log_path)
    at = _app(page, log_path)
    t = time.time()
    at.run()
    timing = {"first_run_s": round(time.time() - t, 2)}
    errors = [f"{page or 'dashboard'} · first render: {e.value}" for e in at.exception]
    # a script that fails to COMPILE raises no element exception: it just renders nothing
    if not errors and len(at.main.children) == 0:
        errors.append(f"{page or 'dashboard'} · first render: page rendered nothing (script did not run)")
    seen, n_actions, t_actions = set(), 0, 0.0
    # widgets can appear after an interaction (an expander's contents, a custom range),
    # so keep sweeping until no new key turns up
    for _ in range(3):
        keys = [_ident(w) for w in _widgets(at) if _ident(w) not in seen]
        if not keys:
            break
        for key in keys:
            seen.add(key)
            w = _find(at, key)
            if w is None:
                continue
            kind = type(w).__name__
            if any(x in key for x in SKIP_KEYS_CONTAINING):
                continue
            if kind == "Slider" and key.startswith("top_win_"):      # datetime range slider
                continue
            if kind == "Button":
                if any(str(w.label).startswith(s) for s in SKIP_BUTTON_LABELS):
                    continue
                actions = [("click", None)]
            elif kind == "Selectbox":
                # by position: the displayed options may be formatted (title-cased etc.)
                actions = [("index", i) for i in range(min(MAX_OPTIONS, len(w.options)))]
            else:
                actions = [("set", v) for v in _values(w)]
            for how, v in actions:
                w = _find(at, key)
                if w is None:
                    break
                try:
                    t = time.time()
                    (w.click() if how == "click" else w.select_index(v) if how == "index" else w.set_value(v)).run()
                    t_actions += time.time() - t
                    n_actions += 1
                except Exception as exc:                    # the harness itself failed
                    errors.append(f"{page or 'dashboard'} · {kind} {key} = {v!r}: harness {type(exc).__name__}: {exc}")
                    at = _app(page, log_path)                # a stuck widget value must not cascade
                    at.run()
                    continue
                for e in at.exception:
                    errors.append(f"{page or 'dashboard'} · {kind} {key} = {v!r}: {e.value}")
                if at.exception:
                    at = _app(page, log_path)            # start clean so one bug does not cascade
                    at.run()
    timing.update({"actions": n_actions, "mean_action_s": round(t_actions / max(1, n_actions), 2),
                   "widgets": len(seen)})
    return errors, timing


needs_cache = pytest.mark.skipif(cache.load() is None, reason="no cached run (predictions/analysis_cache.pkl)")
full_only = pytest.mark.skipif(os.environ.get("NEBULA_FULL_UI") != "1", reason="set NEBULA_FULL_UI=1 to run")


@full_only
@needs_cache
@pytest.mark.parametrize("page", PAGES)
def test_every_widget(page, tmp_path):
    errors, _ = exercise(page, tmp_path)
    assert not errors, "\n".join(errors)


if __name__ == "__main__":
    only = sys.argv[1:] or PAGES
    all_errors = []
    with tempfile.TemporaryDirectory() as d:
        for p in only:
            p = "" if p in ("dashboard", "home") else p
            errs, tm = exercise(p, Path(d))
            all_errors += errs
            print(f"{p or 'dashboard':11s} {tm}  errors={len(errs)}", flush=True)
            for e in errs:
                print("   ", e[:400], flush=True)
    print(f"\nTOTAL errors: {len(all_errors)}")
    sys.exit(1 if all_errors else 0)
