"""Data-driven schematics, drawn only from values the models actually produce.

Each function returns inline SVG for st.markdown(unsafe_allow_html=True). Nothing
here invents a position or a value: the ACV train colours cars by their own
ranking scores, the Rail train colours each axle box by its own vibration RMS,
the Door diagram annotates a real cycle. SHM has no location data, so it gets
no schematic (see shm page: damage gauges per file instead).
"""
from __future__ import annotations

from html import escape

import pandas as pd

RAMP = ["#bfe0f7", "#7cc0ea", "#0095ec", "#d68a00", "#b3121f"]   # cool -> hot, on white
GLYPH = {"alert": "✕", "watch": "◐", "ok": "●", "unknown": "—"}      # the console's one severity alphabet


def _ramp(v: float) -> str:
    v = 0.0 if v != v else max(0.0, min(1.0, v))
    return RAMP[min(4, int(v * 5))]


def _car(x: float, y: float, w: float, h: float, fill: str, label: str, sub: str = "", stroke: str = "#10151c") -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-opacity=".25"/>'
            f'<text x="{x + w / 2}" y="{y + 22}" text-anchor="middle" font-size="13" font-weight="600" fill="#10151c">{escape(label)}</text>'
            + (f'<text x="{x + w / 2}" y="{y + 40}" text-anchor="middle" font-size="11" fill="#10151c" fill-opacity=".85">{escape(sub)}</text>' if sub else ""))


def acv_train(ranking: list[str], scores: dict, hot: dict | None, unobserved: list[str]) -> str:
    """The cars in physical order as responsive cards, coloured by rank (#1 red, #2-#3
    amber, the rest neutral). Cards keep a fixed comfortable width and are centred, so
    a train with fewer cars stays centred instead of stretching, and more cars wrap."""
    cars = sorted(ranking)
    n = len(cars)
    cells = []
    for c in cars:
        rank = ranking.index(c) + 1
        if c in unobserved:
            cls, main, sub = "none", "no cooling evidence", ""
        else:
            cls = {1: "r1", 2: "r2", 3: "r3"}.get(rank, "")
            s = scores.get(c)
            main = f"{s:+.2f} °C" if isinstance(s, (int, float)) else "—"
            h = hot.get(c, 0) if hot else 0
            # a small share must not round to 0.0%: two decimals below 1%
            sub = (f"hot {h:.2%} of cooling" if h < 0.01 else f"hot {h:.1%} of cooling") if hot else "mean excess vs other cars"
        tip = f"Car {c}: rank {rank} of {n}" + (f" · {main}" if main else "")
        cells.append(f'<div class="nw-car {cls}" title="{escape(tip)}"><div class="rk">#{rank}</div>'
                     f'<div class="id">Car {escape(c)}</div><div class="m">{escape(main)}</div>'
                     + (f'<div class="s">{escape(sub)}</div>' if sub else "")
                     + '<div class="wheels"><i></i><i></i></div></div>')
    return (f'<div class="nw-train"><div class="cap">Train · {n} cars in physical order · #1 = most likely leak</div>'
            f'<div class="cars">{"".join(cells)}</div></div>')


def rail_train(grid: pd.DataFrame, prediction: str) -> str:
    """Side view as responsive cards: each car with its four Side I axle boxes above and
    four Side II boxes below, coloured by that box's vibration RMS (normalised within the
    recording). The corrugated rail is drawn dashed red. Centred; wraps when narrow."""
    cars = sorted(grid["car"].unique())
    lookup = {(int(r.car), int(r.position)): (float(r.value), float(r.rms)) for r in grid.itertuples()}

    def boxes(car: int, positions) -> str:
        out = []
        for pos in positions:
            v, rms = lookup.get((int(car), pos), (0.0, 0.0))
            out.append(f'<i style="background:{_ramp(v)}" title="Car {car} · position {pos} · RMS {rms:.3f} m/s²"></i>')
        return "".join(out)

    def rail(side: str) -> str:
        hit = prediction == side
        pos = " bottom" if side == "Side II" else ""
        return (f'<div class="rail{" hit" if hit else ""}{pos}"><span>{GLYPH["alert"] if hit else GLYPH["ok"]} '
                f'{side} rail · {"corrugated" if hit else "normal"}</span></div>')

    cells = "".join(f'<div class="nw-rcar"><div class="boxes">{boxes(c, (1, 3, 5, 7))}</div>'
                    f'<div class="body">Car {int(c)}</div><div class="boxes">{boxes(c, (2, 4, 6, 8))}</div></div>'
                    for c in cars)
    return (f'<div class="nw-rtrain"><div class="cap">Axle-box vibration · verdict {escape(prediction)}</div>'
            f'{rail("Side I")}<div class="cars">{cells}</div>{rail("Side II")}'
            '<div class="legend">Dot colour = vibration RMS of that axle box, normalised within this recording. '
            'Hover a dot for its value.</div></div>')


