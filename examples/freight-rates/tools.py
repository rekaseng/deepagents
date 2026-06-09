"""Freight rate tools: Excel negotiated-rate reader, FreightPulse API, GoComet API."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import httpx
import openpyxl
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


def _excel_path() -> str:
    return os.environ.get(
        "FREIGHT_EXCEL_PATH",
        r"C:\Users\reca\Downloads\Freight Summary - Submission to Exp & Imp (2).xlsx",
    )


# ── Excel data loader ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_records(path: str) -> list[dict]:
    """Parse the FCL V-V CIF worksheet into structured carrier-route dicts."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["FCL V-V CIF"]
    rows = list(ws.iter_rows(values_only=True))

    def _rate(v):
        return float(v) if isinstance(v, (int, float)) else None

    def _str(v):
        if v is None:
            return None
        s = str(v).replace("\n", " ").strip()
        return None if s in ("", "-", "None") else s

    records = []
    for row in rows[3:]:  # rows 0-2 are header rows
        pol = _str(row[7])
        pod = _str(row[8])
        if not pol or not pod:
            continue
        records.append({
            "pol": pol,
            "pod": pod,
            "carrier": _str(row[9]),
            "final_nominated": _str(row[10]),
            "rate_20ft_current": _rate(row[11]),
            "rate_40ft_current": _rate(row[12]),
            "rate_20ft_new": _rate(row[13]),
            "rate_40ft_new": _rate(row[14]),
            "freight_condition": _str(row[15]),
            "transit_days": _rate(row[16]),
            "frequency_weekly": _str(row[17]),
            "transshipment_port": _str(row[18]),
            "service_provider": _str(row[19]),
            "cy_closed_day": _str(row[20]),
            "etd_day": _str(row[21]),
            "dem_origin": _rate(row[24]),
            "det_origin": _rate(row[25]),
            "dem_det_combined_origin": _rate(row[26]),
            "dem_pod": _rate(row[27]),
            "det_pod": _rate(row[28]),
            "dem_det_combined_pod": _rate(row[29]),
            "remarks": _str(row[30]),
            "ttap_comment": _str(row[31]),
            "importer_comment": _str(row[32]),
            "exporter_comment": _str(row[33]),
        })
    return records


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
def list_routes() -> str:
    """List all unique trade lanes (origin → destination) in the negotiated freight rate Excel."""
    records = _load_records(_excel_path())
    routes: dict[tuple, list[str]] = {}
    for r in records:
        key = (r["pol"], r["pod"])
        routes.setdefault(key, [])
        if r["carrier"]:
            routes[key].append(r["carrier"])

    lines = ["Negotiated Trade Lanes (FCL V-V CIF)\n" + "─" * 55]
    for (pol, pod), carriers in sorted(routes.items()):
        unique = sorted(set(carriers))
        lines.append(f"  {pol}  →  {pod}  ({len(unique)} carrier(s))")
    return "\n".join(lines)


