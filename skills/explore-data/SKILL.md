---
name: explore-data
description: Answers questions about the synthetic credit-risk lakehouse (tables raw and features) with read-only DuckDB SQL through the standards-mcp server - row counts, distributions, default rates by segment, missing values, train/test split. Use when the user asks what is in the data, wants a quick profile or a feature idea checked against the data. Do not use to change, export or write data (the lakehouse is read-only), or to train models.
---

# Explore the data

Goal: answer the data question with the smallest correct query, and show the SQL you ran.

## MCP tools
- `mcp__standards-mcp__get_standard` — lakehouse table names and the row cap.
- `mcp__standards-mcp__query_lakehouse` — one read-only DuckDB query per call.

## Procedure
1. If you do not know the columns yet: `query_lakehouse` with `DESCRIBE features` (or `DESCRIBE raw`).
2. Write ONE aggregate query that answers the question. Prefer aggregates over raw rows:
   `SELECT loan_purpose, count(*) n, round(avg(default_12m), 4) default_rate FROM features GROUP BY 1 ORDER BY 3 DESC`
3. The `features` view has a `split` column (`train` / `test`, out-of-time from 2024-10). Mention which split
   you used when it matters.
4. Answer in two parts: the result (small table) and the SQL used.

## Rules
- Only SELECT / WITH / FROM / DESCRIBE / SUMMARIZE. Writes, COPY, ATTACH and multiple statements are rejected
  by the server; do not try to work around that.
- If `truncated` is true, say so and aggregate instead of asking for more rows.
- The data is synthetic. Never present a finding as a fact about real people or a real lender.
