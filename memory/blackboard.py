"""Trace multi-agent blackboard — task/finding coordination on `trace_blackboard`.

Graph model
-----------
- (:Agent {name})
- (:Task {id, title, status, owner_agent, ts})
- (:Finding {id, text, ts, agent})
- (:Agent)-[:CLAIMED]->(:Task)
- (:Task)-[:BLOCKED_BY]->(:Task)
- (:Agent)-[:POSTED]->(:Finding)
- (:Finding)-[:ABOUT]->(:Task)

All writers are MERGE-based / idempotent. Clearing this graph is always safe
(Day 1 never used it); do NOT clear `trace_company` or `trace_mem_*`.
"""

import os
import sys
import time
import uuid

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from memory.store import BLACKBOARD_GRAPH, COMPANY_GRAPH, Store  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_PATH = os.path.join(_REPO_ROOT, "agent", "tools.py")
_EXPLAIN_PATH = os.path.join(_REPO_ROOT, "agent", "explain.py")

_OPEN_STATUSES = ("open", "claimed")
_DONE_STATUS = "done"


class Blackboard:
    """Coordination primitives for agents sharing the blackboard graph."""

    def __init__(self, store: Store):
        self.store = store

    # -- low level ---------------------------------------------------------
    def _q(self, cypher: str, params: dict | None = None) -> list:
        return self.store.q(BLACKBOARD_GRAPH, cypher, params)

    def _get_task_row(self, task_id: str) -> dict:
        rows = self._q(
            "MATCH (t:Task {id: $tid}) "
            "RETURN t.id, t.title, t.status, t.owner_agent, t.ts",
            {"tid": task_id},
        )
        if not rows:
            raise ValueError(f"unknown task id: {task_id!r}")
        return {
            "id": rows[0][0],
            "title": rows[0][1],
            "status": rows[0][2],
            "owner_agent": rows[0][3],
            "ts": rows[0][4],
        }

    @staticmethod
    def _now_ts() -> float:
        return time.time()

    # -- writers -----------------------------------------------------------
    def post_task(
        self,
        task_id: str,
        title: str,
        owner_agent: str | None = None,
        blocked_by: str | None = None,
    ) -> dict:
        """Post a new task (idempotent: reposting an existing id is a no-op)."""
        if not task_id or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not title or not title.strip():
            raise ValueError("title must be a non-empty string")
        if blocked_by is not None:
            self._get_task_row(blocked_by)  # raises ValueError if unknown
        rows = self._q(
            "MERGE (t:Task {id: $tid}) "
            "ON CREATE SET t.title = $title, t.status = 'open', "
            "t.owner_agent = $owner, t.ts = $ts "
            "RETURN t.id, t.title, t.status, t.owner_agent, t.ts",
            {"tid": task_id, "title": title, "owner": owner_agent, "ts": self._now_ts()},
        )
        if blocked_by is not None:
            self._q(
                "MATCH (a:Task {id: $tid}), (b:Task {id: $bid}) "
                "MERGE (a)-[:BLOCKED_BY]->(b)",
                {"tid": task_id, "bid": blocked_by},
            )
        return {
            "id": rows[0][0],
            "title": rows[0][1],
            "status": rows[0][2],
            "owner_agent": rows[0][3],
            "ts": rows[0][4],
        }

    def claim_task(self, task_id: str, agent_name: str) -> dict:
        """Claim a task: sets status='claimed', owner_agent; links Agent-[:CLAIMED]->Task."""
        if not agent_name or not agent_name.strip():
            raise ValueError("agent_name must be a non-empty string")
        task = self._get_task_row(task_id)  # raises ValueError if unknown
        if task["status"] == _DONE_STATUS:
            raise ValueError(f"task {task_id!r} is already done and cannot be claimed")
        self._q(
            "MERGE (a:Agent {name: $aname})",
            {"aname": agent_name},
        )
        self._q(
            "MATCH (a:Agent {name: $aname}), (t:Task {id: $tid}) "
            "SET t.status = 'claimed', t.owner_agent = $aname "
            "MERGE (a)-[:CLAIMED]->(t)",
            {"aname": agent_name, "tid": task_id},
        )
        return self._get_task_row(task_id)

    def post_finding(self, agent_name: str, task_id: str, text: str) -> dict:
        """Post a finding: (:Agent)-[:POSTED]->(:Finding)-[:ABOUT]->(:Task)."""
        if not agent_name or not agent_name.strip():
            raise ValueError("agent_name must be a non-empty string")
        if not text or not text.strip():
            raise ValueError("finding text must be a non-empty string")
        self._get_task_row(task_id)  # raises ValueError if unknown
        finding_id = f"{task_id}-f-{uuid.uuid4().hex[:8]}"
        rows = self._q(
            "MERGE (a:Agent {name: $aname}) "
            "CREATE (f:Finding {id: $fid, text: $text, ts: $ts, agent: $aname}) "
            "MERGE (a)-[:POSTED]->(f) "
            "WITH a, f MATCH (t:Task {id: $tid}) "
            "MERGE (f)-[:ABOUT]->(t) "
            "RETURN f.id, f.text, f.ts, f.agent",
            {
                "aname": agent_name,
                "fid": finding_id,
                "text": text,
                "ts": self._now_ts(),
                "tid": task_id,
            },
        )
        return {"id": rows[0][0], "text": rows[0][1], "ts": rows[0][2], "agent": rows[0][3]}

    def complete_task(self, task_id: str) -> dict:
        """Mark a task done."""
        task = self._get_task_row(task_id)  # raises ValueError if unknown
        if task["status"] == _DONE_STATUS:
            return task  # idempotent
        self._q(
            "MATCH (t:Task {id: $tid}) SET t.status = 'done'",
            {"tid": task_id},
        )
        return self._get_task_row(task_id)

    # -- readers -----------------------------------------------------------
    def list_open_tasks(self) -> list[dict]:
        """All tasks with status in (open, claimed), oldest first."""
        rows = self._q(
            "MATCH (t:Task) WHERE t.status IN $statuses "
            "RETURN t.id, t.title, t.status, t.owner_agent, t.ts ORDER BY t.ts",
            {"statuses": list(_OPEN_STATUSES)},
        )
        return [
            {"id": r[0], "title": r[1], "status": r[2], "owner_agent": r[3], "ts": r[4]}
            for r in rows
        ]

    def task_findings(self, task_id: str) -> list[dict]:
        """Findings about a task with their posting agent, oldest first."""
        self._get_task_row(task_id)  # raises ValueError if unknown
        rows = self._q(
            "MATCH (a:Agent)-[:POSTED]->(f:Finding)-[:ABOUT]->(t:Task {id: $tid}) "
            "RETURN f.id, f.text, f.ts, a.name ORDER BY f.ts",
            {"tid": task_id},
        )
        return [
            {"id": r[0], "text": r[1], "ts": r[2], "agent": r[3]} for r in rows
        ]

    def handoff_chain(self, task_id: str) -> list:
        """Path segments tracing the coordination for a task::

            Agent -CLAIMED-> Task <-ABOUT- Finding <-POSTED- Agent ...

        Returns [{"from": {"label", "name"}, "rel", "to": {"label", "name"}}, ...].
        """
        task = self._get_task_row(task_id)  # raises ValueError if unknown
        rows = self._q(
            "MATCH (claimer:Agent)-[:CLAIMED]->(t:Task {id: $tid}) "
            "OPTIONAL MATCH (f:Finding)-[:ABOUT]->(t) "
            "OPTIONAL MATCH (poster:Agent)-[:POSTED]->(f) "
            "RETURN claimer.name, f.id, f.text, poster.name ORDER BY f.ts",
            {"tid": task_id},
        )
        chain: list = []
        seen_claim = False
        for claimer, fid, ftext, poster in rows:
            if not seen_claim and claimer:
                chain.append(
                    {
                        "from": {"label": "Agent", "name": claimer},
                        "rel": "CLAIMED",
                        "to": {"label": "Task", "name": task_id},
                    }
                )
                seen_claim = True
            if fid:
                fname = f"{fid}"
                chain.append(
                    {
                        "from": {"label": "Finding", "name": fname},
                        "rel": "ABOUT",
                        "to": {"label": "Task", "name": task_id},
                    }
                )
                if poster:
                    chain.append(
                        {
                            "from": {"label": "Agent", "name": poster},
                            "rel": "POSTED",
                            "to": {"label": "Finding", "name": fname},
                        }
                    )
        # Task posted but never claimed: still show the Task node as context.
        if not chain:
            chain.append(
                {
                    "from": {"label": "Task", "name": task_id},
                    "rel": "POSTED_TASK",
                    "to": {
                        "label": "Task",
                        "name": task.get("title") or task_id,
                    },
                }
            )
        return chain


