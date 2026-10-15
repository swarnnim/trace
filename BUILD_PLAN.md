# Trace — Build plan (Oct 15–18, 2026)

> Hackathon window: Thu Oct 15 00:01 → Sun Oct 18 23:59 IST. All work below is
> new implementation written during the event (per rules). Prep (scaffold,
> architecture, dataset spec, smoke test) is done.

## Thu Oct 15 — Memory layer + ingestion

- `memory/store.py`: FalkorDBLite connection (path-persisted), named-graph helpers (`company`, `mem_<user>`, `blackboard`), index creation (vector + fulltext).
- `memory/ingest.py` + `demo_data/loader.py`: load DATASET_SPEC (15 people, 8 projects, 13 docs, 8 decisions, episodes, beliefs) as Cypher.
- `memory/episodic.py`, `memory/semantic.py`: remember/recall, belief contradiction handling.
- `tests/test_memory.py`: round-trip + contradiction tests green.
- **Definition of done:** loader runs end-to-end; `MATCH (n) RETURN count(n)` shows the full dataset; all memory tests pass.

## Fri Oct 16 — Agent reasoning + multi-agent blackboard

- `agent/tools.py`: CypherTool, ShortestPathTool, PageRankTool, VectorSearchTool, FulltextTool (all return the traversed path, not just the answer).
- `agent/loop.py`: question classifier (memory / blast-radius / who-decided / who-knows) → tool chain → answer.
- `agent/explain.py`: path → evidence-chain rendering ("Because: … → … → …").
- `agent/llm.py`: MockLLM (template composer, $0, offline) as default; env-gated real adapter stub.
- `agent/cli.py`: REPL with `ask`, `remember`, `explain`, `demo` commands.
- `memory/blackboard.py`: Task/Finding primitives; two demo agents (planner, researcher) coordinating on one question.
- `tests/test_agent.py`: tool outputs + explanation rendering green.
- **Definition of done:** all 6 demo questions from DATASET_SPEC answer correctly in the CLI, each with a printed reasoning path; blackboard demo runs with 2 agents.

## Sat Oct 17 — Web UI + explainability

- `web/app.py` (Flask): `/` ask box; answer card + expandable "How I got this" path visualization (rendered as a node→edge→node chain, no JS framework needed); `/remember` quick-add; `/graph` counts per label.
- Polish: clean dark UI, demo-friendly. Mobile-usable.
- Dry-run the 5-part demo script from ARCHITECTURE.md; fix rough edges.
- **Definition of done:** full demo script runs in the browser end-to-end without touching the CLI; every answer shows its path.

## Sun Oct 18 — Demo video, README, submission

- Morning: record the 3-minute demo video (screen capture of web UI following the demo script; voiceover optional).
- README: final quickstart, architecture summary, tracks mapping table, "what the graph does" section.
- Blog post draft (AirPods 5 side prize): "Why I put my agent's memory in a graph" — publish on DEV/Hashnode, link in submission.
- Afternoon: `git` history tidy; submit on WeMakeDevs before 21:00 IST (buffer before the 23:59 deadline): repo link, README, demo video, deployment notes (local run; note FalkorDBLite = zero-infra).
- **Definition of done:** submission shows "submitted" on WeMakeDevs; repo public with green tests; video + blog linked.

## Cross-cutting rules

- $0: no paid APIs, no cloud services in the demo path. MockLLM default.
- No secrets in repo (`.env` gitignored; nothing to commit anyway).
- Every claim in README/blog about FalkorDB performance: use our own measured numbers or none — never marketing benchmarks.
- If time runs short, cut in this order: blog post → web UI polish → blackboard demo → (never cut: loader, 6 demo questions, explainability paths).
