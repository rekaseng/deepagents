"""FastAPI server exposing the Freight Rates Agent as an Azure Bot endpoint.

Usage:
    uvicorn server:app --host 0.0.0.0 --port 3978 --reload

Azure Bot messaging endpoint to register:
    https://<your-host>/api/messages

Required environment variables (add to .env):
    MICROSOFT_APP_ID        — Azure Bot app ID (from Azure portal)
    MICROSOFT_APP_PASSWORD  — Azure Bot client secret
    MICROSOFT_APP_TENANT_ID — Azure Tenant ID (Single Tenant bots only)
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from pathlib import Path

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes, Attachment
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage

from agent import agent

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Freight Rates Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

_tenant_id = os.environ.get("MICROSOFT_APP_TENANT_ID", "")

_ADAPTER = BotFrameworkAdapter(
    BotFrameworkAdapterSettings(
        app_id=os.environ.get("MICROSOFT_APP_ID", ""),
        app_password=os.environ.get("MICROSOFT_APP_PASSWORD", ""),
        channel_auth_tenant=_tenant_id or None,
    )
)


async def _on_error(context: TurnContext, error: Exception) -> None:
    logger.error("Unhandled bot error: %s", error, exc_info=True)
    await context.send_activity(f"Sorry, something went wrong: {error}")


_ADAPTER.on_turn_error = _on_error



def _build_options_card(data: dict) -> Attachment:
    """Build an Adaptive Card with clickable choice buttons from structured agent output."""
    message = data.get("message", "Please choose an option:")
    choices = data.get("choices", [])

    body = [{"type": "TextBlock", "text": message, "wrap": True, "weight": "Bolder"}]

    actions = [
        {
            "type": "Action.Submit",
            "title": c.get("title", c.get("value", "Option")),
            "data": {"query": c.get("value", c.get("title", ""))},
        }
        for c in choices
    ]

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


async def _handle_turn(turn_context: TurnContext) -> None:
    if turn_context.activity.type != ActivityTypes.message:
        return

    # Button clicks arrive with activity.value instead of activity.text
    value = turn_context.activity.value
    if value and isinstance(value, dict) and "query" in value:
        user_text = value["query"].strip()
    else:
        user_text = (turn_context.activity.text or "").strip()

    if not user_text:
        return

    thread_id = turn_context.activity.conversation.id

    result = await agent.ainvoke(
        {"messages": [HumanMessage(user_text)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result["messages"]
    last = messages[-1]
    content = last.content
    if not isinstance(content, str):
        content = json.dumps(content, indent=2)

    # Strip markdown code fences DeepSeek sometimes wraps JSON in
    stripped = content.strip()
    for fence in ("```json", "```"):
        if stripped.startswith(fence):
            stripped = stripped[len(fence):]
            break
    stripped = stripped.removesuffix("```").strip()

    # Detect structured options response → send only the card
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and parsed.get("type") == "options":
            reply = Activity(
                type=ActivityTypes.message,
                attachments=[_build_options_card(parsed)],
            )
            await turn_context.send_activity(reply)
            return
    except (json.JSONDecodeError, TypeError):
        pass

    # Send the agent's plain text answer
    await turn_context.send_activity(content)


@app.post("/api/messages")
async def messages(req: Request) -> Response:
    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    try:
        await _ADAPTER.process_activity(activity, auth_header, _handle_turn)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return Response(status_code=200)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
