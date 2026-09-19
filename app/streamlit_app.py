"""Nebula Wayside - train condition monitoring console.

Run from the project root:

    streamlit run app/streamlit_app.py

The app contains no modelling code. Every prediction comes from a subsystem
package's predict()/analyze(), discovered through core.registry, and every
download passes core.submission's schema validator first.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for p in (str(PROJECT_ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib  # noqa: E402
import os  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402


def _reload_project_modules(modules) -> bool:
    """Reload every project module once per code version.

    Hosted Streamlit re-runs this script when a deploy lands but keeps the modules
    it imported earlier, so a new script can meet an old module. The newest mtime
    across the script and the modules is the version stamp: when any of them
    changes, reload them all in dependency order. A few milliseconds, once per
    change per process."""
    import core as _core_pkg
    files = [__file__] + [getattr(m, "__file__", None) for m in modules]
    stamp = max(os.path.getmtime(f) for f in files if f and os.path.exists(f))
    if getattr(_core_pkg, "__script_stamp__", None) == stamp:
        return False
    for m in modules:
        try:
            importlib.reload(m)
        except Exception:
            pass
    _core_pkg.__script_stamp__ = stamp
    return True


import charts  # noqa: E402
import components as ui  # noqa: E402
import insight  # noqa: E402
import livemap  # noqa: E402
import lta_live  # noqa: E402
import schematics  # noqa: E402
import core.cache as _core_cache  # noqa: E402
import core.decisions as _core_decisions  # noqa: E402
import core.events as _core_events  # noqa: E402
import core.quickdrop as _core_quickdrop  # noqa: E402
import core.registry as _core_registry  # noqa: E402
import core.submission as _core_submission  # noqa: E402
import subsystems.generic.monitor as _generic_monitor  # noqa: E402

import network as _network  # noqa: E402
import theme as _theme  # noqa: E402

_reload_project_modules((_core_events, _core_cache, _core_decisions, _core_quickdrop, _core_registry, _core_submission,
                         _generic_monitor, _theme, ui, charts, _network, livemap, insight, schematics))
# rebind the names this script uses, in case a module object was replaced
result_cache, event_log, quickdrop, monitor = _core_cache, _core_events, _core_quickdrop, _generic_monitor
decisions = _core_decisions
from core.registry import DATA_ROOT, SUBSYSTEMS, SubsystemSpec  # noqa: E402,F811
from core.submission import SCHEMAS, build_predictions_zip, validate_submission  # noqa: E402,F811
from theme import T, css  # noqa: E402,F811

st.set_page_config(page_title="Nebula Wayside", page_icon="🚆", layout="wide")


def _resolve_theme() -> str:
    """The console is light only: one palette, validated for colour-vision deficiency."""
    return "light"


_theme.set_theme(_resolve_theme())
_tokens_cache_key = _theme.THEME
st.markdown(css(), unsafe_allow_html=True)

IDENTITY = {"door": "subsystem-door", "shm": "subsystem-shm",
            "rail": "subsystem-rail", "acv": "subsystem-acv"}

#: Illustrative planning bands for SHM. Miner's rule fixes failure at D = 1;
#: where an operator starts watching or acting is their call, not the model's.
SHM_WATCH, SHM_ALERT = 0.5, 0.8
#: What Normal / Watch / Fault mean for each subsystem: the exact rules the app applies.
HEALTH_BANDS = {
    "door": ("Door", "Model's chance that a door cycle shows abnormal resistance",
             [("ok", "under 50%: cycle classed Normal"),
              ("alert", "50% or more: Abnormal resistance, inspect the door")]),
    "shm": ("Structural health", "Fatigue damage D (Miner's rule, 1 = end of fatigue life)",
            [("ok", f"D below {SHM_WATCH:.1f} (under {SHM_WATCH:.0%} of life used)"),
             ("watch", f"D {SHM_WATCH:.1f} to {SHM_ALERT:.1f}: plan an inspection"),
             ("alert", f"D {SHM_ALERT:.1f} or more: act before D = 1")]),
    "rail": ("Rail", "Corrugation verdict per axle-box recording",
             [("ok", "Normal: no corrugation found"),
              ("alert", "Side I or Side II: corrugated rail on that side")]),
    "acv": ("Air conditioning", "How much hotter the #1 car runs than the #2 car during cooling",
            [("watch", "lead under 0.03 °C: #1 is a weak suspect"),
             ("alert", "lead 0.03 °C or more (the ACV page also counts 1+ point more hot time): #1 is the likely leak")]),
}


def health_key(keys=("door", "shm", "rail", "acv")) -> None:
    html(ui.health_bands([HEALTH_BANDS[k] for k in keys]))


METRIC_SHORT = {"door": "IoU-weighted F1", "shm": "max(0, 1 − MAPE)",
                "rail": "macro F1", "acv": "rank decay"}


_SVG_ANIMATION = __import__("re").compile(
    r"<animate(?:Transform|Motion)?\b[^>]*?(?:/>|>.*?</animate(?:Transform|Motion)?>)", __import__("re").S)


def html(s: str) -> None:
    """Render HTML. Every page shows its final state instantly: SVG animations are
    stripped here, in the one place all schematics pass through, so a needle or door
    leaf is drawn where it ends rather than sweeping into place."""
    st.markdown(_SVG_ANIMATION.sub("", s), unsafe_allow_html=True)


def txt(v, default: str = "—") -> str:
    """Display string for a value that may be None or NaN. Kept in this file on purpose:
    the script reloads on every deploy, imported modules only on a restart."""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return default
    except Exception:
        return default
    return str(v) if str(v) not in ("", "nan", "None") else default


_plot_n = {"n": 0}


def engineer_view() -> bool:
    return st.session_state.get("view_mode_persist", "Operator") == "Engineer"


def eng_only(what: str) -> bool:
    """Operator view shows the verdict and what to do; Engineer view adds the evidence.
    Returns True in Engineer view; in Operator view leaves a one-line pointer instead."""
    from html import escape as _esc
    if engineer_view():
        return True
    html(f'<div class="nw-engnote">Engineer view adds {_esc(what)}. Switch to <b>Engineer</b> at the top of the page.</div>')
    return False


def plot(fig, key: str | None = None, always: bool = False) -> None:
    """Every chart gets its own key, so two empty figures on one page can never collide.
    Charts render in both views. Operator view used to hide them, which left section
    headings and captions sitting over empty space; `always` is kept for callers."""
    _plot_n["n"] += 1
    # Vertical toolbar on the right edge: a horizontal one sits on top of the legend.
    # The right margin gives it its own gutter, so it never covers the last points.
    fig.update_layout(modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)"))
    # Inner spacing lives in the figure's margins (the frame around it takes no layout
    # space, see theme.py); the paper is transparent so the frame's hairline shows.
    m = fig.layout.margin
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=max(16, m.l or 0), r=max(48, m.r or 0), t=max(14, m.t or 0), b=max(12, m.b or 0)))
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key=key or f"fig_{_plot_n['n']}")


#: One toolbar on every chart: zoom in (+), zoom out (-), pan, reset, save as PNG.
#: It is always visible, so a chart zoomed by an accidental drag can always be reset.
PLOT_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "scrollZoom": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "toggleSpikelines",
                               "hoverClosestCartesian", "hoverCompareCartesian"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def _persist(widget_key: str, store_key: str) -> None:
    st.session_state[store_key] = st.session_state[widget_key]


def lta_key_field(label_visible: bool = True) -> str:
    """Kept for callers of the earlier key UI. The key now loads automatically and is
    never displayed; see lta_key_input."""
    return lta_key_input("field")

def view_toggle() -> None:
    """The Operator / Engineer view switch, on every page (the console is light only). Widget state is dropped by Streamlit
    when a page does not draw the widget, so the chosen values are copied into plain
    session keys that every page reads."""
    c1, c2 = st.columns([1, 3])
    with c1:
        st.segmented_control("View", ["Operator", "Engineer"],
                             default=st.session_state.get("view_mode_persist", "Operator"),
                             key="view_mode", label_visibility="collapsed",
                             on_change=_persist, args=("view_mode", "view_mode_persist"),
                             help="Operator: actions and plain words. Engineer: every chart, table and model detail.")
    with c2:
        st.caption("Operator: what to do. Engineer: adds every chart and model detail."
                   if not engineer_view() else "Engineer view: all charts and model detail are shown.")


def _pct(v: float) -> str:
    """Percent with one decimal near the ends, so 99.6% and 99.9% do not both read 100%."""
    return f"{v:.1%}" if (v >= 0.99 or v <= 0.01) else f"{v:.0%}"


#: Human labels for event-log columns wherever the log is shown as a table.
EVENT_COLS = {"time": st.column_config.DatetimeColumn("When", format="D MMM YYYY, HH:mm"),
              "subsystem_name": "Subsystem", "state": "State", "status": "Status", "title": "Event",
              "detail": "Evidence", "train": "Train", "line": "Line", "station": "Station",
              "file_id": "Source file", "outcome": "Finding", "stored_file": "Stored file"}


def _door_when(s) -> str:
    """The logger's stamp (2023-7-5-0-22-38-967) as people read it: 05 Jul 2023 · 00:22:38."""
    try:
        return _door_time(s).strftime("%d %b %Y · %H:%M:%S")
    except Exception:
        return str(s)


def plain_error(exc: Exception) -> str:
    """A model's input error in words a user can act on. The subsystems raise precise
    technical messages; the few that quote Python internals are translated here."""
    import re
    msg = str(exc)
    if "codec can't decode" in msg or "invalid start byte" in msg:
        return (msg.split(":")[0] + ": this is not a readable text CSV. It may be a different kind of file "
                "renamed to .csv; upload the original CSV export.")
    if "No columns to parse" in msg:
        return msg.split(":")[0] + ": the file is empty."
    m = re.search(r"Invalid rail-corrugation schema: missing=\[([^\]]*)\]", msg)
    if m:
        cols = [c.strip(" '\"") for c in m.group(1).split(",")][:3]
        return (msg.split(":")[0] + ": this is not a rail axle-box recording. It is missing columns such as "
                + ", ".join(cols) + ". Upload one of the Test*.csv recordings.")
    m = re.search(r"missing required column\(s\): (.*)", msg)
    if m:
        cols = [c.strip(" '\"") for c in m.group(1).split(",")][:3]
        return ("This is not a door-controller stream. It is missing columns such as " + ", ".join(cols)
                + ". Upload Test.csv or a file in the same format.")
    return msg


def _door_time(s: str) -> pd.Timestamp:
    """The Door stream's unpadded Y-M-D-H-M-S-ms stamp -> Timestamp."""
    y, mo, d, h, mi, sec, ms = (int(p) for p in str(s).split("-"))
    return pd.Timestamp(y, mo, d, h, mi, sec) + pd.Timedelta(milliseconds=ms)


def _window(times: pd.Series, key: str, label: str = "Time window"):
    """Pick a time window: one-tap presets, with a slider only for a custom range.
    Returns (lo, hi) as naive datetimes."""
    t = pd.to_datetime(times)
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_localize(None)
    lo, hi = t.min().to_pydatetime(), t.max().to_pydatetime()
    if lo >= hi:
        return lo, hi
    span = hi - lo
    presets = {"Whole file": None}
    for name, delta in (("Last 24 h", pd.Timedelta(hours=24)), ("Last 6 h", pd.Timedelta(hours=6)),
                        ("Last hour", pd.Timedelta(hours=1)), ("Last 10 min", pd.Timedelta(minutes=10))):
        if delta < span:
            presets[name] = delta
    presets["Custom"] = "custom"
    pick = st.pills(label, list(presets), default="Whole file", key=f"{key}_preset") or "Whole file"
    if pick == "Custom":
        return st.slider("Custom range", min_value=lo, max_value=hi, value=(lo, hi),
                         format="D MMM HH:mm", key=key, label_visibility="collapsed")
    if presets[pick] is None:
        return lo, hi
    return (pd.Timestamp(hi) - presets[pick]).to_pydatetime(), hi


def _window_note(lo, hi, n_in: int, what: str) -> None:
    span = pd.Timestamp(hi) - pd.Timestamp(lo)
    h = span.total_seconds() / 3600
    dur = f"{h / 24:.1f} days" if h >= 48 else f"{h:.1f} h" if h >= 1 else f"{span.total_seconds() / 60:.0f} min"
    html(f'<div class="nw-winnote">Window <b>{pd.Timestamp(lo):%d %b %H:%M}</b> → <b>{pd.Timestamp(hi):%d %b %H:%M}</b>'
         f' · {dur} · <b>{n_in:,}</b> {what}</div>')


