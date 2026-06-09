"""Freight rate tools: FreightPulse API, GoComet API."""

from __future__ import annotations

import os
from typing import Optional

import httpx
from langchain_core.tools import tool

# ── Port name → UNLOCODE lookup ───────────────────────────────────────────────

_PORT_CODES: dict[str, str] = {
    "dalian": "CNDLC",
    "laemchabang": "THLCH",
    "bangkok": "THBKK",
    "shanghai": "CNSHA",
    "haiphong": "VNHPH",
    "ho chi minh": "VNSGN",
    "hochiminh": "VNSGN",
    "hochiminhcity": "VNSGN",
    "jakarta": "IDJKT",
    "port klang": "MYPKG",
    "klang": "MYPKG",
    "chennai": "INMAA",
    "mundra": "INMUN",
    "nhava sheva": "INNSA",
    "pipavav": "INPAV",
    "nansha": "CNNSA",
    "xingang": "CNTXG",
    "tianjin": "CNTXG",
    "manila": "PHMNL",
    "batangas": "PHBTG",
    "durban": "ZADUR",
    "taipei": "TWTPE",
    "taoyuan": "TWTYQ",
    "leixoes": "PTLEI",
    "kattupalli": "INKTP",
    "icd khatuwas": "INKHL",
    "icd patli": "INPTL",
}


def _to_unlocode(port_name: str) -> str:
    """Convert a human-readable port name to its UNLOCODE (best-effort)."""
    key = port_name.lower().strip()
    # Strip country/type suffixes like " (CN) HC", " DG"
    for sep in ["(", " dg", " hc", " gp"]:
        key = key.split(sep)[0].strip()
    if key in _PORT_CODES:
        return _PORT_CODES[key]
    # Partial match
    for k, v in _PORT_CODES.items():
        if k in key:
            return v
    return key.upper().replace(" ", "")


# ── FreightPulse helpers ──────────────────────────────────────────────────────

_FP_BASE = "https://freightpulsehq.com/api/v1"


async def _fp_get(endpoint: str, params: dict | None = None) -> dict | str:
    api_key = os.environ.get("FREIGHTPULSE_API_KEY", "")
    if not api_key:
        return "FREIGHTPULSE_API_KEY not configured."
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_FP_BASE}/{endpoint}",
            headers={"X-API-Key": api_key},
            params=params or {},
            timeout=30,
        )
    if resp.status_code == 401:
        return "FreightPulse: invalid API key."
    if resp.status_code != 200:
        return f"FreightPulse error {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# ── GoComet helpers ───────────────────────────────────────────────────────────

_GC_BASE = "https://app.gocomet.com/api"


async def _gc_get(endpoint: str, params: dict | None = None) -> dict | str:
    api_key = os.environ.get("GOCOMET_API_KEY", "")
    org_id = os.environ.get("GOCOMET_ORG_ID", "")
    if not api_key:
        return "GOCOMET_API_KEY not set. Add it to .env (get it from GoComet → Settings → API)."
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Org-Id": org_id,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_GC_BASE}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=30,
        )
    if resp.status_code == 401:
        return "GoComet: invalid credentials."
    if resp.status_code != 200:
        return f"GoComet error {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS
# ═════════════════════════════════════════════════════════════════════════════


@tool
async def get_market_rates(origin: str, destination: str) -> str:
    """Fetch live ocean freight market rates from FreightPulse for a trade lane.

    Args:
        origin: Port of Loading — name or UNLOCODE (e.g. 'Dalian', 'CNDLC', 'Shanghai')
        destination: Port of Discharge — name or UNLOCODE (e.g. 'Laemchabang', 'THLCH', 'Bangkok')
    """
    origin_code = _to_unlocode(origin)
    dest_code = _to_unlocode(destination)

    data = await _fp_get("freight-rates", {"mode": "ocean", "origin": origin_code, "destination": dest_code})
    if isinstance(data, str):
        return data

    ocean = data.get("ocean", [])
    if not ocean:
        return f"No FreightPulse market rates found for {origin} ({origin_code}) → {destination} ({dest_code})."

    lines = [f"FreightPulse Live Market Rates — {origin} → {destination}", "─" * 60]
    for r in ocean:
        route = r.get("route", f"{origin} → {destination}")
        rate40 = r.get("rate_40ft", "N/A")
        transit = r.get("transit_days", "?")
        trend = r.get("trend", "N/A")
        lines.append(f"  • {route}  |  40ft: ${rate40}  |  {transit} days  |  Trend: {trend}")

    ts = data.get("timestamp", "")
    if ts:
        lines.append(f"\n  Data as of: {ts}")
    return "\n".join(lines)


@tool
async def get_port_congestion(port: Optional[str] = None) -> str:
    """Get real-time port congestion levels from FreightPulse.

    Args:
        port: Optional port name or UNLOCODE. If omitted, returns all monitored ports.
    """
    params = {}
    if port:
        params["port"] = _to_unlocode(port)

    data = await _fp_get("port-congestion", params)
    if isinstance(data, str):
        return data

    ports_data = data.get("ports", data) if isinstance(data, dict) else data
    if not ports_data:
        return "No port congestion data available."

    lines = ["Port Congestion — FreightPulse", "─" * 45]
    for p in (ports_data if isinstance(ports_data, list) else [ports_data]):
        name = p.get("port") or p.get("name", "Unknown")
        level = p.get("congestion_level") or p.get("level", "N/A")
        wait = p.get("waiting_time") or p.get("wait_days", "N/A")
        vessels = p.get("vessels_waiting", "")
        line = f"  • {name}: {level} congestion | Wait: {wait}"
        if vessels:
            line += f" | Vessels: {vessels}"
        lines.append(line)
    return "\n".join(lines)


