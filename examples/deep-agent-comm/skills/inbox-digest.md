---
name: inbox-digest
description: Schedule-triggered — summarize unread inbox into a digest draft addressed to the owner.
triggers: inbox digest
intent: digest
---
You are producing a scheduled inbox digest for the mailbox owner.

1. Call `gmail_list_unread` to see waiting mail.
2. If there is no unread mail, finish with "Inbox clear — no digest needed" and do NOT create a draft.
3. Otherwise group what you find: urgent-looking items first, then the rest. One line each: sender — subject — what they want.
4. Create a DRAFT with `gmail_create_draft` addressed to the mailbox owner (the agent's own address), subject "Inbox digest".
5. Sign "— Deep Agent (assistant)".

Never send mail. Drafts only.
