"""Live LTA page: every DataMall feed, refreshing itself.

The whole body is one Streamlit fragment that re-runs every 20 seconds. Each
feed is cached until its own refresh window rolls over (lta_live.fetch), so a
20-second re-run only calls the feeds that have actually changed at source.

Rendering helpers (html, plot, map_chart) are passed in from streamlit_app so
this module shares the app's styling, chart toolbar and map resize fix without
importing the app itself.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

import charts
import components as ui
import insight
import livemap
import lta_live as L
from theme import T

REFRESH_S = 20
LEVEL_WORD = {"l": "low", "m": "moderate", "h": "high"}
LEVEL_TOKEN = {"l": "status-ok", "m": "status-watch", "h": "status-alert"}


def _stamp(res: dict, feed_key: str) -> str:
    f = L.FEEDS[feed_key]
    if not res.get("ok"):
        return f"{f.title}: {res.get('reason', 'unavailable')}"
    extra = " · first pages only" if res.get("capped") else ""
    return f"{f.title} · fetched {res['fetched_at']} SGT · source updates {L.every(f.refresh_s)}{extra}"


def _hex_rgb(h: str, a: int = 200) -> list[int]:
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [a]


def render(key: str, key_source: str, html, plot, map_chart) -> None:
    html(ui.header("Live LTA", "The network, right now",
                   "Every real-time feed from LTA DataMall - rail status, platform crowding, lift "
                   "maintenance, roads, buses, taxis, carparks and floods - refreshing on its own. "
                   "Each card says when it was fetched and how often LTA updates it.",
                   T("series-1")))
    if not key:
        html(ui.empty("No DataMall key configured",
                      ["Add LTA_ACCOUNT_KEY to .streamlit/secrets.toml (local) or the app's Secrets "
                       "(Streamlit Cloud), or paste it on the Dashboard. Use the API Account Key from the "
                       "DataMall email - 24 characters ending in ==."]))
        return

    @st.fragment(run_every=f"{REFRESH_S}s")
    def live_body() -> None:
        now = pd.Timestamp.now(tz="Asia/Singapore").strftime("%a %d %b · %H:%M:%S")
        html(ui.chip("ok", "Live", f"{now} SGT · page refreshes every {REFRESH_S} s · key from {key_source}"))

        # ---------------------------------------------------------------- fetch
        # every feed this page shows, fetched in parallel; the reads below hit the cache
        jobs = [(L.fetch, (fk, key), {}) for fk in ("alerts", "lifts", "incidents", "vms", "cameras", "taxis",
                                                    "carparks", "floods", "faulty_lights", "travel", "speed")]
        jobs += [(livemap.fetch_crowd, (key, ln), {}) for ln in livemap.LINES]
        jobs.append((L.fetch, ("crowd_fc", key), {"TrainLine": st.session_state.get("live_fc_line", L.TRAIN_LINES[0])}))
        stop_ = str(st.session_state.get("live_stop_input", st.session_state.get("live_stop", "83139"))).strip()
        if stop_:
            jobs.append((L.fetch, ("bus_arrival", key), {"BusStopCode": stop_}))
        pc_ = str(st.session_state.get("live_ev_pc", "018989")).strip()
        if pc_:
            jobs.append((L.fetch, ("ev", key), {"PostalCode": pc_}))
        L.prefetch(key, jobs)
        alerts = L.fetch("alerts", key)
        lifts = L.fetch("lifts", key)
        incidents = L.fetch("incidents", key)
        vms = L.fetch("vms", key)
        cameras = L.fetch("cameras", key)
        taxis = L.fetch("taxis", key)
        cps = L.fetch("carparks", key)
        floods = L.fetch("floods", key)
        faulty = L.fetch("faulty_lights", key)
        crowd_parts = {ln: livemap.fetch_crowd(key, ln) for ln in livemap.LINES}
        crowd_rows = pd.concat([p["rows"].assign(line=ln) for ln, p in crowd_parts.items()
                                if p.get("ok") and not p["rows"].empty], ignore_index=True) \
            if any(p.get("ok") and not p["rows"].empty for p in crowd_parts.values()) else pd.DataFrame()

        # ---------------------------------------------------------------- headline
        av = (alerts.get("raw") or {}).get("value") or {}
        segs = av.get("AffectedSegments") or []
        rail_ok = alerts.get("ok") and int(av.get("Status", 1) or 1) == 1 and not segs
        n_high = int((crowd_rows["level"] == "h").sum()) if len(crowd_rows) else 0
        cp_all = L.carparks(cps)
        # LotType C = cars, Y = motorcycles, H = heavy vehicles. Adding them together
        # would overstate car parking several-fold, so the page shows car lots only.
        cp = cp_all[cp_all["LotType"] == "C"] if "LotType" in cp_all else cp_all
        html(ui.kpis([
            ("Train service", ("Normal" if rail_ok else "Disrupted") if alerts.get("ok") else "—",
             f"{len(segs)} affected segment(s)" if alerts.get("ok") else alerts.get("reason")),
            ("Stations at high crowd", f"{n_high}", f"of {crowd_rows['code'].nunique() if len(crowd_rows) else 0} reporting"),
            ("Lifts under maintenance", f"{len(lifts.get('rows') or [])}", "MRT stations"),
            ("Traffic incidents", f"{len(incidents.get('rows') or [])}", f"{len(faulty.get('rows') or [])} faulty traffic light(s)"),
            ("Taxis available", f"{len(taxis.get('rows') or []):,}", "island-wide, now"),
            ("Car lots free", f"{int(pd.to_numeric(cp.get('AvailableLots', pd.Series(dtype=float)), errors='coerce').sum()):,}"
             if len(cp) else "—", f"across {len(cp):,} carparks"),
        ]))

        # ---------------------------------------------------------------- rail
        html(ui.section("Rail · service, crowding and station lifts"))
        a, b = st.columns([1, 1], gap="medium")
        with a:
            if not alerts.get("ok"):
                html(ui.chip("unknown", "Service feed unavailable", alerts.get("reason")))
            elif rail_ok:
                html(ui.chip("ok", "All MRT and LRT lines running normally", f"fetched {alerts['fetched_at']} SGT"))
            else:
                html(ui.chip("alert", "Disruption reported", f"{len(segs)} affected segment(s)"))
                for sg in segs:
                    st.markdown(f"**{sg.get('Line', '?')}** · {sg.get('Direction', '')} · "
                                f"{sg.get('Stations', '')}  \nFree bus: {sg.get('FreePublicBus', '—')} · "
                                f"Free shuttle: {sg.get('FreeMRTShuttle', '—')}")
            for m in (av.get("Message") or []):
                if isinstance(m, dict) and m.get("Content"):
                    st.info(m["Content"])
            st.caption(_stamp(alerts, "alerts"))

            lf = L.frame(lifts)
            st.markdown("**Lifts under maintenance**")
            if len(lf):
                st.dataframe(lf.rename(columns={"StationName": "Station", "StationCode": "Code",
                                                "LiftID": "Lift", "LiftDesc": "Where"})
                             [[c for c in ["Line", "Code", "Station", "Lift", "Where"] if c in lf.rename(columns={
                                 "StationName": "Station", "StationCode": "Code", "LiftID": "Lift", "LiftDesc": "Where"}).columns]],
                             hide_index=True, width="stretch")
            else:
                st.caption("No lifts reported under maintenance.")
            st.caption(_stamp(lifts, "lifts"))
        with b:
            if len(crowd_rows):
                counts = (crowd_rows.assign(level=crowd_rows["level"].map(LEVEL_WORD))
                          .groupby(["line", "level"]).size().unstack(fill_value=0))
                fig = go.Figure()
                for lv in ("low", "moderate", "high"):
                    if lv in counts:
                        tok = {"low": "status-ok", "moderate": "status-watch", "high": "status-alert"}[lv]
                        fig.add_bar(y=counts.index, x=counts[lv], name=lv, orientation="h",
                                    marker_color=T(tok),
                                    hovertemplate="%{y} · %{x} station(s) " + lv + "<extra></extra>")
                fig.update_layout(barmode="stack")
                fig.update_xaxes(title="stations")
                plot(charts._base(fig, 300), always=True)
                st.caption("Platform crowd level per line, now (DataMall PCDRealTime, 10-minute feed).")
            else:
                reasons = {p.get("reason") for p in crowd_parts.values() if not p.get("ok")}
                st.caption("Platform crowding: " + ("; ".join(r for r in reasons if r) or
                                                     "no stations listed - normal outside operating hours (about 05:30-00:30)"))

            line = st.selectbox("Crowd forecast for line", L.TRAIN_LINES, key="live_fc_line")
            fc_res = L.fetch("crowd_fc", key, TrainLine=line)
            fc = L.crowd_forecast(fc_res)
            if len(fc):
                share = (fc.assign(high=fc["level"].eq("h"), mod=fc["level"].eq("m"))
                         .groupby("start")[["high", "mod"]].mean() * 100)
                fig = go.Figure()
                fig.add_scatter(x=share.index, y=share["mod"], name="moderate", mode="lines",
                                line=dict(color=T("status-watch"), width=2),
                                hovertemplate="%{x|%H:%M} · %{y:.0f}% of stations moderate<extra></extra>")
                fig.add_scatter(x=share.index, y=share["high"], name="high", mode="lines",
                                line=dict(color=T("status-alert"), width=2),
                                hovertemplate="%{x|%H:%M} · %{y:.0f}% of stations high<extra></extra>")
                fig.add_vline(x=pd.Timestamp.now(tz="Asia/Singapore"), line=dict(color=T("ink-muted"), dash="dot"))
                fig.update_yaxes(title="% of stations", rangemode="tozero")
                plot(charts._base(fig, 260), always=True)
            st.caption(_stamp(fc_res, "crowd_fc"))

        # ---------------------------------------------------------------- map
        html(ui.section("Live map"))
        layer_names = ["Incidents", "Signboards", "Cameras", "Station crowding", "Carparks", "Taxis"]
        show = st.pills("Layers", layer_names, selection_mode="multi",
                        default=["Incidents", "Signboards", "Cameras", "Station crowding"],
                        key="live_layers", label_visibility="collapsed") or []
        layers = []

        def points(df, lat, lon, color, radius, label_fn):
            if df is None or df.empty or lat not in df or lon not in df:
                return None
            d = df.copy()
            d["lat"] = pd.to_numeric(d[lat], errors="coerce")
            d["lon"] = pd.to_numeric(d[lon], errors="coerce")
            d = d.dropna(subset=["lat", "lon"])
            d = d[(d["lat"].between(1.1, 1.5)) & (d["lon"].between(103.5, 104.1))]
            d["label"] = [label_fn(r) for r in d.to_dict("records")]
            return pdk.Layer("ScatterplotLayer", data=d[["lat", "lon", "label"]], get_position="[lon, lat]",
                             get_fill_color=color, get_radius=radius, pickable=True, stroked=True,
                             get_line_color=[255, 255, 255, 120], line_width_min_pixels=1)

        spec = {
            "Taxis": (L.frame(taxis), "Latitude", "Longitude", [240, 180, 41, 150], 45, lambda r: "Available taxi"),
            "Carparks": (cp, "lat", "lon", _hex_rgb(T("status-ok"), 170), 90,
                         lambda r: f"{r.get('Development')} · {r.get('AvailableLots')} lots free ({r.get('Agency')})"),
            "Cameras": (L.frame(cameras), "Latitude", "Longitude", _hex_rgb(T("series-1"), 220), 160,
                        lambda r: f"Traffic camera {r.get('CameraID')}"),
            "Signboards": (L.frame(vms), "Latitude", "Longitude", _hex_rgb(T("status-watch"), 220), 170,
                           lambda r: f"Signboard: {r.get('Message') or '(blank)'}"),
            "Incidents": (L.frame(incidents), "Latitude", "Longitude", _hex_rgb(T("status-alert"), 235), 260,
                          lambda r: f"{r.get('Type')}: {r.get('Message')}"),
        }
        for name in ["Taxis", "Carparks", "Cameras", "Signboards", "Incidents"]:
            if name in show:
                lay = points(*spec[name])
                if lay is not None:
                    layers.append(lay)
        if "Station crowding" in show and len(crowd_rows):
            df_st = insight.with_zones(livemap.stations())
            layers = insight.crowd_layer({"ok": True, "rows": crowd_rows}, df_st) + layers
        deck = pdk.Deck(layers=layers, map_provider="carto", map_style=__import__("theme").map_style(),
                        initial_view_state=pdk.ViewState(latitude=1.3521, longitude=103.8198, zoom=10.4),
                        tooltip={"html": "{label}", "style": {"backgroundColor": "#10151c", "color": "#f7f8fa",
                                                              "fontSize": "12px"}})
        map_chart(deck, key="live_map")
        st.caption("Red: incidents · amber: expressway signboards · blue: traffic cameras · rings: platform "
                   "crowd (green low, amber moderate, red high) · green dots: carparks · yellow: available taxis. "
                   "Hover any point for details.")

        # ---------------------------------------------------------------- roads
        html(ui.section("Roads · incidents, signboards, travel times, speeds"))
        a, b = st.columns([1, 1], gap="medium")
        with a:
            inc = L.frame(incidents)
            st.markdown("**Traffic incidents**")
            if len(inc):
                st.dataframe(inc[["Type", "Message"]], hide_index=True, width="stretch")
            else:
                st.caption("No incidents reported.")
            st.caption(_stamp(incidents, "incidents"))
            vm = L.frame(vms)
            st.markdown("**What the expressway signboards say**")
            if len(vm):
                vm = vm[vm["Message"].astype(str).str.strip() != ""]
                st.dataframe(vm[["EquipmentID", "Message"]].rename(columns={"EquipmentID": "Sign"}),
                             hide_index=True, width="stretch")
            st.caption(_stamp(vms, "vms"))
            fl = L.frame(faulty)
            if len(fl):
                st.markdown("**Faulty traffic lights**")
                st.dataframe(fl, hide_index=True, width="stretch")
            st.caption(_stamp(faulty, "faulty_lights"))
        with b:
            tt_res = L.fetch("travel", key)
            tt = L.frame(tt_res)
            st.markdown("**Expressway travel times**")
            if len(tt):
                tt = tt.rename(columns={"Name": "Expressway", "StartPoint": "From", "EndPoint": "To",
                                        "FarEndPoint": "Towards", "EstTime": "Minutes"})
                st.dataframe(tt[["Expressway", "Towards", "From", "To", "Minutes"]], hide_index=True,
                             width="stretch", height=260)
            st.caption(_stamp(tt_res, "travel"))
            sp_res = L.fetch("speed", key)
            sp = L.frame(sp_res)
            if len(sp):
                c = sp["SpeedBand"].astype(int).value_counts().sort_index()
                fig = go.Figure(go.Bar(x=c.index, y=c.values,
                                       marker_color=[charts.ramp_color(1 - (b_ - 1) / 7) for b_ in c.index],
                                       hovertemplate="speed band %{x}<br>%{y} road links<extra></extra>"))
                fig.update_xaxes(title="speed band (1 slowest - 8 fastest)", dtick=1)
                fig.update_yaxes(title="road links")
                plot(charts._base(fig, 240, legend=False), always=True)
            st.caption(_stamp(sp_res, "speed"))

        # ---------------------------------------------------------------- cameras
        cam = L.frame(cameras)
        if len(cam):
            html(ui.section(f"Traffic cameras · {len(cam)} live images"))
            cols = st.columns(4, gap="small")
            for i, r in enumerate(cam.head(12).to_dict("records")):
                with cols[i % 4]:
                    st.image(r["ImageLink"], caption=f"Camera {r['CameraID']}", width="stretch")
            st.caption(_stamp(cameras, "cameras"))

        # ---------------------------------------------------------------- public transport
        html(ui.section("Public transport · buses, taxis, carparks"))
        a, b = st.columns([1, 1], gap="medium")
        with a:
            stop = st.text_input("Bus stop code", value=st.session_state.get("live_stop", "83139"),
                                 key="live_stop", max_chars=5, help="Five digits, printed on the bus stop pole.")
            ba_res = L.fetch("bus_arrival", key, BusStopCode=stop.strip())
            ba = L.bus_arrivals(ba_res)
            if len(ba):
                st.dataframe(ba, hide_index=True, width="stretch")
            else:
                st.caption("No buses due at this stop right now (or the code is not a bus stop).")
            st.caption(_stamp(ba_res, "bus_arrival"))
        with b:
            if len(cp):
                top = (cp.assign(AvailableLots=pd.to_numeric(cp["AvailableLots"], errors="coerce"))
                       .groupby("Area")["AvailableLots"].sum().sort_values(ascending=False).head(10))
                top = top[top.index.astype(str).str.strip() != ""]
                fig = go.Figure(go.Bar(y=top.index[::-1], x=top.values[::-1], orientation="h",
                                       marker_color=T("status-ok"),
                                       hovertemplate="%{y}<br>%{x:,} lots free<extra></extra>"))
                fig.update_xaxes(title="lots free")
                plot(charts._base(fig, 300, legend=False), always=True)
                st.caption("Carpark areas with the most free lots. " + _stamp(cps, "carparks"))
            st.caption(_stamp(taxis, "taxis"))

        # ---------------------------------------------------------------- environment
        html(ui.section("Environment · floods and EV charging"))
        a, b = st.columns([1, 1], gap="medium")
        with a:
            fd = L.frame(floods)
            if len(fd):
                html(ui.chip("alert", f"{len(fd)} PUB flood alert(s)"))
                st.dataframe(fd, hide_index=True, width="stretch")
            else:
                html(ui.chip("ok", "No PUB flood alerts"))
            st.caption(_stamp(floods, "floods"))
        with b:
            pc = st.text_input("EV charging near postal code", value="018989", key="live_ev_pc", max_chars=6)
            ev_res = L.fetch("ev", key, PostalCode=pc.strip())
            ev = L.ev_points(ev_res)
            if len(ev):
                st.dataframe(ev.drop(columns=["lat", "lon"], errors="ignore"), hide_index=True, width="stretch")
            else:
                st.caption("No charging points listed for that postal code.")
            st.caption(_stamp(ev_res, "ev"))

    live_body()

    # -------------------------------------------------------------------- datasets
    # Outside the fragment: these are monthly / quarterly files, fetched only on request.
    html(ui.section("Bulk datasets · download links"))
    st.caption("These feeds return a download link that DataMall expires after a few minutes, so each is "
               "fetched only when you ask. Reference feeds (bus services, stops, routes, taxi stands, road "
               "works) are listed below the links.")
    ds = [f for f in L.FEEDS.values() if f.link]
    cols = st.columns(3, gap="small")
    for i, f in enumerate(ds):
        with cols[i % 3]:
            if st.button(f"Get link: {f.title}", key=f"ds_{f.key}", width="stretch"):
                res = L.fetch(f.key, key)
                rows = res.get("rows") or []
                link = rows[0].get("Link") if rows and isinstance(rows[0], dict) else None
                if link:
                    st.link_button("Download (link expires soon)", link, width="stretch")
                else:
                    st.caption(res.get("reason") or "No link returned.")
            st.caption(f.blurb)
    html(ui.section("Reference feeds"))
    # Large, slow-changing lists (bus routes alone is tens of thousands of rows): fetched
    # only when one is picked, never on page load.
    ref = ["bus_services", "bus_stops", "bus_routes", "taxi_stands", "roadworks", "openings", "planned_bus"]
    fk = st.selectbox("Reference feed", ref, index=None, key="live_ref_feed",
                      format_func=lambda k: f"{L.FEEDS[k].title}",
                      placeholder="Choose a feed to load (bus services, stops, routes, taxi stands, road works...)")
    if fk:
        with st.spinner(f"Loading {L.FEEDS[fk].title}..."):
            res = L.fetch(fk, key)
        st.caption(L.FEEDS[fk].blurb)
        d = L.frame(res)
        if len(d):
            st.dataframe(d.head(500), hide_index=True, width="stretch", height=320)
            if len(d) > 500:
                st.caption(f"Showing 500 of {len(d):,} rows.")
        st.caption(_stamp(res, fk))