def top_n_panel(key: str, res: dict) -> None:
    """Top 3-10 of whatever a subsystem assesses, ranked by a measure the user picks,
    over a time window wherever the data carries time. It only re-orders what the
    model already produced; the official verdict and submission are unaffected."""
    if not res:
        return
    title = {"door": "Top door cycles", "shm": "Top fatigue hot spots",
             "rail": "Top rail recordings", "acv": "Top cars"}[key]
    html(ui.section(title))
    c1, c2, c3 = st.columns([1, 1.3, 2.2], gap="medium")
    with c1:
        n = st.slider("How many", 3, 10, 5, key=f"top_n_{key}")
    rows: list[dict] = []

    if key == "door":
        d = res.get("cycles")
        if d is None or d.empty:
            st.caption("No cycles to rank.")
            return
        d = d.copy()
        d["t"] = [_door_time(s) for s in d["start_time"]]
        with c2:
            by = st.selectbox("Rank by", ["Chance of abnormal resistance", "Sustained motor current"], key="top_by_door")
        with c3:
            lo, hi = _window(d["t"], "top_win_door")
        d = d[(d["t"] >= lo) & (d["t"] <= hi)]
        _window_note(lo, hi, len(d), "cycles in the window")
        col = "p_abnormal" if by.startswith("Chance") else "cur_mean_mid"
        d = d.sort_values([col, "cur_mean_mid"], ascending=False).head(n)
        top = max(float(d[col].max()), 1e-9) if len(d) else 1.0
        for i, r in enumerate(d.itertuples(), 1):
            rows.append({"rank": i, "title": f"Cycle {r.cycle} · {r.operation} · {r.prediction}",
                         "detail": f"{_door_when(r.start_time)} · {r.duration_s:.2f} s · {r.cur_mean_mid:.0f} mA sustained",
                         "value": _pct(r.p_abnormal) if col == "p_abnormal" else f"{r.cur_mean_mid:.0f} mA",
                         "frac": getattr(r, col) / top,
                         "state": "alert" if r.prediction == "Abnormal resistance" else "ok"})

    elif key == "acv":
        files = res.get("files") or []
        if not files:
            return
        f = files[0]
        if len(files) > 1:
            with c3:
                pick = st.selectbox("Case", [x["file_id"] for x in files], key="top_acv_case")
            f = next(x for x in files if x["file_id"] == pick)
        ex = f.get("excess_full")
        if ex is None:
            ex = f.get("excess_timeline")          # results saved before full resolution was kept
        if ex is None or ex.empty:
            st.caption("No cooling timeline in this case.")
            return
        ex = ex.copy()
        ex["time"] = pd.to_datetime(ex["time"])
        with c2:
            by = st.selectbox("Rank by", ["Official ranking (whole file)", "Mean excess over the other cars",
                                          "Share of time more than 2 °C hotter"],
                              key="top_by_acv",
                              help="How much hotter each car ran than the median of the other cars, during cooling.")
        official = by.startswith("Official")
        with c3:
            if official:
                st.caption("The official ranking always uses the whole file. Pick another measure to "
                           "re-rank the cars inside a time window.")
                lo, hi = ex["time"].min(), ex["time"].max()
            else:
                lo, hi = _window(ex["time"], "top_win_acv")
        w = ex[(ex["time"] >= lo) & (ex["time"] <= hi)]
        cars = [c for c in ex.columns if c != "time"]
        pm = f.get("peer_mean") or f.get("scores") or {}
        hf = f.get("hot_fraction") or {}
        n_valid = int(w[cars].notna().any(axis=1).sum())
        if not official:
            _window_note(lo, hi, n_valid, "cooling readings in the window")
        if official:
            order = [c for c in f["ranking"]][:n]
            vals = {c: float(hf.get(c, 0)) for c in order}
        else:
            means = {c: float(w[c].mean()) for c in cars}
            if by.startswith("Share"):
                vals = {c: float((w[c].dropna() > 2).mean()) if w[c].notna().any() else float("nan") for c in cars}
            else:
                vals = dict(means)
            vals = {c: v for c, v in vals.items() if v == v}
            # ties (e.g. no car ever 2 °C hotter) are broken by the mean excess
            order = sorted(vals, key=lambda c: (vals[c], means.get(c, float("-inf"))), reverse=True)[:n]
            if by.startswith("Share") and vals and max(vals.values()) == 0:
                html(ui.chip("ok", "No car ran more than 2 °C hotter in this window",
                             "order below falls back to mean excess"))
        if not order:
            st.caption("No cooling readings in this window: widen it.")
            return
        share = official or by.startswith("Share")
        src = ex if official else w
        hot_n = {c: (int((src[c].dropna() > 2).sum()), int(src[c].notna().sum())) for c in cars}
        top = max([abs(v) for v in vals.values()] + [1e-9])
        for i, c in enumerate(order, 1):
            v = vals.get(c, float("nan"))
            rank = f["ranking"].index(c) + 1 if c in f["ranking"] else None
            if official:
                detail = f"{pm.get(c, 0):+.2f} °C mean excess over the other cars"
            else:
                move = (rank - i) if rank else 0
                arrow = f"▲{move} vs official" if move > 0 else f"▼{-move} vs official" if move < 0 else "same as official"
                detail = f"official rank #{rank} · {arrow}"
            if share:
                k, m = hot_n.get(c, (0, 0))
                detail += f" · {k:,} of {m:,} cooling readings more than 2 °C hotter"
            rows.append({"rank": i, "title": f"Car {c}", "detail": detail,
                         "value": ((f"{v:.2%}" if 0 < v < 0.01 else f"{v:.1%}") + " hot" if share else f"{v:+.2f} °C") if v == v else "—",
                         "frac": max(v, 0) / top if v == v else 0,
                         # colour only a car that is actually hotter; a cooler-than-peers car in
                         # the top 3 of a short window is not a warning
                         "state": ("alert" if i == 1 else "watch" if i <= 3 else "") if (official or v > 0) else ""})
        st.caption("Each value compares a car with the median of the other cars at the same moment, "
                   "during cooling only. Try Last 6 h or Last hour to see whether a gap is recent.")

    elif key == "rail":
        files = res.get("files") or []
        with c2:
            by = st.selectbox("Rank by", ["Chance of corrugation (either side)", "Chance of Side I",
                                          "Chance of Side II", "Train speed"], key="top_by_rail")
        with c3:
            only = st.toggle("Corrugated verdicts only", value=False, key="top_rail_only")
            st.caption("Each recording is one second with no clock time, so there is no time window.")
        def val(f):
            p = f.get("proba", {})
            return {"Chance of corrugation (either side)": 1 - p.get("Normal", 0), "Chance of Side I": p.get("Side I", 0),
                    "Chance of Side II": p.get("Side II", 0),
                    "Train speed": (f.get("speed") or {}).get("speed_km_h", 0)}[by]
        pool = [f for f in files if not only or f["prediction"] != "Normal"]
        pool = sorted(pool, key=val, reverse=True)[:n]
        top = max([val(f) for f in pool] + [1e-9])
        for i, f in enumerate(pool, 1):
            v = val(f)
            rows.append({"rank": i, "title": f"{f['file_id']} · {f['prediction']}",
                         "detail": " · ".join(f"P({k}) {_pct(v2)}" for k, v2 in f.get("proba", {}).items())
                                   + f" · {(f.get('speed') or {}).get('speed_km_h', 0):.0f} km/h",
                         "value": f"{v:.0f} km/h" if by == "Train speed" else _pct(v), "frac": v / top,
                         "state": "alert" if f["prediction"] != "Normal" else "ok"})

    elif key == "shm":
        files = res.get("files") or []
        with c2:
            by = st.selectbox("Rank by", ["Fatigue damage", "Largest stress range", "Stress cycles counted"],
                              key="top_by_shm")
        with c3:
            st.caption("Stress files carry no timestamps, so there is no time window.")
        col = {"Fatigue damage": "damage", "Largest stress range": "max_range",
               "Stress cycles counted": "n_cycles"}[by]
        pool = sorted(files, key=lambda f: f.get(col, 0), reverse=True)[:n]
        top = max([float(f.get(col, 0)) for f in pool] + [1e-9])
        for i, f in enumerate(pool, 1):
            v, d_ = float(f.get(col, 0)), float(f["damage"])
            rows.append({"rank": i, "title": f["file_id"],
                         "detail": f"damage {d_:.3f} ({d_:.0%} of fatigue life) · largest range {f.get('max_range', 0):.1f} · "
                                   f"{f.get('n_cycles', 0):,.0f} cycles",
                         "value": f"{v:.3f}" if col == "damage" else f"{v:,.1f}" if col == "max_range" else f"{v:,.0f}",
                         "frac": v / top, "state": "alert" if d_ >= SHM_ALERT else "watch" if d_ >= SHM_WATCH else "ok"})

    if rows:
        html(ui.top_list(rows))
    else:
        st.caption("Nothing in the selected window.")


def drift_chip(res: dict, key: str) -> None:
    """One line on how far this data sits from what the model was validated on."""
    from core import drift as _dr
    if key == "door":
        d = res.get("drift")
    else:
        d = _dr.summarise([f.get("drift") for f in res["files"]])
    if not d:
        return
    state = {"low": "ok", "moderate": "watch", "high": "alert"}[d["level"]]
    word = {"low": "Data looks like the training data", "moderate": "Data drifts from the training data",
            "high": "Data far from the training data"}[d["level"]]
    html(ui.chip(state, word, f"{d['score']:.0%} of features beyond 3 MAD"
                 + (f" · {d['high_files']} file(s) high" if d.get("high_files") else "")
                 + " · verdicts carry less certainty as drift rises"))


def how_to_read(key: str) -> None:
    g = decisions.GLOSSARY[key]
    with st.expander("How to read this (for someone new to the data)"):
        st.markdown(f"**What is measured.** {g['what']}\n\n**How to read the result.** {g['read']}\n\n**What to do.** {g['act']}")


def actions_panel(acts: list[dict], title: str = "What to do now", here: str | None = None) -> None:
    """here: the subsystem page this panel sits on, so it does not link to itself."""
    html(ui.section(title))
    if not acts:
        html(ui.empty("Nothing to act on yet", ["Drop a file above, or load a dataset. Actions appear here in "
                                                "order of urgency, with the reason and who owns them."]))
        return
    for a in acts:
        html(f'<div class="nw-panel nw-act {a["state"]}" style="padding:14px 18px;margin-bottom:8px">'
             f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
             f'<span class="nw-urg {a["state"]}">{a["urgency"]}</span>'
             f'<b style="font-size:15px">{quickdrop.SUBSYSTEM_EMOJI.get(a["page"], "")} {a["action"]}</b>'
             f'<span class="muted" style="margin-left:auto;font-size:12px">{a["owner"]} · {a["subsystem"]}</span></div>'
             f'<div class="muted" style="font-size:13px;margin-top:6px">{a["why"]}</div></div>')
        if a["page"] in PAGE_BY_KEY and a["page"] != here:
            st.page_link(PAGE_BY_KEY[a["page"]], label=f"Open {a['subsystem']} →", icon=":material/arrow_forward:")


def as_files(payload: list[tuple[str, bytes]]) -> list[io.BytesIO]:
    out = []
    for name, data in payload:
        b = io.BytesIO(data)
        b.name = name
        out.append(b)
    return out


def choose_input(spec: SubsystemSpec) -> list[tuple[str, bytes]] | None:
    """Provided test data or an upload - the same two choices on every page."""
    provided = spec.test_inputs()
    options = (["Provided test data", "Upload a file"] if provided else ["Upload a file"])
    mode = st.segmented_control("Data source", options, default=options[0],
                                key=f"{spec.key}_src") or options[0]
    if mode == "Provided test data":
        what = (provided[0].name if len(provided) == 1
                else f"{len(provided)} files, {provided[0].name} to {provided[-1].name}")
        st.caption(f"From the competition test set: {what}")
        return [(p.name, p.read_bytes()) for p in provided]
    up = st.file_uploader(
        f"Drop {'one or more' if spec.multi_file else 'a'} .{'/.'.join(spec.accepts)} file"
        f"{'s' if spec.multi_file else ''} here", type=list(spec.accepts),
        accept_multiple_files=spec.multi_file, key=f"{spec.key}_upload")
    if not up:
        return None
    ups = up if isinstance(up, list) else [up]
    return [(u.name, u.getvalue()) for u in ups]


def context_panel(key: str) -> dict:
    """Which train and where: attached to every event this run produces."""
    with st.expander("Where did this data come from? (train and station, for the fleet log)"):
        df = livemap.stations()
        c1, c2, c3 = st.columns(3)
        with c1:
            line = st.selectbox("Line", ["unknown"] + list(livemap.LINES), key=f"{key}_ctx_line",
                                format_func=lambda k: LINE_NAMES.get(k, "Not known"))
        with c2:
            train = st.selectbox("Train set", ["unknown"] + (event_log.roster(line) if line != "unknown" else []),
                                 key=f"{key}_ctx_train")
        with c3:
            names = [n for n in livemap.LINES[line][1] if n in set(df["key"])] if line != "unknown" else []
            station = st.selectbox("Recorded near", ["unknown"] + names, key=f"{key}_ctx_station",
                                   format_func=lambda k: k.title() if k != "unknown" else "Not known")
        st.caption("The competition files carry no fleet metadata, so this is how an event gets a place on the "
                   "map and a train in the roster. Leave it unknown and the event still goes in the log.")
    return {"line": None if line == "unknown" else line, "train": None if train == "unknown" else train,
            "station": None if station == "unknown" else station, "source": "run",
            "dataset": f"Upload {event_log.now().strftime('%d %b %H:%M')}"}


def run_panel(spec: SubsystemSpec, button: str):
    """Input + run button. Returns the stored result for this subsystem, if any."""
    payload = choose_input(spec)
    ctx = context_panel(spec.key)
    if st.button(button, type="primary", disabled=payload is None, key=f"{spec.key}_run") and payload is not None:
        try:
            if spec.key in ("shm", "rail", "acv"):
                verb = {"shm": "Rainflow-counted", "rail": "Analysed", "acv": "Ranked"}[spec.key]
                bar = st.progress(0.0, text="Starting...")

                def tick(i, n, name):
                    bar.progress(i / n, text=f"{verb} {name}  ({i}/{n})")

                res = spec.module.analyze(as_files(payload), progress=tick)
                bar.empty()
            else:
                with st.spinner("Analysing..."):
                    res = spec.module.analyze(as_files(payload))
            st.session_state[f"{spec.key}_result"] = res
            for name, data in payload:
                event_log.store_upload(ctx.get("dataset"), name, data)
            added, skipped = event_log.append_unique(event_log.events_from_result(spec.key, res, ctx))
            st.toast(f"{added} new event(s) logged"
                     + (f", {skipped} already in the log (same file, same verdicts)" if skipped else ""), icon="✅")
        except (ValueError, FileNotFoundError) as exc:
            st.session_state.pop(f"{spec.key}_result", None)
            html(ui.verdict("unknown", spec.name, "This input could not be assessed",
                            plain_error(exc), "Check the file is the right format for this "
                            "subsystem and try again.", "no prediction was made"))
            return None
    return st.session_state.get(f"{spec.key}_result")


def download(spec: SubsystemSpec, df: pd.DataFrame) -> None:
    errors = validate_submission(spec.key, df)
    if errors:
        st.error("Not downloadable - the output failed schema validation:\n\n- "
                 + "\n- ".join(errors))
        return
    st.download_button(f"Download {SCHEMAS[spec.key].filename}",
                       df.to_csv(index=False).encode(), SCHEMAS[spec.key].filename,
                       "text/csv", type="primary", key=f"{spec.key}_dl")


def evidence_line(card: dict, metric_short: str) -> str:
    v = card["validation"]
    mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
    std = v.get("std_iou_weighted_f1", v.get("std_score"))
    return f"{metric_short} {mean:.3f} ± {std:.3f} · {v['split']} · model {card['model_version']}"


# =================================================================== pages

def session_results() -> dict:
    """Results of this session only. Nothing is loaded behind the user's back: the
    competition test run is a dataset the user picks in the data-source bar."""
    return {k: st.session_state.get(f"{k}_result") for k in SUBSYSTEMS}


LIVE_ONLY = "Live only (today's events and live feeds)"
EVERYTHING = "Everything in the log"


def data_source_bar() -> tuple[str, "pd.DataFrame"]:
    """The one control that decides what a page shows: live only, one dataset, or all.
    Returns (choice, events filtered to that choice). Also manages datasets."""
    log = event_log.with_status(event_log.load())
    ds = event_log.datasets(log)
    names = list(ds["dataset"]) if len(ds) else []
    options = [LIVE_ONLY] + names + ([EVERYTHING] if names else [])
    cached_available = result_cache.CACHE_PATH.exists() and "Competition test data (cached run)" not in names
    # a button below may ask for a different selection: apply it before the widget exists
    wanted = st.session_state.pop("_select_source", None)
    if wanted in options:
        st.session_state["data_source"] = wanted
    elif st.session_state.get("data_source") not in options:
        st.session_state["data_source"] = LIVE_ONLY
    choice = st.selectbox("Data source", options, key="data_source",
                          help="A fresh session starts on live only. Pick a dataset you uploaded, or everything.")
    with st.expander(f"Manage datasets ({len(ds)})", expanded=False):
        if True:
            if cached_available:
                st.caption("The competition test data has a cached run that can be loaded as a dataset.")
                if st.button("Load competition test run", key="ds_load_cache"):
                    cached = result_cache.load() or {}
                    for k, v in cached.items():
                        st.session_state[f"{k}_result"] = v
                    rows = []
                    for k, v in cached.items():
                        rows += event_log.events_from_result(k, v, {"source": "run", "dataset": "Competition test data (cached run)"})
                    a, sk = event_log.append_unique(rows)
                    st.session_state["_select_source"] = "Competition test data (cached run)"
                    st.rerun()
            if len(ds):
                for r in ds.itertuples():
                    a, b = st.columns([3, 1])
                    with a:
                        st.markdown(f"**{r.dataset}**  \n{r.events} events · {r.faults} faults · "
                                    f"{event_log.fmt_time(r.first, '%d %b %Y')} → {event_log.fmt_time(r.last, '%d %b %Y')}")
                    with b:
                        if st.button("Remove", key=f"ds_rm_{abs(hash(r.dataset))}", width="stretch"):
                            event_log.remove_dataset(r.dataset)
                            for k in SUBSYSTEMS:
                                st.session_state.pop(f"{k}_result", None)
                            st.session_state["_select_source"] = LIVE_ONLY
                            st.rerun()
            else:
                st.caption("No datasets yet. Analyse a file on any subsystem page, or drop one on the dashboard.")
    ev = source_events(choice, log)
    if choice == LIVE_ONLY and len(ev) and ev["station"].notna().sum() == 0 and names:
        st.caption("Today's events carry no train or station yet, so the map has nothing to place. Pick a dataset "
                   "or Everything above to see located events, or choose a train and station when analysing a file.")
    return choice, ev


def source_events(choice: str, log: "pd.DataFrame") -> "pd.DataFrame":
    """The log rows a data-source choice covers: today's for live only, one dataset, or all."""
    if not len(log):
        return log.reset_index(drop=True)
    if choice == LIVE_ONLY:
        ev = log[log["time"] >= pd.Timestamp(event_log.now()).normalize()]
    elif choice == EVERYTHING:
        ev = log
    else:
        ev = log[log["dataset"] == choice]
    return ev.reset_index(drop=True)


