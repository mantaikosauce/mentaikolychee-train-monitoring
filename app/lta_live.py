"""LTA DataMall live feeds - one client, one catalogue, every endpoint.

Every endpoint in LTA_DataMall_API_User_Guide.pdf is listed in FEEDS with its
refresh interval from the guide. Each was probed with a live key before this file
was written, so the paths, parameters and field names are the real ones.

The AccountKey is found automatically, in this order:
    1. st.secrets["LTA_ACCOUNT_KEY"]   (Streamlit Cloud: Settings -> Secrets)
    2. the LTA_ACCOUNT_KEY environment variable
    3. <project>/.streamlit/secrets.toml, read directly - so it works whatever
       directory `streamlit run` was started from
It is sent only as the AccountKey header to datamall2.mytransport.sg and is
never written anywhere by the app.

Caching: a response is reused until the feed's refresh window rolls over, so a
page that re-renders every 20 s still calls a 24-hour feed once a day. Every
fetch returns {"ok", "rows", "raw", "fetched_at", "reason"} and never raises,
so one bad feed can never take the page down.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = "https://datamall2.mytransport.sg/ltaodataservice/"
PAGE = 500                                    # DataMall returns at most 500 records per call
PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- key

def auto_key() -> tuple[str, str]:
    """(key, where it came from) - ("", "") if no key is configured."""
    try:
        k = str(st.secrets.get("LTA_ACCOUNT_KEY", "") or "").strip()
        if k:
            return k, "Streamlit secrets"
    except Exception:                          # no secrets file in the working directory
        pass
    k = os.environ.get("LTA_ACCOUNT_KEY", "").strip()
    if k:
        return k, "environment variable"
    p = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if p.exists():
        try:
            import tomllib
            k = str(tomllib.loads(p.read_text(encoding="utf-8")).get("LTA_ACCOUNT_KEY", "")).strip()
            if k:
                return k, ".streamlit/secrets.toml"
        except Exception:
            pass
    return "", ""


# ----------------------------------------------------------------------- catalogue

@dataclass(frozen=True)
class Feed:
    key: str
    path: str
    title: str
    group: str
    refresh_s: int                 # from the guide's "update frequency"
    blurb: str
    params: tuple = ()             # fixed query parameters, as (name, value) pairs
    max_pages: int = 1             # 500 records per page
    link: bool = False             # returns a short-lived download link, not rows
    user_params: tuple = field(default=())   # parameters the page asks the user for


FEEDS: dict[str, Feed] = {f.key: f for f in [
    # ---- rail: closest to the condition-monitoring story
    Feed("alerts", "TrainServiceAlerts", "Train service alerts", "Rail", 60,
         "Official MRT/LRT disruption status, affected segments and messages."),
    Feed("crowd", "PCDRealTime", "Platform crowding, now", "Rail", 600,
         "Crowd level (low / moderate / high) at every station, 10-minute feed.",
         user_params=("TrainLine",)),
    Feed("crowd_fc", "PCDForecast", "Platform crowding, forecast", "Rail", 86400,
         "Forecast crowd level per station in 30-minute intervals for the day.",
         user_params=("TrainLine",)),
    Feed("lifts", "v2/FacilitiesMaintenance", "Lifts under maintenance", "Rail", 600,
         "MRT station lifts currently out of service for maintenance."),
    # ---- roads
    Feed("incidents", "TrafficIncidents", "Traffic incidents", "Roads", 120,
         "Accidents, breakdowns, road works and obstacles on expressways and major roads."),
    Feed("vms", "VMS", "Expressway signboards (VMS)", "Roads", 120,
         "What the electronic message signs over the expressways say right now."),
    Feed("faulty_lights", "FaultyTrafficLights", "Faulty traffic lights", "Roads", 120,
         "Traffic signals reported faulty or flashing."),
    Feed("travel", "EstTravelTimes", "Expressway travel times", "Roads", 300,
         "Estimated minutes between expressway points, both directions."),
    Feed("speed", "v4/TrafficSpeedBands", "Traffic speed bands", "Roads", 300,
         "Speed band per road link (1 = slowest, 8 = fastest). First 3,000 links sampled.",
         max_pages=6),
    Feed("cameras", "Traffic-Imagesv2", "Traffic cameras", "Roads", 60,
         "Latest image from each expressway camera; links expire after about 15 minutes."),
    Feed("roadworks", "RoadWorks", "Road works", "Roads", 86400,
         "Approved road works: road, dates and responsible department.", max_pages=4),
    Feed("openings", "RoadOpenings", "Road openings", "Roads", 86400,
         "Planned road openings.", max_pages=4),
    # ---- public transport
    Feed("bus_arrival", "v3/BusArrival", "Bus arrivals", "Public transport", 20,
         "Next three buses per service at one stop: minutes, load, wheelchair access.",
         user_params=("BusStopCode",)),
    Feed("taxis", "Taxi-Availability", "Available taxis", "Public transport", 60,
         "Positions of every taxi currently available for hire.", max_pages=12),
    Feed("taxi_stands", "TaxiStands", "Taxi stands", "Public transport", 86400,
         "Location and type of every taxi stand.", max_pages=1),
    Feed("carparks", "CarParkAvailabilityv2", "Carpark availability", "Public transport", 60,
         "Available lots at HDB, LTA and URA carparks.", max_pages=6),
    Feed("bus_services", "BusServices", "Bus services", "Public transport", 86400,
         "Service numbers, operators and peak / off-peak frequencies (first 500)."),
    Feed("bus_stops", "BusStops", "Bus stops", "Public transport", 86400,
         "Bus stop codes, roads and descriptions (first 500)."),
    Feed("bus_routes", "BusRoutes", "Bus routes", "Public transport", 86400,
         "Stop sequences and first / last bus per service (first 500)."),
    # ---- environment and mobility
    Feed("floods", "PubFloodAlerts", "Flood alerts", "Environment", 300,
         "PUB flood alerts that may affect roads and stations."),
    Feed("ev", "EVChargingPoints", "EV charging points", "Environment", 300,
         "Charging points and their status near a postal code.", user_params=("PostalCode",)),
    Feed("bicycles", "BicycleParkingv2", "Bicycle parking", "Environment", 86400,
         "Bicycle parking within a radius of a point.", user_params=("Lat", "Long", "Dist")),
    # ---- bulk datasets: DataMall returns a download link that expires in minutes
    Feed("pv_train", "PV/Train", "Passenger volume by train station", "Datasets", 86400,
         "Monthly tap-in / tap-out volumes per station.", link=True),
    Feed("pv_odtrain", "PV/ODTrain", "Passenger volume, origin-destination train", "Datasets", 86400,
         "Monthly station-to-station journeys.", link=True),
    Feed("pv_bus", "PV/Bus", "Passenger volume by bus stop", "Datasets", 86400,
         "Monthly tap-in / tap-out volumes per bus stop.", link=True),
    Feed("pv_odbus", "PV/ODBus", "Passenger volume, origin-destination bus", "Datasets", 86400,
         "Monthly stop-to-stop journeys.", link=True),
    Feed("traffic_flow", "TrafficFlow", "Traffic flow", "Datasets", 86400,
         "Quarterly hourly traffic volume per road link.", link=True),
    Feed("evc_batch", "EVCBatch", "EV charging points, full list", "Datasets", 86400,
         "Every charging point island-wide, as a file.", link=True),
    Feed("geospatial", "GeospatialWholeIsland", "Geospatial layers (arrow markings)", "Datasets", 86400,
         "Island-wide road geospatial layer; other layers via the ID parameter.",
         params=(("ID", "ArrowMarking"),), link=True),
    Feed("planned_bus", "PlannedBusRoutes", "Planned bus routes", "Datasets", 86400,
         "Upcoming bus route changes."),
]}

GROUPS = ["Rail", "Roads", "Public transport", "Environment", "Datasets"]
TRAIN_LINES = ["NSL", "EWL", "CGL", "NEL", "CCL", "CEL", "DTL", "TEL"]


# -------------------------------------------------------------------------- fetch

def _now_sgt() -> str:
    return pd.Timestamp.now(tz="Asia/Singapore").strftime("%H:%M:%S")


class FeedError(Exception):
    """A failed fetch. Raised inside the cached function so the failure is NOT cached:
    st.cache_data never stores a call that raised, so the next render retries."""

    def __init__(self, reason: str, rejected: bool = False):
        super().__init__(reason)
        self.reason, self.rejected = reason, rejected


@st.cache_data(show_spinner=False, ttl=86400, max_entries=512)
def _fetch(path: str, params: tuple, key: str, max_pages: int, window: int) -> dict:
    """One cached SUCCESS per (endpoint, parameters, refresh window). Raises FeedError."""
    import requests
    rows: list = []
    raw = None
    for page in range(max_pages):
        q = dict(params)
        if page:
            q["$skip"] = page * PAGE
        try:
            r = requests.get(BASE + path, params=q, timeout=12,
                             headers={"AccountKey": key, "accept": "application/json"})
        except Exception as exc:
            raise FeedError(f"could not reach DataMall ({type(exc).__name__}) - retrying on the next refresh")
        if r.status_code != 200:
            if r.status_code in (401, 403):
                raise FeedError(f"DataMall rejected the key (HTTP {r.status_code})", rejected=True)
            raise FeedError(f"DataMall answered HTTP {r.status_code} - retrying on the next refresh")
        j = r.json()
        raw = raw if raw is not None else j
        v = j.get("value", j)
        if not isinstance(v, list):
            break
        rows += v
        if len(v) < PAGE:
            break
    return {"ok": True, "rows": rows, "raw": raw, "fetched_at": _now_sgt(), "reason": "",
            "capped": len(rows) >= max_pages * PAGE}


def fetch(feed_key: str, key: str, **user_params) -> dict:
    """Fetch a catalogue feed. Cached until its refresh window rolls over."""
    f = FEEDS[feed_key]
    if not key:
        return {"ok": False, "reason": "no AccountKey configured", "rows": [], "raw": None, "fetched_at": ""}
    params = tuple(sorted({**dict(f.params), **{k: str(v) for k, v in user_params.items()}}.items()))
    window = int(time.time() // max(f.refresh_s, 10))
    try:
        out = dict(_fetch(f.path, params, key, f.max_pages, window))
    except FeedError as exc:
        return {"ok": False, "reason": exc.reason, "rejected": exc.rejected, "rows": [], "raw": None,
                "fetched_at": _now_sgt(), "refresh_s": f.refresh_s}
    out["refresh_s"] = f.refresh_s
    return out


def prefetch(key: str, jobs: list) -> None:
    """Warm the cache for many feeds at once, in parallel. jobs: (callable, args) pairs.
    The page then reads each feed from the cache, so a page that needs 20 feeds waits
    for the slowest one instead of the sum of all of them."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    if not key or not jobs:
        return
    ctx = get_script_run_ctx()

    def init():
        if ctx is not None:
            add_script_run_ctx(threading.current_thread(), ctx)

    def run(job):
        fn, args, kwargs = job
        try:
            fn(*args, **kwargs)
        except Exception:
            pass                      # the page's own call reports the failure

    with ThreadPoolExecutor(max_workers=12, initializer=init) as pool:
        list(pool.map(run, jobs))


