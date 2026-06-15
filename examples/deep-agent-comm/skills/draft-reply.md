---
name: draft-reply
description: Compose a contextual reply to an email (tone-aware, professional by default).
triggers: draft a reply, reply to this, respond to
intent: compose
---
You are handling an email that needs a composed reply.

1. Read the email content in your goal. Understand what the sender is asking for and what a helpful, complete reply looks like.
2. Compose the reply: professional, warm, concise. Default tone unless the sender's request specifies otherwise (e.g. "decline politely", "make it casual").
3. Answer every question the sender asked. If you lack information to answer something, say so honestly in the draft rather than inventing facts.
4. Create the reply DRAFT with `gmail_create_draft`, in-thread (inReplyTo = original message-id).
5. Sign "— Deep Agent (assistant)".

Never send mail. Drafts only.
