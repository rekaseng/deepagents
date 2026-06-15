"""L2 — Deep agent assembly. Every skill .md becomes a deepagents SUBAGENT:
the main agent routes work to them via the built-in task tool. Skills flagged
subagent: true get only the sandbox-tier toolset (least privilege, no email)."""

import os

from deepagents import create_deep_agent

from ..config import ALLOWED_SENDERS, GMAIL_USER
from ..core.model import get_model
from ..core.skills import Skill, load_skills
from ..tools import GENERAL_TOOLS, SANDBOX_TOOLS


def identity_block() -> str:
    allowed = ", ".join(ALLOWED_SENDERS) if ALLOWED_SENDERS else "(none configured)"
    return f"""Your identity (answer directly, do NOT call tools for these facts):
- You are "Deep Agent (assistant)".
- The Gmail mailbox you manage is: {GMAIL_USER.lower()}
- Channel: Gmail (REST API). You can draft replies but cannot send mail — drafts only.
- Allowed senders (whitelist): {allowed}"""


def skill_to_subagent(skill: Skill) -> dict:
    return {
        "name": skill.name,
        "description": skill.description or f"Skill: {skill.name}",
        "system_prompt": (
            f"You are the '{skill.name}' specialist subagent.\n\n{skill.prompt}\n\n"
            + identity_block()
        ),
        "tools": SANDBOX_TOOLS if skill.subagent else GENERAL_TOOLS,
    }


def build_main_prompt(skills: list[Skill]) -> str:
    catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
    return f"""You are a deep agent for a communication platform. Accomplish the user's goal step by step.

{identity_block()}

Specialist subagents are available via the task tool — one per skill:
{catalog}

Routing rules:
- An intent-router note may accompany the request naming a suggested skill. Prefer delegating to that subagent.
- Delegate heavy or multi-step work (data analysis, charting, code execution) to the matching subagent with a complete, self-contained brief including absolute file paths.
- Handle trivial requests directly with your own tools.
- When done, give a final answer without calling any tool."""


def build_deep_agent(checkpointer=None):
    skills = load_skills()
    agent = create_deep_agent(
        model=get_model(),
        tools=GENERAL_TOOLS,
        system_prompt=build_main_prompt(skills),
        subagents=[skill_to_subagent(s) for s in skills],
        checkpointer=checkpointer,
    )
    return agent, skills
