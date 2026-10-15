"""Tests for the Trace memory layer and demo-data loader.

Written during the Graph Hacks event window (Oct 15, 2026) by Worker C.

Isolation rules enforced here:
- Unit tests run against a Store pointed at a pytest ``tmp_path`` RDB file
  with unique scratch users (``tu_*``). They never touch the default store
  path or the ``trace_company`` / ``trace_mem_sam`` graphs.
- Only ``TestLoaderIntegration`` touches the default store path: it calls
  ``load_all()`` itself in a class-scoped fixture, asserts the expected
  counts, then closes the store.
- Every Store opened here is closed by a fixture finalizer.

Contract assumptions (Workers A/B implement these; flagged, not verified):
  A1. ``EpisodicMemory(store)`` / ``SemanticMemory(store)`` accept the Store
      positionally (required for the tmp-path isolation rule to work).
  A2. ``Store.q()`` returns a list of rows; each row is indexable (list/tuple)
      or a dict. ``_scalar`` handles both.
  A3. ``Episode`` nodes carry a string ``text`` property; ``Belief`` nodes
      carry string ``text``, numeric ``confidence``, string ``source``.
  A4. Temporal chain direction is newer -[:FOLLOWS]-> older.
  A5. ``EpisodicMemory.search(user, query)`` uses the fulltext index on
      ``(Episode, text)`` created via ``Store.ensure_fulltext_index()``.
  A6. ``demo_data.loader.load_all(store)`` accepts an explicit Store and
      (re)builds the full dataset deterministically.
"""

import pytest

from memory.store import Store, COMPANY_GRAPH, user_graph_name
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from demo_data.loader import load_all


def _scalar(rows):
    """First cell of the first row of a Store.q() result."""
    assert rows, "expected at least one result row"
    row = rows[0]
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


@pytest.fixture()
def store(tmp_path):
    """Fresh Store on a temporary RDB path; closed after the test."""
    s = Store(db_path=str(tmp_path / "test.rdb"))
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Store unit tests
# ---------------------------------------------------------------------------

def test_store_roundtrip(store):
    g = "t_roundtrip"
    store.q(g, "CREATE (:Person {name: $name})", {"name": "T"})
    rows = store.q(g, "MATCH (p:Person {name: 'T'}) RETURN p.name")
    assert _scalar(rows) == "T"


def test_store_clear_and_count(store):
    g = "t_clear"
    store.q(g, "CREATE (:Person {name: 'A'}), (:Person {name: 'B'})")
    assert store.count_nodes(g) == 2
    store.clear_graph(g)
    assert store.count_nodes(g) == 0


def test_fulltext_search(store):
    user = "tu_ft1"
    g = user_graph_name(user)
    store.ensure_fulltext_index(g, "Episode", "text")

    em = EpisodicMemory(store)
    hit = "tu_ft1 quantum tunneling observed in the Zurich lab"
    miss = "tu_ft1 standup notes about the office coffee machine"
    em.remember(user, hit, ts="2026-10-15T09:00:00+05:30")
    em.remember(user, miss, ts="2026-10-15T09:05:00+05:30")

    texts = [r["text"] for r in em.search(user, "quantum tunneling")]
    assert hit in texts
    assert miss not in texts


# ---------------------------------------------------------------------------
# Episodic memory unit tests
# ---------------------------------------------------------------------------

def test_episodic_order(store):
    em = EpisodicMemory(store)
    user = "tu_ep1"
    x1 = "tu_ep1 first memory alpha"
    x2 = "tu_ep1 second memory beta"
    x3 = "tu_ep1 third memory gamma"
    eid1 = em.remember(user, x1, ts="2026-10-15T09:00:00+05:30")
    assert isinstance(eid1, str) and eid1
    em.remember(user, x2, ts="2026-10-15T10:00:00+05:30")
    em.remember(user, x3, ts="2026-10-15T11:00:00+05:30")

    # newest-first
    rec = em.recall_recent(user, limit=10)
    assert [d["text"] for d in rec] == [x3, x2, x1]

    # raw chain check: t3 -[:FOLLOWS]-> t2 -[:FOLLOWS]-> t1
    g = user_graph_name(user)
    rows = store.q(
        g,
        "MATCH (a:Episode)-[:FOLLOWS]->(b:Episode)-[:FOLLOWS]->(c:Episode) "
        "WHERE a.text = $x3 AND b.text = $x2 AND c.text = $x1 "
        "RETURN count(*)",
        {"x3": x3, "x2": x2, "x1": x1},
    )
    assert _scalar(rows) == 1


