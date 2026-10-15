"""Episodic memory — what happened.

Per-user named graphs (trace_mem_<user>), implemented as Episode nodes with
temporal FOLLOWS chains plus INVOLVES/ABOUT links to Entity/Topic nodes.

Data model (from ARCHITECTURE.md):
  (:Episode {id, text, ts, kind})
  (:Episode)-[:INVOLVES]->(:Entity {name, kind})
  (:Episode)-[:FOLLOWS]->(:Episode)   # new episode points to previous latest
  (:Episode)-[:ABOUT]->(:Topic {name})
Latest episode = the one with NO incoming [:FOLLOWS] edge.

Written during Graph Hacks Day 1 (Oct 15, 2026) — event code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Tuple, Union
from uuid import uuid4

# NOTE: memory.store is owned by Worker A and may not exist yet at import
# time. Import lazily inside _graph_name(); fall back to the documented
# naming convention trace_mem_<user> so this module still works against a
# contract-compatible Store stub.
try:
    from memory.store import user_graph_name as _user_graph_name_fn
except Exception:  # pragma: no cover - store not yet present
    _user_graph_name_fn = None


def _graph_name(user: str) -> str:
    if _user_graph_name_fn is not None:
        try:
            return _user_graph_name_fn(user)
        except Exception:
            pass
    return f"trace_mem_{user}"


InvolvesItem = Union[str, Tuple[str, str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EpisodicMemory:
    """Remember and recall episodes for a user in their named memory graph."""

    def __init__(self, store) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # writers
    # ------------------------------------------------------------------
    def remember(
        self,
        user: str,
        text: str,
        ts: str | None = None,
        kind: str = "note",
        involves: Iterable[InvolvesItem] = (),
        topics: Iterable[str] = (),
    ) -> str:
        """Record an episode; return its id (uuid4 hex).

        involves entries are either ("Name", "kind") tuples or plain names
        (kind defaults to "thing"). The new episode gets a
        -[:FOLLOWS]-> link to the previous latest episode, if any.
        """
        g = _graph_name(user)
        eid = uuid4().hex
        ts = ts or _now_iso()

        self._store.q(
            g,
            "MERGE (e:Episode {id: $id}) "
            "ON CREATE SET e.text = $text, e.ts = $ts, e.kind = $kind "
            "ON MATCH SET e.text = $text, e.ts = $ts, e.kind = $kind",
            {"id": eid, "text": text, "ts": ts, "kind": kind},
        )

        for item in involves:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                name, ekind = item[0], item[1]
            else:
                name, ekind = item, "thing"
            self._store.q(
                g,
                "MERGE (en:Entity {name: $name}) "
                "ON CREATE SET en.kind = $ekind "
                "WITH en "
                "MATCH (e:Episode {id: $id}) "
                "MERGE (e)-[:INVOLVES]->(en)",
                {"name": name, "ekind": ekind, "id": eid},
            )

        for topic in topics:
            self._store.q(
                g,
                "MERGE (t:Topic {name: $name}) "
                "WITH t "
                "MATCH (e:Episode {id: $id}) "
                "MERGE (e)-[:ABOUT]->(t)",
                {"name": topic, "id": eid},
            )

        # Link FOLLOWS to the previous latest episode (exclude self; self
        # is brand new so it would trivially qualify as "latest").
        prev = self._store.q(
            g,
            "MATCH (e:Episode) "
            "WHERE NOT ()-[:FOLLOWS]->(e) AND e.id <> $id "
            "RETURN e.id ORDER BY e.ts DESC LIMIT 1",
            {"id": eid},
        )
        if prev:
            self._store.q(
                g,
                "MATCH (a:Episode {id: $new}), (b:Episode {id: $prev}) "
                "MERGE (a)-[:FOLLOWS]->(b)",
                {"new": eid, "prev": prev[0][0]},
            )
        return eid

    # ------------------------------------------------------------------
    # readers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "text": row[1],
            "ts": row[2],
            "kind": row[3],
            "involves": sorted({n for n in (row[4] or []) if n}),
            "topics": sorted({n for n in (row[5] or []) if n}),
        }

    def _episode_detail(self, g: str, eid: str) -> dict | None:
        rows = self._store.q(
            g,
            "MATCH (e:Episode {id: $id}) "
            "OPTIONAL MATCH (e)-[:INVOLVES]->(en:Entity) "
            "WITH e, collect(en.name) AS names "
            "OPTIONAL MATCH (e)-[:ABOUT]->(t:Topic) "
            "RETURN e.id, e.text, e.ts, e.kind, names, collect(t.name)",
            {"id": eid},
        )
        return self._row_to_dict(rows[0]) if rows else None

    def _walk_chain(self, g: str, limit: int, pred=None) -> list[dict]:
        """Walk the FOLLOWS chain newest-first, optionally filtering episodes."""
        out: list[dict] = []
        latest = self._store.q(
            g,
            "MATCH (e:Episode) "
            "WHERE NOT ()-[:FOLLOWS]->(e) "
            "RETURN e.id ORDER BY e.ts DESC LIMIT 1",
        )
        if not latest:
            return out
        cur = latest[0][0]
        steps = 0
        while cur and len(out) < limit and steps <= limit + 1:
            steps += 1
            det = self._episode_detail(g, cur)
            if det is None:
                break
            if pred is None or pred(det):
                out.append(det)
            nxt = self._store.q(
                g,
                "MATCH (e:Episode {id: $id})-[:FOLLOWS]->(p:Episode) "
                "RETURN p.id LIMIT 1",
                {"id": cur},
            )
            cur = nxt[0][0] if nxt else None
        return out

    def recall_recent(self, user: str, limit: int = 10) -> list[dict]:
        """Newest-first episodes by walking the FOLLOWS chain from latest."""
        return self._walk_chain(_graph_name(user), limit)

    def recall_about_topic(self, user: str, topic: str, limit: int = 10) -> list[dict]:
        """Newest-first episodes tagged ABOUT the given topic."""
        return self._walk_chain(
            _graph_name(user), limit, lambda d: topic in d["topics"]
        )

    def recall_involving(self, user: str, entity_name: str, limit: int = 10) -> list[dict]:
        """Newest-first episodes INVOLVING the given entity."""
        return self._walk_chain(
            _graph_name(user), limit, lambda d: entity_name in d["involves"]
        )

    def search(self, user: str, query: str, limit: int = 10) -> list[dict]:
        """Keyword search over Episode text.

        Tries the Episode(text) full-text index first; degrades gracefully to
        a CONTAINS scan if the index is missing. Never raises for a missing
        index.
        """
        g = _graph_name(user)
        rows = None
        try:
            rows = self._store.q(
                g,
                "CALL db.idx.fulltext.queryNodes('Episode', 'text', $q) "
                "YIELD node AS e "
                "RETURN e.id, e.text, e.ts, e.kind LIMIT $n",
                {"q": query, "n": limit},
            )
        except Exception:
            rows = None
        if not rows:
            rows = self._store.q(
                g,
                "MATCH (e:Episode) WHERE e.text CONTAINS $q "
                "RETURN e.id, e.text, e.ts, e.kind ORDER BY e.ts DESC LIMIT $n",
                {"q": query, "n": limit},
            )
        out: list[dict] = []
        for r in rows[:limit]:
            det = self._episode_detail(g, r[0])
            out.append(det if det else {"id": r[0], "text": r[1], "ts": r[2],
                                       "kind": r[3], "involves": [], "topics": []})
        return out