def open_counts(ev: "pd.DataFrame") -> dict:
    """Open (unresolved) fault and watch items per subsystem key in these log rows."""
    out = {}
    if not len(ev) or "status" not in ev:
        return out
    live = ev[ev["status"] == "open"]
    for k in SUBSYSTEMS:
        sub = live[live["subsystem"] == k]
        out[k] = {"alert": int((sub["state"] == "alert").sum()), "watch": int((sub["state"] == "watch").sum())}
    return out


def merged_states(states: dict, ev: "pd.DataFrame") -> dict:
    """A subsystem not run in this session still shows the open items waiting for it in
    the work queue, so a tile never says "Not run" beside a banner listing its faults."""
    counts = open_counts(ev)
    out = dict(states)
    for k, s_ in states.items():
        c = counts.get(k, {})
        if s_ == "unknown" and c.get("alert"):
            out[k] = "alert"
        elif s_ == "unknown" and c.get("watch"):
            out[k] = "watch"
    return out


RUN_ALL_DATASET = "Competition test data"


def run_all(specs) -> None:
    """Run every live model on the provided competition test inputs.

    Results go into session state AND the event log, exactly like every other analysis
    path (subsystem pages, the drop box, the cached-run loader). Before this, only the
    session was updated, so "What to do now" listed faults while the work queue and
    Fleet view - which read the log - said nothing was found.
    """
    bar = st.progress(0.0, text="Starting...")
    logged = 0
    for i, spec in enumerate(specs):
        inputs = spec.test_inputs()
        files = as_files([(p.name, p.read_bytes()) for p in inputs])

        def tick(j, n, name, _s=spec, _i=i, _k=len(specs)):
            bar.progress((_i + j / n) / _k, text=f"{_s.name}: {name} ({j}/{n})")
        try:
            res = spec.module.analyze(files, progress=tick) if spec.key != "door" else spec.module.analyze(files)
            st.session_state[f"{spec.key}_result"] = res
            added, _ = event_log.append_unique(event_log.events_from_result(
                spec.key, res, {"source": "run", "dataset": RUN_ALL_DATASET}))
            logged += added
        except (ValueError, FileNotFoundError) as exc:
            st.error(f"{spec.name}: {plain_error(exc)}")
    bar.empty()
    st.session_state["_select_source"] = RUN_ALL_DATASET     # show what was just run
    st.toast(f"{logged} new event(s) logged to '{RUN_ALL_DATASET}'", icon="✅")


def dash_map_view(df, ev, line, lines_selected=None):
    """Camera choice shared by the maps: whole island, affected lines, or one line."""
    affected = insight.affected_lines(ev)
    labels = ["Whole Singapore"] + (["Affected lines"] if affected else []) + ["This line"]
    pick = st.segmented_control("Map view", labels, default=st.session_state.get("dash_mapview", "Whole Singapore")
                                if st.session_state.get("dash_mapview", "Whole Singapore") in labels else "Whole Singapore",
                                key="dash_mapview", label_visibility="collapsed")
    if pick == "Affected lines":
        pts, focus = insight.stations_on(df, affected), affected
    elif pick == "This line":
        pts, focus = insight.stations_on(df, lines_selected or [line]), (lines_selected or [line])
    else:
        pts, focus = None, []
    prev = st.session_state.get("_dash_lastpick")
    if prev != pick:
        st.session_state["_dash_lastpick"] = pick
        st.session_state["_dash_mapnonce"] = st.session_state.get("_dash_mapnonce", 0) + 1
    return insight.view_for(pts), focus, pick

def overview_page() -> None:
    results = session_results()
    states = insight.fleet_state(results)
    ev = insight.events(results)
    tr = insight.trends(results)
    rank = {"alert": 3, "watch": 2, "ok": 1, "unknown": 0}
    worst = max(states.values(), key=lambda x: rank[x])
    live = [sp for sp in SUBSYSTEMS.values() if sp.available and sp.test_inputs()]

    # ---- data source first: live only, one dataset, or everything
    choice, log_all = data_source_bar()
    states = merged_states(states, log_all)
    worst = max(states.values(), key=lambda x: rank[x])
    n_open_faults = int(((log_all["state"] == "alert") & (log_all["status"] == "open")).sum()) if len(log_all) else 0
    n_open_watch = int(((log_all["state"] == "watch") & (log_all["status"] == "open")).sum()) if len(log_all) else 0

    @st.fragment(run_every="60s")
    def hero_fragment():
        weather = livemap.fetch_weather()
        wx_lines, wx_emoji, wx_big = [], "🌤️", "—"
        if weather.get("ok"):
            w = livemap.weather_near(weather, 1.30, 103.85)
            wx_emoji = livemap.weather_emoji(w.get("forecast"), w.get("rain_mm"))
            wx_big = f"{w.get('temp_c', float('nan')):.1f} °C"
            wx_lines = [f"{w.get('forecast', '')}",
                        f"rain {w.get('rain_mm', 0):.1f} mm · NEA reading {weather.get('reading_time', '')} SGT"]
        else:
            wx_lines = [f"weather unavailable: {weather.get('reason', '')}"]
        if n_open_faults:
            headline = f"{n_open_faults} open fault(s) need an owner"
        elif n_open_watch:
            headline = f"Nothing failing · {n_open_watch} on watch"
        elif len(log_all):
            headline = "Fleet is healthy"
        else:
            headline = "Drop a file to begin"
        html(ui.hero("Nebula Wayside · " + event_log.now().strftime("%a %d %b · %H:%M:%S SGT") + " · refreshes every minute",
                     headline, "Door, structural health, rail corrugation and air conditioning on one screen, "
                     "with the network they run on and the live conditions around it.", wx_emoji, wx_big, wx_lines))

    hero_fragment()
    with st.expander("What Healthy, Watch and Fault mean", expanded=False):
        st.caption("The banner reads Fleet is healthy when no Fault or Watch item is open in the work queue. "
                   "Each subsystem decides its own state with these rules:")
        health_key()

    # ---- quick drop: any competition-format file, routed by its own layout
    view_toggle()
    q1, q2 = st.columns([2.2, 1], gap="medium")
    with q1:
        drops = st.file_uploader("Drop any file here: the console works out which subsystem it is",
                                 type=["csv", "xlsx"], accept_multiple_files=True, key="quick_drop")
        if drops:
            routed = {}
            for u in drops:
                key, why = quickdrop.detect(u.name, u.getvalue())
                routed.setdefault(key, []).append((u.name, u.getvalue(), why))
            html(" ".join(ui.chip("ok" if k != "generic" else "watch",
                                  f"{quickdrop.SUBSYSTEM_EMOJI[k]} {len(v)} → {SUBSYSTEMS[k].name if k in SUBSYSTEMS else 'New data'}",
                                  v[0][2]) for k, v in routed.items()))
            if st.button("Analyse everything dropped", type="primary", key="quick_run"):
                bar = st.progress(0.0, text="Starting...")
                items = [(k, v) for k, v in routed.items() if k in SUBSYSTEMS]
                for i, (k, v) in enumerate(items):
                    bar.progress(i / max(1, len(items)), text=f"{SUBSYSTEMS[k].name}: {len(v)} file(s)")
                    try:
                        res = SUBSYSTEMS[k].module.analyze(as_files([(n, d) for n, d, _ in v]))
                        st.session_state[f"{k}_result"] = res
                        ds_name = f"Upload {event_log.now().strftime('%d %b %H:%M')}"
                        for n, d, _ in v:
                            event_log.store_upload(ds_name, n, d)
                        added, skipped = event_log.append_unique(event_log.events_from_result(
                            k, res, {"source": "run", "dataset": ds_name}))
                        st.toast(f"{SUBSYSTEMS[k].name}: {added} new event(s)"
                                 + (f", {skipped} duplicate(s) skipped" if skipped else ""), icon="✅")
                    except (ValueError, FileNotFoundError) as exc:
                        st.error(f"{SUBSYSTEMS[k].name}: {plain_error(exc)}")
                bar.empty()
                if "generic" in routed:
                    st.info("Unrecognised file(s) go to New data → Screen a dataset.")
                st.rerun()
    with q2:
        st.write("")
        if live and st.button(f"Run all {len(live)} on the provided test data", width="stretch"):
            run_all(live)
            st.rerun()
        st.caption("Or load the competition test run from Manage datasets.")

    # ---- counts for the KPI cards and the status bar
    n_assets = sum(len(r["files"]) if r and "files" in r else (len(r["cycles"]) if r else 0) for r in results.values())
    n_alert = sum(1 for e in ev if e["state"] == "alert")
    n_watch = sum(1 for e in ev if e["state"] == "watch")
    shm_w = max((f["damage"] for f in results["shm"]["files"]), default=None) if results.get("shm") else None
    acv_top = results["acv"]["files"][0]["ranking"][0] if results.get("acv") else None
    n_unassessed = sum(1 for v in states.values() if v == "unknown")

    if n_open_faults:
        html(ui.beacon(f"{n_open_faults} open fault(s) need an owner",
                       "acknowledge or close them in the work queue below"))
    left, right = st.columns([1, 2.15], gap="medium")
    with left:
        html(ui.kpis([
            ("Assets assessed", f"{n_assets}", "cycles, files, recordings, cases"),
            ("Faults flagged", f"{n_alert}", f"{n_watch} on watch" if ev else "nothing run yet"),
            ("Worst fatigue", f"{shm_w:.2f}" if shm_w is not None else "—", "of fatigue life used"),
            ("Leak suspect", f"Car {acv_top}" if acv_top else "—", "most likely faulty car"),
        ]).replace('class="nw-kpis"', 'class="nw-kpis two"')
              .replace('<div class="nw-kpi"><div class="l">Faults flagged', '<div class="nw-kpi warn"><div class="l">Faults flagged' if n_alert else '<div class="nw-kpi"><div class="l">Faults flagged'))
        html(ui.status_bar({"alert": n_alert, "watch": n_watch,
                            "ok": max(0, n_assets - n_alert - n_watch), "unknown": n_unassessed},
                           "Status overview · assets"))
        html('<div class="nw-panel"><div class="t">Trend</div>')
        if "door" in tr:
            st.caption("Door · sustained motor current per 5-minute window, abnormal cycles in red")
            plot(charts.door_trend_compact(tr["door"]), always=True)
        elif "rail" in tr:
            st.caption("Rail · P(corrugated) across recordings")
            plot(charts.rail_trend(tr["rail"]), always=True)
        else:
            st.caption("Run a subsystem to see a trend.")
        html('</div>')

    with right:
        df = insight.with_zones(livemap.stations())
        c1, c2, c3 = st.columns([1.1, 0.9, 1.6])
        with c1:
            line = st.selectbox("Line of the assessed train", list(livemap.LINES), key="fleet_line",
                                format_func=lambda k: LINE_NAMES[k], label_visibility="collapsed")
        with c2:
            mode = st.segmented_control("Colour", ["Line", "Zone"], default="Line", key="dash_map_mode",
                                        label_visibility="collapsed") or "Line"
        view, focus, pick = dash_map_view(df, log_all, line)
        key = st.session_state.get("lta_key_persist", "")
        with c3:
            zones = insight.zones_for_line(df, line)
            html(ui.chip(worst, {"ok": "All assessed systems normal", "watch": "Watch",
                                 "alert": f"{n_alert} fault(s) on this train", "unknown": "Nothing assessed yet"}[worst],
                         f"{line} · {', '.join(zones) if zones else '—'}"))
        k1, k2 = st.columns([1.1, 2.5])
        with k1:
            lta_key = lta_key_input("dash")
        with k2:
            live_key_status(lta_key)
        if df.empty:
            html(ui.empty("Station map unavailable", ["data/stations/AmendmenttoMP2014RailStation.geojson is missing."]))
        else:
            weather = livemap.fetch_weather()
            deck = insight.network_deck(df, line, worst, "zones" if mode == "Zone" else "lines", weather, view,
                                        focus if pick != "Whole Singapore" else None)
            alerts = livemap.fetch_train_alerts(lta_key) if lta_key else None
            crowd = crowd_for_lines(lta_key, []) if lta_key else None
            deck.layers = insight.crowd_layer(crowd, df) + insight.alert_layer(alerts, df) + deck.layers
            map_chart(deck, key=f"dash_map_{st.session_state.get('_dash_mapnonce', 0)}_{bool(lta_key)}")
            crowd_caption(crowd)
            if alerts and alerts.get("ok"):
                for m in alerts.get("messages", []):          # LTA planned notices, e.g. line closures
                    st.caption("📋 " + m)
            if pick == "Affected lines":
                st.caption("Showing the lines that carry a fault or watch in the selected data: " + ", ".join(focus)
                           + ". Choose Whole Singapore to zoom back out.")
            legend = " &nbsp; ".join(
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:{c};margin-right:4px"></span>{k}'
                for k, (c, _) in livemap.LINES.items()) if mode == "Line" else " &nbsp; ".join(
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:rgb({",".join(map(str, z["rgb"]))});margin-right:4px"></span>{k}'
                for k, z in insight.ZONES.items())
            wl = ""
            if weather.get("ok"):
                sel = df[df["key"].isin(livemap.LINES[line][1])]
                w = livemap.weather_near(weather, float(sel["lat"].mean()), float(sel["lon"].mean())) if not sel.empty else {}
                wl = (f' &nbsp;·&nbsp; live NEA: {w.get("temp_c", float("nan")):.1f} °C at {w.get("station", "?")}, '
                      f'rain {w.get("rain_mm", 0):.1f} mm, {w.get("area", "")} {w.get("forecast", "")}'
                      f' &nbsp;·&nbsp; blue discs = rain gauges')
            html(f'<div style="font-size:12px;color:var(--ink-secondary);margin-top:6px">{legend}{wl}</div>')

    # ---- first run: three steps, nothing to read
    if not any(results.values()) and not len(log_all):
        html(ui.steps([
            ("Drop a file", "Any competition-format file above; the console works out which subsystem it is."),
            ("Read the action", "Each verdict becomes one line: what to do, why, how urgent, who owns it."),
            ("Track it", "Acknowledge, shelve or close it in the work queue; see it on the map in Fleet view."),
        ]))
        c1, c2 = st.columns([1, 1])
        with c1:
            st.page_link(PAGE_DOOR, label="Or start with a subsystem page →", icon=":material/door_sliding:")
        with c2:
            st.caption("The competition test run is one click away under Manage datasets.")

    # ---- decisions first: what to do, then why
    acts = decisions.recommend(results)
    actions_panel(acts)
    tips = decisions.insights(results)
    if tips:
        html(ui.section("What the data is telling you"))
        html('<div class="nw-panel"><ul class="nw-tips">' + "".join(f"<li>{t}</li>" for t in tips) + "</ul></div>")

    # ---- work queue: open faults, acknowledge / close like a maintenance system
    html(ui.section("Work queue"))
    log = log_all
    q = log[log["state"].isin(["alert", "watch"])] if len(log) else log
    f1, f2, f3 = st.columns([1.6, 1.4, 2])
    with f1:
        flt = st.segmented_control("Status", ["Open", "Acknowledged", "Shelved", "Closed", "All"], default="Open",
                                   key="wq_filter", label_visibility="collapsed") or "Open"
    with f2:
        wq_sub = st.multiselect("Subsystem", list(event_log.SUBSYSTEM_NAME.values()), default=[],
                                key="wq_sub", placeholder="All subsystems", label_visibility="collapsed")
    rows = q if flt == "All" else q[q["status"] == flt.lower()]
    if wq_sub is not None and len(wq_sub) and len(rows):
        rows = rows[rows["subsystem_name"].isin(wq_sub)]
    rows = rows.sort_values(["severity", "time"], ascending=[False, False]) if len(rows) else rows
    with f3:
        # Alarm load counts alarms only (faults and watches). The 10-per-10-min guideline
        # is an alarm-rate guideline; counting Normal verdicts would flag every batch run.
        alarms = log[log["state"].isin(["alert", "watch"])] if len(log) else log
        recent = int((pd.Timestamp(event_log.now()) - alarms["analysed_at"] <= pd.Timedelta(minutes=10)).sum()) if len(alarms) else 0
        st.caption(f"{int((q['status'] == 'open').sum()) if len(q) else 0} open · "
                   f"{int((q['status'] == 'acknowledged').sum()) if len(q) else 0} acknowledged · "
                   f"{int((q['status'] == 'shelved').sum()) if len(q) else 0} shelved · "
                   f"{int((q['status'] == 'closed').sum()) if len(q) else 0} closed · "
                   f"alarm load {recent} new in the last 10 min" + (" ⚠ above the 10-per-10-min guideline" if recent > 10 else ""))
    if not len(rows):
        html(ui.empty("Queue is clear", ["No faults or watches with this status. Run a subsystem page to add checks."]))
    else:
        for wi, x in enumerate(rows.head(8).itertuples()):
            c1, c2, c3, c4 = st.columns([3.6, 1.0, 1.0, 1.0])
            with c1:
                html(f'<div class="nw-panel" style="padding:12px 16px;margin-bottom:6px">'
                     f'<div class="h" style="display:flex;gap:10px;align-items:center">{ui.pill(x.state, ui.STATES[x.state][1])}'
                     f'<b>{quickdrop.SUBSYSTEM_EMOJI.get(x.subsystem, "")} {x.title}</b><span class="mono" style="margin-left:auto;font-size:11px;color:var(--ink-muted)">'
                     f'{event_log.fmt_time(x.time)}</span></div>'
                     f'<div class="muted" style="font-size:12px;margin-top:4px">{x.subsystem_name} · {txt(x.train, "train not known")} · '
                     f'{txt(x.station, "location not known").title()} · {txt(x.detail, "")}'
                     + (f' · <i>{x.note}</i>' if x.note else "") + '</div></div>')
            with c2:
                if x.status == "open" and st.button("Acknowledge", key=f"ack_{wi}_{x.id}", width="stretch"):
                    event_log.set_status(x.id, "acknowledged")
                    st.rerun()
                elif x.status == "acknowledged":
                    html(ui.pill("watch", "acknowledged"))
                elif x.status == "closed":
                    html(ui.pill("ok", "closed"))
            with c3:
                if x.status in ("open", "acknowledged") and st.button("Shelve 4 h", key=f"shelve_{wi}_{x.id}", width="stretch",
                                                                    help="Hide it for four hours; it comes back by itself and stays visible under Shelved."):
                    event_log.set_status(x.id, "shelved", "shelved for 4 h")
                    st.rerun()
                elif x.status == "shelved":
                    html(ui.pill("unknown", "shelved"))
            with c4:
                if x.status != "closed":
                    with st.popover("Close", width="stretch"):
                        oc = st.radio("What was found?", ["Confirmed fault", "No fault found", "Inconclusive"],
                                      key=f"oc_{wi}_{x.id}", help="This becomes a labelled example for the learning loop.")
                        note = st.text_input("Note (optional)", key=f"ocn_{wi}_{x.id}")
                        if st.button("Close with this outcome", key=f"cl_{wi}_{x.id}", type="primary"):
                            event_log.set_status(x.id, "closed", note or "closed from the dashboard",
                                                 outcome={"Confirmed fault": "confirmed", "No fault found": "no_fault_found",
                                                          "Inconclusive": "inconclusive"}[oc])
                            st.rerun()
                st.page_link({"door": PAGE_DOOR, "shm": PAGE_SHM, "rail": PAGE_RAIL, "acv": PAGE_ACV}[x.subsystem],
                             label="Details →", icon=":material/open_in_new:")
        if len(rows) > 8:
            with st.expander(f"All {len(rows)} in this view"):
                st.dataframe(rows[["time", "subsystem_name", "state", "status", "title", "train", "station", "detail"]],
                             hide_index=True, width="stretch", column_config=EVENT_COLS)
    st.caption(f"Showing: {choice}. Acknowledge when someone owns it, shelve to silence it for four hours, close when "
               "the inspection is done. Every action is logged with a time and is visible to the next operator.")

    # ---- deeper tabs
    tab_glance, tab_trends, tab_zones = st.tabs(["Subsystems", "Trends", "Zones"] if engineer_view() else ["Subsystems", "Trends", "Zones (engineer view)"])
    with tab_glance:
        cols = st.columns(4, gap="small")
        for col, spec in zip(cols, SUBSYSTEMS.values()):
            card, state = spec.model_card(), states[spec.key]
            v = card["validation"] if card else {}
            mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
            std = v.get("std_iou_weighted_f1", v.get("std_score"))
            word = {"ok": "Normal", "watch": "Watch", "alert": "Fault found", "unknown": "Not assessed"}[state]
            with col:
                html(ui.system_tile(T(IDENTITY[spec.key]), state, word, spec.name, spec.question,
                                    f"{mean:.3f} ± {std:.3f}" if card else "—",
                                    f"{METRIC_SHORT[spec.key]}, cross-validated" if card else "not validated", spec.method,
                                    quickdrop.SUBSYSTEM_EMOJI[spec.key]))
        links = {"door": PAGE_DOOR, "shm": PAGE_SHM, "rail": PAGE_RAIL, "acv": PAGE_ACV}
        cols = st.columns(4, gap="small")
        for col, spec in zip(cols, SUBSYSTEMS.values()):
            with col:
                st.page_link(links[spec.key], label=f"Open {spec.name} →", icon=":material/arrow_forward:")
    with tab_trends:
        if not tr:
            html(ui.empty("No trends yet", ["Trends need results. Run all, or one subsystem."]))
        a, b = st.columns(2, gap="medium")
        if "door" in tr:
            with a:
                html(ui.section("Door · over the stream"))
                plot(charts.door_trend(tr["door"]))
        if "acv" in tr:
            with b:
                html(ui.section("Air conditioning · top car, day by day"))
                plot(charts.acv_trend(tr["acv"]))
        if "rail" in tr:
            html(ui.section("Rail · corrugation probability across recordings"))
            plot(charts.rail_trend(tr["rail"]))
        if "shm" in tr:
            html(ui.section("Structural health · damage by measurement point"))
            plot(charts.shm_damage(tr["shm"]))
    with tab_zones:
        if not engineer_view():
            st.caption("Zones are an engineer-view detail: switch the view above to see station counts by region.")
        elif df.empty:
            st.caption("Station file missing.")
        else:
            zs = insight.zone_summary(df)
            mine = set(insight.zones_for_line(df, line))
            cols = st.columns(5, gap="small")
            for col, r in zip(cols, zs.itertuples()):
                with col:
                    rgb = insight.ZONES[r.zone]["rgb"]
                    html(ui.system_tile(f"rgb({rgb[0]},{rgb[1]},{rgb[2]})", worst if r.zone in mine else "unknown",
                                        "On this train's line" if r.zone in mine else "No assessed train",
                                        r.zone, r.hint, f"{r.stations}", "stations", f"lines: {r.lines}"))
            st.caption("A verdict belongs to a train, not a place. Zones light up through the selected line.")


