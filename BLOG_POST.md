# Why I put my agent's memory in a graph

*Built for Graph Hacks (WeMakeDevs × FalkorDB) — the project is [Trace](https://github.com/swarnnim/trace), a research agent whose memory is a FalkorDB graph.*

Every agent I've built has had the same two embarrassing failure modes. First, it
forgets. Ask it about the payments outage on Monday, ask again on Thursday, and
it stares at you blankly — the conversation is gone. Second, it can't explain
itself. When it does answer, you get a confident paragraph with no way to check
the work. For a research assistant, those two flaws are fatal.

The standard fix for forgetting is a vector store: chunk everything, embed it,
retrieve by similarity. That solves storage but not structure. "Who decided to
pause Project Helios, and why?" is not a similarity question — it's a
relationship question. The answer lives in a chain: a *person* made a
*decision*, recorded in a *document*, motivated by another *document*. Vectors
don't do chains. Graphs do.

So for this hackathon I put the whole memory in a graph.

## The design

Trace keeps three named graphs on one embedded FalkorDB instance. Named graphs
turned out to be the quiet superpower here: `trace_mem_sam` is my memory,
`trace_company` is the shared company brain, `trace_blackboard` is where agents
coordinate. Tenant isolation with zero extra code — no `WHERE tenant_id = ...`
sprinkled through every query.

**Episodic memory** — what happened — is `Episode` nodes linked by `FOLLOWS`
edges into a temporal chain, with `INVOLVES` links to the people and systems
mentioned. "What did we discuss about the payments outage?" walks the chain and
finds the October 10th episode: root cause was the Redis failover, Dev ran the
runbook. With a timestamp. That's the whole trick of cross-session memory —
it's just a linked list the agent can traverse.

**Semantic memory** — what is true — is `Belief` nodes with confidence scores
and sources. The part I'm proudest of: beliefs are never deleted. When the
team rumor "Helios is cancelled" was corrected to "Helios is paused, not
cancelled," the new belief got a `CONTRADICTS` edge to the old one. The old
node stays. Current beliefs are simply the ones with no incoming `CONTRADICTS`
edge. An agent that can't show you what it used to believe — and why it
changed its mind — doesn't really have memory. It has a cache.

**The blackboard** is how two agents coordinate without messaging each other.
A `planner` posts a task, a `researcher` claims it, findings accumulate as
`Finding` nodes linked by `POSTED` and `ABOUT` edges. The handoff chain is
itself a traversable path. In the demo, neither the skill graph nor the
authorship edge alone could answer "Who knows Redis best?" — PageRank over the
skill graph tied across candidates, which the agent says out loud instead of
pretending the ranking was decisive. The authorship edge (Ananya wrote the
Redis failover runbook) broke the tie. Coordination, not cleverness.

## One question, worked end to end

"Who decided to pause Helios, and why?"

The agent finds the decision with a full-text search, then walks the real
edges and renders this as the answer's evidence chain:

```
Person "Priya Nair" -[MADE]-> Decision "Pause Project Helios"
Decision "Pause Project Helios" -[DECIDED_IN]-> Doc "Helios pause RFC"
Decision "Pause Project Helios" -[AFFECTS]-> Project "Helios"
```

And the "why" comes from the document the decision points to: burn was
unsustainable while the team stabilized the ledger after the September
incident — plus a second doc the traversal surfaced, Zoya's launch retro,
where onboarding leaked 40% of signups. The answer isn't generated and then
justified. The path *is* the answer; the text just narrates it.

My favorite moment in testing was the opposite case: "Is the Postgres upgrade
done?" The decision's status is `proposed`, not `accepted` — and a seeded
memory note says "don't state it as done." The agent answers "No" and cites
both. An agent that reads its own memory as a guardrail against
hallucination is worth more to me than one more point of retrieval recall.

## What FalkorDB specifically made possible

I could have built this on Postgres with a recursive CTE, and for a demo it
would have worked. Three things made the graph database the right call:

1. **Named graphs per user.** Multigraph isolation meant memory, company
   knowledge, and agent coordination live side by side with no tenant plumbing.
2. **`shortestPath()` as an explainability primitive.** The evidence chain
   isn't a feature I bolted on — it's a one-line query. Every answer's "how I
   got this" is a real path, rendered node by node in the UI.
3. **Algorithms as tools.** `CALL algo.pageRank('Person','KNOWS')` turned
   "who knows X best" from a vibes question into a computed ranking — with the
   honest fallback when the math ties.

And pragmatically: FalkorDBLite runs embedded with `pip install`, no Docker,
no server to babysit. The entire demo — database included — runs on a laptop
with zero infrastructure. For a four-day hackathon, that mattered more than
any feature.

## The honest limits

I won't pretend this is a production system. The "LLM" in the demo is a
deterministic template composer — it stitches tool outputs into sentences and
is physically incapable of inventing facts, which is a feature for a demo and
a ceiling for a product. The vector search uses hashed character trigrams,
not neural embeddings: it finds text that *looks* like your query, not text
that *means* it. Question routing is keyword rules, not an LLM classifier. The
company is fictional. The scale is dozens of nodes, not millions.

But the core bet survived contact with reality: when memory is a graph,
remembering and explaining become the same operation — a traversal. The agent
doesn't retrieve context and then reason about it. It reasons *by* traversing.
That's the idea I'd keep, whatever the scale.

---

*Trace was built during Graph Hacks (Oct 15–18, 2026). AI coding assistants
wrote the implementation under my direction; the architecture, data model, and
every design trade-off above are mine. 39/39 tests green, $0 spent.*
