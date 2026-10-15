# Trace — Architecture

> Pre-event design doc. The FalkorDB implementation (ingestion, queries, agent
> tools) is written during the event window (Oct 15–18); this doc fixes the
> data model and module boundaries now.

## Concept

Trace is a research agent with **graph-native memory**. Instead of a vector
store of flat chunks, everything the agent learns becomes nodes and edges in
FalkorDB. When asked a question, the agent traverses the graph — and every
answer ships with the exact path it followed, so the reasoning is inspectable.

## Data model

### Company-brain subgraph (demo dataset, one shared graph `trace_company`)

**Node labels**

| Label | Key properties |
|---|---|
| `Person` | name, role, team, email, skills[] |
| `Project` | name, status (active/paused/shipped), owner, started |
| `Doc` | title, kind (spec/rfc/postmortem/notes), author, date, summary |
| `Decision` | title, date, summary, status (proposed/accepted/reverted) |
| `System` | name, kind (service/db/queue), criticality |
| `Topic` | name (skill/domain tag, e.g. "payments", "oncall") |

**Relationship types**

| Type | From → To | Meaning |
|---|---|---|
| `WORKS_ON` | Person → Project | staffing |
| `LEADS` | Person → Project | ownership |
| `AUTHORED` | Person → Doc | authorship |
| `ABOUT` | Doc → Project \| System | subject |
| `MADE` | Person → Decision | who decided |
| `DECIDED_IN` | Decision → Doc | recorded where |
| `AFFECTS` | Decision → Project \| System | impact |
| `DEPENDS_ON` | Project → System \| Project → Project | dependency |
| `KNOWS` | Person → Topic | expertise |
| `REPORTS_TO` | Person → Person | org chart |
| `SUPERSEDES` | Doc → Doc | version chain |
| `MENTIONS` | Doc → Person \| Topic | extracted reference |

### Memory subgraph (per-user named graphs `trace_mem_<user>`)

**Episodic memory** — what happened:

- `(:Episode {text, ts, kind})` — a single remembered event/observation
- `(:Episode)-[:INVOLVES]->(:Entity {name, kind})` — people/projects/systems referenced
- `(:Episode)-[:FOLLOWS]->(:Episode)` — temporal chain per user
- `(:Episode)-[:ABOUT]->(:Topic)` — semantic tagging

**Semantic memory** — what is true:

- `(:Belief {text, confidence, ts, source})` — durable facts/preferences
- `(:Belief)-[:CONTRADICTS]->(:Belief)` — belief revision (old beliefs kept, not deleted)
- `(:Belief)-[:SUPPORTS]->(:Belief)` — corroboration

**Multi-agent blackboard** (shared graph `trace_blackboard`):

- `(:Task {id, title, status, owner_agent})`
- `(:Agent {name})-[:CLAIMED]->(:Task)`, `(:Task)-[:BLOCKED_BY]->(:Task)`
- `(:Finding {text, ts})-[:ABOUT]->(:Task)`, `(:Agent)-[:POSTED]->(:Finding)`
- Agents coordinate by reading/writing the blackboard; handoffs are edges, not messages.

## FalkorDB features → tracks

| Feature | Track | Use |
|---|---|---|
| Multi-hop Cypher (`-[*1..4]-`) | 01 | "Who worked on a system that Project X depends on?" |
| `shortestPath()` (directed, WITH/RETURN form) | 01, 03 | Explainability: the exact reasoning path behind each answer |
| `algo.pageRank(label, reltype)` | 01 | "Who is the most central expert on payments?" |
| `algo.betweenness` / WCC | 01 | Bottleneck people; disconnected knowledge islands |
| HNSW vector index on `Doc.summary` / `Episode.text` | 02 | Hybrid retrieval: vector similarity → graph expansion |
| BM25 full-text index | 02, 03 | Keyword search over docs/decisions |
| Named graphs per user (`trace_mem_<user>`) | 02 | Tenant isolation with zero extra code |
| Redis KV alongside graph | 02 | Session cursors, rate counters |

Verified dialect notes (smoke-tested 2026-10-14): import is
`from redislite import FalkorDB`; `shortestPath` must be directed and used as
`RETURN shortestPath((a)-[*]->(c))`; `algo.pageRank` needs `(label, reltype)`
args; vector index option is camelCase `similarityFunction`; vector search
returns cosine distance (0.0 = identical, `ORDER BY score ASC`).

## Module responsibilities

```
agent/
  cli.py          # REPL: ask, remember, explain; demo script runner
  loop.py         # reason→act loop: classify question → pick graph tools → compose answer + path
  tools.py        # GraphTool wrappers: cypher(), shortest_path(), pagerank(), vector_search(), fulltext()
  llm.py          # LLM interface; MockLLM (template-based, $0, offline) default;
                  # optional real-LLM adapter behind env var, never required
  explain.py      # path → human-readable "why": renders traversed nodes/edges as evidence chain
memory/
  store.py        # FalkorDB connection (Lite embedded, path-persisted); named-graph helpers
  ingest.py       # dataset + episode/belief writers (EVENT WORK)
  episodic.py     # remember/recall episodes, temporal chains
  semantic.py     # beliefs with confidence + contradiction handling
  blackboard.py   # multi-agent task/finding coordination primitives
web/
  app.py          # Flask: /ask (answer + path viz as list), /remember, /graph (node/edge counts)
demo_data/
  DATASET_SPEC.md # fictional company spec (this repo)
  loader.py       # Cypher loader (EVENT WORK)
tests/
  test_memory.py  # store round-trip, contradiction handling (EVENT WORK)
  test_agent.py   # tool outputs, explanation rendering (EVENT WORK)
```

## Demo script outline (the 3-minute video)

1. **Setup (15s):** "Trace remembers across sessions." Ask: *"What did we discuss about the payments outage?"* → answer cites a prior-session `Episode` with timestamp.
2. **Track 01 (45s):** *"If the ledger service goes down, what breaks?"* → multi-hop `DEPENDS_ON` traversal + PageRank-ordered blast radius; answer lists affected projects with the path shown.
3. **Track 03 (45s):** *"Who decided to pause Project Helios, and why?"* → `Decision` ← `MADE` ← `Person`, `DECIDED_IN` → `Doc`; answer quotes the doc with the full evidence chain.
4. **Track 02 (45s):** Two agents (`planner`, `researcher`) coordinate on the blackboard to answer a question neither could alone; handoff edges visible.
5. **Explainability (30s):** Every answer expands to show the Cypher path — "here is exactly how I got this."

## Non-goals (keep it buildable)

- No real LLM API calls in the demo path (MockLLM; real adapter optional).
- No auth/multi-tenancy beyond named graphs.
- No deployment beyond local + clear README (live deploy only if time on Sun).
- No label expressions or exotic Cypher — stick to the verified subset.
