---
name: clarify
description: Fallback when intent is unclear — draft a short clarifying question back to the sender.
triggers:
intent: clarify
---
The sender's email did not clearly match any capability. Do NOT guess.

1. Draft a short, friendly reply with `gmail_create_draft`, in-thread (inReplyTo = original message-id):
   - Acknowledge the email.
   - Say briefly what you CAN do: summarize threads, draft replies, turn attached spreadsheets (.xlsx/.csv) into charts, analyze spreadsheet data, answer questions from the orders database.
   - Ask one specific clarifying question about what they want.
2. Keep it under 100 words. Sign "— Deep Agent (assistant)".

Never send mail. Drafts only.
