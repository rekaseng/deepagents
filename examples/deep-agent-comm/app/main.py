"""FastAPI server — same HTTP surface as the TS Express server (src/api/server.ts),
serving the same web UI from public/. Sessions = LangGraph checkpointer threads."""

import asyncio
import uuid
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from .agent.builder import build_deep_agent
from .agent.supervisor import build_supervisor_graph
from .channels.gmail_api import gmail_channel
from .config import CHECKPOINT_DB_PATH, GMAIL_USER, PORT, PUBLIC_DIR
from .core.steps import final_answer, messages_to_steps
from .memory.store import get_task, list_session_tasks, list_sessions, list_tasks
from .memory.store import save_task
from .tools import GENERAL_TOOLS
from .triggers import email as email_trigger
from .triggers.schedule import start_schedules, stop_schedules
from .teams import register_teams

import os


class RunRequest(BaseModel):
    goal: str
    sessionId: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = await aiosqlite.connect(CHECKPOINT_DB_PATH)
    checkpointer = AsyncSqliteSaver(conn)
    deep_agent, skills = build_deep_agent()
    graph = build_supervisor_graph(deep_agent, skills, checkpointer)

    app.state.graph = graph
    app.state.skills = skills

    email_task = asyncio.create_task(email_trigger.email_trigger_loop(graph, skills))
    start_schedules(graph)
    print(f"Deep Agent Platform (LangGraph/deepagents) running on http://localhost:{PORT}")

    yield

    email_task.cancel()
    stop_schedules()
    await conn.close()


app = FastAPI(lifespan=lifespan)


@app.post("/run")
async def run(req: RunRequest):
    if not req.goal:
        raise HTTPException(400, "goal required")
    # No sessionId → new session (thread). With sessionId → continue it; the
    # checkpointer replays the thread state automatically.
    session_id = req.sessionId or str(uuid.uuid4())
    task_id = uuid.uuid4().hex
    try:
        result = await app.state.graph.ainvoke(
            {"messages": [HumanMessage(req.goal)], "forced_skill": None, "system_suffix": None},
            config={"configurable": {"thread_id": session_id}},
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    answer = final_answer(result["messages"])
    # Steps for THIS turn only: take messages from the latest matching goal on.
    msgs = result["messages"]
    start = 0
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].type == "human" and str(msgs[i].content) == req.goal:
            start = i
            break
    steps = messages_to_steps(msgs[start:])
    save_task(task_id, req.goal, answer, steps, session_id)
    return {"taskId": task_id, "sessionId": session_id, "result": answer, "steps": steps}


@app.get("/sessions")
async def sessions():
    return list_sessions()


@app.get("/sessions/{session_id}")
async def session_tasks(session_id: str):
    return list_session_tasks(session_id)


@app.get("/tasks")
async def tasks():
    return list_tasks()


@app.get("/tasks/{task_id}")
async def task(task_id: str):
    t = get_task(task_id)
    if not t:
        raise HTTPException(404, "not found")
    return t


@app.get("/tools")
async def tools():
    builtin = [
        {"name": "task", "description": "deepagents built-in: delegate to a skill subagent"},
        {"name": "write_todos", "description": "deepagents built-in: planning todo list"},
        {"name": "ls/read_file/write_file/edit_file", "description": "deepagents built-in: virtual filesystem"},
    ]
    return [{"name": t.name, "description": t.description} for t in GENERAL_TOOLS] + builtin


@app.get("/skills")
async def skills():
    return [
        {"name": s.name, "description": s.description, "intent": s.intent, "subagent": s.subagent}
        for s in app.state.skills
    ]


@app.get("/channel/status")
async def channel_status():
    return {
        "gmail": {
            "configured": gmail_channel.is_configured(),
            "user": gmail_channel.self_address,
            "defaulted": not os.getenv("GMAIL_USER"),
            "trigger": email_trigger.status,
        }
    }


# Teams / Azure Bot endpoint (POST /api/messages). Registered before the
# catch-all static mount below so the route resolves ahead of the SPA.
register_teams(app)

app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="static")


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
