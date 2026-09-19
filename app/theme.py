"""App theme, derived from the design system's tokens.json.

There is exactly one source of colour, type and spacing: the published Nebula
Wayside design system. This module reads it, resolves aliases, and emits both
the page CSS and the chart palette, so the app cannot drift from the system.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

TOKENS_PATH = (Path(__file__).resolve().parents[1]
               / "design-system" / "project" / "tokens.json")
THEME = "light"         # the console is light only


def set_theme(name: str) -> None:
    """Kept for callers; the console is light only."""
    global THEME
    THEME = "light"


def map_style() -> str:
    return "light" if THEME == "light" else "dark"


def tokens() -> dict[str, str]:
    return _tokens(THEME)


@lru_cache(maxsize=2)
def _tokens(theme: str) -> dict[str, str]:
    """Flat name -> CSS value map for one theme, aliases resolved."""
    THEME_ = theme
    data = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    raw_colors = {}
    for t in data["color"]["tokens"]:
        v = t["value"]
        raw_colors[t["name"]] = v.get(THEME_, v.get("light")) if isinstance(v, dict) else v
    alias = re.compile(r"^\{(.+)\}$")

    def resolve(name: str, depth: int = 0) -> str:
        v = raw_colors[name]
        m = alias.match(v)
        if m and depth < 16:
            return resolve(m.group(1), depth + 1)
        return v

    for name in raw_colors:
        out[name] = resolve(name)
    for fam in ("spacing", "radius", "stroke"):
        for t in data.get(fam, {}).get("tokens", []):
            out[t["name"]] = str(t["value"])
    for t in data.get("shadow", {}).get("tokens", []):
        v = t["value"]
        out[t["name"]] = v.get(THEME_, v.get("light")) if isinstance(v, dict) else v
    for key, stack in data["type"]["families"].items():
        out[f"font-{key}"] = stack
    return out


def T(name: str) -> str:
    return tokens()[name]


STATE_TOKEN = {"ok": "status-ok", "watch": "status-watch",
               "alert": "status-alert", "unknown": "status-unknown"}


def css() -> str:
    t = tokens()
    root = "\n".join(f"  --{k}: {v};" for k, v in t.items())
    root += "\n  --nw-scheme: " + ("dark" if THEME == "dark" else "light") + ";"
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root {{
{root}
}}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  color-scheme: var(--nw-scheme);
  background: var(--surface-page);
  color: var(--ink-primary);
  font-family: var(--font-sans);
}}
.stApp :is(p, li, label, h1, h2, h3, h4, input, textarea, button, td, th, a),
.stApp [data-testid="stMarkdownContainer"] {{ font-family: var(--font-sans); }}
/* never restyle icon glyphs: they are a ligature font, not text */
[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
.stApp code, .stApp pre {{ font-family: var(--font-mono); }}
[data-testid="stHeader"] {{ background: var(--surface-page); z-index: 1000; }}
.block-container {{ padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1320px; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ font-size: 14px !important; line-height: 20px; }}
.stApp .stButtonGroup button, .stApp .stButton > button {{ font-size: 15px; }}
.stApp [data-testid="stWidgetLabel"] p {{ font-size: 14px; }}
h1, h2, h3 {{ font-family: var(--font-sans); color: var(--ink-primary); letter-spacing: -0.01em; }}

/* ---- page header ---- */
.nw-eyebrow {{ font-size: 12px; line-height: 16px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ink-muted); font-weight: 600; margin: 0 0 6px; display:flex; align-items:center; gap:8px; }}
.nw-eyebrow .dot {{ width: 8px; height: 8px; border-radius: 2px; display:inline-block; }}
.nw-h1 {{ font-size: 32px; line-height: 36px; font-weight: 600; letter-spacing: -0.01em; margin: 0 0 6px; }}
.nw-lede {{ font-size: 16px; line-height: 22px; color: var(--ink-secondary); margin: 0 0 20px; max-width: 760px; }}
.nw-section {{ font-size: 13px; line-height: 18px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; color: var(--ink-muted); margin: 28px 0 10px; }}

/* ---- status chip ---- */
.nw-chip {{ display:inline-flex; align-items:center; gap:8px; padding:4px 12px; border-radius:999px;
  font-size:13px; line-height:18px; font-weight:600; letter-spacing:.04em; white-space:nowrap; }}
.nw-chip .g {{ font-size: 11px; line-height: 1; }}
.nw-chip .d {{ color: var(--ink-secondary); font-weight: 400; letter-spacing: 0; }}
.nw-chip.ok {{ background: var(--status-ok-soft); color: var(--status-ok); }}
.nw-chip.watch {{ background: var(--status-watch-soft); color: var(--status-watch); }}
.nw-chip.alert {{ background: var(--status-alert-soft); color: var(--status-alert); }}
.nw-chip.unknown {{ background: var(--surface-sunken); color: var(--status-unknown); }}

/* ---- verdict card ---- */
.nw-card {{ background: var(--surface-card); border: 1px solid var(--line-hairline);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card); padding: 24px; }}
.nw-card .head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }}
.nw-card .sub {{ font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); }}
.nw-card h3 {{ font-size:22px; line-height:28px; font-weight:600; margin:0 0 8px; }}
.nw-card .meaning {{ font-size:16px; line-height:23px; color:var(--ink-secondary); margin:0 0 16px; }}
.nw-card .action {{ background:var(--surface-sunken); border-radius:var(--radius-md); padding:12px 16px;
  font-size:15px; line-height:22px; margin:0; }}
.nw-card .action b {{ font-weight:600; }}
.nw-card .evidence {{ font-family:var(--font-mono); font-size:13px; line-height:18px; color:var(--ink-muted); margin:12px 0 0; }}

/* ---- KPI tiles ---- */
.nw-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin: 0 0 4px; }}
.nw-kpi {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:16px 18px; }}
.nw-kpi .l {{ font-size:14px; line-height:18px; font-weight:500; color:var(--ink-secondary); margin-bottom:6px; }}
.nw-kpi .v {{ font-family:var(--font-mono); font-size:30px; line-height:34px; font-weight:500; color:var(--ink-primary); }}
.nw-kpi .s {{ font-size:13px; line-height:18px; color:var(--ink-muted); margin-top:4px; }}

/* ---- subsystem tiles (overview) ---- */
.nw-sys {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg);
  padding:20px; height:100%; position:relative; overflow:hidden; }}
.nw-sys .bar {{ position:absolute; left:0; top:0; right:0; height:4px; }}
.nw-sys .name {{ font-size:18px; line-height:24px; font-weight:600; margin:6px 0 4px; }}
.nw-sys .q {{ font-size:15px; line-height:21px; color:var(--ink-secondary); margin:0 0 14px; min-height:40px; }}
.nw-sys .score {{ font-family:var(--font-mono); font-size:26px; line-height:30px; font-weight:500; }}
.nw-sys .metric {{ font-size:13px; color:var(--ink-muted); margin-top:2px; }}
.nw-sys .split {{ font-family:var(--font-mono); font-size:12px; line-height:17px; color:var(--ink-muted);
  border-top:1px solid var(--line-hairline); margin-top:14px; padding-top:10px; }}

/* ---- steps ---- */
.nw-steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
.nw-step {{ border:1px dashed var(--line-control); border-radius:var(--radius-lg); padding:16px 18px; background:transparent; }}
.nw-step .n {{ font-family:var(--font-mono); font-size:13px; color:var(--ink-muted); }}
.nw-step .t {{ font-size:16px; font-weight:600; margin:4px 0 2px; }}
.nw-step .b {{ font-size:14px; line-height:20px; color:var(--ink-secondary); }}

/* ---- empty / pending state ---- */
.nw-empty {{ background:var(--surface-sunken); border-radius:var(--radius-lg); padding:28px; }}
.nw-empty h3 {{ font-size:18px; margin:10px 0 6px; }}
.nw-empty p {{ color:var(--ink-secondary); font-size:15px; line-height:22px; margin:0 0 8px; max-width:720px; }}


/* ---- car rank ---- */
.nw-rank {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:14px 18px; }}
.nw-rank-row {{ display:grid; grid-template-columns:24px 64px 1fr 120px; align-items:center; gap:10px; padding:6px 0; }}
.nw-rank-row .r {{ font-family:var(--font-mono); font-size:13px; color:var(--ink-muted); }}
.nw-rank-row .id {{ font-weight:600; font-size:14px; }}
.nw-rank-row .bar {{ height:12px; background:var(--surface-sunken); border-radius:999px; overflow:hidden; }}
.nw-rank-row .bar span {{ display:block; height:100%; background:var(--series-1); border-radius:999px; }}
.nw-rank-row.top .bar span {{ background:var(--status-alert); }}
.nw-rank-row.top .id {{ color:var(--status-alert); }}
.nw-rank-row.na .v {{ color:var(--ink-muted); }}
.nw-rank-row .v {{ font-family:var(--font-mono); font-size:13px; color:var(--ink-secondary); text-align:right; }}
.nw-rank .cap {{ font-size:13px; color:var(--ink-muted); margin-top:8px; }}

/* ---- fleet board ---- */
.nw-fleet {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-left:4px solid var(--status-unknown);
  border-radius:var(--radius-lg); padding:14px 16px; margin-bottom:10px; }}
.nw-fleet.ok {{ border-left-color:var(--status-ok); }}
.nw-fleet.watch {{ border-left-color:var(--status-watch); }}
.nw-fleet.alert {{ border-left-color:var(--status-alert); }}
.nw-fleet .n {{ font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); margin-bottom:6px; }}
.nw-fleet .h {{ display:flex; align-items:center; gap:10px; font-size:15px; font-weight:600; }}
.nw-fleet .d {{ font-size:14px; color:var(--ink-secondary); margin-top:4px; }}

/* ---- dashboard panels ---- */
.nw-panel {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:18px 20px; margin-bottom:12px; }}
.nw-panel .t {{ font-size:16px; font-weight:600; margin-bottom:12px; }}
.nw-panel .muted {{ color:var(--ink-muted); font-size:14px; margin:0; }}
.nw-stack {{ display:flex; height:14px; border-radius:999px; overflow:hidden; background:var(--surface-sunken); gap:2px; }}
.nw-stack span {{ display:block; height:100%; }}
.nw-stack .alert, .nw-legend i.alert {{ background:var(--status-alert); }}
.nw-stack .watch, .nw-legend i.watch {{ background:var(--status-watch); }}
.nw-stack .ok, .nw-legend i.ok {{ background:var(--status-ok); }}
.nw-stack .unknown, .nw-legend i.unknown {{ background:var(--line-control); }}
.nw-legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:10px; font-size:13px; color:var(--ink-secondary); }}
.nw-legend i {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
.nw-pill {{ display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600; white-space:nowrap; }}
.nw-pill i {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.nw-pill.alert {{ color:var(--status-alert); }} .nw-pill.alert i {{ background:var(--status-alert); }}
.nw-pill.watch {{ color:var(--status-watch); }} .nw-pill.watch i {{ background:var(--status-watch); }}
.nw-pill.ok {{ color:var(--status-ok); }} .nw-pill.ok i {{ background:var(--status-ok); }}
.nw-pill.unknown {{ color:var(--ink-muted); }} .nw-pill.unknown i {{ background:var(--line-control); }}
.nw-table {{ width:100%; border-collapse:collapse; font-size:14px; }}
.nw-table th {{ text-align:left; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--line-hairline); }}
.nw-table td {{ padding:10px 8px; border-bottom:1px solid var(--line-hairline); vertical-align:top; }}
.nw-table tr:last-child td {{ border-bottom:0; }}
.nw-table .mono {{ font-family:var(--font-mono); color:var(--ink-muted); font-size:13px; }}
.nw-table .muted {{ color:var(--ink-secondary); font-size:13px; }}
.nw-kpis.two {{ grid-template-columns:1fr; gap:8px; }}
.nw-kpis.two .nw-kpi {{ display:grid; grid-template-columns:1fr auto; grid-template-areas:"l v" "s v"; align-items:center; column-gap:14px; padding:14px 18px; }}
.nw-kpis.two .nw-kpi .l {{ grid-area:l; margin:0; }} .nw-kpis.two .nw-kpi .v {{ grid-area:v; font-size:28px; line-height:32px; }} .nw-kpis.two .nw-kpi .s {{ grid-area:s; margin-top:2px; }}
.nw-hero {{ display:flex; align-items:center; gap:10px; margin:0 0 10px; }}
.nw-hero .n {{ font-family:var(--font-mono); font-size:22px; font-weight:500; background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:999px; padding:6px 16px; }}

.nw-health {{ display:inline-block; width:64px; height:8px; background:var(--surface-sunken); border-radius:999px; overflow:hidden; vertical-align:middle; margin-right:8px; }}
.nw-health span {{ display:block; height:100%; border-radius:999px; }}
.nw-health .ok {{ background:var(--status-ok); }} .nw-health .watch {{ background:var(--status-watch); }} .nw-health .alert {{ background:var(--status-alert); }}
.nw-cell {{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:3px; background:var(--surface-sunken); }}
.nw-cell.ok {{ background:var(--status-ok); }} .nw-cell.watch {{ background:var(--status-watch); }} .nw-cell.alert {{ background:var(--status-alert); }}


/* ---- motion: entrance, live bars, and a blinking warning state ---- */
@keyframes nw-rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
@keyframes nw-blink {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(224,67,79,.55); }} 50% {{ box-shadow:0 0 0 8px rgba(224,67,79,0); }} }}
@keyframes nw-blink-text {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:.35; }} }}
@keyframes nw-grow {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}
@keyframes nw-sweep {{ 0% {{ background-position:-200% 0; }} 100% {{ background-position:200% 0; }} }}
/* Motion rule: an animation must show a real quantity or a real state change.
   Bars grow to their value; the beacon blinks only while faults are open; the
   schematics move at the measured rate. Nothing floats, lifts or slides for decoration. */
.nw-rank-row .bar span, .nw-health span, .nw-stack span {{ transform-origin:left; animation: nw-grow .7s cubic-bezier(.2,.7,.2,1) both; }}
.nw-card:has(.nw-chip.alert) {{ border-color: var(--status-alert); }}
.nw-kpi.warn .v {{ color: var(--status-alert); }}
.nw-beacon {{ display:flex; align-items:center; gap:10px; background:var(--status-alert-soft); border:1px solid var(--status-alert);
  color:var(--ink-primary); border-radius:var(--radius-lg); padding:12px 18px; margin:0 0 14px; font-size:15px; font-weight:600;
  animation: nw-rise .45s both; }}
.nw-beacon i {{ width:10px; height:10px; border-radius:50%; background:var(--status-alert); animation: nw-blink 1.2s ease-out infinite; flex:none; }}
.nw-beacon .d {{ font-weight:400; color:var(--ink-secondary); margin-left:auto; font-size:13px; }}
.nw-live {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--status-ok); }}
.nw-live i {{ width:7px; height:7px; border-radius:50%; background:var(--status-ok); animation: nw-blink-text 1.4s ease-in-out infinite; }}
.nw-skeleton {{ background: linear-gradient(90deg, var(--surface-sunken) 25%, var(--surface-card) 50%, var(--surface-sunken) 75%); background-size:200% 100%; animation: nw-sweep 1.4s linear infinite; border-radius:var(--radius-md); }}
/* Everything is shown instantly: no fade-ins, growing bars, floating cards or blinking
   dots. Only the loading skeleton moves, because its motion means "still loading". */
[class*="nw-"]:not(.nw-skeleton):not(.nw-art):not(.nw-art *),
[class*="nw-"] *:not(.nw-skeleton):not(.nw-art):not(.nw-art *) {{ animation: none !important; }}
@media (prefers-reduced-motion: reduce) {{ .nw-card, .nw-panel, .nw-kpi, .nw-sys, .nw-fleet, .nw-rank, .nw-empty, .nw-step, .nw-chip, .nw-pill i, .nw-pill, .nw-beacon i, .nw-live i, .nw-kpi.warn .v, .nw-rank-row .bar span, .nw-health span, .nw-stack span {{ animation:none !important; }} }}

/* ---- hero + glass ---- */
@keyframes nw-float {{ 0%,100% {{ transform:translateY(0); }} 50% {{ transform:translateY(-4px); }} }}
.nw-hero-card {{ position:relative; overflow:hidden; border-radius:22px; padding:22px 26px; margin:0 0 14px;
  background: linear-gradient(135deg, rgba(46,143,212,.16), color-mix(in srgb, var(--surface-card) 70%, transparent) 45%, rgba(224,67,79,.10));
  border:1px solid var(--line-hairline); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  animation: nw-rise .5s both; display:grid; grid-template-columns: 1fr auto; gap:18px; align-items:center; }}
.nw-hero-card::before {{ content:""; position:absolute; inset:-40% -20% auto auto; width:420px; height:420px; border-radius:50%;
  background: radial-gradient(closest-side, rgba(46,143,212,.28), transparent); pointer-events:none; }}
.nw-hero-card .k {{ font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-muted); font-weight:600; }}
.nw-hero-card .t {{ font-size:34px; line-height:38px; font-weight:600; letter-spacing:-.02em; margin:4px 0 6px; }}
.nw-hero-card .s {{ font-size:15px; color:var(--ink-secondary); max-width:720px; }}
.nw-hero-card .wx {{ text-align:right; font-family:var(--font-mono); font-size:14px; color:var(--ink-secondary); line-height:1.5; }}
.nw-hero-card .wx .e {{ display:inline-block; font-size:44px; line-height:1; filter: drop-shadow(0 4px 10px rgba(16,21,28,.18)); }}
.nw-hero-card .wx .big {{ font-size:26px; color:var(--ink-primary); font-weight:500; }}
.nw-panel, .nw-kpi, .nw-card, .nw-sys, .nw-fleet, .nw-rank {{ background: color-mix(in srgb, var(--surface-card) 82%, transparent);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }}
.nw-emoji {{ display:inline-block; margin-right:6px; }}
.nw-drop {{ border:1px dashed var(--line-control); border-radius:var(--radius-lg); padding:10px 14px; font-size:13px; color:var(--ink-secondary); }}
.nw-drop b {{ color:var(--ink-primary); }}
[data-testid="stFileUploaderDropzone"] {{ min-height:64px; }}

.nw-urg {{ font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; padding:4px 10px; border-radius:999px; }}
.nw-urg.alert {{ background:var(--status-alert); color:#fff; }}
.nw-urg.watch {{ background:var(--status-watch); color:#111; }}
.nw-urg.ok {{ background:var(--status-ok-soft); color:var(--status-ok); }}
.nw-act.alert {{ border-left:4px solid var(--status-alert); }} .nw-act.watch {{ border-left:4px solid var(--status-watch); }} .nw-act.ok {{ border-left:4px solid var(--status-ok); }}
.nw-tips {{ margin:0; padding-left:18px; font-size:15px; line-height:1.6; color:var(--ink-secondary); }}
.nw-tips li {{ margin:4px 0; }}

/* ---- transitions ---- */
html {{ scroll-behavior: smooth; }}
@keyframes nw-fade {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
[data-testid="stExpander"] details summary, .stButton > button, a[data-testid="stPageLink-NavLink"] {{ transition: background .15s ease, transform .15s ease, border-color .15s ease; }}
[data-testid="stSegmentedControl"] button {{ transition: background .15s ease, color .15s ease; }}

/* ---- widgets follow the console theme ---- */
/* segmented controls, pills, radio-like button groups */
.stApp .stButtonGroup button {{ background: var(--surface-card) !important; color: var(--ink-secondary) !important;
  border-color: var(--line-hairline) !important; }}
/* Streamlit marks the chosen option with aria-checked (segmented control) or aria-pressed /
   data-selected (pills); all four are covered so a chosen option is always visibly chosen. */
.stApp .stButtonGroup button[aria-checked="true"], .stApp .stButtonGroup button[aria-selected="true"],
.stApp .stButtonGroup button[aria-pressed="true"], .stApp .stButtonGroup button[data-selected="true"] {{
  background: color-mix(in srgb, var(--series-1) 18%, var(--surface-card)) !important; color: var(--series-1) !important;
  border-color: var(--series-1) !important; }}
.stApp .stButtonGroup button p, .stApp .stButtonGroup button span {{ color: inherit !important; }}
.stApp .stButtonGroup button[aria-pressed="true"]::before {{ content: "✓ "; font-weight: 700; margin-right: 2px; }}
/* select boxes, multiselects, text and date inputs */
.stApp [data-baseweb="select"], .stApp [data-baseweb="select"] > div, .stApp [data-baseweb="select"] > div > div,
.stApp [data-baseweb="input"], .stApp [data-baseweb="input"] > div, .stApp [data-baseweb="base-input"],
.stApp .stTextInput input, .stApp .stDateInput input, .stApp .stNumberInput input {{
  background-color: var(--surface-card) !important; color: var(--ink-primary) !important; border-color: var(--line-hairline) !important; }}
.stApp [data-baseweb="select"] svg, .stApp [data-baseweb="input"] svg {{ fill: var(--ink-secondary) !important; }}
.stApp [data-baseweb="select"] input {{ color: var(--ink-primary) !important; }}
.stApp [data-baseweb="tag"] {{ background: var(--surface-sunken) !important; color: var(--ink-primary) !important; }}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] ul, [data-baseweb="menu"] {{ background: var(--surface-card) !important; }}
[data-baseweb="popover"] li, [data-baseweb="popover"] [role="option"] {{ background: var(--surface-card) !important; color: var(--ink-primary) !important; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] [role="option"]:hover, [data-baseweb="popover"] [aria-selected="true"] {{ background: var(--surface-sunken) !important; }}
[data-baseweb="calendar"], [data-baseweb="calendar"] * {{ background-color: var(--surface-card); color: var(--ink-primary); }}
/* select and multiselect shells: no attribute hook in this build, so reach them through the combobox */
.stApp .stSelectbox div:has(> [role="combobox"]), .stApp .stSelectbox div:has(> div > [role="combobox"]),
.stApp .stMultiSelect div:has(> [role="combobox"]), .stApp .stMultiSelect div:has(> div > [role="combobox"]),
.stApp .stSelectbox div:has(> input), .stApp .stMultiSelect div:has(> input),
.stApp .stTextInput div:has(> input), .stApp .stDateInput div:has(> input), .stApp .stNumberInput div:has(> input) {{
  background-color: var(--surface-card) !important; border-color: var(--line-hairline) !important; color: var(--ink-primary) !important; }}
.stApp .stSelectbox [role="combobox"], .stApp .stMultiSelect [role="combobox"], .stApp .stSelectbox input, .stApp .stMultiSelect input {{
  color: var(--ink-primary) !important; -webkit-text-fill-color: var(--ink-primary) !important; }}
.stApp .stSelectbox svg, .stApp .stMultiSelect svg, .stApp .stDateInput svg {{ fill: var(--ink-secondary) !important; }}
/* buttons, expanders, uploader, tabs, links, labels */
.stApp .stButton > button, .stApp .stDownloadButton > button {{ background: var(--surface-card) !important; color: var(--ink-primary) !important; border-color: var(--line-control) !important; }}
.stApp .stButton > button[kind="primary"], .stApp .stDownloadButton > button[kind="primary"] {{ background: var(--series-1) !important; border-color: var(--series-1) !important; color: #fff !important; }}
.stApp [data-testid="stExpander"] details, .stApp [data-testid="stExpander"] summary {{ background: var(--surface-card) !important; color: var(--ink-primary) !important; }}
.stApp [data-testid="stExpander"] summary * {{ color: var(--ink-primary) !important; }}
.stApp [data-testid="stFileUploaderDropzone"] {{ background: var(--surface-card) !important; color: var(--ink-secondary) !important; }}
.stApp [data-testid="stFileUploaderDropzone"] button {{ background: var(--surface-sunken) !important; color: var(--ink-primary) !important; border-color: var(--line-hairline) !important; }}
.stApp [data-testid="stFileUploaderDropzone"] span, .stApp [data-testid="stFileUploaderDropzone"] small {{ color: var(--ink-secondary) !important; }}
.stApp label, .stApp [data-testid="stWidgetLabel"] p, .stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color: var(--ink-secondary) !important; }}
.stApp [data-testid="stMarkdownContainer"] p, .stApp [data-testid="stMarkdownContainer"] li, .stApp [data-testid="stMarkdownContainer"] td {{ color: var(--ink-primary); }}
.stApp [data-testid="stTabs"] button {{ color: var(--ink-secondary) !important; }}
.stApp [data-testid="stTabs"] button[aria-selected="true"] {{ color: var(--series-1) !important; }}
.stApp a[data-testid="stPageLink-NavLink"], .stApp a[data-testid="stPageLink-NavLink"] * {{ color: var(--ink-primary) !important; }}
.stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"] {{ color: var(--ink-primary) !important; }}
.stApp [data-testid="stDataFrame"], .stApp [data-testid="stDataFrame"] * {{ color-scheme: var(--nw-scheme); }}
.stApp .stAlert, .stApp [data-testid="stAlert"] {{ color: var(--ink-primary); }}
.stApp [data-testid="stToolbar"], .stApp [data-testid="stStatusWidget"] {{ color: var(--ink-secondary); }}
[data-testid="stHeader"] a, [data-testid="stHeader"] button, [data-testid="stHeader"] span {{ color: var(--ink-primary) !important; }}
/* menus drawn in portals (navigation dropdowns, select lists, popovers) sit outside .stApp */
[data-baseweb="popover"], [data-baseweb="popover"] > div, [data-baseweb="popover"] > div > div, [data-baseweb="menu"],
[role="menu"], ul[role="listbox"], [data-testid="stHeader"] ul, [data-testid="stHeader"] [role="menu"],
[data-testid^="stTopNav"] ul, [data-testid^="stTopNav"] [role="menu"], [data-testid*="Menu"], [data-testid*="SectionMenu"] {{
  background-color: var(--surface-card) !important; color: var(--ink-primary) !important; border-color: var(--line-hairline) !important; }}
[data-baseweb="popover"] a, [data-baseweb="popover"] li, [data-baseweb="popover"] span, [data-baseweb="popover"] p, [data-baseweb="popover"] label,
[role="menuitem"], [role="menuitem"] *, [data-testid^="stTopNav"] a, [data-testid^="stTopNav"] a *, [data-testid="stHeader"] a, [data-testid="stHeader"] a * {{
  color: var(--ink-primary) !important; }}
[data-baseweb="popover"] li:hover, [role="menuitem"]:hover, [data-testid^="stTopNav"] a:hover {{ background-color: var(--surface-sunken) !important; }}
[data-baseweb="popover"] [data-testid="stIconMaterial"], [data-testid="stHeader"] [data-testid="stIconMaterial"] {{ color: var(--ink-secondary) !important; }}
.stApp hr {{ border-color: var(--line-hairline); }}

/* ---- streamlit widget polish ---- */
.stButton > button, .stDownloadButton > button {{ border-radius: var(--radius-md); font-weight: 600;
  border: 1px solid var(--line-control); }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: var(--ink-primary); border-color: var(--ink-primary); color: var(--ink-inverse); }}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.15); color: var(--ink-inverse); }}
[data-testid="stTabs"] button {{ font-weight:600; }}
[data-testid="stFileUploaderDropzone"] {{ background: var(--surface-card); border: 1px dashed var(--line-control);
  border-radius: var(--radius-lg); }}
[data-testid="stExpander"] {{ border-radius: var(--radius-lg); border-color: var(--line-hairline); background: var(--surface-card); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line-hairline); border-radius: var(--radius-md); }}
*:focus-visible {{ outline: 2px solid var(--focus-ring) !important; outline-offset: 2px; }}

/* ---- bento: one card language for every widget, taken from the dashboard hero ----
   Soft blue-to-red wash over the card surface, a hairline border and generous
   rounding, in the manner of Apple's feature grids. Placed last so it wins the
   cascade; it sets background and shape only, so state borders (a verdict card's
   red alert edge) still come from their own, more specific rules. Works in both
   themes because the wash is mixed from the theme's own surface colour. */
:root {{
  --nw-wash: linear-gradient(135deg, rgba(46,143,212,.13) 0%,
             color-mix(in srgb, var(--surface-card) 84%, transparent) 40%,
             color-mix(in srgb, var(--surface-card) 84%, transparent) 72%,
             rgba(224,67,79,.08) 100%);
  --nw-bento-radius: 20px;
}}
.nw-pagehead {{ background: var(--nw-wash); border: 1px solid var(--line-hairline); border-radius: 22px;
  padding: 22px 26px 4px; margin: 0 0 18px; }}
.nw-pagehead .nw-lede {{ margin-bottom: 18px; }}
.nw-section {{ background: var(--nw-wash); border: 1px solid var(--line-hairline); border-radius: 14px;
  padding: 11px 16px; margin: 28px 0 12px; color: var(--ink-primary); }}
.nw-card, .nw-panel, .nw-kpi, .nw-sys, .nw-step, .nw-empty {{
  background: var(--nw-wash); border-radius: var(--nw-bento-radius); }}
.nw-kpi, .nw-sys, .nw-step, .nw-empty {{ border: 1px solid var(--line-hairline); }}
/* The frame must not take layout space: Plotly sizes its drawing to this element's
   OUTER width, so padding or a border here pushes the right edge (and the toolbar)
   out of view. The hairline is an inset shadow and the breathing room is the figure's
   own margin. */
[data-testid="stPlotlyChart"] {{ background: var(--surface-card); box-shadow: inset 0 0 0 1px var(--line-hairline);
  border-radius: var(--nw-bento-radius); padding: 0; border: 0; overflow: hidden; }}
[data-testid="stDeckGlJsonChart"] {{ border: 1px solid var(--line-hairline); border-radius: var(--nw-bento-radius);
  overflow: hidden; }}
[data-testid="stDataFrame"], [data-testid="stExpander"] {{ border-radius: 16px; overflow: hidden; }}
/* ---- train diagrams: fixed-width cards, centred, wrapping ----
   Fewer cars stay centred at the same size; more cars wrap to a new row. */
.nw-train, .nw-rtrain {{ margin: 8px 0 18px; }}
.nw-train .cap, .nw-rtrain .cap {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ink-muted); text-align: center; margin: 0 0 14px; }}
.nw-train .cars, .nw-rtrain .cars {{ display: flex; justify-content: center; flex-wrap: wrap; gap: 22px 12px; }}
.nw-car {{ position: relative; flex: 0 1 132px; min-width: 110px; padding: 12px 10px 20px; border-radius: 16px;
  background: var(--surface-card); border: 1px solid var(--line-hairline); text-align: center; color: var(--ink-primary); }}
.nw-car .rk {{ font-family: var(--font-mono); font-size: 12px; color: var(--ink-muted); }}
.nw-car .id {{ font-size: 18px; font-weight: 700; line-height: 22px; margin: 2px 0; }}
.nw-car .m {{ font-family: var(--font-mono); font-size: 16px; font-weight: 500; }}
.nw-car .s {{ font-size: 12px; line-height: 15px; color: var(--ink-secondary); margin-top: 2px; }}
.nw-car .wheels {{ position: absolute; left: 16px; right: 16px; bottom: -8px; display: flex; justify-content: space-between; }}
.nw-car .wheels i {{ width: 15px; height: 15px; border-radius: 50%; background: var(--surface-page); border: 2px solid var(--ink-muted); }}
.nw-car.r1 {{ background: var(--status-alert); border-color: var(--status-alert); color: #fff; }}
.nw-car.r2 {{ background: var(--status-watch); border-color: var(--status-watch); color: #fff; }}
.nw-car.r1 .rk, .nw-car.r1 .s, .nw-car.r2 .rk, .nw-car.r2 .s {{ color: rgba(255,255,255,.88); }}
.nw-car.r3 {{ background: color-mix(in srgb, var(--status-watch) 32%, var(--surface-card)); border-color: var(--status-watch); }}
.nw-car.none {{ opacity: .55; border-style: dashed; }}
.nw-rtrain .rail {{ position: relative; height: 6px; border-radius: 3px; background: var(--line-control); margin: 26px 0 10px; }}
.nw-rtrain .rail.bottom {{ margin: 10px 0 34px; }}
.nw-rtrain .rail.bottom span {{ top: 12px; }}
.nw-rtrain .rail span {{ position: absolute; left: 0; top: -22px; font-size: 13px; color: var(--ink-secondary); }}
.nw-rtrain .rail.hit {{ background: repeating-linear-gradient(90deg, var(--status-alert) 0 12px, transparent 12px 18px); }}
.nw-rtrain .rail.hit span {{ color: var(--status-alert); font-weight: 600; }}
.nw-rcar {{ flex: 0 1 120px; min-width: 104px; }}
.nw-rcar .boxes {{ display: flex; justify-content: center; gap: 7px; margin: 7px 0; }}
.nw-rcar .boxes i {{ width: 17px; height: 17px; border-radius: 50%; border: 2px solid var(--surface-page); cursor: help; }}
.nw-rcar .body {{ border-radius: 12px; background: var(--surface-card); border: 1px solid var(--line-hairline);
  padding: 10px 0; text-align: center; font-weight: 600; font-size: 15px; }}
.nw-rtrain .legend {{ font-size: 13px; color: var(--ink-muted); text-align: center; }}

/* ---- Top-N ranked lists ---- */
.nw-top {{ display: grid; gap: 8px; margin: 6px 0 4px; }}
.nw-top-row {{ display: grid; grid-template-columns: 38px minmax(0, 1fr) minmax(90px, 26%) 92px; align-items: center;
  gap: 14px; padding: 12px 16px; border-radius: 14px; background: var(--nw-wash); border: 1px solid var(--line-hairline); }}
.nw-top-row .r {{ font-family: var(--font-mono); font-size: 20px; font-weight: 600; color: var(--ink-muted); text-align: center; }}
.nw-top-row .t {{ font-size: 16px; font-weight: 600; line-height: 21px; }}
.nw-top-row .d {{ font-size: 13px; line-height: 18px; color: var(--ink-secondary); margin-top: 2px; overflow-wrap: anywhere; }}
.nw-top-row .bar {{ height: 10px; border-radius: 5px; background: var(--surface-sunken); overflow: hidden; }}
.nw-top-row .bar span {{ display: block; height: 100%; border-radius: 5px; background: var(--series-1); }}
.nw-top-row .v {{ font-family: var(--font-mono); font-size: 17px; font-weight: 500; text-align: right; }}
.nw-top-row.alert {{ border-color: color-mix(in srgb, var(--status-alert) 55%, transparent); }}
.nw-top-row.alert .r, .nw-top-row.alert .v {{ color: var(--status-alert); }}
.nw-top-row.alert .bar span {{ background: var(--status-alert); }}
.nw-top-row.watch .r, .nw-top-row.watch .v {{ color: var(--status-watch); }}
.nw-top-row.watch .bar span {{ background: var(--status-watch); }}
@media (max-width: 700px) {{ .nw-top-row {{ grid-template-columns: 30px minmax(0, 1fr) 80px; }} .nw-top-row .bar {{ display: none; }} }}

/* ---- page-header illustration: text left, themed schematic right ---- */
.nw-pagehead.has-art {{ display: grid; grid-template-columns: minmax(0, 1fr) 250px; column-gap: 28px; align-items: center; }}
.nw-pagehead.has-art > :not(.nw-art) {{ grid-column: 1; }}
.nw-pagehead .nw-art {{ grid-column: 2; grid-row: 1 / span 3; width: 250px; padding: 6px 0 14px; }}
.nw-pagehead .nw-art svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
.nw-art .a-spin, .nw-art .a-pulse, .nw-art .a-temp {{ transform-box: fill-box; transform-origin: center; }}
.nw-art .a-temp {{ transform-origin: bottom; }}
.nw-art .a-door-l {{ animation: nwa-door-l 5s ease-in-out infinite; }}
.nw-art .a-door-r {{ animation: nwa-door-r 5s ease-in-out infinite; }}
.nw-art .a-flow   {{ animation: nwa-flow 1.6s linear infinite; }}
.nw-art .a-spin   {{ animation: nwa-spin 2.4s linear infinite; }}
.nw-art .a-pulse  {{ animation: nwa-pulse 2.2s ease-out infinite; }}
.nw-art .a-late   {{ animation-delay: 1.1s; }}
.nw-art .a-scroll {{ animation: nwa-scroll 4s linear infinite; }}
.nw-art .a-roll   {{ animation: nwa-roll 6s ease-in-out infinite alternate; }}
.nw-art .a-temp   {{ animation: nwa-temp 4s ease-in-out infinite; }}
.nw-art .a-fold   {{ animation: nwa-fold 6s steps(5) infinite; }}
.nw-art .a-scan   {{ animation: nwa-scan 5s ease-in-out infinite alternate; }}
.nw-art .a-draw   {{ animation: nwa-draw 3s ease-in-out infinite; }}
@keyframes nwa-door-l {{ 0%, 15% {{ transform: translateX(0); }} 40%, 65% {{ transform: translateX(-40px); }} 90%, 100% {{ transform: translateX(0); }} }}
@keyframes nwa-door-r {{ 0%, 15% {{ transform: translateX(0); }} 40%, 65% {{ transform: translateX(40px); }} 90%, 100% {{ transform: translateX(0); }} }}
@keyframes nwa-flow {{ to {{ stroke-dashoffset: -20; }} }}
@keyframes nwa-spin {{ to {{ transform: rotate(360deg); }} }}
@keyframes nwa-pulse {{ 0% {{ transform: scale(1); opacity: .9; }} 100% {{ transform: scale(3.2); opacity: 0; }} }}
@keyframes nwa-scroll {{ to {{ transform: translateX(-60px); }} }}
@keyframes nwa-roll {{ from {{ transform: translateX(-70px); }} to {{ transform: translateX(70px); }} }}
@keyframes nwa-temp {{ 0%, 100% {{ transform: scaleY(.45); }} 50% {{ transform: scaleY(1); }} }}
@keyframes nwa-fold {{ from {{ transform: translateX(0); }} to {{ transform: translateX(210px); }} }}
@keyframes nwa-scan {{ from {{ transform: translateX(0); }} to {{ transform: translateX(130px); }} }}
@keyframes nwa-draw {{ 0% {{ stroke-dashoffset: 30; }} 40%, 100% {{ stroke-dashoffset: 0; }} }}
@media (max-width: 820px) {{ .nw-pagehead.has-art {{ display: block; }} .nw-pagehead .nw-art {{ display: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .nw-art * {{ animation: none !important; }} }}

/* Status chips wrap inside their column instead of running off the edge. */
.nw-chip {{ white-space: normal; flex-wrap: wrap; max-width: 100%; row-gap: 2px; }}
/* subsystem switcher: four big tiles above every page */
[class*="st-key-nw_switch"] {{ margin: 2px 0 10px; }}
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a {{ min-height:64px; padding:12px 16px; border-radius:16px;
  background:var(--surface-card); border:1px solid var(--line-hairline); justify-content:flex-start; }}
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a:hover {{ border-color:var(--ink-muted); }}
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a p, [class*="st-key-nw_switch"] [data-testid="stPageLink"] a span {{ font-size:16px !important; font-weight:600; }}
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a [data-testid="stIconMaterial"] {{ font-size:26px !important; }}
[class*="st-key-nw_switch"] [class*="_alert"] [data-testid="stPageLink"] a {{ box-shadow: inset 4px 0 0 var(--status-alert); }}
[class*="st-key-nw_switch"] [class*="_watch"] [data-testid="stPageLink"] a {{ box-shadow: inset 4px 0 0 var(--status-watch); }}
[class*="st-key-nw_switch"] [class*="_ok"] [data-testid="stPageLink"] a {{ box-shadow: inset 4px 0 0 var(--status-ok); }}
[class*="st-key-nw_switch"] [class*="_here"] [data-testid="stPageLink"] a {{ border:2px solid var(--ink-primary); background:var(--surface-sunken); }}
/* five tiles share the row: labels wrap onto a second line instead of being cut off */
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a span:not([data-testid="stIconMaterial"]),
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a [data-testid="stMarkdownContainer"],
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a p {{ white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; line-height: 1.25; }}
[class*="st-key-nw_switch"] [data-testid="stPageLink"] a p, [class*="st-key-nw_ov"] [data-testid="stPopover"] button p {{ font-size:15px !important; }}
/* the Overview tile: a dropdown button styled like the subsystem tiles */
[class*="st-key-nw_ov"] [data-testid="stPopover"] > div > button, [class*="st-key-nw_ov"] [data-testid="stPopoverButton"] {{
  min-height:64px; padding:12px 16px; border-radius:16px; background:var(--nw-wash) !important;
  border:1px solid var(--line-hairline) !important; justify-content:flex-start; }}
[class*="st-key-nw_ov"] [data-testid="stPopover"] button p {{ font-size:16px !important; font-weight:650; }}
[class*="st-key-nw_ov"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] {{ font-size:26px !important; }}
[class*="st-key-nw_ov_here"] [data-testid="stPopover"] > div > button, [class*="st-key-nw_ov_here"] [data-testid="stPopoverButton"] {{
  border:2px solid var(--ink-primary) !important; background:var(--surface-sunken) !important; }}
.nw-engnote {{ margin:10px 0 14px; padding:12px 16px; border-radius:14px; border:1px dashed var(--line-control);
  color:var(--ink-secondary); font-size:14px; }}
.nw-engnote b {{ color:var(--ink-primary); }}
/* live feed panels: equal height, gradient bento border, scroll inside */
.nw-feedtitle {{ font-size:16px; font-weight:650; color:var(--ink-primary); margin:4px 0 8px; display:flex; gap:10px; align-items:center; }}
.nw-feedtitle span {{ font-size:12px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted);
  border:1px solid var(--line-hairline); border-radius:999px; padding:2px 10px; }}
[class*="st-key-nw_feed_"] {{ background: var(--nw-wash) !important; border:1px solid var(--line-hairline) !important;
  border-radius: 18px !important; padding: 14px 18px !important; }}
[class*="st-key-nw_feed_"] p, [class*="st-key-nw_feed_"] li {{ font-size:14.5px; line-height:1.55; }}
[class*="st-key-nw_feed_"] [data-testid="stMarkdownContainer"] {{ border-bottom:1px solid var(--line-hairline); padding-bottom:8px; }}
.nw-winnote {{ margin:4px 0 10px; padding:8px 14px; border-radius:12px; background:var(--surface-sunken);
  color:var(--ink-secondary); font-size:14px; }}
.nw-winnote b {{ color:var(--ink-primary); font-weight:600; }}
/* toasts sit bottom-right, clear of the subsystem tiles along the top */
[data-testid="stToastContainer"] {{ top: auto !important; bottom: 20px !important; }}
/* health key: value ranges behind Normal / Watch / Fault */
.nw-bands {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; margin:6px 0 14px; }}
.nw-band {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:16px; padding:14px 16px; }}
.nw-band .n {{ font-size:15px; font-weight:650; color:var(--ink-primary); }}
.nw-band .m {{ font-size:13px; color:var(--ink-secondary); margin:2px 0 10px; line-height:1.4; }}
.nw-band .b {{ display:grid; grid-template-columns:86px 1fr; gap:10px; align-items:baseline; padding:6px 0;
  border-top:1px solid var(--line-hairline); font-size:14px; line-height:1.4; }}
.nw-band .b .w {{ font-weight:600; white-space:nowrap; }}
.nw-band .b .w .g {{ font-size:11px; margin-right:6px; }}
.nw-band .b.ok .w {{ color:var(--status-ok); }}
.nw-band .b.watch .w {{ color:var(--status-watch); }}
.nw-band .b.alert .w {{ color:var(--status-alert); }}
.nw-band .b .r {{ color:var(--ink-primary); }}

.nw-chip .d {{ overflow-wrap: anywhere; }}
</style>
"""