def door_page() -> None:
    spec, card = SUBSYSTEMS["door"], SUBSYSTEMS["door"].model_card()
    html(ui.header("Door · abnormal resistance", "Door cycles",
                   "The door controller streams motor current, voltage, back-EMF and "
                   "door position. This finds every open or close cycle in the stream "
                   "and checks each one for abnormal resistance.", T("subsystem-door")))
    view_toggle()
    how_to_read("door")
    res = run_panel(spec, "Analyse door stream")
    if not res:
        return
    actions_panel(decisions.recommend({"door": res}), "What to do", here="door")
    cyc, trace = res["cycles"], res["trace"]
    if cyc.empty:
        html(ui.verdict("unknown", "Door", "No door cycles found",
                        "The stream contained no gap-separated cycles.",
                        "Check this is a door-controller stream.", evidence_line(card, "IoU-F1")))
        return

    n = len(cyc)
    abn = cyc[cyc["prediction"] == "Abnormal resistance"]
    nrm = cyc[cyc["prediction"] == "Normal"]
    span = float(cyc["end_s"].max())

    html(ui.kpis([
        ("Cycles detected", f"{n}", f"in {span / 60:.1f} min of stream"),
        ("Abnormal resistance", f"{len(abn)}", f"{len(abn) / n:.0%} of cycles"),
        ("Normal", f"{len(nrm)}", None),
        ("Segmentation gap", f"{card['gap_seconds']:.2f}s", "derived from data, not tuned"),
    ]))
    st.write("")

    if len(abn):
        excess = []
        for op in ("Close", "Open"):
            a = abn[abn.operation == op]["cur_mean_mid"]
            b = nrm[nrm.operation == op]["cur_mean_mid"]
            if len(a) and len(b):
                excess.append(a.mean() / b.mean() - 1)
        pct = f"about {100 * sum(excess) / len(excess):.0f}% more" if excess else "more"
        ids = ", ".join(str(c) for c in abn["cycle"].head(8))
        more = f" and {len(abn) - 8} more" if len(abn) > 8 else ""
        html(ui.verdict(
            "alert", "Door",
            f"{len(abn)} of {n} door cycles show abnormal resistance",
            f"The flagged cycles drew {pct} sustained motor current than normal cycles "
            "moving the same way. Resistance forces the motor to work harder for the same "
            "travel, which is the signature of a foreign object in the slide rail, a "
            "jamming seal or a deformed door leaf.",
            f"Inspect the slide rails, rubber seals and leaf alignment. Flagged cycles: {ids}{more}.",
            evidence_line(card, "IoU-weighted F1"), "Abnormal resistance"))
    else:
        html(ui.verdict("ok", "Door", f"All {n} door cycles are normal",
                        "Every cycle drew motor current in line with normal operation.",
                        "No action needed.", evidence_line(card, "IoU-weighted F1")))

    if engineer_view():
        drift_chip(res, "door")
    health_key(("door",))

    top_n_panel("door", res)
    html(ui.section("Where the cycles are"))
    plot(charts.door_timeline(cyc, span))

    if eng_only("the sustained current of every cycle and the measured motor current and door travel of any cycle"):
        left, right = st.columns([1.1, 1], gap="medium")
        with left:
            html(ui.section("Sustained current per cycle"))
            plot(charts.door_load(cyc))
            st.caption("Mean motor current over the middle 60% of each cycle, excluding "
                       "start-up inrush. This is the model's strongest single feature.")
        with right:
            html(ui.section("Inspect a cycle"))
            default = int(abn["cycle"].iloc[0]) if len(abn) else 1
            options = list(cyc["cycle"])
            pick = st.selectbox(
                "Cycle", options, index=options.index(default),
                format_func=lambda c: f"Cycle {c} · {cyc.set_index('cycle').loc[c, 'operation']}"
                                      f" · {cyc.set_index('cycle').loc[c, 'prediction']}")
            row = cyc.set_index("cycle").loc[pick]
            state = "alert" if row["prediction"] == "Abnormal resistance" else "ok"
            html(ui.chip(state, row["prediction"],
                         f"P(abnormal) {row['p_abnormal']:.0%} · {row['duration_s']:.2f}s · "
                         f"{_door_when(row['start_time'])}"))
            # The measured current and door position for this cycle - what actually happened,
            # rather than a decorative drawing of a door leaf.
            plot(charts.door_cycle_detail(trace[trace["cycle"] == pick]))

    html(ui.section("Predictions"))
    show = cyc[["cycle", "start_time", "end_time", "operation", "prediction", "p_abnormal", "cur_mean_mid"]].copy()
    show["start_time"] = [_door_when(x) for x in show["start_time"]]
    show["end_time"] = [_door_when(x).split(" · ")[-1] for x in show["end_time"]]
    st.dataframe(
        show, hide_index=True, width="stretch",
        column_config={
            "cycle": st.column_config.NumberColumn("Cycle", format="%d"),
            "start_time": "Start", "end_time": "End", "operation": "Operation", "prediction": "Verdict",
            "p_abnormal": st.column_config.ProgressColumn("Chance of abnormal resistance", min_value=0.0,
                                                          max_value=1.0, format="%.2f"),
            "cur_mean_mid": st.column_config.NumberColumn("Sustained current (mA)", format="%.0f"),
        })
    st.caption("The downloaded file keeps the official competition format and timestamps.")
    download(spec, res["predictions"])
    n1, n2 = st.columns(2)
    with n1:
        st.page_link(PAGE_DASHBOARD, label="← Back to what to do now", icon=":material/dashboard:")
    with n2:
        st.page_link(PAGE_FLEET, label="See it on the fleet map →", icon=":material/map:")


def shm_page() -> None:
    spec, card = SUBSYSTEMS["shm"], SUBSYSTEMS["shm"].model_card()
    html(ui.header("Structural health · fatigue", "Cumulative fatigue damage",
                   "Each file is a long dynamic-stress recording from one measurement point. "
                   "This counts every stress cycle and converts them into fatigue damage, "
                   "where 1.0 is the end of the structure's fatigue life.", T("subsystem-shm")))
    view_toggle()
    how_to_read("shm")
    res = run_panel(spec, "Assess fatigue damage")
    if not res:
        return
    actions_panel(decisions.recommend({"shm": res}), "What to do", here="shm")

    files = pd.DataFrame([{k: v for k, v in f.items() if k not in ("profile", "envelope")}
                          for f in res["files"]])
    worst = files.loc[files["damage"].idxmax()]
    n_watch = int((files["damage"] >= SHM_WATCH).sum())
    n_alert = int((files["damage"] >= SHM_ALERT).sum())

    html(ui.kpis([
        ("Files assessed", f"{len(files)}", f"{files['n_cycles'].sum() / 1e6:.1f}M stress cycles counted"),
        ("Highest damage", f"{worst['damage']:.3f}", str(worst["file_id"])),
        ("Median damage", f"{files['damage'].median():.3f}", None),
        (f"At or above {SHM_WATCH}", f"{n_watch}", f"{n_alert} at or above {SHM_ALERT}"),
    ]))
    st.write("")

    ev = (evidence_line(card, "max(0,1−MAPE)") + f" · m = {card['m']:.3f}")
    if n_alert:
        state, title = "alert", f"{worst['file_id']} has used {worst['damage']:.0%} of its fatigue life"
        action = (f"Prioritise inspection at the measurement point behind {worst['file_id']}"
                  + (f" and {n_alert - 1} other file(s) above {SHM_ALERT}" if n_alert > 1 else "")
                  + ". Review the loading history for the high-amplitude cycles below.")
    elif n_watch:
        state, title = "watch", f"{n_watch} file(s) past the watch band"
        action = "Schedule inspection of the flagged measurement points at the next planned service."
    else:
        state, title = "ok", f"All {len(files)} files are below the watch band"
        action = "No action needed. Continue routine monitoring."
    html(ui.verdict(
        state, "Structural health", title,
        "Every stress cycle uses up a little fatigue life, and large cycles use far more than "
        "small ones - damage scales with stress range to the power m, and for this structure "
        f"m ≈ {card['m']:.1f}, the textbook exponent for welded steel. Under Miner's rule the "
        "structure reaches the end of its fatigue life at D = 1.",
        action, ev))
    st.caption(f"Watch ({SHM_WATCH}) and alert ({SHM_ALERT}) bands are illustrative planning "
               "thresholds for an operator to set. The model predicts D; it does not choose them.")
    _, gauge_col, _ = st.columns([1, 1.6, 1])      # centred, not squeezed into a side column
    with gauge_col:
        html(schematics.shm_gauge(str(worst["file_id"]), float(worst["damage"]),
                                  (1 - float(worst["damage"])) / max(float(worst["damage"]), 1e-9)))
        html('<div style="text-align:center;font-size:13px;opacity:.7;margin-bottom:12px">The worst measurement '
             'point in this run. The files carry no position on the vehicle, so none is drawn.</div>')

    files["segments_to_failure"] = (1.0 - files["damage"]) / files["damage"]
    if engineer_view():
        drift_chip(res, "shm")
    health_key(("shm",))
    top_n_panel("shm", res)
    html(ui.section("Damage by file"))
    plot(charts.shm_damage(files))
    if eng_only("the life forecast and, per file, the cycle counts, damage sources and stress history"):
        html(ui.section("Forecast · segments of this length left before D = 1"))
        st.caption("Miner's rule is linear: if a measurement point keeps accruing damage at the rate seen "
                   "in its file, it reaches D = 1 after (1 − D) / D more segments of the same length. "
                   "A forecast of the loading pattern continuing, not a prediction of failure.")
        plot(charts.shm_forecast(files))

        html(ui.section("Inspect a file"))
        ids = list(files["file_id"])
        pick = st.selectbox("File", ids, index=ids.index(worst["file_id"]))
        f = next(x for x in res["files"] if x["file_id"] == pick)
        html(ui.kpis([
            ("Damage", f"{f['damage']:.4f}", f"{f['damage']:.1%} of fatigue life"),
            ("Stress cycles counted", f"{f['n_cycles']:,.0f}", f"from {f['n_samples']:,} samples"),
            ("Largest stress range", f"{f['max_range']:.1f}", None),
            ("Damage from the largest 0.1% of cycles", f"{f['top_share']:.1%}",
             "a handful of large cycles do almost all of it"),
        ]))
        a, b = st.columns(2, gap="medium")
        with a:
            html(ui.section("How many cycles, by stress range"))
            plot(charts.shm_cycles_by_range(f["profile"]))
        with b:
            html(ui.section("Where the damage comes from"))
            plot(charts.shm_damage_share(f["profile"]))
        st.caption("Almost all cycles are small, but damage grows as range to the power m, so "
                   "the rare large cycles on the right cause most of it.")
        with st.expander("Stress history (min/max envelope, peaks preserved)"):
            plot(charts.shm_envelope(f["envelope"]))

    html(ui.section("Predictions"))
    st.dataframe(files[["file_id", "damage", "segments_to_failure", "n_cycles", "top_share"]],
                 hide_index=True, width="stretch",
                 column_config={
                     "file_id": "File",
                     "segments_to_failure": st.column_config.NumberColumn("Segments to D = 1", format="%.1f"),
                     "damage": st.column_config.ProgressColumn("Damage D", min_value=0.0,
                                                               max_value=1.0, format="%.4f"),
                     "n_cycles": st.column_config.NumberColumn("Cycles", format="%,.0f"),
                     "top_share": st.column_config.NumberColumn(
                         "Share from top 0.1% of cycles", format="percent"),
                 })
    download(spec, res["predictions"])
    n1, n2 = st.columns(2)
    with n1:
        st.page_link(PAGE_DASHBOARD, label="← Back to what to do now", icon=":material/dashboard:")
    with n2:
        st.page_link(PAGE_FLEET, label="See it on the fleet map →", icon=":material/map:")


