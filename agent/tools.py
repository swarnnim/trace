"""Trace graph tools — Cypher, shortest-path, PageRank, vector, full-text.

Every method returns ``(answer: str, path: list)`` and NEVER raises: all
exceptions are caught and returned as ``("Tool error: ...", [])``.

DEMO-GRADE EMBEDDINGS (see ``embed_text``): vector_search does NOT use a real
neural embedding model. It uses a deterministic hashed char-3-gram bucket
vector (64-dim, L2-normalized) so the offline $0 demo has working
similarity search without any network or API key. It is lexical, not
semantic — "payments outage" matches docs that share character trigrams
with that phrase. Swap ``embed_text`` for a real model when online.
"""

import hashlib
import math
import re
import struct

from memory.store import COMPANY_GRAPH, BLACKBOARD_GRAPH, user_graph_name

try:  # falkordb-py path type; duck-typed fallback if import moves
    from falkordb.path import Path as _FalkorPath
except Exception:  # pragma: no cover
    _FalkorPath = None

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(value, what="identifier"):
    if not isinstance(value, str) or not _IDENT.match(value):
        raise ValueError(f"bad {what}: {value!r}")
    return value


def embed_text(text):
    """DEMO-GRADE embedding: hashed char-3-gram buckets -> 64-dim L2 vector.

    Deterministic, offline, $0. NOT a neural/semantic embedding — purely a
    lexical hash for demo retrieval. See module docstring.
    """
    vec = [0.0] * 64
    t = (text or "").lower()
    for i in range(len(t) - 2):
        digest = hashlib.md5(t[i:i + 3].encode("utf-8")).digest()
        vec[struct.unpack("<H", digest[:2])[0] % 64] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def backfill_embeddings(store, graph, label, field):
    """Write ``n.emb = embed_text(n.<field>)`` on nodes missing it.

    Returns the number of nodes written. Idempotent.
    """
    label = _ident(label, "label")
    rows = store.q(
        graph,
        f"MATCH (n:{label}) WHERE n.emb IS NULL AND n.`{field}` IS NOT NULL "
        "RETURN id(n), n.`" + field + "`",
    )
    done = 0
    for row in rows:
        nid, text = row[0], row[1]
        store.q(graph, "MATCH (n) WHERE id(n) = $id SET n.emb = $v",
                {"id": nid, "v": embed_text(text)})
        done += 1
    return done


def _display_name(props):
    props = props or {}
    name = props.get("name") or props.get("title")
    if name:
        return str(name)
    text = props.get("text") or ""
    return str(text)[:40]


def _node_summary(node):
    """Compact ``Label "name"`` for a falkordb Node (duck-typed)."""
    labels = getattr(node, "labels", None) or []
    props = getattr(node, "properties", None) or {}
    label = labels[0] if labels else "Node"
    return f'{label} "{_display_name(props)}"'


def _is_path(obj):
    if _FalkorPath is not None and isinstance(obj, _FalkorPath):
        return True
    # duck-type: has callable nodes()/edges() returning sequences
    nodes = getattr(obj, "nodes", None)
    edges = getattr(obj, "edges", None)
    return callable(nodes) and callable(edges)


def _path_nodes_edges(path):
    nodes = path.nodes() if callable(getattr(path, "nodes", None)) else path.nodes
    edges = path.edges() if callable(getattr(path, "edges", None)) else path.edges
    return list(nodes), list(edges)


def _extract_segments(path):
    """Path -> list of {"from","rel","to"} segment dicts."""
    segments = []
    nodes, edges = _path_nodes_edges(path)
    for i, edge in enumerate(edges):
        if i + 1 >= len(nodes):
            break
        src, dst = nodes[i], nodes[i + 1]
        src_labels = getattr(src, "labels", None) or ["Node"]
        dst_labels = getattr(dst, "labels", None) or ["Node"]
        rel = getattr(edge, "relation", None) or getattr(edge, "type", "")
        segments.append({
            "from": {"label": src_labels[0],
                     "name": _display_name(getattr(src, "properties", None))},
            "rel": str(rel),
            "to": {"label": dst_labels[0],
                   "name": _display_name(getattr(dst, "properties", None))},
        })
    return segments


