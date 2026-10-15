"""Tests for the Trace agent layer (Day 2, event work).

Isolation: all tests run against a scratch Store on a pytest tmp_path RDB.
The company dataset is (re)built via demo_data.loader.load_all(store).
Nothing touches the default data/trace.rdb.
"""

import pytest

from memory.store import Store, COMPANY_GRAPH, BLACKBOARD_GRAPH
from agent.tools import GraphTools
from agent.explain import render_path, render_answer
from agent.llm import MockLLM, get_llm
from agent.loop import AgentLoop
from memory.blackboard import Blackboard
from demo_data.loader import load_all


@pytest.fixture()
def store(tmp_path):
    s = Store(db_path=str(tmp_path / "agent_test.rdb"))
    load_all(s)
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def tools(store):
    return GraphTools(store, user="sam")


# ---------------------------------------------------------------- tools ---
class TestGraphTools:
    def test_shortest_path_checkout_to_postgres(self, tools):
        ans, path = tools.shortest_path(
            "Project", "Checkout API", "System", "Postgres", ["DEPENDS_ON"]
        )
        assert "Checkout API" in ans and "Postgres" in ans
        assert len(path) == 2, f"expected 2 hops, got {path}"
        assert path[0]["rel"] == "DEPENDS_ON"
        assert path[1]["to"]["name"] == "Postgres"

    def test_shortest_path_none(self, tools):
        ans, path = tools.shortest_path(
            "Person", "Farah Sheikh", "System", "Kafka", ["KNOWS"]
        )
        assert path == []

    def test_pagerank_runs(self, tools):
        ans, path = tools.pagerank("Person", "KNOWS", top_n=5)
        assert "Ananya Das" in ans or "Vikram Rao" in ans

    def test_fulltext_finds_ledger_docs(self, tools):
        ans, path = tools.fulltext("Doc", "summary", "ledger", top_n=5)
        assert "postmortem" in ans.lower() or "Ledger" in ans

    def test_vector_search_returns_hits(self, tools):
        ans, path = tools.vector_search("Doc", "summary", "payments outage", top_n=3)
        assert ans and "distance" in ans

    def test_cypher_compact(self, tools):
        ans, path = tools.cypher(
            "MATCH (p:Person) RETURN p.name LIMIT 3", graph="company"
        )
        assert "Priya Nair" in ans

    def test_tools_never_raise(self, tools):
        ans, path = tools.cypher("THIS IS NOT CYPHER", graph="company")
        assert "Tool error" in ans and path == []


# ---------------------------------------------------------------- explain -
class TestExplain:
    def test_render_path_format(self):
        path = [
            {"from": {"label": "Person", "name": "Priya Nair"},
             "rel": "MADE",
             "to": {"label": "Decision", "name": "Pause Project Helios"}},
            {"from": {"label": "Decision", "name": "Pause Project Helios"},
             "rel": "DECIDED_IN",
             "to": {"label": "Doc", "name": "Helios pause RFC"}},
        ]
        out = render_path(path)
        assert "Because:" in out
        assert "Priya Nair" in out and "MADE" in out and "Helios pause RFC" in out

    def test_render_path_empty(self):
        assert "no graph traversal" in render_path([]).lower()

    def test_render_answer_combines(self):
        out = render_answer("42.", [])
        assert "42." in out


# ------------------------------------------------------------------- llm --
class TestLLM:
    def test_mock_composes(self):
        llm = get_llm()
        assert isinstance(llm, MockLLM)
        out = llm.compose(
            "Who knows Redis best?",
            [{"tool": "pagerank", "answer": "Ananya Das (0.9)", "path": []}],
        )
        assert "Ananya Das" in out

    def test_mock_empty(self):
        out = MockLLM().compose("xyz", [])
        assert "couldn't find" in out.lower() or "nothing" in out.lower()


# ------------------------------------------------------------------ loop --
DEMO_QA = [
    ("If the ledger service goes down, what breaks?",
     ["Checkout API", "Helios"]),
    ("Who decided to pause Helios, and why?",
     ["Priya Nair", "Helios pause RFC"]),
    ("Who knows Redis best?",
     ["Ananya Das"]),
    ("What did we discuss about the payments outage?",
     ["Redis failover", "Dev"]),
    ("Is the Postgres upgrade done?",
     ["No", "proposed"]),
    ("What breaks if Redis goes down?",
     ["Ledger Service", "Checkout API", "Helios"]),
]

CLASSIFY_EXPECT = {
    "If the ledger service goes down, what breaks?": "blast_radius",
    "Who decided to pause Helios, and why?": "who_decided",
    "Who knows Redis best?": "who_knows",
    "What did we discuss about the payments outage?": "memory",
    "Is the Postgres upgrade done?": "status",
}


class TestLoop:
    def test_classify(self, store):
        loop = AgentLoop(store=store)
        for q, expected in CLASSIFY_EXPECT.items():
            assert loop.classify(q) == expected, q

    @pytest.mark.parametrize("question,needles", DEMO_QA)
    def test_demo_questions(self, store, question, needles):
        loop = AgentLoop(store=store)
        answer, path = loop.ask(question)
        for needle in needles:
            assert needle in answer, f"{needle!r} missing in: {answer}"
        assert len(path) > 0, f"empty path for: {question}"
        loop.store.close() if False else None

    def test_last_path_set(self, store):
        loop = AgentLoop(store=store)
        loop.ask("Who knows Redis best?")
        assert loop.last_path, "last_path not set"
        assert "Ananya Das" in loop.last_answer


# ------------------------------------------------------------- blackboard -
class TestBlackboard:
    def test_full_handoff(self, store):
        bb = Blackboard(store)
        bb.post_task("t1", "Find the top Redis expert", owner_agent="planner")
        bb.claim_task("t1", "researcher")
        bb.post_finding("researcher", "t1", "pagerank: all tied")
        bb.post_finding("planner", "t1", "final: Ananya Das")
        bb.complete_task("t1")
        assert bb.list_open_tasks() == []
        findings = bb.task_findings("t1")
        assert len(findings) == 2
        assert findings[0]["agent"] == "researcher"
        chain = bb.handoff_chain("t1")
        assert len(chain) >= 3
        rels = {s["rel"] for s in chain}
        assert {"CLAIMED", "POSTED", "ABOUT"} <= rels

    def test_errors(self, store):
        bb = Blackboard(store)
        with pytest.raises(ValueError):
            bb.claim_task("nope", "researcher")
        with pytest.raises(ValueError):
            bb.post_task("", "empty id")
        bb.post_task("t9", "x")
        bb.complete_task("t9")
        with pytest.raises(ValueError):
            bb.claim_task("t9", "researcher")