def pending_page(key: str, facts: list[str]) -> None:
    spec = SUBSYSTEMS[key]
    html(ui.header(f"{spec.name}", spec.name, spec.question, T(IDENTITY[key])))
    html(ui.empty(
        "No validated model yet",
        ["This console only shows predictions from models that have passed a leakage-safe "
         "validation. Rather than show an unvalidated guess, this subsystem stays pending "
         "until its model does.",
         f"When ready it will predict {spec.predicts}, using {spec.method.replace('planned: ', '')}."],
        tag="Model pending"))
    html(ui.section("What we already know about this data"))
    for fact in facts:
        st.markdown(f"- {fact}")


def rail_page() -> None:
    spec, card = SUBSYSTEMS["rail"], SUBSYSTEMS["rail"].model_card()
    html(ui.header("Rail · corrugation", "Rail corrugation",
                   "Each file is one second of axle-box vibration and shock from all 64 "
                   "bearings of an 8-car train at 10 kHz, plus a rotating-speed pulse. "
                   "Positions 1, 3, 5, 7 ride the Side I rail and 2, 4, 6, 8 the Side II rail, "
                   "so the two rails are judged independently.", T("subsystem-rail")))
    view_toggle()
    how_to_read("rail")
    res = run_panel(spec, "Classify recordings")
    if not res:
        return
    actions_panel(decisions.recommend({"rail": res}), "What to do", here="rail")
    files = pd.DataFrame([{"file_id": f["file_id"], "prediction": f["prediction"],
                           "speed_km_h": f["speed"]["speed_km_h"],
                           "side_i_rms": f["side_i_rms"], "side_ii_rms": f["side_ii_rms"],
                           **{f"p_{k}": v for k, v in f["proba"].items()}}
                          for f in res["files"]])
    flagged = files[files["prediction"] != "Normal"]
    v = card["validation"]
    ev = (f"macro F1 {v['mean_score']:.3f} ± {v['std_score']:.3f} · {v['split'].split(',')[0]} · "
          f"Side I recall {v['side_i_recall']:.2f} · model {card['model_version']}")

    html(ui.kpis([
        ("Recordings", f"{len(files)}", f"{files['speed_km_h'].mean():.0f} km/h mean speed from the pulse"),
        ("Side I corrugation", f"{int((files.prediction == 'Side I').sum())}", None),
        ("Side II corrugation", f"{int((files.prediction == 'Side II').sum())}", None),
        ("Normal", f"{int((files.prediction == 'Normal').sum())}", None),
    ]))
    st.write("")
    if len(flagged):
        ids = ", ".join(f"{r.file_id} ({r.prediction})" for r in flagged.head(6).itertuples())
        more = f" and {len(flagged) - 6} more" if len(flagged) > 6 else ""
        html(ui.verdict(
            "alert", "Rail corrugation",
            f"{len(flagged)} of {len(files)} recordings show a corrugated rail",
            "Corrugation is a periodic wear pattern on the rail head. As wheels roll over it, "
            "every axle box on that side of the train vibrates at the same wavelength, while the "
            "other side stays quiet - which is why the two rails are scored separately.",
            f"Schedule rail grinding on the flagged side and locate the section from the train's "
            f"position log. Flagged: {ids}{more}.", ev, "Corrugation"))
    else:
        html(ui.verdict("ok", "Rail corrugation", f"All {len(files)} recordings read as normal track",
                        "Neither rail shows the periodic axle-box vibration that corrugation produces.",
                        "No action needed. Continue routine monitoring.", ev))
    if engineer_view():
        drift_chip(res, "rail")
    health_key(("rail",))
    top_n_panel("rail", res)
    st.caption("Side I is the rare class (14 of 272 training files) and the model recalls about "
               "two-thirds of it in validation, so a clean Side I result carries less certainty "
               "than a clean Side II result.")

    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        html(ui.section("Verdicts"))
        plot(charts.rail_summary(files))
    with right:
        html(ui.section("Inspect a recording"))
        ids = list(files["file_id"])
        default = flagged["file_id"].iloc[0] if len(flagged) else ids[0]
        pick = st.selectbox("Recording", ids, index=ids.index(default),
                            format_func=lambda i: f"{i} · {files.set_index('file_id').loc[i, 'prediction']}")
        f = next(x for x in res["files"] if x["file_id"] == pick)
        state = "ok" if f["prediction"] == "Normal" else "alert"
        pr = f["proba"]
        html(ui.chip(state, f["prediction"],
                     f"P(Normal) {pr['Normal']:.0%} · P(Side I) {pr['Side I']:.0%} · "
                     f"P(Side II) {pr['Side II']:.0%} · {f['speed']['speed_km_h']:.0f} km/h"))
        st.caption(f"Speed from {f['speed']['transitions']} pulse edges in one second: "
                   f"90-tooth wheel, 0.85 m diameter → {f['speed']['speed_m_s']:.2f} m/s.")

    html(ui.section("The train and its rails"))
    html(schematics.rail_train(f["grid"], f["prediction"]))
    st.caption("Each dot is one axle box, coloured by its own vibration RMS in this recording; the dashed rail is the one the verdict names.")
    if eng_only("the vibration energy per axle box and the wavelength spectrum of each rail"):
        html(ui.section("Vibration energy by axle box"))
        plot(charts.rail_axle_grid(f["grid"]))
        st.caption("Vibration RMS per bearing, normalised to the loudest box in this recording. A "
                   "corrugated rail lights up one whole band, not one car.")
        html(ui.section("Spectrum per rail, in the wavelength domain"))
        plot(charts.rail_spectrum(f["spectrum"]))
        st.caption("λ = v / f converts each frequency to a distance along the rail using the measured "
                   "speed, so the same corrugation pitch lands in the same place at any speed. The "
                   "classifier itself uses per-side statistics and frequency bands; this view is the "
                   "physical reading of the same signal.")

    html(ui.section("Predictions"))
    st.dataframe(files, hide_index=True, width="stretch",
                 column_config={
                     "file_id": "Recording", "prediction": "Verdict",
                     "speed_km_h": st.column_config.NumberColumn("Speed km/h", format="%.0f"),
                     "side_i_rms": st.column_config.NumberColumn("Side I RMS", format="%.3f"),
                     "side_ii_rms": st.column_config.NumberColumn("Side II RMS", format="%.3f"),
                     "p_Normal": st.column_config.ProgressColumn("P(Normal)", min_value=0.0, max_value=1.0, format="%.2f"),
                     "p_Side I": st.column_config.ProgressColumn("P(Side I)", min_value=0.0, max_value=1.0, format="%.2f"),
                     "p_Side II": st.column_config.ProgressColumn("P(Side II)", min_value=0.0, max_value=1.0, format="%.2f"),
                 })
    download(spec, res["predictions"])
    n1, n2 = st.columns(2)
    with n1:
        st.page_link(PAGE_DASHBOARD, label="← Back to what to do now", icon=":material/dashboard:")
    with n2:
        st.page_link(PAGE_FLEET, label="See it on the fleet map →", icon=":material/map:")


def acv_page() -> None:
    spec, card = SUBSYSTEMS["acv"], SUBSYSTEMS["acv"].model_card()
    html(ui.header("Air conditioning · refrigerant leak", "Which car is leaking?",
                   "Each case is one train's air-conditioning telemetry: cabin temperature, "
                   "cooling setpoint and running mode for all eight cars, every 30 seconds. A car "
                   "that has lost refrigerant cannot pull its cabin down to the setpoint, so it "
                   "runs warmer than its neighbours under the same conditions.", T("subsystem-acv")))
    view_toggle()
    how_to_read("acv")
    res = run_panel(spec, "Rank the cars")
    if not res:
        return
    actions_panel(decisions.recommend({"acv": res}), "What to do", here="acv")
    v = card["validation"]
    ev = (f"rank decay {v['mean_score']:.3f} ± {v['std_score']:.3f} · {v['split'].split(',')[0]} · "
          f"random ranking {v['random_ranking_baseline']} · model {card['model_version']}")
    ids = [f["file_id"] for f in res["files"]]
    pick = ids[0] if len(ids) == 1 else st.selectbox("Case", ids)
    f = next(x for x in res["files"] if x["file_id"] == pick)
    top, second = f["ranking"][0], f["ranking"][1]
    pm, hf = f.get("peer_mean", f["scores"]), f.get("hot_fraction", {})
    s_top, s_2 = pm.get(top), pm.get(second)
    gap = (s_top - s_2) if (s_top is not None and s_2 is not None) else None
    h_top, h_2 = hf.get(top, 0.0), hf.get(second, 0.0)
    v2 = f.get("rule") == "hot_fraction_then_peer_mean"
    cars = [(c, (hf.get(c) if v2 else pm.get(c)) if c not in f["unobserved"] else None) for c in f["ranking"]]

    html(ui.kpis([
        ("Cases ranked", f"{len(ids)}", None),
        ("Most likely faulty", f"Car {top}", ((f"hot {h_top:.1%} of cooling time · {s_top:+.2f} °C mean" if h_top > 0
                                              else f"no hot episodes; {s_top:+.2f} °C mean excess decides") if v2
                                              else f"{s_top:+.2f} °C above the other cars") if s_top is not None else None),
        ("Margin to runner-up", (f"{(h_top - h_2):.1%} of time" if v2 else f"{gap:.2f} °C") if gap is not None else "—",
         f"runner-up Car {second}" + (f" · {gap:+.2f} °C mean gap" if v2 and gap is not None else "")),
        ("Cooling readings used", f"{max(f['cooling_readings'].values()):,}", f"of {f['n_readings']:,} rows"),
    ]))
    st.write("")
    state = "alert" if (gap is not None and gap >= 0.03) or (v2 and h_top - h_2 >= 0.01) else "watch"
    html(ui.verdict(
        state, "Air conditioning",
        f"Car {top} is the most likely refrigerant leak in {pick}",
        ((f"During cooling, Car {top} ran more than 2 °C hotter than the median of the other seven cars "
          f"for {h_top:.1%} of the time (runner-up {h_2:.1%}), and {s_top:+.2f} °C hotter on average. ")
         if h_top > 0 else
         (f"No car in this file ran more than 2 °C above the others during cooling, so the ranking falls "
          f"back to the mean excess: Car {top} ran {s_top:+.2f} °C hotter than the median of the other seven "
          f"cars, Car {second} {s_2:+.2f} °C. ") if s_2 is not None else "") +
        (
         "A car that has lost refrigerant cannot hold its cabin down when the load rises, so it shows "
         "hot episodes the other cars do not. Comparing cars to each other cancels the weather, the "
         "passenger load and the route, which all eight cars share." if v2 else
         f"During cooling, Car {top}'s cabin ran {s_top:+.2f} °C against the median of the other "
         f"seven cars on the same train at the same moment. Comparing cars to each other cancels "
         f"the weather, the passenger load and the route, which all eight cars share.")
        + (" The margin over the runner-up is narrow, so treat the top two as candidates."
           if state == "watch" else ""),
        f"Check refrigerant pressure and the condenser on Car {top} first"
        + (f", then Car {second}." if state == "watch" else "."),
        ev, "Leak suspected"))
    if engineer_view():
        drift_chip(res, "acv")
    health_key(("acv",))
    top_n_panel("acv", res)
    if f["unobserved"]:
        st.warning(f"No usable cooling evidence for car(s) {', '.join(f['unobserved'])}: placed "
                   "last by identifier order, which does not mean they are healthy.")

    html(ui.section("The train"))
    html(schematics.acv_train(f["ranking"], pm, hf if v2 else None, f["unobserved"]))
    st.caption("Cars in physical order; colour follows the ranking from this file's own telemetry.")
    left, right = st.columns([1, 1.4], gap="medium") if engineer_view() else (st.container(), None)
    with left:
        html(ui.section("All eight cars, ranked"))
        html(ui.car_rank(cars, ("Bars: share of cooling time more than 2 °C above the other cars. " if v2 else "")
                         + "Every car is listed: the scoring gives partial credit for a close "
                           "miss and none for an omitted car. A random ordering scores 0.5625.",
                         fmt=(lambda s: f"{s:.2%} hot") if v2 else (lambda s: f"{s:+.2f} °C")))
    if right is None:
        eng_only("the temperature excess of every car over time")
    else:
        with right:
            html(ui.section("Temperature excess over the other cars"))
            plot(charts.acv_excess(f["excess_timeline"], f["ranking"]))
            st.caption("Cooling periods only. The ranked-first car is drawn in red.")

    html(ui.section("Predictions"))
    st.dataframe(res["predictions"], hide_index=True, width="stretch",
                 column_config={"file_id": "Case", "ranked_cars": "Cars, most likely leak first"})
    download(spec, res["predictions"])
    n1, n2 = st.columns(2)
    with n1:
        st.page_link(PAGE_DASHBOARD, label="← Back to what to do now", icon=":material/dashboard:")
    with n2:
        st.page_link(PAGE_FLEET, label="See it on the fleet map →", icon=":material/map:")


# ------------------------------------------------------------------ fleet

LINE_NAMES = {"NSL": "North–South (NSL)", "EWL": "East–West (EWL)", "NEL": "North East (NEL)",
              "CCL": "Circle (CCL)", "DTL": "Downtown (DTL)", "TEL": "Thomson–East Coast (TEL)"}


RANGES = {"Today": 1, "7 days": 7, "30 days": 30, "90 days": 90, "1 year": 365, "All": None, "Custom": "custom"}


