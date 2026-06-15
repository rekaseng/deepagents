---
name: excel-to-chart
description: Turn an attached spreadsheet (.xlsx/.csv) into a chart image and draft it back to the sender. The flagship demo.
triggers: chart this, make a chart, visualize this
intent: visualize
subagent: true
---
You are handling an email with a spreadsheet attachment. The sender wants a chart.

1. Your goal lists the local file path(s) of the attachment(s).
2. Delegate the data work to a sub-agent with `spawn_subagent`. Give it a complete goal, for example:
   "Read <attachment path> with excel_read. Identify the columns relevant to the sender's request: <sender's request>. Aggregate the data appropriately (e.g. revenue by month). Then call chart_generate with a suitable Chart.js config (bar unless the data suggests otherwise). Report the chart PNG file path."
3. The sub-agent returns its answer with a FILES: line listing the chart path.
4. Create a reply DRAFT with `gmail_create_draft`:
   - to: the sender, in-thread (inReplyTo = original message-id)
   - body: 2-4 sentences describing what the chart shows (key trend, biggest/smallest values)
   - attachmentPaths: [the chart PNG path]
5. Sign "— Deep Agent (assistant)".

If the attachment is missing or unreadable, draft a reply explaining the problem and asking the sender to re-send.

Never send mail. Drafts only.
