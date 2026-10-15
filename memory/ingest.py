"""Trace memory ingestors — MERGE-based, idempotent writers.

CompanyIngestor: writes the company-brain graph (trace_company).
MemoryIngestor: writes per-user episodic/semantic memory (trace_mem_<user>).
All methods take/return plain values; no LLM, no network, no secrets.
"""

import uuid

from .store import user_graph_name


class CompanyIngestor:
    def __init__(self, store):
        self.store = store

    def person(self, name, role, team, email=None, skills=()):
        self.store.q(
            "trace_company",
            "MERGE (p:Person {name: $name}) "
            "SET p.role = $role, p.team = $team, p.email = $email",
            {"name": name, "role": role, "team": team, "email": email},
        )
        for skill in skills:
            self.store.q(
                "trace_company",
                "MERGE (t:Topic {name: $skill}) "
                "WITH t MATCH (p:Person {name: $name}) "
                "MERGE (p)-[:KNOWS]->(t)",
                {"name": name, "skill": skill},
            )

    def project(self, name, status, lead_name, started=None):
        self.store.q(
            "trace_company",
            "MERGE (p:Project {name: $name}) "
            "SET p.status = $status, p.owner = $lead, p.started = $started",
            {"name": name, "status": status, "lead": lead_name, "started": started},
        )
        if lead_name:
            self.store.q(
                "trace_company",
                "MATCH (p:Person {name: $lead}), (pr:Project {name: $name}) "
                "MERGE (p)-[:LEADS]->(pr)",
                {"lead": lead_name, "name": name},
            )

    def system(self, name, kind, criticality, extra_labels=()):
        if "Project" in extra_labels:
            # dual-label node (e.g. Ledger Service): keep ONE node, add :System
            self.store.q(
                "trace_company",
                "MATCH (s:Project {name: $name}) "
                "SET s:System, s.kind = $kind, s.criticality = $criticality",
                {"name": name, "kind": kind, "criticality": criticality},
            )
        else:
            self.store.q(
                "trace_company",
                "MERGE (s:System {name: $name}) "
                "SET s.kind = $kind, s.criticality = $criticality",
                {"name": name, "kind": kind, "criticality": criticality},
            )

    def doc(
        self,
        title,
        kind,
        author_name,
        date,
        summary,
        about=(),
        mentions_people=(),
        mentions_topics=(),
        supersedes_title=None,
    ):
        self.store.q(
            "trace_company",
            "MERGE (d:Doc {title: $title}) "
            "SET d.kind = $kind, d.author = $author, d.date = $date, "
            "d.summary = $summary",
            {
                "title": title,
                "kind": kind,
                "author": author_name,
                "date": date,
                "summary": summary,
            },
        )
        if author_name:
            self.store.q(
                "trace_company",
                "MATCH (p:Person {name: $author}), (d:Doc {title: $title}) "
                "MERGE (p)-[:AUTHORED]->(d)",
                {"author": author_name, "title": title},
            )
        for target in about:
            self.store.q(
                "trace_company",
                "MATCH (d:Doc {title: $title}) "
                "MATCH (t) WHERE (t:Project OR t:System) AND t.name = $target "
                "MERGE (d)-[:ABOUT]->(t)",
                {"title": title, "target": target},
            )
        for person in mentions_people:
            self.store.q(
                "trace_company",
                "MATCH (d:Doc {title: $title}), (p:Person {name: $person}) "
                "MERGE (d)-[:MENTIONS]->(p)",
                {"title": title, "person": person},
            )
        for topic in mentions_topics:
            self.store.q(
                "trace_company",
                "MERGE (t:Topic {name: $topic}) "
                "WITH t MATCH (d:Doc {title: $title}) "
                "MERGE (d)-[:MENTIONS]->(t)",
                {"title": title, "topic": topic},
            )
        if supersedes_title:
            self.store.q(
                "trace_company",
                "MATCH (n:Doc {title: $title}), (o:Doc {title: $old}) "
                "MERGE (n)-[:SUPERSEDES]->(o)",
                {"title": title, "old": supersedes_title},
            )

    def decision(
        self,
        title,
        made_by,
        date,
        recorded_in_title,
        affects=(),
        status="accepted",
        summary="",
    ):
        self.store.q(
            "trace_company",
            "MERGE (d:Decision {title: $title}) "
            "SET d.date = $date, d.status = $status, d.summary = $summary",
            {"title": title, "date": date, "status": status, "summary": summary},
        )
        if made_by:
            self.store.q(
                "trace_company",
                "MATCH (p:Person {name: $by}), (d:Decision {title: $title}) "
                "MERGE (p)-[:MADE]->(d)",
                {"by": made_by, "title": title},
            )
        if recorded_in_title:
            self.store.q(
                "trace_company",
                "MATCH (d:Decision {title: $title}), (doc:Doc {title: $doc}) "
                "MERGE (d)-[:DECIDED_IN]->(doc)",
                {"title": title, "doc": recorded_in_title},
            )
        for target in affects:
            self.store.q(
                "trace_company",
                "MATCH (d:Decision {title: $title}) "
                "MATCH (t) WHERE (t:Project OR t:System) AND t.name = $target "
                "MERGE (d)-[:AFFECTS]->(t)",
                {"title": title, "target": target},
            )

    def works_on(self, person, project):
        self.store.q(
            "trace_company",
            "MATCH (p:Person {name: $person}), (pr:Project {name: $project}) "
            "MERGE (p)-[:WORKS_ON]->(pr)",
            {"person": person, "project": project},
        )

    def depends_on(self, project, target):
        self.store.q(
            "trace_company",
            "MATCH (p:Project {name: $project}) "
            "MATCH (t) WHERE (t:Project OR t:System) AND t.name = $target "
            "MERGE (p)-[:DEPENDS_ON]->(t)",
            {"project": project, "target": target},
        )

    def reports_to(self, person, manager):
        self.store.q(
            "trace_company",
            "MATCH (p:Person {name: $person}), (m:Person {name: $manager}) "
            "MERGE (p)-[:REPORTS_TO]->(m)",
            {"person": person, "manager": manager},
        )


