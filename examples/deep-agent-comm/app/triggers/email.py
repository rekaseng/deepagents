"""Trigger ① — inbound email. Polls Gmail, applies the guard chain
(self-filter → dedupe → allow-list), then runs the supervisor graph with the
classifier-forced skill. Port of src/triggers/email.ts."""

import asyncio
import uuid

from langchain_core.messages import HumanMessage

from ..agent.classifier import classify_intent
from ..channels.gmail_api import ChannelMessage, gmail_channel
from ..config import ALLOWED_SENDERS, POLL_INTERVAL_MS
from ..core.steps import final_answer, messages_to_steps
from ..memory.store import is_processed, mark_processed, save_task

EMAIL_RULES = """You are handling email on behalf of the mailbox owner as a named assistant ("Deep Agent").
Hard rules:
- You can ONLY create drafts (gmail_create_draft). Sending mail is impossible — never claim you sent anything; say a draft was prepared.
- Reply in-thread: always pass the original message id as in_reply_to.
- Sign drafts "— Deep Agent (assistant)".
- Never invent facts about the sender's business; if unsure, ask in the draft."""

status = {"enabled": False, "lastPollAt": 0, "lastError": "", "processedCount": 0}


def _build_goal(msg: ChannelMessage) -> str:
    attach_lines = "\n".join(
        f"- {a.filename} ({a.mimeType}, {a.sizeBytes} bytes) at local path: {a.localPath}"
        for a in msg.attachments
    )
    return f"""You received an inbound email. Handle it according to your active skill.

From: {msg.from_['name']} <{msg.from_['address']}>
Subject: {msg.subject}
Message id (use as in_reply_to when drafting the reply): {msg.id}
Attachments:
{attach_lines or '(none)'}

Email body:
\"\"\"
{msg.body[:6000]}
\"\"\""""


async def _handle_message(graph, skills, msg: ChannelMessage) -> None:
    if msg.from_["address"] == gmail_channel.self_address:
        return                                           # self-mail → loop guard
    if is_processed(msg.id):
        return                                           # dedupe
    if ALLOWED_SENDERS and msg.from_["address"] not in ALLOWED_SENDERS:
        mark_processed(msg.id)                           # ignore, but don't reprocess
        return

    print(f'[email-trigger] processing: "{msg.subject}" from {msg.from_["address"]}')

    attach_info = (
        f"Attachments: {', '.join(a.filename for a in msg.attachments)}"
        if msg.attachments else "No attachments."
    )
    intent = await classify_intent(
        msg.body, skills,
        context=f"From: {msg.from_['address']}\nSubject: {msg.subject}\n{attach_info}",
    )
    print(f"[email-trigger] intent={intent.intent} skill={intent.skill_name} conf={intent.confidence}")

    task_id = uuid.uuid4().hex
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(_build_goal(msg))],
            "forced_skill": intent.skill_name,
            "system_suffix": EMAIL_RULES,
        },
        config={"configurable": {"thread_id": task_id}},
    )
    answer = final_answer(result["messages"])
    steps = messages_to_steps(result["messages"])
    save_task(task_id, f"[email] {msg.subject} ({intent.skill_name})", answer, steps)
    mark_processed(msg.id)
    try:
        await asyncio.to_thread(gmail_channel.mark_read, msg.id)
    except Exception:
        pass
    status["processedCount"] += 1


async def _poll(graph, skills) -> None:
    import time
    try:
        messages = await asyncio.to_thread(gmail_channel.fetch_unread)
        status["lastPollAt"] = int(time.time() * 1000)
        status["lastError"] = ""
        for msg in messages:
            try:
                await _handle_message(graph, skills, msg)
            except Exception as e:
                print(f'[email-trigger] failed on "{msg.subject}": {e}')
    except Exception as e:
        status["lastError"] = str(e)
        print(f"[email-trigger] poll error: {e}")


async def email_trigger_loop(graph, skills) -> None:
    if not gmail_channel.is_configured():
        print("[email-trigger] gmail secrets missing — email trigger disabled")
        return
    status["enabled"] = True
    allow = ", ".join(ALLOWED_SENDERS) or "(open!)"
    print(f"[email-trigger] polling every {POLL_INTERVAL_MS / 1000}s, allow-list: {allow}")
    while True:
        await _poll(graph, skills)
        await asyncio.sleep(POLL_INTERVAL_MS / 1000)
