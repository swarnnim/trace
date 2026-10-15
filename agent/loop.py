"""Trace agent loop — classify -> tool chain -> compose -> render.

Event code (Day 2). Strictly $0 / offline: uses GraphTools (FalkorDB),
EpisodicMemory/SemanticMemory, and MockLLM.
"""

from __future__ import annotations

from datetime import datetime

from agent.llm import get_llm
from agent.tools import GraphTools
from agent.explain import render_path, render_answer  # noqa: F401  (re-exported for cli)
from memory.store import Store, COMPANY_GRAPH
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory

_STOPWORDS = {
    "the", "a", "an", "if", "is", "it", "to", "of", "and", "or", "in", "on",
    "for", "what", "who", "we", "did", "do", "does", "are", "was", "were",
    "about", "that", "this", "with", "by", "as", "at", "be", "goes", "go",
    "down", "up", "me", "tell", "show", "how", "why", "when", "which",
}

_CLASSIFY_RULES = [
    ("blast_radius", ["goes down", "what breaks", "breaks if", "impact of", "fails"]),
    ("who_decided", ["who decided", "who paused", "why was", "decision to"]),
    ("who_knows", ["who knows", "expert", "best at", "most knowledgeable"]),
    ("memory", ["discuss", "what did we", "talked about", "remember", "recall"]),
    ("status", ["is the", "is it done", "done?", "finished", "status of"]),
]


def _seg(frm_label, frm_name, rel, to_label, to_name):
    return {
        "from": {"label": frm_label, "name": frm_name},
        "rel": rel,
        "to": {"label": to_label, "name": to_name},
    }


def _merge_paths(*paths):
    seen, out = set(), []
    for p in paths:
        for seg in p or []:
            key = (
                seg.get("from", {}).get("label"), seg.get("from", {}).get("name"),
                seg.get("rel"),
                seg.get("to", {}).get("label"), seg.get("to", {}).get("name"),
            )
            if key not in seen:
                seen.add(key)
                out.append(seg)
    return out


def _fmt_date(ts):
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d.strftime("%b %-d")
    except Exception:
        return str(ts)[:10]


def _keywords(question):
    words = []
    for w in question.replace("?", " ").replace(",", " ").split():
        w = w.strip(".,!?\"'").lower()
        if w and w not in _STOPWORDS and len(w) > 2:
            words.append(w)
    return words