class MemoryIngestor:
    def __init__(self, store):
        self.store = store

    def episode(self, user, text, ts, kind="note", involves=(), topics=()) -> str:
        g = user_graph_name(user)
        eid = uuid.uuid4().hex
        self.store.q(
            g,
            "MERGE (e:Episode {id: $id}) SET e.text = $text, e.ts = $ts, e.kind = $kind",
            {"id": eid, "text": text, "ts": ts, "kind": kind},
        )
        for item in involves:
            if isinstance(item, (tuple, list)):
                name, ent_kind = item[0], item[1]
            else:
                name, ent_kind = item, None
            self.store.q(
                g,
                "MERGE (en:Entity {name: $name}) "
                "SET en.kind = coalesce($kind, en.kind) "
                "WITH en MATCH (e:Episode {id: $id}) "
                "MERGE (e)-[:INVOLVES]->(en)",
                {"name": name, "kind": ent_kind, "id": eid},
            )
        for topic in topics:
            self.store.q(
                g,
                "MERGE (t:Topic {name: $topic}) "
                "WITH t MATCH (e:Episode {id: $id}) "
                "MERGE (e)-[:ABOUT]->(t)",
                {"topic": topic, "id": eid},
            )
        # temporal chain: new -[:FOLLOWS]-> previous latest
        # (latest = episode with no incoming [:FOLLOWS])
        rows = self.store.q(
            g,
            "MATCH (e:Episode) WHERE NOT ()-[:FOLLOWS]->(e) AND e.id <> $id "
            "RETURN e.id ORDER BY e.ts DESC LIMIT 1",
            {"id": eid},
        )
        if rows:
            self.store.q(
                g,
                "MATCH (n:Episode {id: $id}), (o:Episode {id: $old}) "
                "MERGE (n)-[:FOLLOWS]->(o)",
                {"id": eid, "old": rows[0][0]},
            )
        return eid

    def belief(self, user, text, confidence, source, ts=None) -> str:
        g = user_graph_name(user)
        bid = uuid.uuid4().hex
        self.store.q(
            g,
            "MERGE (b:Belief {id: $id}) "
            "SET b.text = $text, b.confidence = $conf, b.source = $source, b.ts = $ts",
            {"id": bid, "text": text, "conf": confidence, "source": source, "ts": ts},
        )
        return bid

    def contradicts(self, user, new_text, old_text):
        g = user_graph_name(user)
        self.store.q(
            g,
            "MATCH (n:Belief {text: $new}), (o:Belief {text: $old}) "
            "MERGE (n)-[:CONTRADICTS]->(o)",
            {"new": new_text, "old": old_text},
        )

    def supports(self, user, belief_text, supporting_text):
        g = user_graph_name(user)
        self.store.q(
            g,
            "MATCH (b:Belief {text: $belief}), (s:Belief {text: $supporting}) "
            "MERGE (s)-[:SUPPORTS]->(b)",
            {"belief": belief_text, "supporting": supporting_text},
        )
