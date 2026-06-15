"""Trigger ② — schedules: inbox digest (8:00 weekdays) + unanswered-mail nudge
(17:30 weekdays). Read + draft only — no send tool exists anywhere.

Deviation from the TS port: deepagents builds its toolset at agent-build time,
so per-run tool restriction is expressed in the goal text instead of a
filtered registry. Same effective behavior (list unread + create draft)."""

import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from langchain_core.messages import HumanMessage

from ..channels.gmail_api import gmail_channel
from ..core.steps import final_answer, messages_to_steps
from ..memory.store import save_task

_scheduler: AsyncIOScheduler | None = None


async def _run_scheduled(graph, label: str, goal: str, forced_skill: str | None = None) -> None:
    print(f"[schedule] running: {label}")
    try:
        task_id = uuid.uuid4().hex
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(goal)],
                "forced_skill": forced_skill,
                "system_suffix": "Use ONLY gmail_list_unread and gmail_create_draft for this scheduled run.",
            },
            config={"configurable": {"thread_id": task_id}},
        )
        save_task(task_id, f"[schedule] {label}", final_answer(result["messages"]),
                  messages_to_steps(result["messages"]))
        print(f"[schedule] {label} done")
    except Exception as e:
        print(f"[schedule] {label} failed: {e}")


def start_schedules(graph) -> None:
    global _scheduler
    if not gmail_channel.is_configured():
        print("[schedule] gmail not configured — schedules disabled")
        return

    self_addr = gmail_channel.self_address
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_scheduled,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        args=[graph, "inbox digest",
              f"Produce the morning inbox digest. The mailbox owner's address is {self_addr}.",
              "inbox-digest"],
    )
    _scheduler.add_job(
        _run_scheduled,
        CronTrigger(day_of_week="mon-fri", hour=17, minute=30),
        args=[graph, "unanswered nudge",
              f'End-of-day check: call gmail_list_unread. If any unread mail is waiting, create a DRAFT to {self_addr} '
              f'with subject "Unanswered mail nudge" listing each one (sender — subject — one-line gist) so the owner '
              f'can deal with them. If inbox is clear, just finish without drafting. Sign "— Deep Agent (assistant)".'],
    )
    _scheduler.start()
    print("[schedule] registered: inbox digest (08:00 wd), unanswered nudge (17:30 wd)")


def stop_schedules() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
