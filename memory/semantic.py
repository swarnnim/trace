"""Semantic memory — what is true.

Belief nodes in the per-user memory graph (trace_mem_<user>) with confidence,
source, and revision history. Old beliefs are NEVER deleted: revisions add
(new)-[:CONTRADICTS]->(old) edges, so the full history stays traversable.

Data model (from ARCHITECTURE.md):
  (:Belief {id, text, confidence, ts, source})
  (:Belief)-[:CONTRADICTS]->(:Belief)   # new contradicts old
  (:Belief)-[:SUPPORTS]->(:Belief)      # corroboration
Current beliefs = those with NO incoming [:CONTRADICTS] edge.

Written during Graph Hacks Day 1 (Oct 15, 2026) — event code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SemanticMemory:
    """Durable beliefs with confidence, sources, and revision history."""

    def __init__(self, store) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # writers
    # ------------------------------------------------------------------
    def _create_belief(
        self, g: str, text: str, confidence: float, source: str, ts: str
    ) -> str:
        bid = uuid4().hex
        self._store.q(
            g,
            "MERGE (b:Belief {id: $id}) "
            "ON CREATE SET b.text = $text, b.confidence = $confidence, "
            "b.ts = $ts, b.source = $source "
            "ON MATCH SET b.text = $text, b.confidence = $confidence, "
            "b.ts = $ts, b.source = $source",
            {
                "id": bid,
                "text": text,
                "confidence": float(confidence),
                "ts": ts,
                "source": source,
            },
        )
        return bid

    def add_belief(
        self,
        user: str,
        text: str,
        confidence: float,
        source: str,
        ts: str | None = None,
    ) -> str:
        """Add a belief; return its id."""
        return self._create_belief(
            _graph_name(user), text, confidence, source, ts or _now_iso()
        )

    def revise_belief(
        self,
        user: str,
        old_text: str,
        new_text: str,
        confidence: float,
        source: str,
        ts: str | None = None,
    ) -> str:
        """Create a new belief contradicting the current belief with exact
        old_text. The old node is KEPT, never deleted. Raises ValueError if
        no current belief matches old_text.
        """
        g = _graph_name(user)
        match = self._store.q(
            g,
            "MATCH (b:Belief) "
            "WHERE NOT ()-[:CONTRADICTS]->(b) AND b.text = $text "
            "RETURN b.id LIMIT 1",
            {"text": old_text},
        )
        if not match:
            raise ValueError(f"no current belief matches: {old_text!r}")
        new_id = self._create_belief(g, new_text, confidence, source, ts or _now_iso())
        self._store.q(
            g,
            "MATCH (n:Belief {id: $new}), (o:Belief {id: $old}) "
            "MERGE (n)-[:CONTRADICTS]->(o)",
            {"new": new_id, "old": match[0][0]},
        )
        return new_id

    def support_belief(
        self,
        user: str,
        belief_text: str,
        supporting_text: str,
        confidence: float,
        source: str,
        ts: str | None = None,
    ) -> str:
        """Create a supporting belief linked via SUPPORTS to the current
        belief with exact belief_text. Raises ValueError if not found.
        """
        g = _graph_name(user)
        match = self._store.q(
            g,
            "MATCH (b:Belief) "
            "WHERE NOT ()-[:CONTRADICTS]->(b) AND b.text = $text "
            "RETURN b.id LIMIT 1",
            {"text": belief_text},
        )
        if not match:
            raise ValueError(f"no current belief matches: {belief_text!r}")
        sup_id = self._create_belief(g, supporting_text, confidence, source, ts or _now_iso())
        self._store.q(
            g,
            "MATCH (s:Belief {id: $sup}), (b:Belief {id: $belief}) "
            "MERGE (s)-[:SUPPORTS]->(b)",
            {"sup": sup_id, "belief": match[0][0]},
        )
        return sup_id

    # ------------------------------------------------------------------
    # readers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "text": row[1],
            "confidence": row[2],
            "ts": row[3],
            "source": row[4],
        }

    def current_beliefs(self, user: str) -> list[dict]:
        """All beliefs with no incoming CONTRADICTS edge (newest first)."""
        rows = self._store.q(
            _graph_name(user),
            "MATCH (b:Belief) WHERE NOT ()-[:CONTRADICTS]->(b) "
            "RETURN b.id, b.text, b.confidence, b.ts, b.source "
            "ORDER BY b.ts DESC",
        )
        return [self._row_to_dict(r) for r in rows]

    def belief_history(self, user: str, text: str) -> list[dict]:
        """Revision history for the belief matching text (any version):
        start at the matched node, then walk outgoing CONTRADICTS edges
        newest -> oldest. Includes the start node itself.
        """
        g = _graph_name(user)
        match = self._store.q(
            g,
            "MATCH (b:Belief {text: $text}) "
            "RETURN b.id ORDER BY b.ts DESC LIMIT 1",
            {"text": text},
        )
        if not match:
            return []
        out: list[dict] = []
        cur = match[0][0]
        while cur:
            rows = self._store.q(
                g,
                "MATCH (b:Belief {id: $id}) "
                "RETURN b.id, b.text, b.confidence, b.ts, b.source",
                {"id": cur},
            )
            if not rows:
                break
            out.append(self._row_to_dict(rows[0]))
            nxt = self._store.q(
                g,
                "MATCH (b:Belief {id: $id})-[:CONTRADICTS]->(o:Belief) "
                "RETURN o.id ORDER BY o.ts DESC LIMIT 1",
                {"id": cur},
            )
            cur = nxt[0][0] if nxt else None
        return out
