# Trace — a graph-native memory agent

> Hackathon submission for **Graph Hacks: Context for AI Agents** (WeMakeDevs × FalkorDB, Oct 15–18, 2026).

Trace is a research agent whose entire memory lives in [FalkorDB](https://www.falkordb.com/).
Episodic memory (what happened), semantic memory (what is true), and a multi-agent
blackboard are all nodes and edges — not flat vector chunks. When asked a question,
the agent traverses the graph, and **every answer ships with the exact path it
followed**, so the reasoning is inspectable instead of a black box.

## Tracks entered

| Track | How Trace qualifies |
|---|---|
| 01 — Agents That Act on Connected Data | Multi-hop Cypher traversals + graph algorithms (`shortestPath`, `algo.pageRank`) exposed as agent tools; the agent acts on what the graph shows |
| 02 — Agent Memory and Coordination | Episodic + semantic memory persisted across sessions in per-user named graphs; two agents coordinate via a shared blackboard graph |
| 03 — Company Brain | Fictional-company demo answers "who knows what / who decided what / what breaks if X changes", every answer traced to its evidence chain |

## Quickstart

Requirements: Python 3.12+, no Docker, no API keys, no network — everything runs
locally via embedded FalkorDB (FalkorDBLite). $0.

```bash
# 1. environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. load the fictional "Northwind Labs" dataset (idempotent — safe to re-run)
.venv/bin/python -m demo_data.loader

# 3a. CLI
.venv/bin/python -m agent.cli
# trace> ask If the ledger service goes down, what breaks?
# trace> ask Who decided to pause Helios, and why?
# trace> remember We agreed to revisit the Redis plan next sprint.
# trace> explain        # re-print the evidence chain for the last answer
# trace> demo           # runs the 6 demo questions
# trace> quit

# 3b. web UI (http://127.0.0.1:5000)
.venv/bin/python -m web.app
# /            ask box + expandable "How I got this" evidence chain
# /remember    store a note as episodic memory
# /graph       live node/relationship counts per graph
# /blackboard  run the 2-agent (planner + researcher) coordination demo
```

## Demo questions (all answered with evidence chains)

1. `If the ledger service goes down, what breaks?` — blast-radius traversal
2. `Who decided to pause Helios, and why?` — decision provenance + motivation
3. `Who knows Redis best?` — PageRank + authorship + episodic evidence
4. `What did we discuss about the payments outage?` — cross-session recall
5. `Is the Postgres upgrade done?` — status guard (proposed ≠ accepted)
6. `What breaks if Redis goes down?` — dependency blast radius

## The graph data model

Three named graphs on one embedded instance: `trace_company` (shared company
brain), `trace_mem_<user>` (per-user memory), `trace_blackboard` (agent
coordination).

**Company-brain nodes:** `Person` (name, role, team, email, skills), `Project`
(name, status, owner, started), `Doc` (title, kind, author, date, summary),
`Decision` (title, date, summary, status), `System` (name, kind, criticality),
`Topic` (skill/domain tag).

**Company-brain relationships:** `WORKS_ON`, `LEADS`, `AUTHORED`, `ABOUT`,
`MADE`, `DECIDED_IN`, `AFFECTS`, `DEPENDS_ON`, `KNOWS`, `REPORTS_TO`,
`SUPERSEDES`, `MENTIONS`.

**Memory nodes:** `Episode` (id, text, ts, kind), `Entity` (name, kind),
`Belief` (id, text, confidence, ts, source).

**Memory relationships:** `INVOLVES` (episode → entity), `FOLLOWS` (temporal
episode chain), `ABOUT` (episode → topic), `CONTRADICTS` (new belief → old
belief; old beliefs are **kept**, never deleted), `SUPPORTS` (corroboration).

**Blackboard nodes/relationships:** `Agent`, `Task` (id, title, status,
owner_agent, ts), `Finding` (id, text, ts, agent); `CLAIMED`, `BLOCKED_BY`,
`POSTED`, `ABOUT`. Handoffs between agents are edges, not messages.

## The Cypher the product depends on

Every query below is in the codebase (`agent/tools.py`, `agent/loop.py`,
`memory/*.py`); nothing here is aspirational.

- **Multi-hop dependency traversal** — `MATCH (x:Project)-[:DEPENDS_ON*1..3]->(t)`
  powers the blast-radius answers ("what breaks if X goes down").
- **Directed `shortestPath()`** — the explainability engine: each answer's
  evidence chain is a real shortest path between the entities involved.
- **`CALL algo.pageRank(label, reltype)`** — ranks people by centrality on the
  `KNOWS` skill graph for "who knows X best" (with an honesty fallback when
  scores tie — see below).
- **`CALL db.idx.fulltext.queryNodes(...)`** (BM25) — keyword search over docs,
  decisions, and episodes, with a `CONTAINS` fallback if the index is missing.
- **`CALL db.idx.vector.queryNodes(...)`** (HNSW) — similarity search over
  embeddings, with a Python-side cosine scan fallback.
- **Named graphs as tenants** — `trace_mem_<user>` gives per-user memory
  isolation with zero extra code, FalkorDB's multigraph model.
- **Parameterized, identifier-sanitized Cypher** — all tool inputs go through
  an identifier allowlist; user text only ever reaches `$params`.

## Architecture

```
agent/
  loop.py    question classifier → tool chain → composed answer + path
  tools.py   GraphTools: cypher / shortest_path / pagerank / vector_search / fulltext
             (every tool returns (answer, path); never raises)
  llm.py     MockLLM default (deterministic, template-based); real-LLM adapter is a stub
  explain.py path → human-readable "Because: … → … → …" evidence chain
  cli.py     REPL: ask | remember | explain | demo | quit
memory/
  store.py   FalkorDBLite connection (path-persisted RDB), named-graph helpers, indexes
  ingest.py  MERGE-based idempotent writers (company + memory)
  episodic.py remember/recall with FOLLOWS temporal chains
  semantic.py beliefs with confidence + CONTRADICTS revision history
  blackboard.py Task/Finding coordination primitives + 2-agent demo
web/
  app.py     Flask: / (ask), /remember, /graph (live counts), /blackboard (demo)
demo_data/
  northwind.py  fictional "Northwind Labs": 15 people, 8 projects, 13 docs, 8 decisions
  loader.py     Cypher loader (re-runnable)
tests/       39 tests, all green (memory round-trips, contradiction handling,
             tool outputs, explanation rendering, web routes)
```

## Honesty notes

- **No real LLM in the demo path.** `MockLLM` is a deterministic template
  composer — it never invents facts; it only stitches tool outputs. The real-LLM
  adapter (`RealLLMAdapter`) is a stub that refuses to run without
  `TRACE_LLM_API_KEY`.
- **Embeddings are demo-grade, not neural.** `vector_search` uses a
  deterministic hashed char-3-gram vector (64-dim, L2-normalized) — purely
  lexical similarity, offline and $0. It finds docs that *share text patterns*
  with your query, not semantic meaning. Swap `embed_text()` for a real model
  when online.
- **Question classification is rule-based**, not an LLM router — keyword rules
  in `agent/loop.py`. It works on the demo questions; it is not general NLU.
- **No performance claims.** We make no benchmark or latency claims — FalkorDB
  marketing numbers are not cited anywhere in this repo.
- **The dataset is fictional.** Northwind Labs, its people, and its decisions
  are invented for the demo.

## AI-assistant disclosure

Per the hackathon rules: AI coding assistants were used to implement this
project. Concretely: the human submitter designed the concept, the data model,
the demo questions, and the day-by-day build plan, and directed every stage of
the work. AI assistants wrote the implementation code, the tests, and the
documentation under that direction. The submitter ran the full test suite
(39/39 green), executed the demo flows end-to-end in both the CLI and the web
UI, and can explain the code, the graph model, the Cypher queries, and the
architecture — the design decisions, including the honesty trade-offs above,
are the submitter's own.

## Layout

```
agent/        reasoning loop, graph tools, mock LLM, explainer, CLI
memory/       store, ingestion, episodic/semantic memory, blackboard
web/          Flask UI
demo_data/    fictional dataset + loader (DATASET_SPEC.md describes it)
tests/        pytest suite
ARCHITECTURE.md  data model + module responsibilities (pre-event design)
BUILD_PLAN.md    day-by-day build log
BLOG_POST.md     "Why I put my agent's memory in a graph" (side-prize entry)
```
