"""HTML components mirroring the design system's StatusChip / VerdictCard.

Every user-derived string is escaped. State is always colour + glyph + word,
never colour alone.
"""
from __future__ import annotations

from html import escape

STATES = {
    "ok": ("●", "Normal"),
    "watch": ("◐", "Watch"),
    "alert": ("✕", "Fault"),
    "unknown": ("—", "Unknown"),
}


def chip(state: str, label: str | None = None, detail: str | None = None) -> str:
    state = state if state in STATES else "unknown"
    glyph, word = STATES[state]
    d = f'<span class="d">{escape(detail)}</span>' if detail else ""
    return (f'<span class="nw-chip {state}" role="status"><span class="g" aria-hidden="true">'
            f'{glyph}</span>{escape(label or word)}{d}</span>')


# ---- header illustrations -------------------------------------------------------
# One small themed schematic per page, drawn in the right-hand side of the page
# header. Colours come from the theme's CSS variables, so they follow the theme.
# Motion is a gentle CSS loop (classes a-*, keyframes in theme.py); it is decoration
# beside the title, never a gate on data, and stops under prefers-reduced-motion.
_V = 'viewBox="0 0 240 130" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"'
_MUTED, _LINE, _SUNK = "var(--ink-muted)", "var(--line-control)", "var(--surface-sunken)"

ART: dict[str, str] = {
    "door": f'''<svg {_V}>
  <rect x="18" y="8" width="204" height="100" rx="12" fill="{_SUNK}" stroke="{_LINE}"/>
  <rect x="66" y="16" width="108" height="92" rx="4" fill="var(--surface-page)" stroke="{_LINE}"/>
  <g class="a-door-l"><rect x="68" y="18" width="52" height="90" rx="3" fill="var(--subsystem-door)" opacity=".9"/>
    <rect x="78" y="28" width="32" height="34" rx="3" fill="var(--surface-page)" opacity=".55"/></g>
  <g class="a-door-r"><rect x="120" y="18" width="52" height="90" rx="3" fill="var(--subsystem-door)" opacity=".9"/>
    <rect x="130" y="28" width="32" height="34" rx="3" fill="var(--surface-page)" opacity=".55"/></g>
  <path class="a-flow" d="M18 122 H60 l6 -10 l6 20 l6 -14 l6 4 H120 l8 -12 l6 18 l6 -10 H222" fill="none"
        stroke="var(--status-alert)" stroke-width="2" stroke-dasharray="6 4" stroke-linecap="round"/>
</svg>''',
    "shm": f'''<svg {_V}>
  <path d="M20 70 L60 30 L100 70 L140 30 L180 70 L220 30" fill="none" stroke="var(--subsystem-shm)" stroke-width="5" stroke-linejoin="round"/>
  <path d="M20 70 H220 M20 30 H220" stroke="{_LINE}" stroke-width="4"/>
  <circle cx="100" cy="70" r="7" fill="var(--status-alert)"/>
  <circle class="a-pulse" cx="100" cy="70" r="7" fill="none" stroke="var(--status-alert)" stroke-width="2"/>
  <clipPath id="shmclip"><rect x="18" y="86" width="204" height="40"/></clipPath>
  <g clip-path="url(#shmclip)"><path class="a-scroll" d="M0 106 q10 -18 20 0 t20 0 q5 -8 10 0 t10 0 q15 -22 30 0 t30 0 q10 -18 20 0 t20 0 q5 -8 10 0 t10 0 q15 -22 30 0 t30 0 q10 -18 20 0 t20 0"
        fill="none" stroke="var(--series-1)" stroke-width="2"/></g>
</svg>''',
    "rail": f'''<svg {_V}>
  <path d="M10 100 H230" stroke="{_LINE}" stroke-width="8"/>
  <path d="M60 96 q6 -6 12 0 t12 0 t12 0 t12 0 t12 0 t12 0 t12 0 t12 0 t12 0" fill="none" stroke="var(--status-watch)" stroke-width="3"/>
  <g class="a-roll"><circle cx="120" cy="72" r="22" fill="{_SUNK}" stroke="var(--subsystem-rail)" stroke-width="5"/>
    <g class="a-spin"><path d="M120 54 V90 M102 72 H138" stroke="var(--subsystem-rail)" stroke-width="3"/></g>
    <circle cx="120" cy="72" r="4" fill="var(--subsystem-rail)"/></g>
  <path class="a-flow" d="M14 22 l10 -8 l10 16 l10 -12 l10 8 l10 -10 l10 14 l10 -8 l10 6 l10 -12 l10 16 l10 -10 l10 6 l10 -8 l10 12 l10 -10 l10 8 l10 -6 l10 10 l10 -8 l10 4"
        fill="none" stroke="var(--series-1)" stroke-width="2" stroke-dasharray="7 4"/>
</svg>''',
    "acv": f'''<svg {_V}>
  <rect x="20" y="48" width="170" height="64" rx="12" fill="{_SUNK}" stroke="{_LINE}"/>
  <rect x="34" y="62" width="30" height="22" rx="3" fill="var(--surface-page)"/><rect x="74" y="62" width="30" height="22" rx="3" fill="var(--surface-page)"/>
  <rect x="114" y="62" width="30" height="22" rx="3" fill="var(--surface-page)"/><rect x="154" y="62" width="24" height="22" rx="3" fill="var(--surface-page)"/>
  <rect x="70" y="26" width="72" height="22" rx="5" fill="var(--subsystem-acv)"/>
  <g class="a-spin" transform-origin="106 37"><path d="M106 29 V45 M98 37 H114 M100 31 L112 43 M112 31 L100 43" stroke="var(--surface-page)" stroke-width="2.5" stroke-linecap="round"/></g>
  <path class="a-flow" d="M84 52 q6 8 0 16 t0 16 M106 52 q6 8 0 16 t0 16 M128 52 q6 8 0 16 t0 16" fill="none" stroke="var(--series-5, var(--series-1))" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round"/>
  <rect x="206" y="30" width="12" height="72" rx="6" fill="{_SUNK}" stroke="{_LINE}"/>
  <rect class="a-temp" x="209" y="52" width="6" height="46" rx="3" fill="var(--status-alert)"/>
  <circle cx="212" cy="104" r="9" fill="var(--status-alert)"/>
</svg>''',
    "fleet": f'''<svg {_V}>
  <path d="M20 100 C70 90 90 40 130 40 S200 30 222 18" fill="none" stroke="#d42e12" stroke-width="5"/>
  <path d="M18 60 H222" fill="none" stroke="#009645" stroke-width="5"/>
  <path d="M70 118 C90 80 150 90 170 20" fill="none" stroke="#9900aa" stroke-width="5"/>
  <circle cx="130" cy="40" r="6" fill="var(--surface-page)" stroke="{_MUTED}" stroke-width="3"/>
  <circle cx="106" cy="60" r="6" fill="var(--surface-page)" stroke="{_MUTED}" stroke-width="3"/>
  <circle cx="60" cy="60" r="6" fill="var(--surface-page)" stroke="{_MUTED}" stroke-width="3"/>
  <circle cx="176" cy="60" r="7" fill="var(--status-alert)"/>
  <circle class="a-pulse" cx="176" cy="60" r="7" fill="none" stroke="var(--status-alert)" stroke-width="2"/>
</svg>''',
    "live": f'''<svg {_V}>
  <circle cx="120" cy="65" r="10" fill="var(--series-1)"/>
  <circle class="a-pulse" cx="120" cy="65" r="12" fill="none" stroke="var(--series-1)" stroke-width="2"/>
  <circle class="a-pulse a-late" cx="120" cy="65" r="12" fill="none" stroke="var(--series-1)" stroke-width="2"/>
  <path d="M86 31 a48 48 0 0 0 0 68 M154 31 a48 48 0 0 1 0 68" fill="none" stroke="{_MUTED}" stroke-width="3" stroke-linecap="round"/>
  <path d="M64 13 a78 78 0 0 0 0 104 M176 13 a78 78 0 0 1 0 104" fill="none" stroke="{_LINE}" stroke-width="3" stroke-linecap="round"/>
</svg>''',
    "folds": f'''<svg {_V}>
  <g fill="{_SUNK}" stroke="{_LINE}">
    <rect x="20" y="22" width="36" height="24" rx="5"/><rect x="62" y="22" width="36" height="24" rx="5"/><rect x="104" y="22" width="36" height="24" rx="5"/><rect x="146" y="22" width="36" height="24" rx="5"/><rect x="188" y="22" width="36" height="24" rx="5"/>
    <rect x="20" y="56" width="36" height="24" rx="5"/><rect x="62" y="56" width="36" height="24" rx="5"/><rect x="104" y="56" width="36" height="24" rx="5"/><rect x="146" y="56" width="36" height="24" rx="5"/><rect x="188" y="56" width="36" height="24" rx="5"/>
  </g>
  <rect class="a-fold" x="20" y="22" width="36" height="58" rx="5" fill="var(--status-watch)" opacity=".85"/>
  <text x="120" y="110" text-anchor="middle" font-size="12" fill="{_MUTED}">held-out fold steps across</text>
</svg>''',
    "monitor": f'''<svg {_V}>
  <path d="M10 70 l12 -20 l12 34 l12 -26 l12 14 l12 -8 l12 22 l12 -30 l12 18 l12 -6 l12 14 l12 -24 l12 16 l12 -4 l12 8 l12 -14 l12 10 l12 -6" fill="none" stroke="var(--series-1)" stroke-width="2.5"/>
  <g class="a-scan"><circle cx="60" cy="62" r="24" fill="var(--surface-page)" fill-opacity=".25" stroke="var(--status-watch)" stroke-width="4"/>
    <path d="M77 79 L96 98" stroke="var(--status-watch)" stroke-width="7" stroke-linecap="round"/></g>
</svg>''',
    "package": f'''<svg {_V}>
  <path d="M70 44 L120 22 L170 44 L170 100 L120 122 L70 100 Z" fill="{_SUNK}" stroke="{_LINE}" stroke-width="2"/>
  <path d="M70 44 L120 66 L170 44 M120 66 V122" fill="none" stroke="{_LINE}" stroke-width="2"/>
  <circle cx="178" cy="36" r="20" fill="var(--status-ok)"/>
  <path class="a-draw" d="M168 36 l7 7 l13 -14" fill="none" stroke="var(--surface-page)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="30"/>
</svg>''',
    "pipeline": f'''<svg {_V}>
  <path id="pl" d="M30 65 C70 20 90 110 130 65 S190 20 212 65" fill="none" stroke="{_LINE}" stroke-width="3"/>
  <circle cx="30" cy="65" r="12" fill="var(--series-1)"/><circle cx="92" cy="72" r="12" fill="var(--series-2)"/>
  <circle cx="160" cy="48" r="12" fill="var(--series-3)"/><circle cx="212" cy="65" r="12" fill="var(--series-4)"/>
  <path class="a-flow" d="M30 65 C70 20 90 110 130 65 S190 20 212 65" fill="none" stroke="var(--ink-primary)" stroke-width="3" stroke-dasharray="2 14" stroke-linecap="round"/>
</svg>''',
}

_ART_FOR = [("door", "door"), ("structural", "shm"), ("rail", "rail"), ("air condition", "acv"),
            ("fleet", "fleet"), ("live", "live"), ("evidence", "folds"), ("validat", "folds"),
            ("new data", "monitor"), ("deliverable", "package"), ("submission", "package"),
            ("how it works", "pipeline"), ("method", "pipeline")]


def health_bands(groups: list[tuple[str, str, list[tuple[str, str]]]]) -> str:
    """The health key: for each subsystem, the value range behind Normal / Watch / Fault.
    groups = [(name, what_is_measured, [(state, range text), ...]), ...]"""
    cards = []
    for name, measure, bands in groups:
        rows = "".join(f'<div class="b {st}"><span class="w"><span class="g" aria-hidden="true">{STATES[st][0]}</span>'
                       f'{STATES[st][1]}</span><span class="r">{escape(txt)}</span></div>' for st, txt in bands)
        cards.append(f'<div class="nw-band"><div class="n">{escape(name)}</div>'
                     f'<div class="m">{escape(measure)}</div>{rows}</div>')
    return f'<div class="nw-bands">{"".join(cards)}</div>'


def top_list(rows: list[dict]) -> str:
    """Ranked list for the Top-N panels: rank, title + detail, a bar scaled to the
    leader, and the value. Each row: rank, title, detail, value, frac (0-1), state."""
    items = "".join(
        f'<div class="nw-top-row {r.get("state", "")}"><span class="r">{r["rank"]}</span>'
        f'<div class="main"><div class="t">{escape(str(r["title"]))}</div>'
        f'<div class="d">{escape(str(r.get("detail", "")))}</div></div>'
        f'<div class="bar"><span style="width:{max(3, min(100, round(100 * float(r.get("frac", 0)))))}%"></span></div>'
        f'<span class="v">{escape(str(r["value"]))}</span></div>' for r in rows)
    return f'<div class="nw-top">{items}</div>'