class AgentLoop:
    def __init__(self, store=None, user="sam", llm=None):
        self.store = store or Store()
        self.user = user
        self.tools = GraphTools(self.store, user)
        self.llm = llm or get_llm()
        self.episodic = EpisodicMemory(self.store)
        self.semantic = SemanticMemory(self.store)
        self.last_path: list = []
        self.last_answer: str = ""
        self._candidates = None  # [(name, label)]

    # ------------------------------------------------------------------
    # classification + entity extraction
    # ------------------------------------------------------------------
    def classify(self, question: str) -> str:
        q = question.lower()
        for kind, keys in _CLASSIFY_RULES:
            if any(k in q for k in keys):
                return kind
        return "general"

    def _load_candidates(self):
        if self._candidates is None:
            cands = []
            for label in ("Person", "Project", "System", "Topic"):
                rows = self.store.q(
                    COMPANY_GRAPH, f"MATCH (n:{label}) RETURN DISTINCT n.name"
                )
                for r in rows:
                    if r[0]:
                        cands.append((r[0], label))
            self._candidates = cands
        return self._candidates

    def extract_entity(self, question: str):
        """Longest case-insensitive substring match -> (name, label) or None."""
        q = question.lower()
        best = None
        for name, label in self._load_candidates():
            if name.lower() in q:
                # prefer Project over System for dual-labeled nodes
                score = (len(name), 0 if label != "System" else 1)
                if best is None or score > best[0]:
                    best = (score, name, label)
        return (best[1], best[2]) if best else None

    def _tool_call(self, method, *args, **kwargs):
        """Unpack the (answer, path) contract defensively."""
        res = method(*args, **kwargs)
        if isinstance(res, tuple) and len(res) == 2:
            return (res[0] or "", res[1] or [])
        return (str(res), [])

    # ------------------------------------------------------------------
    # tool chains
    # ------------------------------------------------------------------
    def _blast_radius(self, question):
        ent = self.extract_entity(question)
        if not ent:
            return [self._unresolved(question)]
        name, label = ent
        ans, _ = self._tool_call(
            self.tools.cypher,
            "MATCH (t) WHERE (t:Project OR t:System) AND t.name=$n "
            "WITH t MATCH (x:Project)-[:DEPENDS_ON*1..3]->(t) "
            "RETURN DISTINCT x.name ORDER BY x.name",
            {"n": name},
        )
        # Robust dependent extraction: match known Project names in the answer.
        dependents = [
            pname for pname, plabel in self._load_candidates()
            if plabel == "Project" and pname.lower() in str(ans).lower()
            and pname.lower() != name.lower()
        ]
        if not dependents:
            # fallback to structured query if the tool answer didn't render names
            dependents = [
                r[0] for r in self.store.q(
                    COMPANY_GRAPH,
                    "MATCH (t) WHERE (t:Project OR t:System) AND t.name=$n "
                    "WITH t MATCH (x:Project)-[:DEPENDS_ON*1..3]->(t) "
                    "RETURN DISTINCT x.name ORDER BY x.name",
                    {"n": name},
                )
            ]
        path = []
        for dep in dependents:
            _, sp = self._tool_call(
                self.tools.shortest_path,
                "Project", dep, label, name, ["DEPENDS_ON"], 4, "company",
            )
            path = _merge_paths(path, sp)
        if not dependents:
            return [{
                "tool": "shortest-path traversal",
                "answer": f"Nothing in the graph depends on {name}.",
                "path": [],
            }]
        lst = ", ".join(dependents)
        n = len(dependents)
        return [{
            "tool": "shortest-path traversal",
            "answer": f"If {name} goes down, {n} project{'s' if n != 1 else ''} break: {lst}.",
            "path": path,
        }]

    def _who_decided(self, question):
        ent = self.extract_entity(question)
        if not ent:
            return [self._unresolved(question)]
        name, _ = ent
        ans, _ = self._tool_call(self.tools.fulltext, "Decision", "title", name, 5, "company")
        rows, _ = self._tool_call(
            self.tools.cypher,
            "MATCH (d:Decision) WHERE d.title CONTAINS $kw "
            "RETURN d.title, d.date, d.summary, d.status ORDER BY d.date DESC LIMIT 3",
            {"kw": name},
        )
        det_rows = self.store.q(
            COMPANY_GRAPH,
            "MATCH (p:Person)-[:MADE]->(d:Decision) "
            "WHERE d.title CONTAINS $kw "
            "OPTIONAL MATCH (d)-[:DECIDED_IN]->(doc:Doc) "
            "OPTIONAL MATCH (d)-[:AFFECTS]->(t) "
            "RETURN p.name, d.title, d.date, d.summary, d.status, "
            "doc.title, doc.summary, doc.author, t.name",
            {"kw": name},
        )
        if not det_rows:
            return [{
                "tool": "full-text search",
                "answer": f"Found decisions about {name} but no maker recorded: {ans}",
                "path": [],
            }]
        # prefer the accepted decision (e.g. "Pause Project Helios") over
        # reverted/rejected ones mentioning the same topic
        def _dkey(r):
            return (0 if str(r[4] or "").lower() == "accepted" else 1, r[2] or "")

        det = sorted(det_rows, key=_dkey)[0]
        (who, title, date, summary, status, doc_title, doc_sum, doc_author, affects) = det
        path = [
            _seg("Person", who, "MADE", "Decision", title),
            _seg("Decision", title, "DECIDED_IN", "Doc", doc_title or ""),
        ]
        if affects:
            path.append(_seg("Decision", title, "AFFECTS", "Project", affects))
        # motivation: other docs about the affected project (e.g. Zoya's retro)
        retro = ""
        if affects:
            mot = self.store.q(
                COMPANY_GRAPH,
                "MATCH (doc:Doc)-[:ABOUT]->(t) "
                "WHERE (t:Project OR t:System) AND t.name=$n "
                "AND doc.title <> $main RETURN doc.title, doc.author, doc.kind LIMIT 3",
                {"n": affects, "main": doc_title or ""},
            )
            for mt, ma, _mk in mot:
                path.append(_seg("Doc", doc_title or "", "MENTIONS", "Doc", mt))
            if mot:
                retro = " Context: " + "; ".join(
                    f"'{mt}' by {ma or 'unknown'}" for mt, ma, _ in mot
                ) + "."
        why = (doc_sum or summary or "").strip()
        return [{
            "tool": "graph traversal",
            "answer": (
                f"{who} decided: '{title}' ({_fmt_date(date)}, status {status}), "
                f"recorded in '{doc_title}' by {doc_author or 'unknown'}.{retro} "
                f"Why: {why}."
            ),
            "path": path,
        }]

    def _who_knows(self, question):
        ent = self.extract_entity(question)
        if not ent:
            return [self._unresolved(question)]
        name, _ = ent
        trows = self.store.q(
            COMPANY_GRAPH,
            "MATCH (t:Topic) WHERE toLower(t.name)=toLower($n) RETURN t.name",
            {"n": name},
        )
        topic = trows[0][0] if trows else name
        experts = self.store.q(
            COMPANY_GRAPH,
            "MATCH (p:Person)-[:KNOWS]->(t:Topic) "
            "WHERE toLower(t.name)=toLower($n) RETURN p.name",
            {"n": name},
        )
        experts = [r[0] for r in experts]
        pr_ans, _ = self._tool_call(self.tools.pagerank, "Person", "KNOWS", 10, "company")

        def pr_rank(person):
            idx = str(pr_ans).lower().find(person.lower())
            return idx if idx >= 0 else 10 ** 9

        # PageRank tie detection: parse "Name (score)" lines; if every
        # candidate scores the same, PageRank is uninformative — say so.
        import re as _re
        _scores = {}
        for line in str(pr_ans).splitlines():
            m = _re.match(r"\d+\.\s*(.+?)\s*\(([0-9.]+)\)", line.strip())
            if m:
                _scores[m.group(1).strip().lower()] = float(m.group(2))

        # authorship evidence: docs AUTHORED about the topic/system (e.g. runbooks)
        auth = self.store.q(
            COMPANY_GRAPH,
            "MATCH (p:Person)-[:AUTHORED]->(d:Doc)-[:ABOUT]->(t) "
            "WHERE (t:Topic OR t:System) AND toLower(t.name)=toLower($n) "
            "RETURN p.name, d.title",
            {"n": name},
        )
        authored = {}
        for p, d in auth:
            authored.setdefault(p, []).append(d)
        # prior-episode evidence: episodes mentioning the topic and a person
        # (e.g. "Ananya is the Redis expert; wrote the failover runbook.")
        ep_evid: dict = {}
        _seen_ep = set()
        _variants = [topic]
        if topic.title() not in _variants:
            _variants.append(topic.title())
        if topic.capitalize() not in _variants:
            _variants.append(topic.capitalize())
        for variant in _variants:
            for ep in self.episodic.search(self.user, variant, limit=5):
                if ep["id"] in _seen_ep:
                    continue
                _seen_ep.add(ep["id"])
                txt = (ep.get("text") or "")
                tl = txt.lower()
                if name.lower() not in tl:
                    continue
                for cand_name in set(experts) | set(authored):
                    cl = cand_name.lower()
                    # full name, else first name (unique in this dataset)
                    if cl in tl or cl.split()[0] in tl.split():
                        ep_evid.setdefault(cand_name, []).append(ep)
        # candidates: KNOWS experts plus topic-doc authors plus episode-named
        # people; strongest signal first: doc authorship, then episode
        # evidence, then PageRank position
        candidates = []
        for p in experts + [p for p in authored if p not in experts] + \
                [p for p in ep_evid if p not in experts and p not in authored]:
            if p not in candidates:
                candidates.append(p)
        if not candidates:
            return [{
                "tool": "graph traversal",
                "answer": f"No recorded experts on {topic}.",
                "path": [],
            }]
        ranked = sorted(
            candidates,
            key=lambda p: (
                0 if p in authored else 1,
                0 if p in ep_evid else 1,
                pr_rank(p), p,
            ),
        )
        cand_scores = {_scores.get(p.lower()) for p in ranked if p.lower() in _scores}
        pr_tied = len(cand_scores) <= 1
        top = ranked[0]
        why_bits = []
        if top in authored:
            why_bits.append(
                f"authored {', '.join(repr(d) for d in authored[top])} (about {topic})"
            )
        if top in ep_evid:
            ep = ep_evid[top][0]
            why_bits.append(
                f"a prior episode ({(ep.get('ts') or '')[:10]}) confirms: "
                f"'{ep.get('text', '')}'"
            )
        if top in experts:
            why_bits.append(f"recorded KNOWS edge on '{topic}'")
        if pr_tied:
            why_bits.append(
                "PageRank on KNOWS ties across candidates, so the ranking "
                "falls back to this evidence"
            )
        path = [_seg("Person", p, "KNOWS", "Topic", topic) for p in ranked if p in experts]
        for p, docs in authored.items():
            for d in docs:
                path.append(_seg("Person", p, "AUTHORED", "Doc", d))
        others = []
        for e in ranked[1:]:
            note = " (KNOWS edge)" if e in experts and e not in authored else ""
            others.append(f"{e}{note}")
        tail = f" Runner-up: {'; '.join(others)}." if others else ""
        return [{
            "tool": "PageRank + authorship + episodic evidence",
            "answer": f"{top} knows {topic} best — {'; '.join(why_bits)}.{tail}",
            "path": path,
        }]

    def _memory(self, question):
        kws = _keywords(question)
        episodes = {}
        for kw in kws[:4]:
            for ep in self.episodic.recall_about_topic(self.user, kw, limit=5):
                episodes[ep["id"]] = ep
            for ep in self.episodic.recall_involving(self.user, kw.title(), limit=5):
                episodes[ep["id"]] = ep
            for ep in self.episodic.search(self.user, kw, limit=5):
                episodes[ep["id"]] = ep
        # also try Title-cased entity names
        ent = self.extract_entity(question)
        if ent:
            for ep in self.episodic.recall_involving(self.user, ent[0], limit=5):
                episodes[ep["id"]] = ep
        if not episodes:
            return [{
                "tool": "episodic recall",
                "answer": f"No episodes found matching: {question!r}.",
                "path": [],
            }]
        eps = sorted(episodes.values(), key=lambda e: e.get("ts", ""), reverse=True)
        bits = []
        for ep in eps[:3]:
            bits.append(f"On {_fmt_date(ep.get('ts'))} ({ep.get('ts','')[:10]}): {ep.get('text','')}")
        # honest evidence path from the episode's real INVOLVES/ABOUT links
        path = []
        for ep in eps[:2]:
            eid = (ep.get("id") or "")[:8]
            for ent_name in ep.get("involves", []):
                path.append(_seg("Episode", eid, "INVOLVES", "Entity", ent_name))
            for t in ep.get("topics", []):
                path.append(_seg("Episode", eid, "ABOUT", "Topic", t))
        return [{
            "tool": "episodic recall",
            "answer": " ".join(bits),
            "path": path,
        }]

    def _status(self, question):
        ent = self.extract_entity(question)
        kw = ent[0] if ent else ( _keywords(question)[0] if _keywords(question) else question)
        rows = self.store.q(
            COMPANY_GRAPH,
            "MATCH (d:Decision) WHERE d.title CONTAINS $kw "
            "OPTIONAL MATCH (p:Person)-[:MADE]->(d) "
            "RETURN d.title, d.date, d.status, p.name ORDER BY d.date DESC LIMIT 3",
            {"kw": kw},
        )
        if not rows:
            return [{
                "tool": "full-text search",
                "answer": f"No decision found about {kw}.",
                "path": [],
            }]
        title, date, status, who = rows[0]
        # status is a Decision node property (read directly, stated in the
        # answer text) — the path shows the real traversal only.
        path = [_seg("Person", who, "MADE", "Decision", title)] if who else []
        guard = ""
        for b in self.semantic.current_beliefs(self.user):
            if kw.lower() in b["text"].lower():
                guard = f" Note: {b['text']}"
                break
        if not guard:
            # guard may also live in episodic memory (seeded episode, not belief)
            for ep in self.episodic.search(self.user, kw, limit=3):
                txt = ep.get("text", "")
                if any(w in txt.lower() for w in ("proposed", "not accepted", "not done", "not yet")):
                    guard = f" Note: {txt}"
                    break
        if str(status).lower() == "accepted":
            answer = f"Yes — '{title}' is accepted ({_fmt_date(date)}, by {who or 'unknown'})."
        else:
            answer = (f"No — '{title}' is {status or 'unknown'} "
                      f"({_fmt_date(date)}, by {who or 'unknown'}), not accepted.{guard}")
        return [{"tool": "graph traversal", "answer": answer, "path": path}]

    def _general(self, question):
        ans, _ = self._tool_call(self.tools.fulltext, "Doc", "summary", question, 3, "company")
        eps = self.episodic.search(self.user, question, limit=3)
        ep_bits = " ".join(e.get("text", "") for e in eps[:2])
        combo = str(ans).strip()
        if ep_bits:
            combo += f" Related memory: {ep_bits}"
        return [{"tool": "full-text search", "answer": combo or "Nothing relevant found.", "path": []}]

    def _unresolved(self, question):
        return {
            "tool": "entity resolution",
            "answer": f"I couldn't identify a company entity in: {question!r}.",
            "path": [],
        }

    # ------------------------------------------------------------------
    # main entry
    # ------------------------------------------------------------------
    def ask(self, question: str) -> tuple[str, list]:
        kind = self.classify(question)
        chain = {
            "blast_radius": self._blast_radius,
            "who_decided": self._who_decided,
            "who_knows": self._who_knows,
            "memory": self._memory,
            "status": self._status,
        }.get(kind, self._general)
        tool_outputs = chain(question)
        final = self.llm.compose(question, tool_outputs)
        merged = []
        for o in tool_outputs:
            merged = _merge_paths(merged, o.get("path", []))
        self.last_path = merged
        self.last_answer = final
        rendered = render_answer(final, merged)
        return rendered, merged