def frame(res: dict) -> pd.DataFrame:
    return pd.DataFrame(res.get("rows") or [])


def every(seconds: int) -> str:
    if seconds < 60:
        return f"every {seconds} s"
    if seconds < 3600:
        return f"every {seconds // 60} min"
    if seconds < 86400:
        return f"every {seconds // 3600} h"
    return "daily"


# ----------------------------------------------------------------- shaped helpers

def minutes_until(iso: str) -> float | None:
    if not iso:
        return None
    try:
        t = pd.Timestamp(iso)
        now = pd.Timestamp.now(tz=t.tz or "Asia/Singapore")
        return max(0.0, (t - now).total_seconds() / 60)
    except Exception:
        return None


LOAD = {"SEA": "seats available", "SDA": "standing", "LSD": "limited standing"}
BUS_TYPE = {"SD": "single deck", "DD": "double deck", "BD": "bendy"}


def bus_arrivals(res: dict) -> pd.DataFrame:
    """v3/BusArrival -> one row per service with the next three buses in minutes."""
    raw = res.get("raw") or {}
    rows = []
    for s in raw.get("Services", []) or []:
        mins = [minutes_until((s.get(k) or {}).get("EstimatedArrival")) for k in ("NextBus", "NextBus2", "NextBus3")]
        nb = s.get("NextBus") or {}
        rows.append({
            "Service": s.get("ServiceNo"), "Operator": s.get("Operator"),
            "Next (min)": None if mins[0] is None else round(mins[0]),
            "2nd (min)": None if mins[1] is None else round(mins[1]),
            "3rd (min)": None if mins[2] is None else round(mins[2]),
            "Load": LOAD.get(nb.get("Load"), nb.get("Load") or "—"),
            "Bus": BUS_TYPE.get(nb.get("Type"), nb.get("Type") or "—"),
            "Wheelchair": "yes" if nb.get("Feature") == "WAB" else "—",
            "Live GPS": "yes" if str(nb.get("Monitored")) == "1" else "scheduled",
        })
    return pd.DataFrame(rows)


