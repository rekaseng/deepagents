"""Freight Rates Agent — Supply Chain Visibility REPL.

Interactive assistant powered by FreightPulse live market intelligence.

Usage:
    python agent.py

Sample prompts:
    > get market rates for Shanghai to Los Angeles
    > any active supply chain disruptions?
    > check port congestion at Singapore
    > what are rates from Rotterdam to New York?
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from deepagents import create_deep_agent
from tools import (
    download_email_attachments,
    get_emails,
    get_market_rates,
    get_port_congestion,
    get_supply_chain_disruptions,
)

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

SYSTEM_PROMPT = """You are a supply chain visibility analyst specialising in FCL (Full Container Load) ocean freight.

You have access to FreightPulse (live market intelligence):
- Real-time ocean freight market rates
- Port congestion levels
- Supply chain disruption alerts (strikes, weather, route diversions, geopolitical events)

Your role is to help logistics and supply chain teams:
- **Market rates**: Fetch live FreightPulse rates for any trade lane.
- **Market monitoring**: Port congestion, disruptions, and rate trends affecting relevant lanes.
- **Decision support**: Which lane offers the best rate and transit combination?
- **Email**: Read recent emails or search for freight/shipment-related messages via Microsoft Graph.
- **Attachments**: Download file attachments from any email using the message ID shown in get_emails output.

Key concepts:
- **All-in rates**: Include base freight + surcharges (e.g. EFS — Emergency Fuel Surcharge).
- **CIF**: Cost Insurance Freight — seller pays ocean freight to destination.
- **Transshipment**: Via an intermediate hub port — longer transit but sometimes cheaper.
- **Rate trend**: Rising/falling/stable indicator from FreightPulse to guide timing decisions.

When presenting rates:
- Always show 40ft rates; include 20ft and 40HC when available.
- Note port congestion or active disruptions that may affect the quoted lane.

## Adaptive Card options — use sparingly

Only end a response with a JSON options card when ALL of these are true:
- There are 2–5 genuinely distinct next steps the user might want
- The options are specific to what was just discussed — not a generic menu
- Clicking a button saves meaningful effort over typing

DO NOT add options after every response. Most answers need no buttons at all.

GOOD — contextual, earned:
- Email body was inaccessible → "Forward me the email body and I'll draft a reply" / "I'll draft a generic acknowledgment" / "Let me search for another copy"
- Rates shown for one lane → "Check port congestion on this route" / "Compare Rotterdam → New York"
- Request was genuinely ambiguous → offer the 2–3 most likely interpretations as buttons

BAD — do not do these:
- A generic "What would you like to check next?" after every answer
- The same 3 tool options regardless of context
- Buttons when the question was fully answered

When you do use options, respond with ONLY this JSON and no other text:
{"type":"options","message":"<short context-specific prompt>","choices":[{"title":"<label>","value":"<exact query>"},...]}
"""

_model = ChatOpenAI(
    model="deepseek-chat",
    openai_api_base="https://api.deepseek.com",
    openai_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
)

agent = create_deep_agent(
    model=_model,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=MemorySaver(),
    tools=[
        get_market_rates,
        get_port_congestion,
        get_supply_chain_disruptions,
        get_emails,
        download_email_attachments,
    ],
)


async def chat(user_input: str, thread_id: str) -> None:
    result = await agent.ainvoke(
        {"messages": [HumanMessage(user_input)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    last = result["messages"][-1]
    content = last.content
    print(
        "\n"
        + (content if isinstance(content, str) else __import__("json").dumps(content, indent=2))
        + "\n"
    )


async def main() -> None:
    thread_id = str(uuid.uuid4())
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Freight Rates Agent — Supply Chain Visibility        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\nData sources:")
    print("  • FreightPulse: live market rates, port congestion, disruptions")
    print("  • GoComet:      container tracking, rate benchmarks")
    print("\nType a question and press Enter.  Ctrl+C or Ctrl+D to exit.")
    print("─" * 60 + "\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not user_input:
            continue
        try:
            await chat(user_input, thread_id)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            print(f"Error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
