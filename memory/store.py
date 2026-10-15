"""Trace memory store — FalkorDB connection and named-graph helpers.

Embedded FalkorDB (via the `redislite` wheel), path-persisted by default so the
RDB survives process restarts. Named graphs:

  trace_company      shared company-brain graph
  trace_mem_<user>   per-user episodic/semantic memory
  trace_blackboard   multi-agent blackboard
"""

import os

from redislite import FalkorDB

COMPANY_GRAPH = "trace_company"
BLACKBOARD_GRAPH = "trace_blackboard"


def user_graph_name(user: str) -> str:
    return f"trace_mem_{user}"


class Store:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "trace.rdb",
            )
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._db = FalkorDB(db_path)

    # -- named graphs -----------------------------------------------------
    def graph(self, name: str):
        return self._db.select_graph(name)

    def company(self):
        return self.graph(COMPANY_GRAPH)

    def user_memory(self, user: str):
        return self.graph(user_graph_name(user))

    def blackboard(self):
        return self.graph(BLACKBOARD_GRAPH)

    # -- query ------------------------------------------------------------
    def q(self, graph_name: str, cypher: str, params: dict | None = None) -> list:
        return self.graph(graph_name).query(cypher, params or {}).result_set

    def count_nodes(self, graph_name: str) -> int:
        rows = self.q(graph_name, "MATCH (n) RETURN count(n)")
        return rows[0][0] if rows else 0

    def count_by_label(self, graph_name: str, label: str) -> int:
        rows = self.q(graph_name, f"MATCH (n:{label}) RETURN count(n)")
        return rows[0][0] if rows else 0

    def clear_graph(self, graph_name: str) -> None:
        self.q(graph_name, "MATCH (n) DETACH DELETE n")

    # -- indexes ----------------------------------------------------------
    def ensure_fulltext_index(self, graph_name: str, label: str, *fields) -> None:
        """Create a BM25 full-text index; idempotent (verify live)."""
        g = self.graph(graph_name)
        field_list = ", ".join(f"n.{f}" for f in fields)
        try:
            g.query(f"CREATE FULLTEXT INDEX FOR (n:{label}) ON ({field_list})")
        except Exception as e:
            if "already indexed" not in str(e):
                raise
        # live verification: every requested field must show FULLTEXT on this label
        rows = g.query("CALL db.indexes()").result_set
        for r in rows:
            if r[0] == label and set(fields) <= set(r[1]):
                covered = all("FULLTEXT" in str(r[2].get(f, "")) for f in fields)
                if covered:
                    return
        raise RuntimeError(
            f"Full-text index verification failed for {label}({', '.join(fields)}) "
            f"on graph {graph_name}"
        )

    def ensure_vector_index(
        self, graph_name: str, label: str, field: str, dim: int = 384
    ) -> bool:
        """Best-effort HNSW vector index. Returns True/False, never raises."""
        try:
            g = self.graph(graph_name)
            # skip if an identical vector index already exists
            for r in g.query("CALL db.indexes()").result_set:
                if r[0] == label and field in (r[1] or []):
                    if "VECTOR" in str(r[2].get(field, "")):
                        return True
            g.query(
                f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{field}) "
                f"OPTIONS {{dimension: {dim}, similarityFunction: 'cosine'}}"
            )
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass
