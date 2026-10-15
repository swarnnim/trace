"""Web UI tests — Flask test client against an isolated tmp Store.

Written during the Graph Hacks event window (Oct 15, 2026), Day 3.
Isolation: everything runs on a Store pointed at a pytest tmp_path RDB file
seeded by demo_data.loader.load_all(); the default data/trace.rdb is untouched.
"""

import pytest

from web.app import create_app
from memory.store import Store, COMPANY_GRAPH, user_graph_name
from memory.episodic import EpisodicMemory
from demo_data.loader import load_all


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("webtest") / "trace.rdb")
    store = Store(db_path=db_path)
    counts = load_all(store)
    app = create_app(store=store)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, store, counts
    store.close()


def test_index_renders(client):
    c, _store, _counts = client
    r = c.get("/")
    assert r.status_code == 200
    assert b"Ask Trace" in r.data
    assert b'name="question"' in r.data


def test_ask_blast_radius_answer_and_path(client):
    c, _store, _counts = client
    r = c.post("/", data={"question": "If the ledger service goes down, what breaks?"})
    assert r.status_code == 200
    assert b"How I got this" in r.data
    assert b"DEPENDS_ON" in r.data  # path rendered as node->edge->node chain
    assert b"break" in r.data.lower()


def test_ask_memory_recall(client):
    c, _store, _counts = client
    r = c.post("/", data={"question": "What did we discuss about the payments outage?"})
    assert r.status_code == 200
    assert b"How I got this" in r.data
    # seeded payments-outage episode text should surface
    assert b"payments" in r.data.lower()


def test_ask_empty_question_no_crash(client):
    c, _store, _counts = client
    r = c.post("/", data={"question": "   "})
    assert r.status_code == 200
    assert b"Type a question first" in r.data


def test_remember_stores_episode(client):
    c, store, _counts = client
    text = "Web-test episode: ran a payments failover drill at dawn."
    before = store.count_nodes(user_graph_name("sam"))
    r = c.post("/remember", data={"text": text})
    assert r.status_code == 200
    assert b"Remembered" in r.data
    after = store.count_nodes(user_graph_name("sam"))
    assert after == before + 1
    hits = EpisodicMemory(store).search("sam", "failover drill", limit=5)
    assert any("failover drill" in (h.get("text") or "") for h in hits)


def test_graph_counts_match_loader(client):
    c, _store, counts = client
    r = c.get("/graph")
    assert r.status_code == 200
    # loader-seeded company graph: 15 people, 8 projects (DATASET_SPEC)
    assert b"Person" in r.data and b">15<" in r.data
    assert b"Project" in r.data and b">8<" in r.data
    # relationship types present
    assert b"DEPENDS_ON" in r.data
    assert b"trace_company" in r.data


def test_blackboard_demo_two_agents(client):
    c, _store, _counts = client
    r = c.post("/blackboard")
    assert r.status_code == 200
    assert b"planner" in r.data
    assert b"researcher" in r.data
    assert b"CLAIMED" in r.data  # handoff chain rendered
    assert b"Top Redis expert" in r.data
