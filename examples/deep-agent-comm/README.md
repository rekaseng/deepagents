# Deep Agent Comm — Email & Productivity Platform

An interactive Deep Agent for communication workflows. It pairs a **web chat UI**
with a **Gmail** mailbox and a library of **skills** (each exposed as a deepagents
subagent), and can also be reached from **Microsoft Teams** via the Bot Framework.

Built on [`deepagents`](../../libs/deepagents) + LangGraph. A small intent
classifier routes each message to the right skill subagent; conversation memory
is checkpointed per session (web) or per conversation (Teams).

## Architecture

```
            ┌────────────── FastAPI app (app/main.py) ──────────────┐
 Web UI  ───▶ POST /run                                             │
 (public/)  │                                                       │
 Teams   ───▶ POST /api/messages (app/teams.py)                     │
            │                                                       │
            │   LangGraph supervisor (app/agent/supervisor.py)      │
            │     START → classify (L1 intent) → deep agent (L2)    │
            │                                  │                    │
            │   deep agent (app/agent/builder.py)                   │
            │     • GENERAL_TOOLS (Gmail, Excel, chart, SQL, …)     │
            │     • one subagent per skill (skills/*.md)            │
            │       sandbox skills get code-exec, no email          │
            └───────────────────────────────────────────────────────┘
   triggers/  email poller (Gmail) + APScheduler (e.g. inbox digest)
   memory/    sqlite: tasks + LangGraph checkpoints (data/)
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A DeepSeek API key — [platform.deepseek.com](https://platform.deepseek.com)
- A Gmail OAuth client + authorized token (see **Gmail setup**)
- _(Teams only)_ An Azure Bot resource

## Setup

**1. Install dependencies** (uses the local editable `deepagents` from `../../libs/deepagents`)

```
uv sync
```

**2. Configure environment**

```
cp .env.example .env
```

Fill in `DEEPSEEK_API_KEY` and `GMAIL_USER` at minimum.

**3. Gmail setup (OAuth)**

The Gmail tools authenticate with OAuth, not an app password. Place two files in `./secrets/`:

| File | What it is |
|------|-----------|
| `secrets/google_oauth_client.json` | OAuth client credentials (Google Cloud Console → APIs & Services → Credentials) |
| `secrets/gmail.token.json` | Authorized user token (access + refresh) for `GMAIL_USER` with the Gmail API scope |

> The agent can read, search, label, organize, and **draft** mail. There is no
> send tool by design — replies are always saved as drafts for human review.

**4. Run**

```
python -m app.main
# or:  uvicorn app.main:app --host 127.0.0.1 --port 3001
```

Open the web UI at **http://localhost:3001**.

## HTTP endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Web chat UI (served from `public/`) |
| `POST` | `/run` | Run a goal: `{"goal": "...", "sessionId": "..."}` → answer + steps |
| `GET`  | `/sessions`, `/sessions/{id}` | List sessions / tasks in a session |
| `GET`  | `/tasks`, `/tasks/{id}` | Task history |
| `GET`  | `/tools`, `/skills` | Introspect available tools / skills |
| `GET`  | `/channel/status` | Gmail configuration + trigger status |
| `POST` | `/api/messages` | Microsoft Teams / Bot Framework endpoint |

## Running in Microsoft Teams

The same agent is exposed over the Bot Framework at `POST /api/messages`
(`app/teams.py`). Each Teams conversation maps to its own agent thread
(`conversation.id` → `thread_id`), so memory stays isolated per conversation.

1. Create an Azure Bot resource and set the **Messaging endpoint** to
   `https://<your-public-host>/api/messages`.
2. Put the credentials in `.env`:
   ```
   MICROSOFT_APP_ID=<bot-app-id>
   MICROSOFT_APP_PASSWORD=<bot-client-secret>
   MICROSOFT_APP_TENANT_ID=<azure-tenant-id>   # single-tenant bots
   ```
3. Add the **Microsoft Teams** channel in the Azure Bot resource.

For local testing, use the [Bot Framework Emulator](https://github.com/microsoft/BotFramework-Emulator)
pointed at `http://localhost:3001/api/messages` (leave App ID / Password blank).

## Skills

Each `skills/*.md` file becomes a routed subagent. Frontmatter (`name`,
`description`, `triggers`, `intent`, `subagent`) controls routing and tool tier.

| Skill | Purpose |
|-------|---------|
| `clarify` | Ask a short clarifying question when intent is unclear (router fallback) |
| `draft-reply` | Compose a contextual, tone-aware email reply (draft only) |
| `summarize-thread` | TL;DR an email/thread: key points, decisions, action items |
| `inbox-digest` | Schedule-triggered unread-inbox digest, drafted to the owner |
| `excel-analyze` | Answer questions about an attached spreadsheet |
| `excel-to-chart` | Turn a spreadsheet into a chart image, drafted back to the sender |
| `data-query` | Answer a data question via read-only SQL, in plain English |
| `grill-me` / `grill-with-docs` | Interrogate a plan one question at a time (latter captures decisions to docs) |
| `caveman` | Terse, token-efficient response style |
| `sync-docs` | Dev-time only (Claude Code); no runtime triggers |

## Tools

**General** (main agent + non-sandbox subagents): `calculator`, `echo`,
`web_fetch`, `excel_read`, `excel_write`, `chart_generate`, `sql_query`, and the
Gmail toolset (`gmail_list_unread`, `gmail_search`, `gmail_get_message`,
`gmail_get_thread`, `gmail_create_draft`, `gmail_update_draft`, `gmail_organize`,
`gmail_label`, … — read/draft/organize, **no send**).

**Sandbox tier** (skills with `subagent: true`): Excel + chart + `calculator` +
`run_code` (isolated subprocess), **no email access** — least privilege.

## Project structure

```
deep-agent-comm/
├── app/
│   ├── main.py            # FastAPI app: web routes + lifespan + static UI
│   ├── teams.py           # Bot Framework /api/messages endpoint
│   ├── agent/             # builder (deep agent), supervisor (graph), classifier
│   ├── tools/             # gmail, excel, chart, sql, run_code, basic
│   ├── channels/          # gmail_api (OAuth Gmail REST client)
│   ├── triggers/          # email poller + APScheduler
│   ├── core/              # model (DeepSeek), skills loader, steps
│   ├── memory/            # sqlite task store
│   └── sandbox/           # subprocess code runner
├── public/                # web chat UI (index.html, app.js, style.css)
├── skills/                # *.md skill definitions (→ subagents)
├── pyproject.toml         # deps; deepagents editable from ../../libs/deepagents
├── .env.example
└── README.md
```