def _render_cell(cell):
    if cell is None:
        return "null"
    if _is_path(cell):
        nodes, edges = _path_nodes_edges(cell)
        names = [_node_summary(n) for n in nodes]
        out = names[0] if names else ""
        for e, nm in zip(edges, names[1:]):
            rel = getattr(e, "relation", None) or getattr(e, "type", "")
            out += f" -[{rel}]-> {nm}"
        return out
    labels = getattr(cell, "labels", None)
    if labels is not None:  # a Node
        return _node_summary(cell)
    if isinstance(cell, float):
        return f"{cell:.4f}"
    return str(cell)


class GraphTools:
    """Graph-native tool wrappers for the Trace agent."""

    def __init__(self, store, user="sam"):
        self.store = store
        self.user = user

    # -- graph routing --------------------------------------------------
    def _graph(self, graph):
        if graph == "memory":
            return user_graph_name(self.user)
        if graph == "blackboard":
            return BLACKBOARD_GRAPH
        return COMPANY_GRAPH  # "company" and anything else

    # -- generic cypher -------------------------------------------------
    def cypher(self, cypher, params=None, graph="company"):
        """Run parameterized Cypher; compact rendering of up to 10 rows."""
        try:
            rows = self.store.q(self._graph(graph), cypher, params or {})
        except Exception as e:
            return f"Tool error: cypher failed: {e}", []
        lines = []
        path = []
        for row in rows[:10]:
            lines.append(" | ".join(_render_cell(c) for c in row))
            for cell in row:
                if cell is not None and _is_path(cell):
                    path.extend(_extract_segments(cell))
        answer = "\n".join(lines) if lines else "(no rows)"
        return answer, path

    # -- shortest path --------------------------------------------------
    def shortest_path(self, from_label, from_name, to_label, to_name,
                      rel_types=None, max_hops=4, graph="company"):
        """Directed shortest path; answer names endpoints + hop count."""
        try:
            fl = _ident(from_label, "from_label")
            tl = _ident(to_label, "to_label")
            hops = max(1, min(int(max_hops), 10))
            if rel_types:
                rels = "|".join(_ident(r, "rel_type") for r in rel_types)
                pattern = f"(a)-[r:{rels}*1..{hops}]->(b)"
            else:
                pattern = f"(a)-[*1..{hops}]->(b)"
            rows = self.store.q(
                self._graph(graph),
                f"MATCH (a:{fl}), (b:{tl}) "
                "WHERE (a.name = $fn OR a.title = $fn) "
                "AND (b.name = $tn OR b.title = $tn) "
                f"RETURN shortestPath({pattern}) AS p",
                {"fn": from_name, "tn": to_name},
            )
        except Exception as e:
            return f"Tool error: shortest_path failed: {e}", []
        if not rows or rows[0][0] is None:
            return (f"No directed path found from {from_label} "
                    f'"{from_name}" to {to_label} "{to_name}" '
                    f"within {max_hops} hops."), []
        path = _extract_segments(rows[0][0])
        hop_n = len(path)
        answer = (f'Shortest directed path from {from_label} "{from_name}" '
                  f'to {to_label} "{to_name}": {hop_n} hop'
                  f'{"s" if hop_n != 1 else ""}.')
        return answer, path

    # -- pagerank -------------------------------------------------------
    def pagerank(self, label, reltype, top_n=5, graph="company"):
        """CALL algo.pageRank(label, reltype); ranked name (score) list."""
        try:
            label = _ident(label, "label")
            reltype = _ident(reltype, "reltype")
            rows = self.store.q(
                self._graph(graph),
                "CALL algo.pageRank($label, $reltype)",
                {"label": label, "reltype": reltype},
            )
        except Exception:
            try:
                rows = self.store.q(
                    self._graph(graph),
                    f"CALL algo.pageRank('{label}', '{reltype}')",
                )
            except Exception as e:
                return f"Tool error: pagerank failed: {e}", []
        ranked = sorted(rows, key=lambda r: r[1], reverse=True)[:top_n]
        lines = []
        for i, (node, score) in enumerate(ranked, 1):
            props = getattr(node, "properties", None) or {}
            lines.append(f"{i}. {_display_name(props)} ({score:.4f})")
        answer = "\n".join(lines) if lines else "(no ranked nodes)"
        return answer, []

    # -- vector search --------------------------------------------------
    def vector_search(self, label, field, query_text, top_n=5, graph="company"):
        """Similarity search over DEMO-GRADE embeddings (see embed_text).

        Tries the HNSW index first, falls back to a python-side cosine
        scan over backfilled ``n.emb`` vectors (the embedded build's vector
        query returns nothing, so the scan is the reliable path).
        Distances are cosine distance (0.0 = identical), ascending.
        """
        try:
            label = _ident(label, "label")
            gname = self._graph(graph)
            backfill_embeddings(self.store, gname, label, field)
            self.store.ensure_vector_index(gname, label, "emb", 64)
            qv = embed_text(query_text)
            results = None
            try:
                rows = self.store.q(
                    gname,
                    "CALL db.idx.vector.queryNodes($label, 'emb', $k, "
                    "vecf32($v)) YIELD node, score",
                    {"label": label, "k": top_n, "v": qv},
                )
                if rows:  # empty result = broken index path -> scan instead
                    results = [(r[0], float(r[1])) for r in rows]
            except Exception:
                results = None
            if results is None:
                rows = self.store.q(
                    gname, f"MATCH (n:{label}) WHERE n.emb IS NOT NULL RETURN n")
                scored = []
                for (node,) in rows:
                    vec = getattr(node, "properties", {}).get("emb") or []
                    if len(vec) != 64:
                        continue
                    dist = 1.0 - sum(a * b for a, b in zip(qv, vec))
                    scored.append((node, dist))
                scored.sort(key=lambda t: t[1])
                results = scored[:top_n]
            lines = []
            for node, dist in results[:top_n]:
                props = getattr(node, "properties", None) or {}
                lines.append(f"{_display_name(props)} — distance {dist:.4f}")
            answer = "\n".join(lines) if lines else "(no matches)"
            return answer, []
        except Exception as e:
            return f"Tool error: vector_search failed: {e}", []

    # -- fulltext -------------------------------------------------------
    def fulltext(self, label, field, query, top_n=5, graph="company"):
        """BM25 full-text search; falls back to CONTAINS on any exception."""
        try:
            label = _ident(label, "label")
            gname = self._graph(graph)
            try:
                self.store.ensure_fulltext_index(gname, label, field)
                rows = self.store.q(
                    gname,
                    "CALL db.idx.fulltext.queryNodes($label, $q)",
                    {"label": label, "q": query},
                )
                nodes = [r[0] for r in rows[:top_n]]
            except Exception:
                rows = self.store.q(
                    gname,
                    f"MATCH (n:{label}) WHERE n.`{field}` CONTAINS $q "
                    f"RETURN n LIMIT {int(top_n)}",
                    {"q": query},
                )
                nodes = [r[0] for r in rows]
            lines = []
            for node in nodes:
                props = getattr(node, "properties", None) or {}
                snippet = str(props.get("summary") or props.get("text") or "")[:120]
                lines.append(f"{_display_name(props)} — {snippet}")
            answer = "\n".join(lines) if lines else "(no matches)"
            return answer, []
        except Exception as e:
            return f"Tool error: fulltext failed: {e}", []
