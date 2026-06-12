"""Freight rate tools: FreightPulse API + Microsoft Graph email."""

from __future__ import annotations

import base64
import os
from pathlib import Path
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


# ═════════════════════════════════════════════════════════════════════════════
# MICROSOFT GRAPH — EMAIL
# ═════════════════════════════════════════════════════════════════════════════
# Required Azure AD app permissions (Application, with admin consent):
#   Mail.Read, Mail.ReadBasic, User.Read.All
# Required .env keys:
#   MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, MICROSOFT_APP_TENANT_ID,
#   GRAPH_USER_EMAIL  (UPN / email of the mailbox to read, e.g. you@company.com)


async def _get_graph_token() -> str:
    """Obtain a client-credentials bearer token for Microsoft Graph."""
    tenant_id = os.environ.get("MICROSOFT_APP_TENANT_ID", "")
    client_id = os.environ.get("MICROSOFT_APP_ID", "")
    client_secret = os.environ.get("MICROSOFT_APP_PASSWORD", "")
    if not all([tenant_id, client_id, client_secret]):
        return ""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
    if resp.status_code != 200:
        return ""
    return resp.json().get("access_token", "")


@tool
async def get_emails(query: Optional[str] = None, top: int = 5) -> str:
    """Fetch recent emails from the configured mailbox via Microsoft Graph.

    Args:
        query: Optional keyword to search in email subject/body (e.g. 'shipment', 'freight').
        top:   Number of emails to return (1–20, default 5).
    """
    user_email = os.environ.get("GRAPH_USER_EMAIL", "")
    if not user_email:
        return "GRAPH_USER_EMAIL is not configured in .env."

    token = await _get_graph_token()
    if not token:
        return (
            "Could not obtain a Microsoft Graph token. "
            "Check MICROSOFT_APP_ID / PASSWORD / TENANT_ID and that "
            "Mail.Read + Mail.ReadBasic application permissions have admin consent."
        )

    params: dict = {
        "$top": min(max(top, 1), 20),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments",
    }
    if query:
        params["$search"] = f'"{query}"'
        params.pop("$orderby", None)  # $search and $orderby cannot be combined

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )

    if resp.status_code == 401:
        return (
            "Graph API returned 401. Verify Mail.Read application permission "
            "has been granted admin consent in Azure AD."
        )
    if resp.status_code == 403:
        return (
            "Graph API returned 403. The app lacks permission to read this mailbox. "
            "Grant Mail.Read (Application) and Mail.ReadBasic (Application) in Azure AD."
        )
    if resp.status_code != 200:
        return f"Graph API error {resp.status_code}: {resp.text[:300]}"

    emails = resp.json().get("value", [])
    if not emails:
        return f"No emails found{' matching ' + repr(query) if query else ''}."

    header = f"Emails — {user_email}" + (f" | search: {query!r}" if query else "")
    lines = [header, "─" * 60]
    for e in emails:
        msg_id = e.get("id", "")
        subject = e.get("subject") or "(no subject)"
        sender = e.get("from", {}).get("emailAddress", {}).get("address", "unknown")
        received = (e.get("receivedDateTime") or "")[:10]
        preview = (e.get("bodyPreview") or "")[:120].replace("\r\n", " ").replace("\n", " ")
        unread = " [UNREAD]" if not e.get("isRead") else ""
        has_att = " [HAS ATTACHMENT]" if e.get("hasAttachments") else ""
        lines.append(f"  • [{received}]{unread}{has_att} {subject}")
        lines.append(f"    From: {sender}")
        lines.append(f"    ID: {msg_id}")
        if preview:
            lines.append(f"    {preview}…")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Attachment size threshold: Graph returns contentBytes inline only for < 3 MB.
# Larger attachments must be streamed via the /$value endpoint.
_SMALL_ATTACHMENT_LIMIT = 3 * 1024 * 1024  # 3 MB


@tool
async def download_email_attachments(message_id: str, save_dir: Optional[str] = None) -> str:
    """Download all file attachments from an Outlook email to a local folder.

    Handles both small attachments (< 3 MB, fetched inline as base64) and large
    attachments (>= 3 MB, streamed in chunks via the Graph /$value endpoint).

    Args:
        message_id: The Graph message ID from get_emails output (the 'ID:' line).
        save_dir:   Folder to save files into. Defaults to ./downloads/ beside server.py.
    """
    user_email = os.environ.get("GRAPH_USER_EMAIL", "")
    if not user_email:
        return "GRAPH_USER_EMAIL is not configured in .env."

    token = await _get_graph_token()
    if not token:
        return "Could not obtain a Microsoft Graph token."

    dest = Path(save_dir) if save_dir else Path(__file__).parent / "downloads"
    dest.mkdir(parents=True, exist_ok=True)

    base_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1 — list attachments (metadata only, no content yet)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/attachments",
            headers=headers,
            params={"$select": "id,name,contentType,size,isInline"},
            timeout=30,
        )

    if resp.status_code == 404:
        return f"Message not found — check the ID is correct: {message_id[:60]}…"
    if resp.status_code != 200:
        return f"Graph API error {resp.status_code}: {resp.text[:300]}"

    # Skip inline attachments (embedded images in the email body)
    all_attachments = resp.json().get("value", [])
    file_attachments = [a for a in all_attachments if not a.get("isInline")]

    if not file_attachments:
        return "This email has no file attachments (only inline images or none at all)."

    results: list[str] = []

    async with httpx.AsyncClient() as client:
        for att in file_attachments:
            att_id = att["id"]
            name = att.get("name") or "attachment"
            size = att.get("size") or 0
            # Sanitise filename to avoid path traversal or illegal chars
            safe_name = "".join(c if c.isalnum() or c in "._- ()" else "_" for c in name)
            out_path = dest / safe_name

            if size <= _SMALL_ATTACHMENT_LIMIT:
                # ── Small attachment: Graph returns contentBytes as base64 ──
                r = await client.get(
                    f"{base_url}/attachments/{att_id}",
                    headers=headers,
                    timeout=60,
                )
                if r.status_code != 200:
                    results.append(f"  FAILED  {name} ({size // 1024} KB) — HTTP {r.status_code}")
                    continue
                content_b64 = r.json().get("contentBytes", "")
                if not content_b64:
                    results.append(f"  FAILED  {name} — no content returned by Graph")
                    continue
                out_path.write_bytes(base64.b64decode(content_b64))
                results.append(f"  OK  {name} ({size // 1024} KB) → {out_path}")

            else:
                # ── Large attachment: stream raw bytes via /$value ──
                size_mb = size / (1024 * 1024)
                async with client.stream(
                    "GET",
                    f"{base_url}/attachments/{att_id}/$value",
                    headers=headers,
                    timeout=300,
                ) as r:
                    if r.status_code != 200:
                        results.append(f"  FAILED  {name} ({size_mb:.1f} MB) — HTTP {r.status_code}")
                        continue
                    with out_path.open("wb") as f:
                        async for chunk in r.aiter_bytes(chunk_size=65_536):
                            f.write(chunk)
                results.append(f"  OK  {name} ({size_mb:.1f} MB) → {out_path}")

    ok_count = sum(1 for r in results if r.startswith("  OK"))
    summary = f"Downloaded {ok_count}/{len(file_attachments)} attachment(s) to {dest}:"
    return summary + "\n" + "\n".join(results)