@tool
async def get_supply_chain_disruptions() -> str:
    """Get active supply chain disruption alerts from FreightPulse
    (port closures, route diversions, labour strikes, weather events, geopolitical risks)."""
    data = await _fp_get("disruptions")
    if isinstance(data, str):
        return data

    disruptions = data.get("disruptions", data) if isinstance(data, dict) else data
    if not disruptions:
        return "No active supply chain disruptions reported by FreightPulse."

    lines = ["Active Supply Chain Disruptions — FreightPulse", "─" * 50]
    for d in (disruptions if isinstance(disruptions, list) else [disruptions]):
        title = d.get("title") or d.get("event", "Unknown event")
        location = d.get("location") or d.get("region") or d.get("port", "")
        severity = d.get("severity") or d.get("impact", "")
        updated = d.get("updated_at") or d.get("date", "")
        line = f"  [{severity.upper() if severity else 'INFO'}] {title}"
        if location:
            line += f" — {location}"
        if updated:
            line += f" (updated: {updated})"
        lines.append(line)
    return "\n".join(lines)


@tool
async def track_container(container_number: str) -> str:
    """Track a container's live status and voyage milestones using GoComet.

    Args:
        container_number: Container number (e.g. TCKU1234567, MSCU9876543)
    """
    data = await _gc_get("container-tracking/track", {"container_number": container_number})
    if isinstance(data, str):
        return data

    # Normalise across potential GoComet response shapes
    tracking = data.get("data") or data.get("tracking") or data

    lines = [f"Container Tracking — {container_number}", "─" * 50]

    status = tracking.get("status") or tracking.get("current_status", "Unknown")
    vessel = tracking.get("vessel") or tracking.get("vessel_name", "")
    voyage = tracking.get("voyage") or tracking.get("voyage_number", "")
    carrier = tracking.get("carrier") or tracking.get("scac", "")
    pol = tracking.get("pol") or tracking.get("origin", "")
    pod = tracking.get("pod") or tracking.get("destination", "")
    eta = tracking.get("eta") or tracking.get("estimated_arrival", "")
    atd = tracking.get("atd") or tracking.get("actual_departure", "")

    lines.append(f"  Status   : {status}")
    if carrier:
        lines.append(f"  Carrier  : {carrier}")
    if vessel:
        lines.append(f"  Vessel   : {vessel}" + (f" / {voyage}" if voyage else ""))
    if pol:
        lines.append(f"  Origin   : {pol}")
    if pod:
        lines.append(f"  Dest     : {pod}")
    if atd:
        lines.append(f"  Departed : {atd}")
    if eta:
        lines.append(f"  ETA      : {eta}")

    events = tracking.get("events") or tracking.get("milestones") or []
    if events:
        lines.append("\n  Events:")
        for ev in events[-6:]:  # last 6 events
            dt = ev.get("date") or ev.get("timestamp", "")
            desc = ev.get("description") or ev.get("event", "")
            loc = ev.get("location") or ev.get("port", "")
            lines.append(f"    {dt}  {desc}" + (f" — {loc}" if loc else ""))

    return "\n".join(lines)


@tool
async def get_gocomet_rate_benchmarks(origin: str, destination: str) -> str:
    """Fetch freight rate benchmarks and market comparisons from GoComet for a trade lane.

    Args:
        origin: Port of Loading name or code (e.g. 'Shanghai', 'CNSHA')
        destination: Port of Discharge name or code (e.g. 'Bangkok', 'THLCH')
    """
    origin_code = _to_unlocode(origin)
    dest_code = _to_unlocode(destination)

    data = await _gc_get(
        "rate-benchmarks",
        {"origin": origin_code, "destination": dest_code, "container_type": "40HC"},
    )
    if isinstance(data, str):
        return data

    benchmarks = data.get("data") or data.get("benchmarks") or data
    lines = [f"GoComet Rate Benchmarks — {origin} → {destination}", "─" * 55]

    if isinstance(benchmarks, dict):
        market_avg = benchmarks.get("market_average") or benchmarks.get("avg_rate")
        market_low = benchmarks.get("market_low") or benchmarks.get("min_rate")
        market_high = benchmarks.get("market_high") or benchmarks.get("max_rate")
        trend = benchmarks.get("trend") or benchmarks.get("rate_trend")
        if market_avg:
            lines.append(f"  Market Average : ${market_avg}")
        if market_low and market_high:
            lines.append(f"  Range          : ${market_low} — ${market_high}")
        if trend:
            lines.append(f"  Trend          : {trend}")
    elif isinstance(benchmarks, list):
        for b in benchmarks:
            carrier = b.get("carrier") or b.get("scac", "")
            rate = b.get("rate") or b.get("all_in_rate", "")
            transit = b.get("transit_days", "")
            lines.append(f"  • {carrier}: ${rate}" + (f" | {transit}d" if transit else ""))
    else:
        lines.append(f"  Raw response: {benchmarks}")

    return "\n".join(lines)