def header(eyebrow: str, title: str, lede: str, color: str | None = None, art: str | None = None) -> str:
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    if art is None:          # pick the illustration from the page's own eyebrow
        low = eyebrow.lower()
        art = next((a for k, a in _ART_FOR if k in low), None)
    pic = f'<div class="nw-art">{ART[art]}</div>' if art in ART else ""
    return (f'<div class="nw-pagehead{" has-art" if pic else ""}"><div class="nw-eyebrow">{dot}{escape(eyebrow)}</div>'
            f'<div class="nw-h1">{escape(title)}</div><p class="nw-lede">{escape(lede)}</p>{pic}</div>')


def section(label: str) -> str:
    return f'<div class="nw-section">{escape(label)}</div>'


def verdict(state: str, subsystem: str, title: str, meaning: str,
            action: str, evidence: str, chip_label: str | None = None) -> str:
    return f"""<div class="nw-card">
  <div class="head">{chip(state, chip_label)}<span class="sub">{escape(subsystem)}</span></div>
  <h3>{escape(title)}</h3>
  <p class="meaning">{escape(meaning)}</p>
  <p class="action"><b>Action &mdash; </b>{escape(action)}</p>
  <p class="evidence">{escape(evidence)}</p>
</div>"""


def kpis(items: list[tuple[str, str, str | None]]) -> str:
    cells = "".join(
        f'<div class="nw-kpi"><div class="l">{escape(l)}</div><div class="v">{escape(v)}</div>'
        + (f'<div class="s">{escape(s)}</div>' if s else "") + "</div>"
        for l, v, s in items)
    return f'<div class="nw-kpis">{cells}</div>'


def system_tile(color: str, state: str, state_label: str, name: str, question: str,
                score: str, metric: str, split: str, emoji: str = "") -> str:
    e = f'<span class="nw-emoji">{emoji}</span>' if emoji else ""
    return f"""<div class="nw-sys"><div class="bar" style="background:{color}"></div>
  {chip(state, state_label)}
  <div class="name">{e}{escape(name)}</div>
  <p class="q">{escape(question)}</p>
  <div class="score">{escape(score)}</div>
  <div class="metric">{escape(metric)}</div>
  <div class="split">{escape(split)}</div>
</div>"""


def steps(items: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<div class="nw-step"><div class="n">0{i}</div><div class="t">{escape(t)}</div>'
        f'<div class="b">{escape(b)}</div></div>' for i, (t, b) in enumerate(items, 1))
    return f'<div class="nw-steps">{cells}</div>'


def empty(title: str, paragraphs: list[str], tag: str | None = None) -> str:
    """An empty state. The status tag is opt-in: only a page whose model is genuinely
    pending says so; an empty queue or an unset filter is not a pending model."""
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    t = chip("unknown", tag) if tag else ""
    return f'<div class="nw-empty">{t}<h3>{escape(title)}</h3>{body}</div>'


