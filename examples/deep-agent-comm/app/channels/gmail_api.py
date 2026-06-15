"""L0 — Gmail API channel (OAuth), Python port of src/channels/gmail-api.ts.
Reuses the SAME secrets files as the TS side (secrets/google_oauth_client.json,
secrets/gmail.token.json) — authorize once with either implementation.

Draft-only is enforced by absence of any send capability."""

import base64
import mimetypes
import re
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..config import (
    ATTACHMENT_MAX_BYTES,
    CLIENT_SECRET_PATH,
    GMAIL_USER,
    SCRATCH_DIR,
    TOKEN_PATH,
)

ALLOWED_SHEET_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
    "application/octet-stream",  # some clients mislabel xlsx; filename check below
}

import json


@dataclass
class ChannelAttachment:
    filename: str
    mimeType: str
    sizeBytes: int
    localPath: Optional[str] = None


@dataclass
class ChannelMessage:
    id: str
    channel: str
    threadId: str
    from_: dict          # {name, address}
    to: list[str]
    subject: str
    body: str
    bodyHtml: Optional[str] = None
    attachments: list[ChannelAttachment] = field(default_factory=list)
    receivedAt: int = 0
    references: list[str] = field(default_factory=list)


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)


class GmailApiChannel:
    name = "gmail"

    def __init__(self) -> None:
        self.user = GMAIL_USER
        self._service: Any = None

    @property
    def self_address(self) -> str:
        return self.user.lower()

    def is_configured(self) -> bool:
        return CLIENT_SECRET_PATH.exists() and TOKEN_PATH.exists()

    def _gmail(self) -> Any:
        if self._service is not None:
            return self._service
        if not self.is_configured():
            raise RuntimeError("Gmail API not authorized. Run the OAuth bootstrap (npx tsx src/channels/gmail-oauth.ts).")
        secret = json.loads(CLIENT_SECRET_PATH.read_text(encoding="utf-8"))
        cfg = secret.get("installed") or secret.get("web")
        token = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        creds = Credentials(
            token=None,
            refresh_token=token["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
        )
        creds.refresh(Request())
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _header(headers: list[dict] | None, name: str) -> str:
        for h in headers or []:
            if (h.get("name") or "").lower() == name.lower():
                return h.get("value") or ""
        return ""

    @staticmethod
    def _parse_from(raw: str) -> dict:
        m = re.match(r'^\s*"?([^"<]*)"?\s*<([^>]+)>\s*$', raw)
        if m:
            return {"name": m.group(1).strip(), "address": m.group(2).strip().lower()}
        return {"name": "", "address": raw.strip().lower()}

    def _walk(self, part: dict | None, acc: dict) -> None:
        if not part:
            return
        mime = part.get("mimeType") or ""
        body = part.get("body") or {}
        if part.get("filename") and body.get("attachmentId"):
            acc["atts"].append(part)
        elif mime == "text/plain" and body.get("data"):
            acc["text"] += _b64url_decode(body["data"]).decode("utf-8", errors="replace")
        elif mime == "text/html" and body.get("data"):
            acc["html"] += _b64url_decode(body["data"]).decode("utf-8", errors="replace")
        for child in part.get("parts") or []:
            self._walk(child, acc)

    def _fetch_message(self, msg_id: str, download: bool) -> ChannelMessage:
        gmail = self._gmail()
        msg = gmail.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = (msg.get("payload") or {}).get("headers")
        acc = {"text": "", "html": "", "atts": []}
        self._walk(msg.get("payload"), acc)

        attachments: list[ChannelAttachment] = []
        for part in acc["atts"]:
            filename = part.get("filename") or "unnamed"
            mime_type = part.get("mimeType") or "application/octet-stream"
            size = int((part.get("body") or {}).get("size") or 0)
            meta = ChannelAttachment(filename=filename, mimeType=mime_type, sizeBytes=size)
            is_sheet = mime_type in ALLOWED_SHEET_TYPES or re.search(r"\.(xlsx|csv)$", filename, re.I)
            att_id = (part.get("body") or {}).get("attachmentId")
            if download and is_sheet and size <= ATTACHMENT_MAX_BYTES and att_id:
                att = gmail.users().messages().attachments().get(userId="me", messageId=msg_id, id=att_id).execute()
                out_dir = SCRATCH_DIR / "inbound" / msg_id
                out_dir.mkdir(parents=True, exist_ok=True)
                local = out_dir / _safe_name(filename)
                local.write_bytes(_b64url_decode(att.get("data") or ""))
                meta.localPath = str(local)
            attachments.append(meta)

        refs = self._header(headers, "References")
        return ChannelMessage(
            id=msg.get("id") or msg_id,
            channel="gmail",
            threadId=msg.get("threadId") or msg_id,
            from_=self._parse_from(self._header(headers, "From")),
            to=[s.strip() for s in self._header(headers, "To").split(",") if s.strip()],
            subject=self._header(headers, "Subject"),
            body=(acc["text"] or msg.get("snippet") or "").strip(),
            bodyHtml=acc["html"] or None,
            attachments=attachments,
            receivedAt=int(msg.get("internalDate") or time.time() * 1000),
            references=[r for r in refs.split() if r] if refs else [],
        )

    def _preview_message(self, msg_id: str) -> ChannelMessage:
        msg = self._gmail().users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        headers = (msg.get("payload") or {}).get("headers")
        atts: list[str] = []

        def collect(p: dict | None) -> None:
            if not p:
                return
            if p.get("filename"):
                atts.append(p["filename"])
            for c in p.get("parts") or []:
                collect(c)

        collect(msg.get("payload"))
        return ChannelMessage(
            id=msg.get("id") or msg_id,
            channel="gmail",
            threadId=msg.get("threadId") or msg_id,
            from_=self._parse_from(self._header(headers, "From")),
            to=[s.strip() for s in self._header(headers, "To").split(",") if s.strip()],
            subject=self._header(headers, "Subject"),
            body=(msg.get("snippet") or "").strip(),
            attachments=[ChannelAttachment(filename=f, mimeType="", sizeBytes=0) for f in atts if f],
            receivedAt=int(msg.get("internalDate") or time.time() * 1000),
        )

    # ── 1. READ / QUERY ────────────────────────────────────────────────

    def fetch_unread(self, limit: int = 20) -> list[ChannelMessage]:
        res = self._gmail().users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=limit
        ).execute()
        ids = [m["id"] for m in res.get("messages") or [] if m.get("id")]
        return [self._fetch_message(i, download=True) for i in ids]

    def search(self, query: str, limit: int = 20) -> list[ChannelMessage]:
        res = self._gmail().users().messages().list(userId="me", q=query, maxResults=limit).execute()
        ids = [m["id"] for m in res.get("messages") or [] if m.get("id")]
        out = [self._preview_message(i) for i in ids]
        return sorted(out, key=lambda m: m.receivedAt, reverse=True)

    def get_message(self, message_id: str, download: bool = False) -> Optional[ChannelMessage]:
        try:
            return self._fetch_message(message_id, download)
        except Exception:
            return None

    def get_thread(self, message_id: str) -> list[ChannelMessage]:
        meta = self._gmail().users().messages().get(
            userId="me", id=message_id, format="metadata", metadataHeaders=[]
        ).execute()
        thread_id = meta.get("threadId")
        if not thread_id:
            return []
        thread = self._gmail().users().threads().get(userId="me", id=thread_id, format="full").execute()
        out = [self._fetch_message(m["id"], False) for m in thread.get("messages") or [] if m.get("id")]
        return sorted(out, key=lambda m: m.receivedAt)

    # ── 2. WRITE (DRAFTS ONLY) ─────────────────────────────────────────

    def _build_raw(self, reply: dict, extra_headers: dict | None = None) -> str:
        mail = EmailMessage()
        mail["From"] = f"Deep Agent (assistant) <{self.user}>"
        mail["To"] = reply["to"]
        if reply.get("cc"):
            mail["Cc"] = ", ".join(reply["cc"])
        if reply.get("bcc"):
            mail["Bcc"] = ", ".join(reply["bcc"])
        mail["Subject"] = reply["subject"]
        for k, v in (extra_headers or {}).items():
            mail[k] = v
        mail.set_content(reply["body"])
        for p in reply.get("attachmentPaths") or []:
            path = Path(p)
            ctype, _ = mimetypes.guess_type(path.name)
            maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
            mail.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
        return base64.urlsafe_b64encode(mail.as_bytes()).decode()

    def create_draft(self, reply: dict) -> None:
        thread_id = None
        extra: dict[str, str] = {}
        if reply.get("inReplyTo"):
            try:
                orig = self._gmail().users().messages().get(
                    userId="me", id=reply["inReplyTo"], format="metadata",
                    metadataHeaders=["Message-ID", "References"],
                ).execute()
                thread_id = orig.get("threadId")
                headers = (orig.get("payload") or {}).get("headers")
                rfc_id = self._header(headers, "Message-ID")
                refs = self._header(headers, "References")
                if rfc_id:
                    extra["In-Reply-To"] = rfc_id
                    extra["References"] = " ".join(x for x in [refs, rfc_id] if x)
            except Exception:
                pass  # original not found — non-threaded draft

        raw = self._build_raw(reply, extra or None)
        body = {"message": {"raw": raw}}
        if thread_id:
            body["message"]["threadId"] = thread_id
        self._gmail().users().drafts().create(userId="me", body=body).execute()

    def create_forward_draft(self, message_id: str, to: str, note: str) -> None:
        orig = self.get_message(message_id, download=True)
        if not orig:
            raise RuntimeError(f"Message not found: {message_id}")
        quoted = (
            (f"{note}\n\n" if note else "")
            + "---------- Forwarded message ----------\n"
            + f"From: {orig.from_['name']} <{orig.from_['address']}>\n"
            + f"Date: {time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(orig.receivedAt / 1000))}Z\n"
            + f"Subject: {orig.subject}\n\n{orig.body}"
        )
        self.create_draft({
            "to": to,
            "subject": f"Fwd: {orig.subject}",
            "body": quoted,
            "attachmentPaths": [a.localPath for a in orig.attachments if a.localPath],
        })

    def list_drafts(self, limit: int = 20) -> list[dict]:
        res = self._gmail().users().drafts().list(userId="me", maxResults=limit).execute()
        out = []
        for d in res.get("drafts") or []:
            if not d.get("id") or not (d.get("message") or {}).get("id"):
                continue
            meta = self._gmail().users().messages().get(
                userId="me", id=d["message"]["id"], format="metadata",
                metadataHeaders=["To", "Subject", "Date"],
            ).execute()
            headers = (meta.get("payload") or {}).get("headers")
            out.append({
                "id": d["id"],
                "subject": self._header(headers, "Subject") or "(no subject)",
                "to": [s.strip() for s in self._header(headers, "To").split(",") if s.strip()],
                "date": self._header(headers, "Date"),
            })
        return out

    def delete_draft(self, draft_id: str) -> None:
        self._gmail().users().drafts().delete(userId="me", id=draft_id).execute()

    def update_draft(self, draft_id: str, reply: dict) -> None:
        raw = self._build_raw(reply)
        self._gmail().users().drafts().update(
            userId="me", id=draft_id, body={"message": {"raw": raw}}
        ).execute()

    # ── 3. ORGANIZE ────────────────────────────────────────────────────

    def _modify(self, message_id: str, add: list[str], remove: list[str]) -> None:
        self._gmail().users().messages().modify(
            userId="me", id=message_id,
            body={"addLabelIds": add, "removeLabelIds": remove},
        ).execute()

    def mark_read(self, message_id: str) -> None: self._modify(message_id, [], ["UNREAD"])
    def mark_unread(self, message_id: str) -> None: self._modify(message_id, ["UNREAD"], [])
    def star(self, message_id: str) -> None: self._modify(message_id, ["STARRED"], [])
    def unstar(self, message_id: str) -> None: self._modify(message_id, [], ["STARRED"])
    def archive(self, message_id: str) -> None: self._modify(message_id, [], ["INBOX"])
    def mark_important(self, message_id: str) -> None: self._modify(message_id, ["IMPORTANT"], [])
    def unmark_important(self, message_id: str) -> None: self._modify(message_id, [], ["IMPORTANT"])

    def trash(self, message_id: str) -> None:
        self._gmail().users().messages().trash(userId="me", id=message_id).execute()

    def restore(self, message_id: str) -> None:
        self._gmail().users().messages().untrash(userId="me", id=message_id).execute()

    # ── Attachments (any type) ─────────────────────────────────────────

    def get_attachment(self, message_id: str, filename: str) -> str:
        gmail = self._gmail()
        msg = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
        acc = {"text": "", "html": "", "atts": []}
        self._walk(msg.get("payload"), acc)
        part = next((p for p in acc["atts"] if (p.get("filename") or "") == filename), None) \
            or next((p for p in acc["atts"] if filename in (p.get("filename") or "")), None)
        att_id = ((part or {}).get("body") or {}).get("attachmentId")
        if not att_id:
            raise RuntimeError(f'Attachment "{filename}" not found on message')
        if int((part.get("body") or {}).get("size") or 0) > ATTACHMENT_MAX_BYTES:
            raise RuntimeError("Attachment exceeds size cap")
        att = gmail.users().messages().attachments().get(userId="me", messageId=message_id, id=att_id).execute()
        out_dir = SCRATCH_DIR / "inbound" / message_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / _safe_name(part.get("filename") or "attachment")
        out_path.write_bytes(_b64url_decode(att.get("data") or ""))
        return str(out_path)

    # ── Labels ─────────────────────────────────────────────────────────

    def list_labels(self) -> list[dict]:
        res = self._gmail().users().labels().list(userId="me").execute()
        return [{"id": l.get("id") or "", "name": l.get("name") or ""} for l in res.get("labels") or []]

    def _resolve_label_id(self, name: str) -> Optional[str]:
        for l in self.list_labels():
            if l["name"].lower() == name.lower():
                return l["id"]
        return None

    def create_label(self, name: str) -> dict:
        res = self._gmail().users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()
        return {"id": res.get("id") or "", "name": res.get("name") or name}

    def delete_label(self, name: str) -> None:
        label_id = self._resolve_label_id(name)
        if not label_id:
            raise RuntimeError(f"Label not found: {name}")
        self._gmail().users().labels().delete(userId="me", id=label_id).execute()

    def apply_label(self, message_id: str, name: str) -> None:
        label_id = self._resolve_label_id(name) or self.create_label(name)["id"]
        self._modify(message_id, [label_id], [])

    def remove_label(self, message_id: str, name: str) -> None:
        label_id = self._resolve_label_id(name)
        if label_id:
            self._modify(message_id, [], [label_id])

    # ── Sync: History API ──────────────────────────────────────────────

    def current_history_id(self) -> str:
        res = self._gmail().users().getProfile(userId="me").execute()
        return str(res.get("historyId") or "")

    def history(self, start_history_id: str) -> dict:
        res = self._gmail().users().history().list(userId="me", startHistoryId=start_history_id).execute()
        added, removed = set(), set()
        for h in res.get("history") or []:
            for m in h.get("messagesAdded") or []:
                if (m.get("message") or {}).get("id"):
                    added.add(m["message"]["id"])
            for m in h.get("messagesDeleted") or []:
                if (m.get("message") or {}).get("id"):
                    removed.add(m["message"]["id"])
        return {
            "historyId": str(res.get("historyId") or start_history_id),
            "added": sorted(added),
            "removed": sorted(removed),
        }


gmail_channel = GmailApiChannel()
