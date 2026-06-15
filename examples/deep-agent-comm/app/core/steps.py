"""Convert LangGraph message lists into the StepRecord shape the web UI renders
(same contract as the TS side: {id, type, input, output, timestamp})."""

import json
import time
import uuid
from typing import Any

from langchain_core.messages import AnyMessage

MAX_OUTPUT_CHARS = 8000


def _serialize(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return content[:MAX_OUTPUT_CHARS]
    return content


def messages_to_steps(messages: list[AnyMessage]) -> list[dict]:
    steps: list[dict] = []
    pending: dict[str, dict] = {}   # tool_call_id → step awaiting its result

    for m in messages:
        now = int(time.time() * 1000)
        if m.type == "ai":
            tool_calls = getattr(m, "tool_calls", None) or []
            for tc in tool_calls:
                step = {
                    "id": uuid.uuid4().hex,
                    "type": "tool",
                    "input": {"tool": tc.get("name"), "args": tc.get("args")},
                    "output": None,
                    "timestamp": now,
                }
                steps.append(step)
                if tc.get("id"):
                    pending[tc["id"]] = step
            if not tool_calls and m.content:
                steps.append({
                    "id": uuid.uuid4().hex,
                    "type": "llm",
                    "input": None,
                    "output": str(m.content)[:MAX_OUTPUT_CHARS],
                    "timestamp": now,
                })
        elif m.type == "tool":
            step = pending.get(getattr(m, "tool_call_id", "") or "")
            if step is not None:
                step["output"] = _serialize(m.content)
            else:
                steps.append({
                    "id": uuid.uuid4().hex,
                    "type": "tool",
                    "input": {"tool": getattr(m, "name", None)},
                    "output": _serialize(m.content),
                    "timestamp": now,
                })
    return steps


def final_answer(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if m.type == "ai" and not (getattr(m, "tool_calls", None) or []):
            return str(m.content)
    return ""
