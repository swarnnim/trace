"""Load the Northwind Labs dataset into FalkorDB. Re-runnable (clears first)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.store import Store, COMPANY_GRAPH, user_graph_name
from memory.ingest import CompanyIngestor, MemoryIngestor
import demo_data.northwind as N


def load_all(store=None) -> dict:
    own_store = store is None
    store = store or Store()
    try:
        return _load(store)
    finally:
        if own_store:
            store.close()


def _load(store) -> dict:
    ci = CompanyIngestor(store)
    mi = MemoryIngestor(store)

    # -- clear (re-runnable) ---------------------------------------------
    mem_graph = user_graph_name("sam")
    store.clear_graph(COMPANY_GRAPH)
    store.clear_graph(mem_graph)

    # -- company brain ----------------------------------------------------
    for name, role, team, email, skills in N.PEOPLE:
        ci.person(name, role, team, email=email, skills=skills)

    for name, status, lead, deps, started in N.PROJECTS:
        ci.project(name, status, lead, started=started)

    for name, kind, criticality, extra in N.SYSTEMS:
        ci.system(name, kind, criticality, extra_labels=extra)

    # -- dependencies (second pass: all Project/System nodes must exist first)
    for name, status, lead, deps, started in N.PROJECTS:
        for dep in deps:
            if dep not in N.EXTERNAL_SYSTEMS:
                ci.depends_on(name, dep)

    for title, kind, author, date, summary, about, mpeople, mtopics, supers in N.DOCS:
        ci.doc(
            title, kind, author, date, summary,
            about=about, mentions_people=mpeople, mentions_topics=mtopics,
            supersedes_title=supers,
        )

    for title, by, date, rec, affects, status, summary in N.DECISIONS:
        ci.decision(title, by, date, rec, affects=affects, status=status, summary=summary)

    for person, manager in N.REPORTS_TO:
        ci.reports_to(person, manager)

    for person, project in N.WORKS_ON:
        ci.works_on(person, project)

    # -- sam's memory ------------------------------------------------------
    for text, ts, kind, involves, topics in N.EPISODES_SAM:
        mi.episode("sam", text, ts, kind=kind, involves=involves, topics=topics)

    for text, conf, source, ts in N.BELIEFS_SAM:
        mi.belief("sam", text, conf, source, ts=ts)

    for new_text, old_text in N.BELIEF_CONTRADICTIONS:
        mi.contradicts("sam", new_text, old_text)

    # -- indexes -----------------------------------------------------------
    store.ensure_fulltext_index(COMPANY_GRAPH, "Doc", "title", "summary")
    store.ensure_fulltext_index(COMPANY_GRAPH, "Decision", "title", "summary")
    store.ensure_fulltext_index(mem_graph, "Episode", "text")
    vec = {
        "doc_summary": store.ensure_vector_index(COMPANY_GRAPH, "Doc", "summary"),
        "episode_text": store.ensure_vector_index(mem_graph, "Episode", "text"),
    }

    counts = {
        "company_nodes": store.count_nodes(COMPANY_GRAPH),
        "person": store.count_by_label(COMPANY_GRAPH, "Person"),
        "project": store.count_by_label(COMPANY_GRAPH, "Project"),
        "system": store.count_by_label(COMPANY_GRAPH, "System"),
        "topic": store.count_by_label(COMPANY_GRAPH, "Topic"),
        "doc": store.count_by_label(COMPANY_GRAPH, "Doc"),
        "decision": store.count_by_label(COMPANY_GRAPH, "Decision"),
        "mem_nodes": store.count_nodes(mem_graph),
        "episodes": store.count_by_label(mem_graph, "Episode"),
        "beliefs": store.count_by_label(mem_graph, "Belief"),
        "entities": store.count_by_label(mem_graph, "Entity"),
        "vector_indexes": vec,
    }
    return counts


if __name__ == "__main__":
    counts = load_all()
    for k, v in counts.items():
        print(f"{k}: {v}")
