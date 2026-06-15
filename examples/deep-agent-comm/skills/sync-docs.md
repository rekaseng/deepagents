---
name: sync-docs
description: Update every doc in docs/ to reflect the latest project state. A Claude Code (dev-time) skill — the platform agent cannot run it (no file-edit tools), so it has no triggers and is never activated at runtime. Invoked by Claude Code when the user says "sync docs" / "update the docs", or by the once-per-conversation SessionStart hook in .claude/settings.json.
---

# Sync Docs — bring docs/ up to date with the code

## Goal

Every file in `docs/` must describe the project as it exists right now. Status markers (✅ built · ◐ partial · 🔲 planned · ⭕ reachable-not-built · 🚫 withheld), file paths, tool/skill inventories, endpoints, and feature notes must match the code — the code is the source of truth, the docs follow it.

## Procedure

1. **Gather current state** (read-only):
   - `git log --oneline -15` and `git status` — what changed recently.
   - `src/api/server.ts` — registered tools/skills and HTTP endpoints (source of truth for what is live).
   - `src/tools/`, `src/skills/*.md`, `src/triggers/`, `src/channels/`, `src/memory/store.ts`, `src/core/agent.ts` — capability inventory.
   - `public/app.js` — `TOOL_CATALOG` / `SKILL_CATALOG`, the UI mirror of `docs/03-communication-layer.md`.

2. **Audit each doc** in `docs/` against that state:
   - `01-architecture.md` — layer/status table (§3), build-order progress (§10), web UI & session memory notes (§11).
   - `02-triggers.md` — trigger status table (§2), resolved questions (§5).
   - `03-communication-layer.md` — tool tables (Tiers 1–4 + withheld), skill tables, cross-cutting features (§4), code mapping (§5), header date.
   - `gmail_channel_functionality.md` — per-capability matrix and implemented-tool count.
   - `answer-for-md.md` — decisions record: append new decisions only; never rewrite past decisions.
   - Any doc added later gets the same treatment.

3. **Fix only what is stale.** Preserve each doc's structure, voice, and legend. Update:
   - status markers and `> **Status:**` header lines (stamp the current date on any doc you change),
   - tool/skill names, counts, and file paths,
   - "next steps" / "still open" lists where items have since been done.
   Never delete decision history or design rationale. Never document features that do not exist in code.

4. **Keep the UI mirror in sync:** if the tool/skill tables in `docs/03-communication-layer.md` changed, update `TOOL_CATALOG` / `SKILL_CATALOG` in `public/app.js` to match (and vice versa). This is the only code edit this skill may make.

5. **Report:** list each file changed with a one-line reason. If nothing is stale, say "docs already current" and change nothing.

## Guardrails

- Docs-only task — no code refactoring (sole exception: the `public/app.js` catalog mirror in step 4).
- Small, factual diffs. No stylistic rewrites.
- Run at most once per conversation; if it already ran in this session, skip.