def door_cycle(row: pd.Series) -> str:
    """One door cycle: leaf travel, sustained current, duration, verdict, from that cycle's values."""
    abnormal = row["prediction"] == "Abnormal resistance"
    col = "#e0434f" if abnormal else "#16a97a"
    travel = float(row.get("pos_range", 0) or 0)
    out = ['<svg viewBox="0 0 640 150" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Door cycle diagram">',
           '<text x="16" y="16" font-size="11" fill="#626c7a" letter-spacing="1.5">DOOR LEAF · MOTOR · ONE CYCLE</text>',
           # door frame and leaf
           '<rect x="16" y="30" width="220" height="100" rx="6" fill="#f7f8fa" stroke="#b8c2cc"/>',
           f'<rect x="{30 if row["operation"] == "Close" else 120}" y="38" width="100" height="84" rx="4" fill="{col}" fill-opacity=".85">'
           f'<animate attributeName="x" values="{"120;30;30" if row["operation"] == "Close" else "30;120;120"}" dur="{max(1.2, float(row["duration_s"]) * 0.6):.1f}s" repeatCount="indefinite"/></rect>',
           f'<text x="220" y="52" text-anchor="end" font-size="14" fill="{col}">{GLYPH["alert" if abnormal else "ok"]}</text>',
           f'<text x="126" y="140" text-anchor="middle" font-size="10" fill="#454f5c">leaf {row["operation"].lower()}s · travel {travel:.0f}</text>',
           # motor + values
           '<circle cx="300" cy="80" r="26" fill="#eef1f5" stroke="#626c7a"/>',
           '<text x="300" y="84" text-anchor="middle" font-size="10" fill="#10151c">motor</text>',
           f'<line x1="236" y1="80" x2="274" y2="80" stroke="{col}" stroke-width="3">'
           + ('<animate attributeName="opacity" values="1;.3;1" dur="0.8s" repeatCount="indefinite"/>' if abnormal else "") + '</line>',
           f'<text x="350" y="56" font-size="13" font-weight="600" fill="#10151c">{escape(str(row["prediction"]))}</text>',
           f'<text x="350" y="78" font-size="12" fill="#454f5c">sustained current {row["cur_mean_mid"]:.0f} mA · P(abnormal) {row["p_abnormal"]:.0%}</text>',
           f'<text x="350" y="98" font-size="12" fill="#454f5c">duration {row["duration_s"]:.2f} s · current per back-EMF {row.get("cur_per_emf", float("nan")):.2f}</text>',
           f'<text x="350" y="118" font-size="11" fill="#626c7a">{escape(str(row["start_time"]))}</text>',
           '</svg>']
    return "".join(out)


def shm_gauge(file_id: str, damage: float, segments_left: float) -> str:
    """An arc from 0 to 1 with the needle at D. Watch band 0.5, alert 0.8, failure at 1."""
    import math
    d = max(0.0, min(1.0, damage))
    state = "alert" if d >= 0.8 else "watch" if d >= 0.5 else "ok"
    col = {"alert": "#e0434f", "watch": "#d68a00", "ok": "#16a97a"}[state]

    def arc(a0, a1, color, width=14):
        r, cx, cy = 90, 130, 120
        x0, y0 = cx + r * math.cos(math.pi * (1 - a0)), cy - r * math.sin(math.pi * (1 - a0))
        x1, y1 = cx + r * math.cos(math.pi * (1 - a1)), cy - r * math.sin(math.pi * (1 - a1))
        return f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="butt"/>'
    # Layout: only the number and the two end labels live inside the drawing. The file
    # name and the explanation are ordinary HTML below it, so they wrap instead of
    # spilling past the edges of the SVG and over the end labels.
    cx, cy, r = 160, 150, 118

    def arc2(a0, a1, color, width=20):
        x0, y0 = cx + r * math.cos(math.pi * (1 - a0)), cy - r * math.sin(math.pi * (1 - a0))
        x1, y1 = cx + r * math.cos(math.pi * (1 - a1)), cy - r * math.sin(math.pi * (1 - a1))
        return (f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="{width}" stroke-linecap="butt"/>')
    ang = math.pi * (1 - d)
    nx, ny = cx + (r - 18) * math.cos(ang), cy - (r - 18) * math.sin(ang)
    ink = "fill:var(--ink-primary, #e8edf3)"
    muted = "fill:var(--ink-muted, #8b96a3)"
    left = "more than the life used so far" if segments_left >= 1 else "less than the life used so far"
    return ("".join([
        '<div style="max-width:440px;margin:8px auto 4px;text-align:center">',
        '<svg viewBox="0 0 320 185" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Fatigue damage gauge: {d:.2f} of 1">',
        arc2(0.0, 0.5, "#16a97a"), arc2(0.5, 0.8, "#d68a00"), arc2(0.8, 1.0, "#e0434f"),
        f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" style="stroke:var(--ink-primary, #e8edf3)" '
        'stroke-width="4" stroke-linecap="round">'
        f'<animate attributeName="x2" from="{cx - r + 18}" to="{nx:.1f}" dur="1s" fill="freeze"/>'
        f'<animate attributeName="y2" from="{cy}" to="{ny:.1f}" dur="1s" fill="freeze"/></line>',
        f'<circle cx="{cx}" cy="{cy}" r="7" style="{ink}"/>',
        f'<text x="{cx}" y="{cy - 40}" text-anchor="middle" font-size="40" font-weight="700" fill="{col}">'
        f'{d:.2f} {GLYPH[state]}</text>',
        f'<text x="{cx - r}" y="{cy + 26}" text-anchor="middle" font-size="15" style="{muted}">0</text>',
        f'<text x="{cx + r}" y="{cy + 26}" text-anchor="middle" font-size="15" style="{muted}">D = 1</text>',
        '</svg>',
        f'<div style="font-size:18px;font-weight:600;margin-top:2px">{escape(file_id)} · '
        f'<span style="color:{col}">{d:.0%} of fatigue life used</span></div>',
        f'<div style="font-size:15px;opacity:.75;margin-top:4px">At this rate, about {segments_left:.1f}× '
        f'the loading already seen before D = 1 ({left}).</div>',
        '</div>']))