@tool
def query_negotiated_rates(
    origin: str,
    destination: str,
    carrier: Optional[str] = None,
) -> str:
    """Query negotiated FCL all-in freight rates from the internal Excel rate sheet.

    Args:
        origin: Port of Loading — partial name OK (e.g. 'Dalian', 'Shanghai', 'Laemchabang')
        destination: Port of Discharge — partial name OK (e.g. 'Bangkok', 'Jakarta', 'Klang')
        carrier: Optional carrier name filter (partial match)
    """
    records = _load_records(_excel_path())
    ol, dl = origin.lower(), destination.lower()

    matches = [
        r for r in records
        if ol in r["pol"].lower() and dl in r["pod"].lower()
        and (carrier is None or carrier.lower() in (r["carrier"] or "").lower())
    ]

    if not matches:
        return f"No negotiated rates found for {origin} → {destination}."

    lines = [f"Negotiated Rates — {origin} → {destination}", "─" * 60]
    for r in matches:
        tag = "  ✓ NOMINATED" if r["final_nominated"] else ""
        lines.append(f"\n  Carrier: {r['carrier'] or 'N/A'}{tag}")

        cur20, cur40 = r["rate_20ft_current"], r["rate_40ft_current"]
        new20, new40 = r["rate_20ft_new"], r["rate_40ft_new"]
        if cur20 or cur40:
            lines.append(f"    Current — 20ft: ${cur20 or 'N/A'}  |  40ft: ${cur40 or 'N/A'}")
        if new20 or new40:
            lines.append(f"    New     — 20ft: ${new20 or 'N/A'}  |  40ft: ${new40 or 'N/A'}")

        td = int(r["transit_days"]) if r["transit_days"] else "?"
        via = f"via {r['transshipment_port']}" if r["transshipment_port"] else "direct"
        lines.append(f"    Transit: {td} days ({via}) | Freq: {r['frequency_weekly'] or '?'}x/week")

        if r["freight_condition"]:
            lines.append(f"    Condition: {r['freight_condition']}")

        ft_parts = []
        if r["dem_pod"]:
            ft_parts.append(f"DEM {int(r['dem_pod'])}d")
        if r["det_pod"]:
            ft_parts.append(f"DET {int(r['det_pod'])}d")
        if r["dem_det_combined_pod"]:
            ft_parts.append(f"DEM+DET {int(r['dem_det_combined_pod'])}d")
        if ft_parts:
            lines.append(f"    Free time POD: {' | '.join(ft_parts)}")

        if r["remarks"]:
            lines.append(f"    Remarks: {r['remarks'][:150]}")

    return "\n".join(lines)


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
async def compare_rates(origin: str, destination: str) -> str:
    """Compare internal negotiated rates (Excel) against live FreightPulse market rates for a trade lane.

    Args:
        origin: Port of Loading name (e.g. 'Dalian', 'Shanghai', 'Laemchabang')
        destination: Port of Discharge name (e.g. 'Bangkok', 'Laemchabang', 'Jakarta')
    """
    records = _load_records(_excel_path())
    ol, dl = origin.lower(), destination.lower()
    matches = [
        r for r in records
        if ol in r["pol"].lower() and dl in r["pod"].lower()
    ]

    # Pull live market data
    origin_code = _to_unlocode(origin)
    dest_code = _to_unlocode(destination)
    market_data = await _fp_get("freight-rates", {"mode": "ocean", "origin": origin_code, "destination": dest_code})
    ocean = (market_data.get("ocean", []) if isinstance(market_data, dict) else [])
    market_40ft = float(ocean[0]["rate_40ft"]) if ocean and ocean[0].get("rate_40ft") else None
    market_trend = ocean[0].get("trend") if ocean else None

    lines = [
        f"Rate Comparison — {origin} → {destination}",
        "═" * 60,
    ]

    if market_40ft:
        lines.append(f"\n  FreightPulse Market (40ft): ${market_40ft:,.0f}  |  Trend: {market_trend or 'N/A'}")
    elif isinstance(market_data, str):
        lines.append(f"\n  FreightPulse: {market_data}")

    if matches:
        lines.append("\n  Negotiated Rates:")
        for r in matches:
            rate40 = r["rate_40ft_new"] or r["rate_40ft_current"]
            rate20 = r["rate_20ft_new"] or r["rate_20ft_current"]
            nominated = " ✓" if r["final_nominated"] else ""
            savings = ""
            if rate40 and market_40ft:
                diff = market_40ft - rate40
                pct = (diff / market_40ft) * 100
                savings = f"  ({'SAVING' if diff > 0 else 'ABOVE MARKET'} {abs(pct):.1f}%)"
            td = int(r["transit_days"]) if r["transit_days"] else "?"
            via = f"via {r['transshipment_port']}" if r["transshipment_port"] else "direct"
            lines.append(
                f"    • {r['carrier'] or 'N/A'}{nominated}: "
                f"20ft ${rate20 or 'N/A'} | 40ft ${rate40 or 'N/A'}{savings} | "
                f"{td}d {via}"
            )
    else:
        lines.append(f"\n  No negotiated rates found for {origin} → {destination} in Excel.")

    return "\n".join(lines)


@tool
def get_nominated_carriers() -> str:
    """List all routes with a Final Nominated Carrier from the Excel rate sheet."""
    records = _load_records(_excel_path())
    nominated = [r for r in records if r["final_nominated"]]
    if not nominated:
        return "No nominated carriers found in the rate sheet."

    lines = ["Final Nominated Carriers — All Lanes", "─" * 55]
    seen = set()
    for r in nominated:
        key = (r["pol"], r["pod"], r["final_nominated"])
        if key in seen:
            continue
        seen.add(key)
        rate = r["rate_40ft_new"] or r["rate_40ft_current"]
        td = int(r["transit_days"]) if r["transit_days"] else "?"
        lines.append(
            f"  • {r['pol']} → {r['pod']}: {r['final_nominated']}"
            + (f"  |  40ft ${rate}" if rate else "")
            + f"  |  {td}d"
        )
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