def map_chart(deck, key: str, height: int = 520) -> None:
    """st.pydeck_chart plus a resize nudge.

    deck.gl fixes its view size in pixels when it first draws and only re-measures on
    a window resize. A map drawn while its column is still laying out (first load, or
    the rerun after typing in a box) therefore stays at the 300x150 canvas default.
    A few resize events after the layout settles make every map on the page re-measure.
    """
    st.pydeck_chart(deck, height=height, key=key)
    # A fixed script with no user input, run in the page itself (st.components.v1.html
    # is deprecated and needed a hidden iframe to reach the page). Besides the resize
    # nudge it stops the scroll-wheel trap: over a map the wheel scrolls the PAGE, and
    # Ctrl + wheel (or the +/- buttons) zooms the map, as on embedded Google Maps.
    st.html("<script>[250, 900, 2000].forEach(t => setTimeout(() => "
            "window.dispatchEvent(new Event('resize')), t));"
            "if (!window.__nwWheel) { window.__nwWheel = true;"
            " document.addEventListener('wheel', e => {"
            "  if (!e.ctrlKey && e.target.closest && e.target.closest('[data-testid=stDeckGlJsonChart]'))"
            "   e.stopPropagation(); }, {capture: true}); }</script>", unsafe_allow_javascript=True)
    st.caption("Scroll moves the page. To zoom the map, hold Ctrl and scroll, or use + / −. Drag to pan.")


def lta_key_input(where: str) -> str:
    """The DataMall AccountKey box, shared by every page that shows live feeds.

    The value lives in one session key, so a key typed on the Dashboard is already
    there in Fleet view and vice versa. It is never written to disk.
    """
    # Automatic: a key in .streamlit/secrets.toml, the app's Secrets or the environment
    # is used without anyone pasting it. When one is configured the key is never put in
    # a widget - a screen recording or a shoulder-surfer cannot see it - and a pasted
    # override lives behind a popover, also never echoed back.
    auto, auto_src = lta_live.auto_key()
    st.session_state.setdefault("lta_key_override", "")

    def _sync() -> None:
        st.session_state["lta_key_override"] = st.session_state.get(f"_lta_key_{where}", "").strip()

    help_text = ("Register free at datamall.lta.gov.sg. Use the API Account Key (24 characters, ending in ==) "
                 "from the DataMall email - not the Extended OBU Library SDK key. It is sent only as the "
                 "AccountKey header to DataMall. Nothing is stored.")
    override = st.session_state["lta_key_override"]
    key = override or auto
    st.session_state["lta_key"] = key          # read by the live layers on every page
    st.session_state["lta_key_persist"] = key  # the name the earlier key UI used
    if key:
        html(ui.chip("ok", "Live data connected", "your key" if override else f"key from {auto_src}"))
        with st.popover("Use a different key", width="stretch"):
            st.text_input("LTA DataMall AccountKey", type="password", key=f"_lta_key_{where}", value="",
                          on_change=_sync, placeholder="paste a key and press Enter", help=help_text)
            if override and st.button("Go back to the saved key", key=f"_lta_reset_{where}"):
                st.session_state["lta_key_override"] = ""
                st.rerun()
    else:
        st.text_input("LTA DataMall AccountKey", type="password", key=f"_lta_key_{where}", value="",
                      on_change=_sync, placeholder="optional - press Enter", help=help_text)
    return key


def crowd_for_lines(key: str, lines: list[str]) -> dict:
    """Platform crowding for every selected line, or the whole network when none is
    selected. Each line is cached for 10 minutes by livemap.fetch_crowd, so this stays
    well inside DataMall's fair-use expectations."""
    # fetched in parallel: one request per line, each cached for 10 minutes
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()
    wanted = lines or list(livemap.LINES)
    with ThreadPoolExecutor(max_workers=min(8, len(wanted) or 1),
                            initializer=lambda: ctx and add_script_run_ctx(threading.current_thread(), ctx)) as pool:
        parts = list(pool.map(lambda ln: livemap.fetch_crowd(key, ln), wanted))
    ok = [p for p in parts if p.get("ok")]
    if not ok:
        return parts[0] if parts else {"ok": False, "reason": "no lines", "rows": pd.DataFrame()}
    return {"ok": True, "rows": pd.concat([p["rows"] for p in ok], ignore_index=True),
            "fetched_at": ok[0].get("fetched_at")}


def live_lta_page() -> None:
    """Every LTA DataMall feed, refreshing itself (app/live_page.py)."""
    import live_page
    auto, auto_src = lta_live.auto_key()
    key = st.session_state.get("lta_key") or auto
    src = auto_src if key == auto else "this session"
    live_page.render(key, src, html, plot, map_chart)


def crowd_caption(crowd: dict | None) -> None:
    """One line under a map saying what the crowd layer shows, or why it is empty."""
    if crowd is None:
        return
    if not crowd.get("ok"):
        st.caption(f"Crowd feed: {crowd.get('reason')}")
    elif crowd["rows"].empty:
        st.caption("Crowd feed answered but listed no stations - normal outside operating hours "
                   f"(about 05:30-00:30) · fetched {crowd.get('fetched_at')} SGT")
    else:
        st.caption(f"Platform crowd rings at {crowd['rows']['code'].nunique()} stations (DataMall PCDRealTime, "
                   f"10-minute feed): green low, amber moderate, red high · fetched {crowd.get('fetched_at')} SGT")


def live_key_status(key: str) -> None:
    """Immediate feedback on the AccountKey, right under the box it was typed into."""
    if not key:
        st.caption("Paste a DataMall AccountKey and press Enter to switch on live service alerts and "
                   "platform crowding. The 24-character key ending in == from the DataMall email - "
                   "not the Extended OBU Library SDK key, which DataMall rejects.")
        return
    al = livemap.fetch_train_alerts(key)
    if not al["ok"]:
        if al.get("rejected"):
            html(ui.chip("alert", "Key not accepted", al["reason"]))
            st.caption("DataMall rejected the key: check it is the API Account Key (24 characters, ending in ==) "
                       "and was copied whole. New keys can take a few minutes to activate.")
        else:
            # A network blip, not a bad key - it is not cached, so the next refresh retries.
            html(ui.chip("watch", "LTA feed temporarily unreachable", al["reason"]))
    elif al["status"] == 1 and not al["segments"]:
        html(ui.chip("ok", "All MRT lines running normally", f"LTA · {al['fetched_at']} SGT"))
    else:
        html(ui.chip("alert", "Train disruption reported",
                     f"{len(al['segments'])} segment(s) · LTA · {al['fetched_at']} SGT"))


