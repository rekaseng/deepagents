---
name: data-query
description: Answer a data question by querying the database (read-only SQL), replying in plain English.
triggers: query the database, from the database, how many orders
intent: data-query
---
You are handling an email asking a question answerable from the database.

1. The database schema: orders(id, customer, product, qty, unit_price, order_date, status).
2. Translate the sender's question into ONE SELECT statement and run it with `sql_query`. The tool is read-only — never attempt writes.
3. If the first query errors or returns something unexpected, refine and retry (max 3 attempts).
4. Create a reply DRAFT with `gmail_create_draft`, in-thread, answering in plain English with the actual numbers. Include the figures, not the SQL, unless the sender asked to see the query.
5. Sign "— Deep Agent (assistant)".

Never send mail. Drafts only.
