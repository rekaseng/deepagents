"""Supervisor graph — the full LangGraph migration of the platform loop:

    START → classify (L1 intent) → agent (L2 deepagents) → END

State is checkpointed per thread_id (= session id), so conversation memory is
handled by the checkpointer — no manual history replay."""

from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..core.skills import Skill
from .classifier import classify_intent


class PlatformState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Optional[str]
    skill: Optional[str]
    confidence: Optional[float]
    # per-run inputs (set by the caller, not persisted meaningfully)
    forced_skill: Optional[str]
    system_suffix: Optional[str]


def _latest_human_text(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if m.type == "human":
            return str(m.content)
    return ""


def build_supervisor_graph(deep_agent, skills: list[Skill], checkpointer):
    async def classify_node(state: PlatformState) -> dict:
        forced = state.get("forced_skill")
        if forced:
            return {"intent": forced, "skill": forced, "confidence": 1.0}
        text = _latest_human_text(state["messages"])
        result = await classify_intent(text, skills)
        return {"intent": result.intent, "skill": result.skill_name, "confidence": result.confidence}

    async def agent_node(state: PlatformState) -> dict:
        hint_parts = []
        if state.get("skill"):
            hint_parts.append(
                f"Intent router: intent={state.get('intent')}, suggested skill subagent="
                f"\"{state.get('skill')}\" (confidence {state.get('confidence')}). "
                "Delegate to that subagent via the task tool if it fits; otherwise handle directly."
            )
        if state.get("system_suffix"):
            hint_parts.append(state["system_suffix"])

        input_messages = list(state["messages"])
        if hint_parts:
            input_messages.append(SystemMessage("\n\n".join(hint_parts)))

        result = await deep_agent.ainvoke({"messages": input_messages})

        # Return only NEW messages (add_messages upserts by id; the transient
        # hint SystemMessage is excluded so it never persists in the thread).
        seen = {m.id for m in input_messages}
        new = [m for m in result["messages"] if m.id not in seen]
        return {"messages": new, "forced_skill": None, "system_suffix": None}

    graph = StateGraph(PlatformState)
    graph.add_node("classify", classify_node)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=checkpointer)