def fleet_page() -> None:
    session_results()
    html(ui.header("Fleet view", "What happened, where, and when",
                   "Every verdict the models produce goes into one fleet log with a time, a train "
                   "and a station. Filter it by time range, line, subsystem and state; the map "
                   "shows where events cluster, the roster shows which trains need attention."))
    view_toggle()
    choice, log = data_source_bar()
    df = insight.with_zones(livemap.stations())
    last = log["analysed_at"].max() if len(log) else None

    # ---- filters: what, then when
    f2, f3, f4, f5 = st.columns([1.2, 1.3, 1.0, 1.5])
    with f2:
        lines = st.multiselect("Lines", list(livemap.LINES), default=[], key="fleet_lines", placeholder="All lines")
    with f3:
        subs = st.multiselect("Subsystems", list(event_log.SUBSYSTEM_NAME.values()), default=[],
                              key="fleet_subs", placeholder="All subsystems")
    with f4:
        states = st.multiselect("State", ["Fault", "Watch", "Normal"], default=["Fault", "Watch"],
                                key="fleet_states", placeholder="Any")
    with f5:
        key = lta_key_input("fleet")
    live_key_status(key)
    html(ui.section("Time range"))
    # A dataset carries its own dates (door cycles keep the recording's timestamps), so a
    # fixed "last 7 days" window would hide them. Switching source resets the window:
    # All for a dataset, 7 days for live-only. After that the user's choice sticks.
    if st.session_state.get("_fleet_last_source") != choice:
        st.session_state["_fleet_last_source"] = choice
        st.session_state["fleet_range"] = "7 days" if choice == LIVE_ONLY else "All"
    rng = st.segmented_control("Preset", [k for k in RANGES if k != "Custom"], key="fleet_range",
                               label_visibility="collapsed", width="stretch") or "7 days"
    today = event_log.now().date()
    if RANGES[rng] is None:
        first = log["time"].min().date() if len(log) else today - pd.Timedelta(days=365)
        preset_from, preset_to = first, today
    elif rng == "Today":
        preset_from, preset_to = today, today
    else:
        preset_from, preset_to = today - pd.Timedelta(days=RANGES[rng]), today
    d1, d2, d3 = st.columns([1, 1, 2])
    with d1:
        start_d = st.date_input("From", value=preset_from, key=f"fleet_from_{rng}", format="DD/MM/YYYY")
    with d2:
        end_d = st.date_input("To", value=preset_to, key=f"fleet_to_{rng}", format="DD/MM/YYYY")
    with d3:
        st.caption("Pick a preset, or edit the dates directly. Both ends are inclusive, Singapore time. "
                   f"Log holds {len(log)} events" + (f", oldest {event_log.fmt_time(log['time'].min(), '%d %b %Y')}." if len(log) else "."))
    t0 = pd.Timestamp(start_d, tz=event_log.SGT)
    t1 = pd.Timestamp(end_d, tz=event_log.SGT) + pd.Timedelta(days=1)

    ev = log.copy()
    if len(ev):
        ev = ev[(ev["time"] >= t0) & (ev["time"] < t1)]
    if lines and len(ev):
        ev = ev[ev["line"].isin(lines)]
    if subs and len(ev):
        ev = ev[ev["subsystem_name"].isin(subs)]
    smap = {"Fault": "alert", "Watch": "watch", "Normal": "ok"}
    if states and len(ev):
        ev = ev[ev["state"].isin([smap[x] for x in states])]

    n_faults = int((ev["state"] == "alert").sum()) if len(ev) else 0
    if n_faults:
        html(ui.beacon(f"{n_faults} fault(s) in the selected range", "red markers on the map, lowest-health trains first in the roster"))
    def _known(col):
        return ev[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna() if len(ev) and col in ev else pd.Series(dtype=str)
    n_trains, n_stations = _known("train").nunique(), _known("station").nunique()
    n_unplaced = int(len(ev) - len(_known("train"))) if len(ev) else 0
    html(ui.kpis([
        ("Events in range", f"{len(ev)}", f"of {len(log)} logged · log updated {event_log.fmt_time(last)}"),
        ("Faults", f"{n_faults}", f"{int((ev['state'] == 'watch').sum()) if len(ev) else 0} on watch"),
        ("Trains affected", f"{n_trains}" if n_trains or not n_unplaced else "—",
         "sets with at least one event" if not n_unplaced else f"{n_unplaced} event(s) not tied to a train"),
        ("Stations affected", f"{n_stations}" if n_stations or not n_unplaced else "—",
         "places with at least one event" if not n_unplaced else "set train and station when you run a page"),
    ]))
    if n_unplaced:
        st.caption(f"{n_unplaced} event(s) in range came from runs with no train or station attached (for example "
                   "Run all on the competition test data), so they count here but cannot go on the map or the roster. "
                   "To place a run, open its subsystem page and fill in “Where did this data come from?” before analysing.")
    if len(log) and (log["source"] == "demo").any():
        st.caption("This dataset is the demo fleet: results assigned to train sets and stations and replayed over "
                   "the past week, so the filters have something to show. Remove it under Manage datasets.")

    # ---- map + roster
    left, right = st.columns([1.7, 1], gap="medium")
    with left:
        html(ui.section("Where events cluster"))
        weather = livemap.fetch_weather()
        agg = insight.station_events(ev, df)
        if len(ev) and agg.empty and not df.empty:
            html(ui.chip("unknown", "No located events in this selection",
                         f"{len(ev)} event(s) match, none has a station · widen the range or choose a dataset with locations"))
        if df.empty:
            html(ui.empty("Station map unavailable", ["data/stations/AmendmenttoMP2014RailStation.geojson is missing."]))
        else:
            view, focus, pick = dash_map_view(df, ev, lines[0] if lines else "NSL", lines or None)
            if pick == "Affected lines":
                st.caption("Lines with a fault or watch in range: " + ", ".join(focus))
            crowd = crowd_for_lines(key, lines) if key else None
            alerts = livemap.fetch_train_alerts(key) if key else None
            deck = insight.fleet_deck(df, agg, (focus if pick != "Whole Singapore" else lines), weather, view)
            deck.layers = insight.crowd_layer(crowd, df) + insight.alert_layer(alerts, df) + deck.layers
            map_chart(deck, key=f"fleet_map_{st.session_state.get('_dash_mapnonce', 0)}")
            crowd_caption(crowd)
            st.caption("Marker size = events at that station in range, colour = worst state, number = faults. "
                       + (f"Weather layer: NEA readings at {weather.get('reading_time', '—')} SGT, fetched {weather.get('fetched_at')}."
                          if weather.get("ok") else "Weather layer unavailable."))
    with right:
        html(ui.section("Train health · lowest first"))
        hi = insight.health_index(ev)
        if len(hi):
            def cell(state):
                return f'<span class="nw-cell {state}" title="{ui.STATES[state][1]}"></span>'
            rows = "".join(
                f'<tr><td><b>{x.train}</b><div class="muted">{x.line}</div></td>'
                f'<td><div class="nw-health"><span style="width:{x.health:.0f}%" class="{"alert" if x.health < 60 else "watch" if x.health < 85 else "ok"}"></span></div>'
                f'<span class="mono">{x.health:.0f}</span></td>'
                f'<td class="cells">{cell(x.door)}{cell(x.shm)}{cell(x.rail)}{cell(x.acv)}</td>'
                f'<td class="mono">{x.faults}/{x.events}</td>'
                f'<td class="muted">{event_log.fmt_time(x.last)}</td></tr>'
                for x in hi.head(14).itertuples())
            html(f'<div class="nw-panel"><table class="nw-table"><thead><tr><th>Train</th><th>Health</th>'
                 f'<th title="Door · Structure · Rail · Air-con">D·S·R·A</th><th>Faults</th><th>Latest</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table>'
                 f'<div class="muted" style="font-size:11px;margin-top:8px">Health index: 100 minus severity-weighted '
                 f'faults and watches in range, floor 40. Cells: worst state per subsystem (Door, Structure, Rail, Air-con).</div></div>')
        else:
            html(ui.empty("No trains in range", [
                (f"The {len(ev)} event(s) in range have no train attached. " if len(ev) else "")
                + "Widen the time range, or run a subsystem page and set the train under "
                  "“Where did this data come from?”."]))
        html(ui.section("By subsystem"))
        plot(charts.events_by_subsystem(ev))

    html(ui.section("Timeline"))
    plot(charts.events_timeline(ev, "D" if (t1 - t0) > pd.Timedelta(days=2) else "h", t0, t1))

    html(ui.section("Events"))
    if len(ev):
        show = ev.head(200).copy()
        rows = "".join(
            f'<tr><td class="mono">{event_log.fmt_time(x.time)}</td><td>{quickdrop.SUBSYSTEM_EMOJI.get(x.subsystem, "")} {x.subsystem_name}</td>'
            f'<td>{x.title}</td><td class="muted">{txt(x.detail, "")}</td><td class="muted">{txt(x.train)} · {txt(x.station).title()}</td>'
            f'<td>{ui.pill(x.state, ui.STATES[x.state][1])}</td></tr>'
            for x in show.head(25).itertuples())
        html(f'<div class="nw-panel"><table class="nw-table"><thead><tr><th>Time</th><th>Subsystem</th><th>Event</th>'
             f'<th>Evidence</th><th>Train · station</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>')
        if len(ev) > 25:
            with st.expander(f"All {len(ev)} events in range"):
                st.dataframe(ev[["time", "subsystem_name", "state", "title", "detail", "train", "line", "station", "file_id"]],
                             hide_index=True, width="stretch", column_config=EVENT_COLS)
        st.download_button("Download events in range (CSV)", ev.to_csv(index=False).encode(), "fleet_events.csv", "text/csv")
    else:
        html(ui.empty("No events in this range", ["Widen the filters, or run a subsystem page."]))

    # ---- live status
    html(ui.section("Live service status") + ui.live("live feeds"))
    if weather.get("ok") and not df.empty:
        focus = df[df["key"].isin(livemap.LINES[lines[0]][1])] if lines else df
        w = livemap.weather_near(weather, float(focus["lat"].mean()), float(focus["lon"].mean()))
        html(ui.kpis([("Air temperature", f"{livemap.weather_emoji(w.get('forecast'), w.get('rain_mm'))} {w.get('temp_c', float('nan')):.1f} °C", f"{w.get('station', '?')} · reading {weather.get('reading_time')} SGT"),
                      ("Rainfall, last 5 min", f"{w.get('rain_mm', 0):.1f} mm", "heavy rain slows the network and loads the doors"),
                      ("2-hour forecast", f"{w.get('forecast', '—')}", f"{w.get('area', '')} · NEA via data.gov.sg"),
                      ("Heat load on air-con", "high" if (w.get('temp_c') or 0) >= 31 else "normal", "leaks show first on hot afternoons")]))
    # Two equal-height bordered panels; long feeds scroll inside their own box.
    a, b = st.columns(2, gap="medium")
    with a:
        html('<div class="nw-feedtitle">LTA DataMall · Train service alerts <span>official</span></div>')
        with st.container(height=520, border=True, key="nw_feed_lta"):
            if not key:
                st.caption("This is the official disruption feed. It needs your own AccountKey (free at datamall.lta.gov.sg). "
                           "Paste it in the field above; the app sends it as the `AccountKey` header exactly like the LTA "
                           "curl example, and shows the result here with the time it was fetched.")
            else:
                al = livemap.fetch_train_alerts(key)
                if not al["ok"]:
                    html(ui.chip("unknown", "Feed unavailable", al["reason"]))
                    st.caption("A 401 means the key was rejected; check it was copied whole. DataMall keys can take a few minutes to activate.")
                elif al["status"] == 1 and not al["segments"]:
                    html(ui.chip("ok", "All lines running normally", f"DataMall status 1 · fetched {al['fetched_at']} SGT"))
                    for m in al["messages"]:
                        st.caption("📋 " + m)
                else:
                    html(ui.chip("alert", "Disruption reported", f"{len(al['segments'])} affected segment(s) · fetched {al['fetched_at']} SGT"))
                    for seg in al["segments"]:
                        mine = str(seg.get("Line", "")).upper() in lines
                        st.markdown(("🔴 **On a selected line** · " if mine else "") +
                                    f"**{seg.get('Line', '?')}** {seg.get('Direction', '')} · {', '.join(n.title() for n in seg.get('StationNames', [])) or seg.get('Stations', '?')} · "
                                    f"free bus: {seg.get('FreePublicBus', '-')} · shuttle: {seg.get('FreeMRTShuttle', '-')}")
                    for m in al["messages"]:
                        st.caption(m)
        if key and st.button("Refresh DataMall", key="fleet_refresh_lta"):
            livemap.fetch_train_alerts.clear()
            st.rerun()
    with b:
        html('<div class="nw-feedtitle">SGMRT community channel · t.me/s/sgmrt <span>unverified</span></div>')
        with st.container(height=520, border=True, key="nw_feed_tg"):
            feed = livemap.fetch_sgmrt()
            if not feed["ok"]:
                html(ui.chip("unknown", "Feed unavailable", feed["reason"]))
            elif not feed["posts"]:
                st.caption("No posts parsed.")
            else:
                hits = [p for p in feed["posts"] if any(livemap.line_mentioned(p["text"], ln) for ln in (lines or livemap.LINES))]
                html(ui.chip("watch" if hits else "ok",
                             f"{len(hits)} recent post(s) mention {'the selected lines' if lines else 'a line'}" if hits else "no recent line mentions",
                             f"community reports, unverified · fetched {feed.get('fetched_at')} SGT"))
                for p in feed["posts"]:
                    when = "" if pd.isna(p["time"]) else p["time"].tz_convert("Asia/Singapore").strftime("%d %b %H:%M")
                    mark = "🔴 " if any(livemap.line_mentioned(p["text"], ln) for ln in (lines or livemap.LINES)) else ""
                    body = " ".join(str(p["text"]).split())     # one paragraph: a trailing "- SMRT" signature is not a list
                    st.markdown(f"{mark}`{when}` {body[:280]}{'…' if len(body) > 280 else ''}")
        if st.button("Refresh feed", key="fleet_refresh_tg"):
            livemap.fetch_sgmrt.clear()
            st.rerun()
    st.caption("Live feeds are context for the maintenance decision, not inputs to any model: every event in the log "
               "comes from the uploaded sensor data.")
    with st.expander("Log maintenance"):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Seed a demo fleet from the competition test run", key="fleet_seed"):
                cached = result_cache.load() or {}
                by_line = {code: [n for n in names if n in set(df["key"])] for code, (_, names) in livemap.LINES.items()}
                st.toast(f"{event_log.seed_demo(cached, by_line)} demo events written")
                st.rerun()
        with c2:
            if st.button("Remove demo events (keep my runs)", key="fleet_clear_demo"):
                event_log.clear("demo")
                st.rerun()


def validation_page() -> None:
    html(ui.header("Evidence", "How the numbers were validated",
                   "Every score on this console is the official competition metric on data the model "
                   "never saw, with the split chosen so nothing can leak, the spread across folds shown, "
                   "and the in-sample score alongside so overfitting is visible rather than hidden."))
    html(ui.steps([
        ("Split so it cannot leak", "Door by contiguous time blocks; SHM by file with constants fitted in-fold; "
                                    "Rail by file with duplicate rows grouped; ACV by whole case."),
        ("Score with the judge's formula", "scoring/metrics.py reimplements all four; 39 tests pin them to the Info Kit worked examples."),
        ("Report the spread", "Mean and standard deviation across folds, never a single lucky split."),
        ("Check for overfitting", "In-sample against out-of-fold. A large gap on a flexible model is expected; the out-of-fold number is the one that ships."),
    ]))
    for spec in SUBSYSTEMS.values():
        card = spec.model_card()
        if not card:
            continue
        v = card["validation"]
        html(ui.section(f"{spec.name} · model {card['model_version']}"))
        if spec.key == "door":
            folds = [f["iou_weighted_f1"] for f in v["folds"]]
            mean, std, base, ins = v["mean_iou_weighted_f1"], v["std_iou_weighted_f1"], 0.7273, None
            note = ("One door, one recording, 110 cycles. Any gap threshold from 0.05 s to 5 s recovers the "
                    "same 110 segments, so the score reduces to per-cycle classification. Treat 0.99 as an upper bound.")
        elif spec.key == "shm":
            folds = [f["score"] for f in v["folds"]]
            mean, std, base, ins = v["mean_score"], v["std_score"], 0.085, 0.9739
            note = (f"Two-parameter physics fit; m stays within {v['m_range_across_folds']} across folds and pinning "
                    f"m = 5 gives {v['fixed_m5_mean_score']:.4f}. In-sample {ins:.4f} versus cross-validated "
                    f"{mean:.4f}: a 0.001 gap, which is what a model that cannot overfit looks like.")
        elif spec.key == "rail":
            folds, mean, std = v["folds"], v["mean_score"], v["std_score"]
            base, ins = v.get("always_normal_baseline"), v.get("in_sample_score")
            note = (f"Pooled out-of-fold macro F1 {v['pooled_out_of_fold_score']:.4f}; per class "
                    + ", ".join(f"{k} {x:.2f}" for k, x in v["per_class_f1"].items())
                    + f". Side I recall {v['side_i_recall']:.2f} is the known weakness: 14 files only."
                    + (f" In-sample {ins:.3f}: the forest memorises its training set, so only the fold scores count."
                       if ins else ""))
        else:
            ranks = list(v["per_case_rank"].values())
            folds = [(8 - (r - 1)) / 8 for r in ranks]
            mean, std, base, ins = v["mean_score"], v["std_score"], v["random_ranking_baseline"], None
            note = ("A fixed rule with no fitted parameters, so nothing can be tuned to the six answers. "
                    "Case 04 (the 63-parameter file) ranks the true car second; the rest rank it first.")
        a, b = st.columns([1.4, 1], gap="medium")
        with a:
            plot(charts.fold_scores(folds, mean, std, base, METRIC_SHORT[spec.key], ins))
        with b:
            html(ui.kpis([(METRIC_SHORT[spec.key], f"{mean:.4f}", f"± {std:.4f} across {len(folds)} folds"),
                          ("Naive baseline", f"{base:.3f}" if base is not None else "—", None)]))
            st.markdown(f"**Split.** {v['split']}")
            st.caption(note)
    import json as _json
    html(ui.section("Training data behind the models"))
    if True:
        d1, d2 = st.columns(2, gap="medium")
        with d1:
            st.caption("Door · 110 labelled cycles in one 24-minute stream")
            plot(charts.class_bar({"Normal": 80, "Abnormal resistance": 30}, {"Normal": "status-ok", "Abnormal resistance": "status-alert"}))
            st.caption("Rail · 272 one-second recordings")
            plot(charts.class_bar({"Normal": 234, "Side I": 14, "Side II": 24}, charts.RAIL_COLOR))
        with d2:
            lab = DATA_ROOT / "SHM" / "Train_Labels.csv"
            st.caption("Structural health · reference damage of the 64 training files")
            if lab.exists():
                plot(charts.damage_hist(pd.read_csv(lab)["damage"]))
            else:
                st.caption("dataset not present on this machine")
            st.caption("Air conditioning · faulty car in the 6 training cases")
            plot(charts.class_bar({"01": 2, "02": 1, "03": 1, "04": 1, "06": 1}, None))
        st.caption("Class balance drives the metric: macro F1 for Rail, IoU-weighted F1 for Door, relative error "
                   "for SHM, rank decay for ACV. The Validation page shows how each was scored.")

    html(ui.section("Model comparison · pre-registered search"))
    st.caption("Every candidate scored under the same leakage-safe protocol; the decision rule was written "
               "before the run (scripts/model_search.py). A candidate that does not clear the rule is "
               "reported and not adopted.")
    for key, name in (("rail", "Rail corrugation"), ("door", "Door"), ("acv", "Air conditioning")):
        bp = PROJECT_ROOT / "subsystems" / key / "artifacts" / "benchmark.json"
        if not bp.exists():
            continue
        b = _json.loads(bp.read_text(encoding="utf-8"))
        d = b["decision"]
        html(ui.chip("ok" if d["adopt"] else "watch", f"{name}: " + ("new model adopted" if d["adopt"] else "incumbent kept"), d["reason"]))
        t = pd.DataFrame(b["table"])
        if key == "rail":
            t = t[["candidate", "features", "mean", "std", "repeats"]].rename(columns={"mean": "repeated CV macro F1", "std": "sd"})
            n = b["nested"]
            st.markdown(f"Nested estimate of the whole search: **{n['macro_f1_pooled']:.4f}** pooled, "
                        f"{n['mean']:.4f} ± {n['std']:.4f} across the 5 outer folds. The candidate chosen inside each "
                        f"outer fold: {', '.join(c['chosen'] + '/' + c['features'] for c in n['chosen_per_fold'])}.")
        elif key == "door":
            t = t.rename(columns={"mean": "IoU-weighted F1", "std": "sd"})
        else:
            t = t.rename(columns={"mean": "rank decay", "per_case": "per case"})
        st.dataframe(t.head(12), hide_index=True, width="stretch")

    html(ui.section("Learning loop · outcomes, drift, retrain gate"))
    oc = event_log.outcomes()
    rl = PROJECT_ROOT / "data" / "retrain_log.json"
    c1, c2, c3 = st.columns(3)
    with c1:
        html(ui.kpis([("Labelled outcomes", f"{len(oc)}", "faults closed with a finding")]))
    with c2:
        n_conf = int((oc["outcome"] == "confirmed").sum()) if len(oc) else 0
        html(ui.kpis([("Confirmed faults", f"{n_conf}", f"{int((oc['outcome'] == 'no_fault_found').sum()) if len(oc) else 0} no fault found")]))
    with c3:
        last = _json.loads(rl.read_text(encoding="utf-8"))[-1] if rl.exists() else None
        html(ui.kpis([("Last retrain", last["at"][:16] if last else "never", (last["summary"][:60] if last else "python -m scripts.retrain"))]))
    st.markdown("""
How the models learn: closing a fault with **Confirmed** or **No fault found** turns that verdict into a labelled
example, and the raw file is kept under `data/uploads/`. `scripts/retrain.py` retrains Door and Rail on the training
data plus those examples under the same leakage-safe folds, and **promotes the challenger only if it beats the
incumbent by the pre-registered margin**; otherwise the attempt is logged and nothing changes. Every run also
records feature drift against the training distribution, shown on each subsystem page. SHM is a physics fit and
ACV a fixed rule: outcomes tune their watch bands, they do not retrain.
""")
    if len(oc):
        st.dataframe(oc[["time", "subsystem_name", "title", "outcome", "train", "station", "stored_file"]].head(20),
                     hide_index=True, width="stretch", column_config=EVENT_COLS)

    html(ui.section("What the classifiers rely on"))
    a, b = st.columns(2, gap="medium")
    for col, key, name in ((a, "door", "Door"), (b, "rail", "Rail corrugation")):
        spec = SUBSYSTEMS[key]
        if not spec.available:
            continue
        try:
            art = spec.module.load_saved_model()[0]
            model = art["model"] if isinstance(art, dict) else art
            names = art.get("feature_names") if isinstance(art, dict) else spec.model_card().get("feature_columns")
            imp = getattr(model, "feature_importances_", None)
        except Exception:
            imp = None
        with col:
            st.markdown(f"**{name}**")
            if imp is None or names is None:
                st.caption("No importances for this model type.")
            else:
                plot(charts.importances(pd.Series(imp, index=names)))
    st.caption("Impurity-based importances from the random forest: which features the trees split on most. "
               "Door leans on sustained current and current per unit back-EMF, the resistance signal itself.")

    exp = PROJECT_ROOT / "subsystems" / "rail" / "artifacts" / "experiment_wavelength.json"
    if exp.exists():
        r = _json.loads(exp.read_text(encoding="utf-8"))
        html(ui.section("Rail refinement · pre-registered experiment"))
        d = r["decision"]
        html(ui.chip("ok" if d["adopt_wavelength"] else "watch",
                     "Wavelength features adopted" if d["adopt_wavelength"] else "Baseline kept (null result)",
                     d["reason"]))
        rows = [{"feature set": k, "n features": r["n_features"][k],
                 "original folds (pooled)": f"{x['pooled_macro_f1']:.4f}",
                 "mean ± sd": f"{x['mean']:.4f} ± {x['std']:.4f}",
                 "fresh shuffles ×3": (f"{r['fresh_shuffles'][k]['mean']:.4f}" if k in r["fresh_shuffles"] else "—")}
                for k, x in r["original_folds"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Decision rule fixed before running: adopt only if better on the original folds and on three "
                   "fresh grouped shuffles. Same classifier, same augmentation, same 272 files.")


def custom_page() -> None:
    html(ui.header("New data", "Screen a dataset that has no model yet",
                   "Screen a new parameter before it has labels. Upload any sensor export, point at the "
                   "columns, and get the same label-free peer comparison the air-conditioning model "
                   "uses, or a robust drift score for a single series. When labels arrive, promote it "
                   "to a full subsystem with the recipe on the Method page."))
    up = st.file_uploader("Drop a .csv or .xlsx export", type=["csv", "xlsx"], key="generic_upload")
    if not up:
        st.caption("Try it on a provided ACV case: it recovers the same ranking as the validated model.")
        provided = SUBSYSTEMS["acv"].test_inputs()
        if provided and st.button("Use acv_test_case.xlsx"):
            st.session_state["generic_demo"] = provided[0]
        demo = st.session_state.get("generic_demo")
        if demo is None:
            return
        b = io.BytesIO(demo.read_bytes()); b.name = demo.name; up = b
    with st.spinner("Reading..."):
        df = monitor.load_table(up)
    tcol = monitor.guess_time_column(df)
    num = monitor.numeric_columns(df, exclude=tcol)
    html(ui.kpis([("Rows", f"{len(df):,}", None), ("Columns", f"{df.shape[1]}", f"{len(num)} numeric"),
                  ("Time column", tcol or "none found", None)]))
    if not num:
        st.warning("No numeric measurement columns were found in this file. Check it is a sensor export "
                   "with one reading per row.")
        return
    method = st.segmented_control("Method", ["Peer comparison across units", "Drift in one series"],
                                  default="Peer comparison across units", key="generic_method")
    if method == "Peer comparison across units":
        default = [c for c in num if "Indoor Average Temperature" in str(c)] or num[:8]
        units = st.multiselect("Columns that are comparable units (one per car, motor, sensor...)",
                               num, default=default[:8], key="generic_units")
        label = st.text_input("What is a unit called?", value="Car" if units and str(units[0]).startswith("Car") else "Unit")
        if len(units) < 2:
            st.caption("Pick at least two columns.")
            return
        rank = monitor.peer_ranking(df, units)
        state, title, meaning = monitor.verdict_for_ranking(rank, label)
        html(ui.verdict(state, "Parameter monitor", title, meaning,
                        f"Inspect {label} {rank.iloc[0]['unit']} first. This is a ranking, not a probability; "
                        "collect labelled cases to validate it.",
                        f"label-free peer-relative excess · {len(units)} units · {len(df):,} rows", "Screen"))
        a, b = st.columns([1, 1.4], gap="medium")
        with a:
            html(ui.car_rank([(str(r.label), None if pd.isna(r.excess_mean) else float(r.excess_mean))
                              for r in rank.itertuples()], "Bars normalise to the top unit."))
        with b:
            top = str(rank.iloc[0]["unit"])
            plot(charts.generic_excess(monitor.peer_excess_series(df, units, tcol), units, top))
        st.dataframe(rank, hide_index=True, width="stretch")
        st.download_button("Download ranking CSV", rank.to_csv(index=False).encode(), "parameter_ranking.csv", "text/csv")
    else:
        col = st.selectbox("Series", num, key="generic_series")
        window = st.slider("Window (rows)", 10, 500, 50, key="generic_window")
        d = monitor.drift_screen(df[col], window)
        worst = d["robust_z"].abs().max()
        state = "alert" if worst >= 3 else "watch" if worst >= 2 else "ok"
        html(ui.verdict(state, "Parameter monitor",
                        f"Largest drift {worst:.1f} MAD units" if np.isfinite(worst) else "Series too short",
                        "Each rolling window is compared with the whole series' median, scaled by the median "
                        "absolute deviation, so one outlier cannot move the baseline.",
                        "Above 3 is a step or sustained drift worth a look; between 2 and 3 keep watching.",
                        f"robust drift screen · window {window} rows", "Screen"))
        plot(charts.generic_drift(d))
    with st.expander("How to promote a parameter to a full subsystem"):
        st.markdown("""
1. **Write the truth down first.** Columns, sampling rate, timestamp format, class counts, sizes, parsing traps. `PROJECT-STATE.md` is the template.
2. **Transcribe the scoring formula and test it** in `scoring/metrics.py` before any model exists.
3. **Choose the split that cannot leak**: by time block, by file, or by whole case, never by row.
4. **Pre-register** the measure, the split and the success criterion. Report a null as a null.
5. Build `subsystems/<key>/predict.py` exposing `predict(files)` and `analyze(files)`, plus `artifacts/config.json` with the validation block.
6. Add one `SubsystemSpec` to `core/registry.py`. The overview, dashboard, validation and submission pages pick it up with no page code.
""")


def submission_page() -> None:
    html(ui.header("Competition deliverable", "Build predictions.zip",
                   "Runs every validated model over the competition test inputs, checks each "
                   "output against the official schema, and packages the CSVs at the top "
                   "level of a single zip - the file judges score."))
    chosen = []
    for spec in SUBSYSTEMS.values():
        n = len(spec.test_inputs())
        c1, c2 = st.columns([3, 2])
        with c1:
            if spec.available:
                if st.checkbox(f"**{spec.name}** — {n} test file{'s' if n != 1 else ''} → "
                               f"`{SCHEMAS[spec.key].filename}`", value=True, key=f"sub_{spec.key}"):
                    chosen.append(spec)
            else:
                st.checkbox(f"**{spec.name}** — model pending", value=False, disabled=True,
                            key=f"sub_{spec.key}")
        with c2:
            html(ui.chip("ok", "Ready") if spec.available and n else
                 ui.chip("unknown", "Pending" if not spec.available else "No test input"))

    if not st.button("Run models and build predictions.zip", type="primary",
                     disabled=not chosen):
        st.caption("The specification allows zipping only the subsystems you attempted. "
                   "Pending subsystems are left out rather than filled with a guess.")
        return

    frames, report = {}, []
    bar = st.progress(0.0, text="Starting...")
    for i, spec in enumerate(chosen):
        inputs = spec.test_inputs()
        bar.progress(i / len(chosen), text=f"{spec.name}: running {len(inputs)} file(s)...")
        files = as_files([(p.name, p.read_bytes()) for p in inputs])
        df = spec.module.predict(files)
        expected = None if spec.key == "door" else [p.name for p in inputs]
        errs = validate_submission(spec.key, df, expected_ids=expected)
        report.append((spec, df, errs))
        if not errs:
            frames[spec.key] = df
    bar.progress(1.0, text="Validating and packaging...")

    for spec, df, errs in report:
        state = "ok" if not errs else "alert"
        html(ui.chip(state, "Schema valid" if not errs else "Failed validation",
                     f"{spec.name} · {len(df)} rows"))
        for e in errs:
            st.error(e)
        with st.expander(f"Preview {SCHEMAS[spec.key].filename}"):
            st.dataframe(df.head(12), hide_index=True, width="stretch")

    if not frames:
        st.error("Nothing passed validation; no zip was written.")
        return
    blob = build_predictions_zip(frames)
    out_dir = PROJECT_ROOT / "predictions"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "predictions.zip").write_bytes(blob)
    for key, df in frames.items():
        df.to_csv(out_dir / SCHEMAS[key].filename, index=False)
    bar.empty()
    st.success(f"predictions.zip built with {len(frames)} validated file(s) and saved to "
               f"predictions/predictions.zip")
    st.download_button("Download predictions.zip", blob, "predictions.zip",
                       "application/zip", type="primary")


def method_page() -> None:
    html(ui.header("How it works", "Method and architecture",
                   "Deterministic, physically grounded models; validation designed to "
                   "prevent leakage; one interface for every subsystem."))
    html(ui.section("Architecture"))
    st.graphviz_chart(f"""
digraph G {{
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="IBM Plex Sans", fontsize=11,
        color="{T('line-hairline')}", fillcolor="{T('surface-card')}", fontcolor="{T('ink-primary')}", margin="0.18,0.1"];
  edge [color="{T('ink-muted')}", arrowsize=0.6];
  ui [label="Streamlit console\\napp/", fillcolor="{T('surface-sunken')}"];
  reg [label="Subsystem registry\\ncore/registry.py"];
  sub [label="Submission validator\\n+ zip builder\\ncore/submission.py"];
  door [label="subsystems/door\\npredict() · analyze()"];
  shm [label="subsystems/shm\\npredict() · analyze()"];
  rail [label="subsystems/rail\\npredict() · analyze()"];
  acv [label="subsystems/acv\\npredict() · analyze()"];
  live [label="app/livemap.py\\nPS2 stations + LTA/SGMRT feeds", fillcolor="{T('surface-sunken')}"];
  art [label="artifacts/\\nmodel + config.json", fillcolor="{T('surface-sunken')}"];
  tok [label="design-system/\\ntokens.json", fillcolor="{T('surface-sunken')}"];
  score [label="scoring/metrics.py\\nofficial formulas, 28 tests", fillcolor="{T('surface-sunken')}"];
  zip [label="predictions.zip", shape=note];
  tok -> ui; ui -> reg; reg -> door; reg -> shm; reg -> rail; reg -> acv;
  door -> art; shm -> art; rail -> art; acv -> art; live -> ui; ui -> sub; sub -> zip; score -> door [style=dashed, label=" validates", fontsize=9, fontcolor="{T('ink-muted')}"];
  score -> shm [style=dashed];
}}""", width="stretch")

    html(ui.section("Validation"))
    rows = []
    for spec in SUBSYSTEMS.values():
        card = spec.model_card()
        if card:
            v = card["validation"]
            mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
            std = v.get("std_iou_weighted_f1", v.get("std_score"))
            rows.append({"Subsystem": spec.name, "Model": card["model_version"],
                         "Metric": v["metric"], "Split": v["split"],
                         "Score": f"{mean:.4f} ± {std:.4f}"})
        else:
            rows.append({"Subsystem": spec.name, "Model": "—", "Metric": "—",
                         "Split": "—", "Score": "pending"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    html(ui.section("Deliverables checklist · spec Section 4"))
    st.markdown("""
| Item | Where | Status |
|---|---|---|
| App covering every attempted subsystem, usable by a non-technical person | this console | done |
| `predictions.zip`, `*_predictions.csv` at the top level, generated through the app | Submission page, or `python -m scripts.build_predictions` | done, schema-validated |
| Demo video ≤ 3 min | record with the app; path in `app/README.md` | to record |
| `predict.py --input/--output` CLI (each Info Kit, Section 5) | `predict.py` at the project root, same inference path as the app | done |
| Team folder: `demo_video`, `predictions.zip`, `app/`, `Optional_Items/{write_up, Door, ACV, Rail Corrugation, SHM}/{code,model}` | `python -m scripts.package_submission --team "<name>"` | done |
| Leakage-safe split, stated assumptions, reported spread | Validation page, `PROJECT-STATE.md` | done |
""")
    html(ui.section("Design method"))
    st.markdown("""
The interface follows three rules borrowed from the products operators already use and from Apple's
Human Interface Guidelines: **clarity** (one verdict per screen, in words, with the action next to it),
**deference** (the chrome stays quiet so the data reads first), and **depth through progressive
disclosure** (status strip → verdict card → evidence charts → per-item inspector → raw table).
Alstom HealthHub and Siemens Railigent X organise fleet health the same way: a real-time fleet board,
then a drill-down per asset, with the network map as the shared frame. See `DESIGN.md` for sources.
""")
    html(ui.section("Principles"))
    st.markdown("""
- **Models encode the physics.** SHM fits the two constants of the S-N curve that generated
  its labels - and recovers m ≈ 5, the standard exponent for welded steel. Door's strongest
  features are sustained motor current and current per unit back-EMF: the mechanical
  resistance signal itself.
- **Validation cannot leak.** Door is split into contiguous time blocks, never random rows.
  SHM's constants are fitted inside each fold only. Every score is on data the model did not
  see, with its spread shown.
- **Best model per subsystem, from two builds.** Door and SHM come from this workspace (physics
  first: Miner's rule recovers m ≈ 5). Rail and ACV are ported unchanged from the teammate's
  final_streamlit_app build, whose leakage-safe folds beat every alternative tried. On the Door
  test stream the two builds agree on all 38 boundaries and 37 of 38 labels.
- **Live context stays outside the models.** The Fleet page reads LTA DataMall and the SGMRT
  channel for situational awareness; no live feed touches a prediction.
- **One interface.** Every subsystem exposes `predict(uploaded_files)`; the app never
  contains modelling code, so a better model drops in without touching the interface.
- **Every download is schema-checked** against the official format before it can leave.
""")


#: The Overview tile's dropdown: page, one line on what it is for.
OVERVIEW_MENU = [("PAGE_DASHBOARD", "What needs doing now, the work queue and the network map"),
                 ("PAGE_FLEET", "Every event by time, line, train and station"),
                 ("PAGE_LIVE", "LTA DataMall feeds, refreshing on their own")]


def subsystem_switcher(current, tag: str = "") -> None:
    """Large tiles above every page: an Overview tile whose dropdown opens the dashboard,
    fleet view and live feeds, then one tap to any subsystem, each with its state."""
    try:
        states = insight.fleet_state(session_results())
        ev = source_events(st.session_state.get("data_source", LIVE_ONLY), event_log.with_status(event_log.load()))
        counts = open_counts(ev)
    except Exception:
        states, counts = {}, {}
    word = {"ok": "● Normal", "watch": "◐ Watch", "alert": "✕ Fault", "unknown": "— Not run"}
    with st.container(key=f"nw_switch{tag}"):
        cols = st.columns([1.15, 1, 1, 1, 1], gap="small")
        menu = [(globals()[name], blurb) for name, blurb in OVERVIEW_MENU]
        cur = getattr(current, "url_path", None)
        on = next((pg for pg, _ in menu if pg.url_path == cur), None)
        with cols[0], st.container(key=f"nw_ov{tag}{'_here' if on else ''}"):
            with st.popover(f"Overview · {on.title}" if on else "Overview", icon=":material/space_dashboard:",
                            width="stretch"):
                for pg, blurb in menu:
                    st.page_link(pg, label=pg.title + ("  ·  you are here" if pg is on else ""),
                                 icon=pg.icon, width="stretch")
                    st.caption(blurb)
        for col, (k, page) in zip(cols[1:], PAGE_BY_KEY.items()):
            s_ = states.get(k, "unknown")
            c = counts.get(k, {})
            label = word[s_]
            if s_ == "unknown" and (c.get("alert") or c.get("watch")):
                s_ = "alert" if c.get("alert") else "watch"
                n = c.get("alert") or c.get("watch")
                label = f"{'✕' if s_ == 'alert' else '◐'} {n} open"
            here = getattr(current, "url_path", None) == page.url_path
            with col, st.container(key=f"nw_sw{tag}_{k}_{s_}{'_here' if here else ''}"):
                st.page_link(page, label=f"{page.title}  \n{label}", icon=page.icon, width="stretch")


PAGE_DASHBOARD = st.Page(overview_page, title="Dashboard", icon=":material/dashboard:", default=True)
PAGE_FLEET = st.Page(fleet_page, title="Fleet view", icon=":material/map:", url_path="fleet")
PAGE_LIVE = st.Page(live_lta_page, title="Live LTA", icon=":material/sensors:", url_path="live")
PAGE_DOOR = st.Page(door_page, title="Door", icon=":material/door_sliding:", url_path="door")
PAGE_SHM = st.Page(shm_page, title="Structural health", icon=":material/architecture:", url_path="shm")
PAGE_RAIL = st.Page(rail_page, title="Rail", icon=":material/train:", url_path="rail")
PAGE_ACV = st.Page(acv_page, title="Air conditioning", icon=":material/ac_unit:", url_path="acv")
PAGE_BY_KEY = {"door": PAGE_DOOR, "shm": PAGE_SHM, "rail": PAGE_RAIL, "acv": PAGE_ACV}
pages = {
    "Overview": [PAGE_DASHBOARD, PAGE_FLEET, PAGE_LIVE],
    "Check a train": [PAGE_DOOR, PAGE_SHM, PAGE_RAIL, PAGE_ACV],
    "New data": [
        st.Page(custom_page, title="Screen a new dataset", icon=":material/add_chart:", url_path="monitor"),
    ],
    "Evidence": [
        st.Page(validation_page, title="Validation", icon=":material/fact_check:", url_path="validation"),
        st.Page(submission_page, title="Submission", icon=":material/inventory_2:", url_path="submission"),
        st.Page(method_page, title="Method", icon=":material/schema:", url_path="method"),
    ],
}
_test_page = os.environ.get("NEBULA_TEST_PAGE")
if _test_page:
    _fn = {"": overview_page, "fleet": fleet_page, "live": live_lta_page, "door": door_page, "shm": shm_page, "rail": rail_page,
           "acv": acv_page, "monitor": custom_page, "validation": validation_page,
           "submission": submission_page, "method": method_page}[_test_page]
    _fn()
else:
    _nav = st.navigation(pages, position="top")
    # Drawn after the page runs (into a slot at the top), so a tile's state reflects an
    # analysis the page has just done rather than the previous run.
    _slot = st.empty()
    with _slot.container():
        subsystem_switcher(_nav)                  # instant, with the states known so far
    try:
        _nav.run()
    finally:
        with _slot.container():
            subsystem_switcher(_nav, "after")    # refreshed in place once the page has run
