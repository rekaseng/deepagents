"""Microsoft Teams / Azure Bot Framework endpoint.

Exposes the SAME deep-agent supervisor graph that powers the web UI over the
Bot Framework messaging protocol, so the agent is reachable from Teams, Web
Chat, or the Bot Framework Emulator.

`register_teams(app)` mounts `POST /api/messages` onto the existing FastAPI app
and reuses `app.state.graph` (built once in main.py's lifespan). Each Bot
conversation maps to its own agent thread via `conversation.id` -> `thread_id`,
so memory stays separate per channel/conversation.

Env (optional — leave blank for local Emulator testing):
    MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, MICROSOFT_APP_TENANT_ID
"""

from __future__ import annotations

import json
import logging

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes, Attachment
from fastapi import FastAPI, HTTPException, Request, Response
from langchain_core.messages import HumanMessage

from .config import MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, MICROSOFT_APP_TENANT_ID
from .core.steps import final_answer

logger = logging.getLogger(__name__)


def _build_options_card(data: dict) -> Attachment:
    """Build an Adaptive Card with clickable buttons from a structured options reply."""
    message = data.get("message", "Please choose an option:")
    choices = data.get("choices", [])
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [{"type": "TextBlock", "text": message, "wrap": True, "weight": "Bolder"}],
        "actions": [
            {
                "type": "Action.Submit",
                "title": c.get("title", c.get("value", "Option")),
                "data": {"query": c.get("value", c.get("title", ""))},
            }
            for c in choices
        ],
    }
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


def _maybe_options(content: str) -> dict | None:
    """Detect a structured options card the agent may emit (optionally fenced)."""
    stripped = content.strip()
    for fence in ("```json", "```"):
        if stripped.startswith(fence):
            stripped = stripped[len(fence):]
            break
    stripped = stripped.removesuffix("```").strip()
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, dict) and parsed.get("type") == "options":
        return parsed
    return None


def register_teams(app: FastAPI) -> None:
    """Mount the Bot Framework messaging endpoint onto an existing FastAPI app."""
    adapter = BotFrameworkAdapter(
        BotFrameworkAdapterSettings(
            app_id=MICROSOFT_APP_ID,
            app_password=MICROSOFT_APP_PASSWORD,
            channel_auth_tenant=MICROSOFT_APP_TENANT_ID or None,
        )
    )

    async def _on_error(context: TurnContext, error: Exception) -> None:
        logger.error("Unhandled bot error: %s", error, exc_info=True)
        await context.send_activity(f"Sorry, something went wrong: {error}")

    adapter.on_turn_error = _on_error

    async def _handle_turn(turn_context: TurnContext) -> None:
        if turn_context.activity.type != ActivityTypes.message:
            return

        # Button clicks arrive as activity.value; typed messages as activity.text
        value = turn_context.activity.value
        if value and isinstance(value, dict) and "query" in value:
            user_text = str(value["query"]).strip()
        else:
            user_text = (turn_context.activity.text or "").strip()
        if not user_text:
            return

        # One agent thread per Bot conversation → memory is isolated per channel.
        thread_id = turn_context.activity.conversation.id

        result = await app.state.graph.ainvoke(
            {"messages": [HumanMessage(user_text)], "forced_skill": None, "system_suffix": None},
            config={"configurable": {"thread_id": thread_id}},
        )
        answer = final_answer(result["messages"])

        options = _maybe_options(answer)
        if options is not None:
            reply = Activity(
                type=ActivityTypes.message,
                attachments=[_build_options_card(options)],
            )
            await turn_context.send_activity(reply)
            return

        await turn_context.send_activity(answer)

    @app.post("/api/messages")
    async def messages(req: Request) -> Response:  # noqa: ANN202
        body = await req.json()
        activity = Activity().deserialize(body)
        auth_header = req.headers.get("Authorization", "")
        try:
            await adapter.process_activity(activity, auth_header, _handle_turn)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return Response(status_code=200)