def hero(kicker: str, title: str, sub: str, emoji: str, big: str, lines: list[str]) -> str:
    right = "".join(f"<div>{escape(x)}</div>" for x in lines)
    return (f'<div class="nw-hero-card"><div><div class="k">{escape(kicker)}</div><div class="t">{escape(title)}</div>'
            f'<div class="s">{escape(sub)}</div></div>'
            f'<div class="wx"><span class="e">{emoji}</span><div class="big">{escape(big)}</div>{right}</div></div>')


def car_rank(cars: list[tuple[str, float | None]], baseline: str | None = None,
             fmt=lambda s: f"{s:+.2f} °C") -> str:
    """CarRank: every car listed best-first; rank 1 wears status-alert, the rest series-1.
    Bars normalise to the top score so a near-tie looks like a near-tie."""
    finite = [s for _, s in cars if s is not None]
    lo = min(finite) if finite else 0.0
    hi = max(finite) if finite else 1.0
    span = (hi - lo) or 1.0
    rows = []
    for i, (cid, s) in enumerate(cars, 1):
        if s is None:
            w, cls, txt = 0, "na", "no cooling evidence"
        else:
            w = max(6, round(100 * (s - lo) / span)) if hi > lo else 100
            cls, txt = ("top" if i == 1 else ""), fmt(s)
        rows.append(f'<div class="nw-rank-row {cls}"><span class="r">{i}</span>'
                    f'<span class="id">Car {escape(cid)}</span>'
                    f'<span class="bar"><span style="width:{w}%"></span></span>'
                    f'<span class="v">{escape(txt)}</span></div>')
    cap = f'<div class="cap">{escape(baseline)}</div>' if baseline else ""
    return f'<div class="nw-rank">{"".join(rows)}{cap}</div>'


def fleet_row(state: str, name: str, headline: str, detail: str) -> str:
    return (f'<div class="nw-fleet {state}"><div class="n">{escape(name)}</div>'
            f'<div class="h">{chip(state)}<span>{escape(headline)}</span></div>'
            f'<div class="d">{escape(detail)}</div></div>')


def pill(state: str, text: str) -> str:
    state = state if state in STATES else "unknown"
    return f'<span class="nw-pill {state}"><i></i>{escape(text)}</span>'


def status_bar(counts: dict[str, int], title: str = "Status overview") -> str:
    """Stacked bar of alert / watch / ok, with a legend. Counts of assets in each state."""
    total = sum(counts.values()) or 1
    segs = "".join(f'<span class="{k}" style="width:{100 * v / total:.1f}%"></span>'
                   for k, v in counts.items() if v)
    words = {"alert": "Fault", "watch": "Watch", "ok": "Normal", "unknown": "Not assessed"}
    legend = "".join(f'<span class="lg"><i class="{k}"></i>{words[k]} {v}</span>' for k, v in counts.items())
    return (f'<div class="nw-panel"><div class="t">{escape(title)}</div>'
            f'<div class="nw-stack">{segs}</div><div class="nw-legend">{legend}</div></div>')


def event_table(rows: list[dict], empty: str = "No events yet") -> str:
    if not rows:
        return f'<div class="nw-panel"><div class="t">Events</div><p class="muted">{escape(empty)}</p></div>'
    body = "".join(
        f'<tr><td class="mono">#{i}</td><td>{escape(r["subsystem"])}</td><td>{escape(r["title"])}</td>'
        f'<td class="muted">{escape(r["detail"])}</td><td class="mono">{r["severity"]:.2f}</td>'
        f'<td>{pill(r["state"], STATES[r["state"]][1])}</td></tr>'
        for i, r in enumerate(rows, 1))
    return (f'<div class="nw-panel"><table class="nw-table"><thead><tr><th></th><th>Subsystem</th>'
            f'<th>Event</th><th>Evidence</th><th>Severity</th><th>Status</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def beacon(text: str, detail: str = "") -> str:
    """Blinking warning strip for the top of a page when something needs attention."""
    return (f'<div class="nw-beacon" role="alert"><i></i>{escape(text)}'
            + (f'<span class="d">{escape(detail)}</span>' if detail else "") + '</div>')


def live(text: str = "Live") -> str:
    return f'<span class="nw-live"><i></i>{escape(text)}</span>'