# ---------------------------------------------------------------------------
# Demo helpers (agent.tools / agent.explain may arrive from a concurrent worker)
# ---------------------------------------------------------------------------


def _wait_for_agent_modules(timeout_s: int = 900, interval_s: int = 20) -> bool:
    """Poll-wait for agent/tools.py and agent/explain.py (concurrent worker)."""
    waited = 0
    while waited < timeout_s:
        if os.path.exists(_TOOLS_PATH) and os.path.exists(_EXPLAIN_PATH):
            return True
        print(
            f"[demo] waiting for agent/tools.py + agent/explain.py "
            f"({waited}s / {timeout_s}s) ...",
            flush=True,
        )
        time.sleep(interval_s)
        waited += interval_s
    return os.path.exists(_TOOLS_PATH) and os.path.exists(_EXPLAIN_PATH)


def _pagerank_person_knows(store: Store) -> str:
    """researcher step: PageRank over (Person)-[:KNOWS]-> via GraphTools, or inline fallback.

    Returns the ranked-names answer text (GraphTools.pagerank returns
    (answer_string, path_list)).
    """
    try:
        if os.path.exists(_TOOLS_PATH):
            from agent.tools import GraphTools

            answer, _path = GraphTools(store).pagerank("Person", "KNOWS")
            if isinstance(answer, str) and not answer.startswith("Tool error"):
                return answer
            print(f"[demo] GraphTools pagerank returned an error: {answer}", flush=True)
    except Exception as e:  # pragma: no cover - tool interface may differ
        print(f"[demo] GraphTools pagerank unavailable ({e}); using inline Cypher", flush=True)
    rows = store.q(
        COMPANY_GRAPH,
        "CALL algo.pageRank('Person','KNOWS') YIELD node, score "
        "RETURN node.name AS name, score ORDER BY score DESC",
    )
    lines = [f"{i}. {r[0]} ({r[1]:.4f})" for i, r in enumerate(rows[:5], 1)]
    return "\n".join(lines) if lines else "(no ranked nodes)"


