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
from botbuilder.schema import Activity, ActivityTypes
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


async def _handle_turn(turn_context: TurnContext) -> None:
    if turn_context.activity.type != ActivityTypes.message:
        return

    user_text = (turn_context.activity.text or "").strip()
    if not user_text:
        return

    thread_id = turn_context.activity.conversation.id

    result = await agent.ainvoke(
        {"messages": [HumanMessage(user_text)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    last = result["messages"][-1]
    content = last.content
    if not isinstance(content, str):
        content = json.dumps(content, indent=2)

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
