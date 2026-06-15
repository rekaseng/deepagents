"""Gmail tools — wrap GmailApiChannel. NOTE: there is deliberately NO gmail_send
tool — draft-only is enforced by absence of capability."""

from datetime import datetime, timezone

from langchain_core.tools import tool

from ..channels.gmail_api import ChannelMessage, gmail_channel


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _summary(m: ChannelMessage) -> dict:
    return {
        "id": m.id,
        "from": m.from_["address"],
        "subject": (m.subject or "")[:120],
        "snippet": " ".join(m.body[:120].split()),
        "attachments": [a.filename for a in m.attachments],
        "receivedAt": _iso(m.receivedAt),
    }


def _clamp(limit: int) -> int:
    return min(max(int(limit or 20), 1), 50)


@tool
def gmail_list_unread(limit: int = 20) -> dict:
    """List the most-recent UNREAD emails in the inbox (narrow: unread only). For anything else — date ranges, a sender, starred, attachments — use gmail_search instead. Default limit 20, max 50."""
    try:
        msgs = gmail_channel.fetch_unread(_clamp(limit))
        return {"success": True, "output": {"count": len(msgs), "messages": [_summary(m) for m in msgs]}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_search(query: str, limit: int = 20) -> dict:
    """Search mail using full Gmail query syntax. Supports from:, to:, subject:, label:, has:attachment, is:unread, is:starred, newer_than:2d, after:2026/06/01, before:, in:inbox, etc. Use this for "emails today", "from X", "with attachments", anything beyond plain unread. Default limit 20, max 50."""
    try:
        msgs = gmail_channel.search(query, _clamp(limit))
        return {"success": True, "output": {"query": query, "count": len(msgs), "messages": [_summary(m) for m in msgs]}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_get_message(message_id: str, download: bool = False) -> dict:
    """Get the full content of one email by its message id: headers, full body text, and attachment metadata. Set download=true to materialize .xlsx/.csv attachments to disk and get their file paths (for charting/analysis)."""
    try:
        m = gmail_channel.get_message(message_id, download)
        if not m:
            return {"success": False, "error": "Message not found"}
        return {
            "success": True,
            "output": {
                "id": m.id,
                "from": m.from_,
                "to": m.to,
                "subject": m.subject,
                "body": m.body[:6000],
                "bodyHtml": m.bodyHtml[:6000] if m.bodyHtml else None,
                "receivedAt": _iso(m.receivedAt),
                "attachments": [
                    {"filename": a.filename, "mimeType": a.mimeType, "sizeBytes": a.sizeBytes, "localPath": a.localPath}
                    for a in m.attachments
                ],
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_get_thread(message_id: str) -> dict:
    """Get a whole conversation thread (ordered oldest→newest) given any message id in it. Use to get full context before drafting a reply."""
    try:
        thread = gmail_channel.get_thread(message_id)
        if not thread:
            return {"success": False, "error": "Thread not found"}
        return {
            "success": True,
            "output": {
                "count": len(thread),
                "messages": [
                    {"id": m.id, "from": m.from_["address"], "subject": m.subject,
                     "body": m.body[:3000], "receivedAt": _iso(m.receivedAt)}
                    for m in thread
                ],
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_get_attachment(message_id: str, filename: str) -> dict:
    """Download a specific attachment (any type) from a message to disk by filename (or a substring of it). Returns the local file path."""
    try:
        path = gmail_channel.get_attachment(message_id, filename)
        return {"success": True, "output": {"filePath": path}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    in_reply_to: str | None = None,
    attachment_paths: list[str] | None = None,
) -> dict:
    """Create a reply or new DRAFT in Gmail (never sends — a human reviews and sends). For reply-all, pass the other recipients in cc. Pass the original message id as in_reply_to to keep it in-thread."""
    try:
        gmail_channel.create_draft({
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body": body,
            "inReplyTo": in_reply_to,
            "attachmentPaths": attachment_paths,
        })
        return {"success": True, "output": "Draft created in Gmail. A human must review and send it."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_forward_draft(message_id: str, to: str, note: str = "") -> dict:
    """Create a FORWARD draft of an existing message (carries the original body + .xlsx/.csv attachments). Never sends."""
    try:
        gmail_channel.create_forward_draft(message_id, to, note)
        return {"success": True, "output": "Forward draft created. A human must review and send it."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_list_drafts(limit: int = 20) -> dict:
    """List existing drafts (id, subject, recipients, date). Use the id to delete or update a draft."""
    try:
        drafts = gmail_channel.list_drafts(_clamp(limit))
        return {"success": True, "output": {"count": len(drafts), "drafts": drafts}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_delete_draft(draft_id: str) -> dict:
    """Delete a draft by its id (get the id from gmail_list_drafts)."""
    try:
        gmail_channel.delete_draft(draft_id)
        return {"success": True, "output": "Draft deleted."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_update_draft(
    draft_id: str,
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    attachment_paths: list[str] | None = None,
) -> dict:
    """Update an existing draft in place by its id (replaces its content). Get the id from gmail_list_drafts."""
    try:
        gmail_channel.update_draft(draft_id, {
            "to": to, "cc": cc, "subject": subject, "body": body,
            "attachmentPaths": attachment_paths,
        })
        return {"success": True, "output": "Draft updated."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_organize(message_id: str, action: str) -> dict:
    """Organize a message by id. action: mark_read | mark_unread | star | unstar | mark_important | unmark_important | archive (remove from inbox) | trash | restore (untrash)."""
    actions = {
        "mark_read": gmail_channel.mark_read,
        "mark_unread": gmail_channel.mark_unread,
        "star": gmail_channel.star,
        "unstar": gmail_channel.unstar,
        "mark_important": gmail_channel.mark_important,
        "unmark_important": gmail_channel.unmark_important,
        "archive": gmail_channel.archive,
        "trash": gmail_channel.trash,
        "restore": gmail_channel.restore,
    }
    fn = actions.get(action)
    if not fn:
        return {"success": False, "error": f"Unknown action: {action}"}
    try:
        fn(message_id)
        return {"success": True, "output": f"Done: {action}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_label(message_id: str, label: str, action: str) -> dict:
    """Apply or remove a Gmail label on a message by name. action: apply | remove. Applying a non-existent label creates it first."""
    try:
        if action == "apply":
            gmail_channel.apply_label(message_id, label)
        else:
            gmail_channel.remove_label(message_id, label)
        return {"success": True, "output": f'{action} label "{label}"'}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_manage_labels(action: str, name: str | None = None) -> dict:
    """Manage the label list itself. action: list | create | delete (name required for create/delete)."""
    try:
        if action == "list":
            return {"success": True, "output": {"labels": [l["name"] for l in gmail_channel.list_labels()]}}
        if not name:
            return {"success": False, "error": "name required"}
        if action == "create":
            created = gmail_channel.create_label(name)
            return {"success": True, "output": {"created": created["name"]}}
        gmail_channel.delete_label(name)
        return {"success": True, "output": {"deleted": name}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_history(start_history_id: str | None = None) -> dict:
    """Incremental sync: list message changes (added/removed ids) since a historyId. Call with no arg to get the current historyId cursor to start from."""
    try:
        if not start_history_id:
            history_id = gmail_channel.current_history_id()
            return {"success": True, "output": {"currentHistoryId": history_id,
                    "note": "Pass this as start_history_id next time to get changes since now."}}
        return {"success": True, "output": gmail_channel.history(start_history_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def gmail_mark_read(message_id: str) -> dict:
    """Mark an email as read (handled) by its message id. (Shortcut for gmail_organize action=mark_read.)"""
    try:
        gmail_channel.mark_read(message_id)
        return {"success": True, "output": "marked read"}
    except Exception as e:
        return {"success": False, "error": str(e)}


GMAIL_TOOLS = [
    gmail_list_unread,
    gmail_search,
    gmail_get_message,
    gmail_get_thread,
    gmail_get_attachment,
    gmail_create_draft,
    gmail_forward_draft,
    gmail_list_drafts,
    gmail_delete_draft,
    gmail_update_draft,
    gmail_organize,
    gmail_label,
    gmail_manage_labels,
    gmail_history,
    gmail_mark_read,
]
