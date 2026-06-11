"""Freight rate tools: FreightPulse API."""

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


def _fp_inner(resp_json: dict) -> dict | str:
    """Unwrap the double-nested FreightPulse envelope: response.data.data"""
    if not resp_json.get("success"):
        return f"FreightPulse returned error: {resp_json}"
    return resp_json.get("data", {}).get("data", {})



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
    raw = await _fp_get("freight-rates", {"mode": "ocean"})
    if isinstance(raw, str):
        return raw

    inner = _fp_inner(raw)
    if isinstance(inner, str):
        return inner

    container_rates: list = inner.get("ocean", {}).get("container_rates", [])
    if not container_rates:
        return "No FreightPulse market rates available."

    # Client-side filtering: the API ignores origin/dest params and returns fixed routes.
    # Match by checking if origin or destination names appear in the route string.
    origin_lc = origin.lower()
    dest_lc = destination.lower()
    matched = [
        r for r in container_rates
        if origin_lc in r.get("route", "").lower() or dest_lc in r.get("route", "").lower()
    ]
    rates_to_show = matched if matched else container_rates
    note = "" if matched else f"\n  (No exact match for {origin} → {destination}; showing all available routes)"

    lines = [f"FreightPulse Live Market Rates — {origin} → {destination}", "─" * 60]
    for r in rates_to_show:
        route = r.get("route", "Unknown route")
        rate20 = r.get("rate_20ft")
        rate40 = r.get("rate_40ft", "N/A")
        rate40hc = r.get("rate_40hc")
        transit = r.get("transit_days", "?")
        trend = r.get("trend", "N/A")
        change = r.get("change_week")
        avail = r.get("carrier_availability", "")
        rate_str = f"20ft: ${rate20}  " if rate20 else ""
        rate_str += f"40ft: ${rate40}"
        if rate40hc:
            rate_str += f"  40HC: ${rate40hc}"
        change_str = f"  ({change:+.1f}% wk)" if change is not None else ""
        avail_str = f"  | Availability: {avail}" if avail else ""
        lines.append(f"  • {route}")
        lines.append(f"    {rate_str}  |  {transit} days  |  Trend: {trend}{change_str}{avail_str}")

    ts = raw.get("data", {}).get("timestamp", "")
    if ts:
        lines.append(f"\n  Data as of: {ts}")
    if note:
        lines.append(note)
    return "\n".join(lines)


@tool
async def get_port_congestion(port: Optional[str] = None) -> str:
    """Get real-time port congestion levels from FreightPulse.

    Args:
        port: Optional port name or UNLOCODE. If omitted, returns all monitored ports.
    """
    raw = await _fp_get("port-congestion")
    if isinstance(raw, str):
        return raw

    inner = _fp_inner(raw)
    if isinstance(inner, str):
        return inner

    all_ports: list = inner.get("ports", [])
    if not all_ports:
        return "No port congestion data available."

    if port:
        port_lc = port.lower()
        port_code = _to_unlocode(port).upper()
        filtered = [
            p for p in all_ports
            if port_lc in p.get("port", "").lower()
            or p.get("port_code", "").upper() == port_code
        ]
        ports_to_show = filtered if filtered else all_ports
        header = f"Port Congestion — {port} — FreightPulse"
        if not filtered:
            header += f"\n  (No exact match for '{port}'; showing all ports)"
    else:
        ports_to_show = all_ports
        header = f"Port Congestion ({len(all_ports)} ports) — FreightPulse"

    lines = [header, "─" * 55]
    for p in ports_to_show:
        name = p.get("port", "Unknown")
        code = p.get("port_code", "")
        level = p.get("congestion_level", "N/A")
        wait_h = p.get("avg_wait_time_hours")
        at_anchor = p.get("vessels_at_anchor")
        at_berth = p.get("vessels_at_berth")
        trend = p.get("trend", "")
        wait_str = f"{wait_h}h wait" if wait_h is not None else ""
        vessel_str = ""
        if at_anchor is not None and at_berth is not None:
            vessel_str = f" | {at_anchor} at anchor, {at_berth} at berth"
        trend_str = f" | {trend}" if trend else ""
        lines.append(f"  • {name} ({code}): {level}{(' | ' + wait_str) if wait_str else ''}{vessel_str}{trend_str}")
    return "\n".join(lines)


@tool
async def get_supply_chain_disruptions() -> str:
    """Get active supply chain disruption alerts from FreightPulse
    (port closures, route diversions, labour strikes, weather events, geopolitical risks)."""
    raw = await _fp_get("disruptions")
    if isinstance(raw, str):
        return raw

    inner = _fp_inner(raw)
    if isinstance(inner, str):
        return inner

    alerts: list = inner.get("alerts", [])
    if not alerts:
        return "No active supply chain disruptions reported by FreightPulse."

    lines = [f"Active Supply Chain Disruptions ({len(alerts)}) — FreightPulse", "─" * 55]
    for d in alerts:
        severity = d.get("severity", "info").upper()
        title = d.get("title", "Unknown event")
        status = d.get("status", "")
        regions = ", ".join(d.get("affected_regions", []))
        impact = d.get("impact", {})
        delay = impact.get("transit_delay_days")
        rate_inc = impact.get("rate_increase_percent")
        lines.append(f"  [{severity}] {title}  ({status})")
        if regions:
            lines.append(f"    Regions: {regions}")
        impact_parts = []
        if delay:
            impact_parts.append(f"+{delay}d transit")
        if rate_inc:
            impact_parts.append(f"+{rate_inc}% rates")
        if impact_parts:
            lines.append(f"    Impact: {', '.join(impact_parts)}")

    forecast = inner.get("risk_forecast", {})
    if forecast:
        outlook = forecast.get("next_7_days", "")
        factors = forecast.get("factors", [])
        lines.append(f"\n  7-day risk outlook: {outlook}")
        for f in factors:
            lines.append(f"    • {f}")
    return "\n".join(lines)