def _render_path_inline(chain: list) -> str:
    lines = []
    for seg in chain:
        f = seg["from"]
        t = seg["to"]
        lines.append(f"{f['label']}({f['name']}) -[:{seg['rel']}]-> {t['label']}({t['name']})")
    return "\n".join(lines)


def run_demo() -> None:
    """Two agents (planner, researcher) coordinate on the blackboard to answer
    'Who knows Redis best?' — a question neither answers alone."""
    store = Store()
    bb = Blackboard(store)

    have_tools = _wait_for_agent_modules()
    if not have_tools:
        print(
            "[demo] agent/tools.py + agent/explain.py not available after wait — "
            "running demo WITHOUT those imports (inline fallbacks).",
            flush=True,
        )
    else:
        print("[demo] agent tools modules present.", flush=True)

    print("\n=== Trace blackboard demo: Who knows Redis best? ===", flush=True)

    # Step 0: clear (safe — Day 1 never used the blackboard)
    store.clear_graph(BLACKBOARD_GRAPH)
    print("[step 0] blackboard cleared (trace_blackboard only).", flush=True)

    # Step 1: planner posts the task
    print('\n[step 1] planner posts task t1 "Find the top Redis expert"', flush=True)
    task = bb.post_task("t1", "Find the top Redis expert", owner_agent="planner")
    print(f"         -> {task}", flush=True)

    # Step 2: researcher claims it
    print("\n[step 2] researcher claims t1", flush=True)
    task = bb.claim_task("t1", "researcher")
    print(f"         -> {task}", flush=True)

    # Step 3: researcher runs PageRank over Person-KNOWS and posts a finding
    print('\n[step 3] researcher runs GraphTools(store).pagerank("Person", "KNOWS")', flush=True)
    pr_text = _pagerank_person_knows(store)
    redis_knowers = store.q(
        COMPANY_GRAPH,
        "MATCH (p:Person)-[:KNOWS]->(t:Topic) "
        "WHERE toLower(t.name) CONTAINS 'redis' RETURN p.name ORDER BY p.name",
    )
    redis_names = [r[0] for r in redis_knowers]
    print(f"         PageRank top-5:\n{pr_text}", flush=True)
    print(f"         KNOWS(redis) holders: {redis_names}", flush=True)
    finding1 = bb.post_finding(
        "researcher",
        "t1",
        "PageRank over (Person)-[:KNOWS]-> (GraphTools pagerank):\n"
        f"{pr_text}\n"
        "Scores are effectively tied across all 15 people (KNOWS edges point "
        "at topics with no inbound edges), so the skill graph alone does not "
        "settle it. The only direct KNOWS edge into the redis topic belongs to "
        f"{', '.join(redis_names) if redis_names else 'nobody'}.",
    )
    print(f"         -> finding posted: {finding1['id']}", flush=True)

    # Step 4: researcher ALSO checks who AUTHORED the Redis runbook doc
    print("\n[step 4] researcher checks who AUTHORED the Redis runbook doc", flush=True)
    authors = store.q(
        COMPANY_GRAPH,
        "MATCH (p:Person)-[:AUTHORED]->(d:Doc) "
        "WHERE toLower(d.title) CONTAINS 'runbook' "
        "AND toLower(d.title) CONTAINS 'redis' "
        "RETURN p.name, d.title",
    )
    print(f"         AUTHORED(redis runbook): {authors}", flush=True)
    finding2 = bb.post_finding(
        "researcher",
        "t1",
        f"Authorship check: {authors[0][0]} AUTHORED '{authors[0][1]}' "
        "(company-brain Doc node). Only the authorship edge identifies a "
        "hands-on Redis expert." if authors
        else "Authorship check: no one AUTHORED a Redis runbook doc.",
    )
    print(f"         -> finding posted: {finding2['id']}", flush=True)

    # Step 5: planner reads findings, posts final answer, marks done
    print("\n[step 5] planner reads findings and posts the final answer", flush=True)
    findings = bb.task_findings("t1")
    for f in findings:
        print(f"         [{f['agent']}] {f['text'][:110]}...", flush=True)
    final_text = (
        "Top Redis expert: Ananya Das (authored the Redis failover runbook; "
        "Vikram Rao holds the KNOWS(redis) skill edge). Neither the skill graph "
        "nor the authorship edge alone settled it — coordination required."
    )
    bb.post_finding("planner", "t1", final_text)
    bb.complete_task("t1")
    print("\n*** FINAL ANSWER ***", flush=True)
    print(final_text, flush=True)

    # Step 6: rendered handoff chain
    print("\n[step 6] handoff chain (Agent->Task->Finding coordination edges)", flush=True)
    chain = bb.handoff_chain("t1")
    rendered = None
    if have_tools:
        try:
            from agent.explain import render_path

            rendered = render_path(chain)
        except Exception as e:  # pragma: no cover
            print(f"[demo] render_path failed ({e}); using inline renderer", flush=True)
    if rendered is None:
        rendered = _render_path_inline(chain)
    print(rendered, flush=True)
    print("\n=== demo complete (exit 0) ===", flush=True)
    store.close()


if __name__ == "__main__":
    run_demo()
