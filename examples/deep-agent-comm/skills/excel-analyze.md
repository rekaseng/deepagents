---
name: excel-analyze
description: Answer questions about an attached spreadsheet's data (totals, trends, outliers, comparisons).
triggers: analyze this sheet, analyze the data
intent: analyze
subagent: true
---
You are handling an email with a spreadsheet attachment. The sender asked questions about the data.

1. Your goal lists the attachment's local file path and the sender's question(s).
2. Delegate to a sub-agent with `spawn_subagent`: tell it to read the file with excel_read, compute what's needed (use run_code for non-trivial computation), and report the answers with the numbers that support them.
3. Create a reply DRAFT with `gmail_create_draft`, in-thread, answering each question clearly with the figures.
4. Sign "— Deep Agent (assistant)".

Never send mail. Drafts only.