def crowd_forecast(res: dict) -> pd.DataFrame:
    """PCDForecast -> long table: station, start time, level."""
    rows = []
    for day in res.get("rows") or []:
        for stn in day.get("Stations", []) or []:
            for iv in stn.get("Interval", []) or []:
                rows.append({"station": stn.get("Station"), "start": pd.Timestamp(iv.get("Start")),
                             "level": str(iv.get("CrowdLevel", "")).lower()[:1]})
    return pd.DataFrame(rows)


def carparks(res: dict) -> pd.DataFrame:
    d = frame(res)
    if d.empty or "Location" not in d:
        return d
    ll = d["Location"].astype(str).str.split(" ", expand=True)
    d["lat"] = pd.to_numeric(ll[0], errors="coerce")
    d["lon"] = pd.to_numeric(ll[1] if ll.shape[1] > 1 else None, errors="coerce")
    return d


def ev_points(res: dict) -> pd.DataFrame:
    rows = []
    for v in res.get("rows") or []:
        for loc in (v.get("evLocationsData") or []) if isinstance(v, dict) else []:
            pts = loc.get("chargingPoints") or []
            rows.append({"Name": loc.get("name"), "Address": loc.get("address"),
                         "Points": len(pts),
                         "Available": sum(1 for p in pts if str(p.get("status")) == "1"),
                         "Operators": ", ".join(sorted({p.get("operator", "") for p in pts if p.get("operator")})),
                         "lat": loc.get("latitude"), "lon": loc.get("longitude")})
    raw = res.get("raw") or {}
    if not rows and isinstance(raw.get("value"), dict):
        return ev_points({"rows": [raw["value"]]})
    return pd.DataFrame(rows)
