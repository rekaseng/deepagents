"""L1 — Intent layer, now a LangGraph node helper. One small LLM call: which
skill handles this message? Does NOT do the work. Low confidence → 'clarify'."""

import json
import re
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from ..core.model import get_model
from ..core.skills import Skill

CONFIDENCE_THRESHOLD = 0.6


@dataclass
class IntentResult:
    intent: str
    skill_name: str
    confidence: float
    reason: str


async def classify_intent(text: str, skills: list[Skill], context: str = "") -> IntentResult:
    routable = [s for s in skills if s.intent]
    if not routable:
        return IntentResult("clarify", "clarify", 0.0, "no routable skills")

    menu = "\n".join(
        f'- intent: "{s.intent}" → skill: "{s.name}" — {s.description}' for s in routable
    )

    system = f"""You are an intent classifier for a communication agent. Given a message, pick exactly one intent from the menu.
Reply with ONLY a JSON object: {{"intent": "...", "skill": "...", "confidence": 0.0-1.0, "reason": "..."}}
If the message doesn't clearly match any intent, use intent "clarify", skill "clarify", confidence below 0.5.

Menu:
{menu}
- intent: "clarify" → skill: "clarify" — fallback when unclear"""

    user = f"{context}\n\n{text[:2000]}" if context else text[:2000]

    try:
        response = await get_model().ainvoke([SystemMessage(system), HumanMessage(user)])
        raw = re.sub(r"```json|```", "", str(response.content)).strip()
        parsed = json.loads(raw)
        result = IntentResult(
            intent=str(parsed.get("intent", "clarify")),
            skill_name=str(parsed.get("skill", "clarify")),
            confidence=float(parsed.get("confidence", 0)),
            reason=str(parsed.get("reason", "")),
        )
        if result.confidence < CONFIDENCE_THRESHOLD:
            return IntentResult(result.intent, "clarify", result.confidence, result.reason)
        if result.skill_name != "clarify" and not any(s.name == result.skill_name for s in routable):
            return IntentResult(result.intent, "clarify", result.confidence, "classifier named unknown skill")
        return result
    except Exception:
        return IntentResult("clarify", "clarify", 0.0, "classifier output unparseable")
