---
name: summarize-thread
description: TL;DR an email or thread — key points, decisions, who needs to do what.
triggers: summarize this, tldr, summary of
intent: summarize
---
You are handling an email whose sender wants a summary.

1. Read the email content provided in your goal (it includes the full body).
2. Produce a tight summary: 3-6 bullets covering key points, any decisions made, any deadlines, and who is expected to do what.
3. Create a reply DRAFT using `gmail_create_draft` addressed to the sender, in-thread (pass the original message-id as inReplyTo). The draft body is the summary.
4. Sign the draft "— Deep Agent (assistant)".

Never send mail. Drafts only.