def test_episodic_topic_involves(store):
    em = EpisodicMemory(store)
    user = "tu_ep2"
    e1 = "tu_ep2 discussed the payments outage postmortem"
    e2 = "tu_ep2 redis failover runbook review"
    e3 = "tu_ep2 checkout latency traced to ledger lock contention"
    em.remember(user, e1, topics=("payments",), involves=("Dev",))
    em.remember(user, e2, topics=("redis",), involves=("Ananya",))
    em.remember(user, e3, topics=("payments",), involves=("Vikram",))

    payments = {d["text"] for d in em.recall_about_topic(user, "payments")}
    assert payments == {e1, e3}
    redis = {d["text"] for d in em.recall_about_topic(user, "redis")}
    assert redis == {e2}

    dev = {d["text"] for d in em.recall_involving(user, "Dev")}
    assert dev == {e1}
    vikram = {d["text"] for d in em.recall_involving(user, "Vikram")}
    assert vikram == {e3}


# ---------------------------------------------------------------------------
# Semantic memory unit tests
# ---------------------------------------------------------------------------

def test_semantic_add_current(store):
    sm = SemanticMemory(store)
    user = "tu_sem1"
    text = "tu_sem1 Ledger Service is the payments single source of truth"
    sm.add_belief(user, text, 0.95, "D4")

    cur = sm.current_beliefs(user)
    by_text = {b["text"]: b for b in cur}
    assert text in by_text
    assert by_text[text]["confidence"] == 0.95
    assert by_text[text]["source"] == "D4"


def test_semantic_revision_keeps_old(store):
    sm = SemanticMemory(store)
    user = "tu_sem2"
    old = "tu_sem2 Helios is cancelled"
    new = "tu_sem2 Helios is paused, not cancelled"
    sm.add_belief(user, old, 0.3, "chat")
    sm.revise_belief(user, old, new, 0.95, "D1")

    g = user_graph_name(user)

    # old node still exists in the DB
    rows = store.q(g, "MATCH (b:Belief {text: $t}) RETURN count(b)", {"t": old})
    assert _scalar(rows) == 1

    # CONTRADICTS edge new -> old
    rows = store.q(
        g,
        "MATCH (n:Belief {text: $nt})-[:CONTRADICTS]->(o:Belief {text: $ot}) "
        "RETURN count(*)",
        {"nt": new, "ot": old},
    )
    assert _scalar(rows) == 1

    # current beliefs contain the new text, not the old
    cur_texts = [b["text"] for b in sm.current_beliefs(user)]
    assert new in cur_texts
    assert old not in cur_texts

    # history newest-first: [new, old]
    hist = sm.belief_history(user, new)
    assert [h["text"] for h in hist] == [new, old]


def test_semantic_support(store):
    sm = SemanticMemory(store)
    user = "tu_sem3"
    a = "tu_sem3 Checkout API depends on Ledger Service"
    s = "tu_sem3 D4 declares the single-writer ledger"
    sm.add_belief(user, a, 1.0, "D4")
    sm.support_belief(user, a, s, 0.9, "D4")

    # SUPPORTS edge supporting -> supported
    g = user_graph_name(user)
    rows = store.q(
        g,
        "MATCH (sup:Belief {text: $st})-[:SUPPORTS]->(bel:Belief {text: $at}) "
        "RETURN count(*)",
        {"st": s, "at": a},
    )
    assert _scalar(rows) == 1

    cur_texts = [b["text"] for b in sm.current_beliefs(user)]
    assert a in cur_texts
    assert s in cur_texts


# ---------------------------------------------------------------------------
# Loader integration tests — the ONLY tests touching the default store path
# ---------------------------------------------------------------------------

class TestLoaderIntegration:
    @pytest.fixture(scope="class")
    def loaded(self):
        s = Store()  # default db path
        try:
            counts = load_all(s)
            yield s, counts
        finally:
            s.close()

    def test_loader_counts(self, loaded):
        _, counts = loaded
        assert counts["company_nodes"] == 74
        assert counts["person"] == 15
        assert counts["project"] == 8
        assert counts["doc"] == 13
        assert counts["decision"] == 8

    def test_loader_mem_counts(self, loaded):
        store, _ = loaded
        g = user_graph_name("sam")
        assert store.count_by_label(g, "Episode") == 10
        assert store.count_by_label(g, "Belief") == 7
