"""Trace web UI — Flask demo app (Day 3, Graph Hacks).

Routes:
  /            ask box; answer card + expandable "How I got this" path
  /remember    quick-add form (text -> Episode via episodic.remember)
  /graph       node-label + relationship-type counts per graph
  /blackboard  two-agent (planner + researcher) coordination demo

Run: ~/workspace/falkordb-graph-hacks/.venv/bin/python -m web.app
Then open http://127.0.0.1:5000/
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, render_template
from jinja2 import DictLoader

from agent.loop import AgentLoop
from agent.tools import GraphTools
from memory.store import Store, COMPANY_GRAPH, BLACKBOARD_GRAPH, user_graph_name
from memory.blackboard import Blackboard
from memory.episodic import EpisodicMemory

WEB_USER = "sam"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #0b0e14; color: #e6e9f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}
nav {
  background: #11151f; border-bottom: 1px solid #232a3a;
  padding: 0.7rem 1rem; position: sticky; top: 0; z-index: 10;
  display: flex; gap: 1.1rem; align-items: center; flex-wrap: wrap;
}
nav .brand { font-weight: 700; color: #7dd3fc; text-decoration: none; font-size: 1.1rem; }
nav a { color: #aeb6c6; text-decoration: none; font-size: 0.95rem; }
nav a:hover { color: #fff; }
main { max-width: 880px; margin: 0 auto; padding: 1.2rem 1rem 3rem; }
h1 { font-size: 1.4rem; margin: 0.4rem 0 1rem; }
h2 { font-size: 1.1rem; color: #7dd3fc; margin: 1.6rem 0 0.6rem; }
.card {
  background: #141a26; border: 1px solid #263049; border-radius: 12px;
  padding: 1rem 1.1rem; margin: 0.9rem 0;
}
.answer { white-space: pre-wrap; font-size: 1.02rem; }
.muted { color: #8b93a7; font-size: 0.9rem; }
form.askform { display: flex; gap: 0.5rem; margin: 1rem 0; }
input[type=text], textarea {
  flex: 1; background: #0f1420; color: #e6e9f0;
  border: 1px solid #2b3550; border-radius: 10px;
  padding: 0.8rem 0.9rem; font-size: 1rem; width: 100%;
}
button {
  background: #2563eb; color: #fff; border: 0; border-radius: 10px;
  padding: 0.8rem 1.2rem; font-size: 1rem; font-weight: 600; cursor: pointer;
}
button:hover { background: #1d4ed8; }
details.path { margin-top: 0.8rem; }
details.path summary {
  cursor: pointer; color: #7dd3fc; font-weight: 600; padding: 0.4rem 0;
  font-size: 0.98rem;
}
ol.chain { list-style: none; padding: 0; margin: 0.6rem 0 0; }
ol.chain li {
  background: #0f1420; border: 1px solid #232c44; border-radius: 8px;
  padding: 0.55rem 0.7rem; margin: 0.35rem 0; font-size: 0.93rem;
  overflow-wrap: anywhere;
}
.node .lbl {
  display: inline-block; background: #1e293b; color: #93c5fd;
  border-radius: 6px; padding: 0.05rem 0.45rem; font-size: 0.78rem;
  margin-right: 0.35rem; font-weight: 600;
}
.rel { color: #fbbf24; font-weight: 700; margin: 0 0.3rem; white-space: nowrap; }
table.counts { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
table.counts th, table.counts td {
  text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid #232c44;
}
table.counts th { color: #8b93a7; font-weight: 600; }
table.counts td.num { text-align: right; font-variant-numeric: tabular-nums; }
.step { display: flex; gap: 0.7rem; margin: 0.5rem 0; align-items: baseline; }
.step .who {
  flex: 0 0 auto; font-weight: 700; color: #a78bfa; font-size: 0.9rem;
  min-width: 6.5rem;
}
.err { color: #f87171; }
.ok { color: #4ade80; }
.demo-q { margin: 0.3rem 0; }
.demo-q a { color: #7dd3fc; }
@media (max-width: 560px) {
  form.askform { flex-direction: column; }
  button { width: 100%; }
}
"""

BASE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — Trace</title>
<style>{{ css }}</style></head>
<body>
<nav>
  <a class="brand" href="/">Trace</a>
  <a href="/">Ask</a>
  <a href="/remember">Remember</a>
  <a href="/graph">Graph</a>
  <a href="/blackboard">Blackboard demo</a>
</nav>
<main>{% block content %}{% endblock %}</main>
</body></html>
"""

ASK_HTML = """{% extends "base.html" %}
{% block content %}
<h1>Ask Trace</h1>
<p class="muted">Every answer ships with the exact graph path behind it —
expand <b>How I got this</b> to inspect the reasoning.</p>
<form class="askform" method="post" action="/">
  <input type="text" name="question" placeholder="Ask about the company, decisions, experts, memory…"
         value="{{ question|e }}" autocomplete="off">
  <button type="submit">Ask</button>
</form>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
{% if answer %}
<div class="card">
  <div class="answer">{{ answer }}</div>
  <details class="path">
    <summary>How I got this ({{ path|length }} step{{ "s" if path|length != 1 }})</summary>
    {% if path %}
    <ol class="chain">
      {% for s in path %}
      <li><span class="node"><span class="lbl">{{ s.from.label }}</span>{{ s.from.name }}</span><span class="rel">—[{{ s.rel }}]→</span><span class="node"><span class="lbl">{{ s.to.label }}</span>{{ s.to.name }}</span></li>
      {% endfor %}
    </ol>
    {% else %}
    <p class="muted">Direct lookup — no graph traversal needed.</p>
    {% endif %}
  </details>
</div>
{% endif %}
<h2>Try the demo questions</h2>
{% for q in demo_questions %}
<p class="demo-q"><a href="/?q={{ q|urlencode }}">“{{ q }}”</a></p>
{% endfor %}
{% endblock %}
"""

REMEMBER_HTML = """{% extends "base.html" %}
{% block content %}
<h1>Remember</h1>
<p class="muted">Store a quick note as an episodic memory. Ask about it later —
Trace recalls it with its timestamp.</p>
<form method="post" action="/remember">
  <textarea name="text" rows="3" placeholder="e.g. We decided to revisit the Redis failover plan next sprint."></textarea>
  <p><button type="submit">Remember this</button></p>
</form>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
{% if episode_id %}
<div class="card"><p class="ok">Remembered.</p>
<p class="muted">Episode id: {{ episode_id }}</p>
<p><a href="/">Ask about it →</a></p></div>
{% endif %}
{% endblock %}
"""

GRAPH_HTML = """{% extends "base.html" %}
{% block content %}
<h1>Graph stats</h1>
<p class="muted">Live counts from FalkorDB — proof the graphs are loaded.</p>
{% for section in sections %}
<h2>{{ section.title }} <span class="muted">({{ section.name }})</span></h2>
<div class="card">
<h2 style="margin-top:0">Nodes by label</h2>
<table class="counts">
<tr><th>Label</th><th style="text-align:right">Count</th></tr>
{% for label, n in section.labels %}
<tr><td>{{ label }}</td><td class="num">{{ n }}</td></tr>
{% endfor %}
<tr><td><b>Total</b></td><td class="num"><b>{{ section.total_nodes }}</b></td></tr>
</table>
<h2>Relationships by type</h2>
<table class="counts">
<tr><th>Type</th><th style="text-align:right">Count</th></tr>
{% for rtype, n in section.rels %}
<tr><td>{{ rtype }}</td><td class="num">{{ n }}</td></tr>
{% endfor %}
<tr><td><b>Total</b></td><td class="num"><b>{{ section.total_rels }}</b></td></tr>
</table>
</div>
{% endfor %}
{% endblock %}
"""

BLACKBOARD_HTML = """{% extends "base.html" %}
{% block content %}
<h1>Blackboard demo — two agents, one question</h1>
<p class="muted"><b>planner</b> and <b>researcher</b> coordinate on the shared
blackboard graph to answer <i>“Who knows Redis best?”</i> — a question neither
settles alone. Handoffs are edges, not messages.</p>
{% if not ran %}
<form method="post" action="/blackboard">
  <button type="submit">Run the 2-agent demo</button>
</form>
{% else %}
<h2>Coordination steps</h2>
<div class="card">
{% for who, what in steps %}
<div class="step"><span class="who">{{ who }}</span><span>{{ what }}</span></div>
{% endfor %}
</div>
<h2>Final answer</h2>
<div class="card"><div class="answer">{{ final }}</div></div>
<h2>Handoff chain (coordination edges)</h2>
<div class="card">
<ol class="chain">
{% for s in chain %}
<li><span class="node"><span class="lbl">{{ s.from.label }}</span>{{ s.from.name }}{% if s.from.label == "Finding" and s.from.name in finding_texts %} — “{{ finding_texts[s.from.name][:90] }}…”{% endif %}</span><span class="rel">—[{{ s.rel }}]→</span><span class="node"><span class="lbl">{{ s.to.label }}</span>{{ s.to.name }}</span></li>
{% endfor %}
</ol>
</div>
<form method="post" action="/blackboard"><button type="submit">Run again</button></form>
{% endif %}
{% endblock %}
"""

DEMO_QUESTIONS = [
    "What did we discuss about the payments outage?",
    "If the ledger service goes down, what breaks?",
    "Who decided to pause Helios, and why?",
    "Who knows Redis best?",
    "Is the Postgres upgrade done?",
]


def _label_counts(store, graph_name):
    try:
        rows = store.q(graph_name, "CALL db.labels()")
        labels = [r[0] for r in rows if r[0]]
    except Exception:
        labels = ["Person", "Project", "Doc", "Decision", "System", "Topic",
                  "Episode", "Entity", "Belief", "Agent", "Task", "Finding"]
    out = []
    for label in labels:
        try:
            n = store.count_by_label(graph_name, label)
        except Exception:
            n = 0
        if n:
            out.append((label, n))
    return out


def _rel_counts(store, graph_name):
    try:
        rows = store.q(graph_name, "CALL db.relationshipTypes()")
        rtypes = [r[0] for r in rows if r[0]]
    except Exception:
        rtypes = []
    out = []
    for rt in rtypes:
        try:
            n = store.q(
                graph_name, f"MATCH ()-[r:{rt}]->() RETURN count(r)")[0][0]
        except Exception:
            n = 0
        if n:
            out.append((rt, n))
    return out


def run_blackboard_demo(store):
    """Drive planner + researcher on the blackboard; return (steps, final, chain, finding_texts).

    Mirrors memory/blackboard.py run_demo() but returns data for the web UI
    instead of printing.
    """
    store.clear_graph(BLACKBOARD_GRAPH)
    bb = Blackboard(store)
    tools = GraphTools(store, WEB_USER)
    steps = []

    bb.post_task("t1", "Find the top Redis expert", owner_agent="planner")
    steps.append(("planner", "posted task t1: “Find the top Redis expert”"))
    bb.claim_task("t1", "researcher")
    steps.append(("researcher", "claimed task t1"))

    pr_answer, _ = tools.pagerank("Person", "KNOWS", 5, "company")
    redis_rows = store.q(
        COMPANY_GRAPH,
        "MATCH (p:Person)-[:KNOWS]->(t:Topic) "
        "WHERE toLower(t.name) CONTAINS 'redis' RETURN p.name",
    )
    knowers = [r[0] for r in redis_rows]
    f1_text = (
        "PageRank over (Person)-[:KNOWS]->:\n" + pr_answer
        + "\nDirect KNOWS(redis) edge holders: "
        + (", ".join(knowers) if knowers else "none")
        + ". Skill-graph scores tie — inconclusive alone."
    )
    bb.post_finding("researcher", "t1", f1_text)
    steps.append(("researcher", "ran PageRank on the skill graph, posted finding 1"))

    auth_rows = store.q(
        COMPANY_GRAPH,
        "MATCH (p:Person)-[:AUTHORED]->(d:Doc) "
        "WHERE toLower(d.title) CONTAINS 'runbook' "
        "AND toLower(d.title) CONTAINS 'redis' "
        "RETURN p.name, d.title",
    )
    if auth_rows:
        f2_text = (f"Authorship check: {auth_rows[0][0]} AUTHORED "
                   f"'{auth_rows[0][1]}' — the only hands-on Redis evidence.")
    else:
        f2_text = "Authorship check: no Redis runbook author found."
    bb.post_finding("researcher", "t1", f2_text)
    steps.append(("researcher", "checked runbook authorship, posted finding 2"))

    author = auth_rows[0][0] if auth_rows else "unknown"
    doc = auth_rows[0][1] if auth_rows else "unknown doc"
    knower = knowers[0] if knowers else "nobody"
    final = (
        f"Top Redis expert: {author} (authored '{doc}'; "
        f"{knower} holds the KNOWS(redis) skill edge). "
        "Neither the skill graph nor the authorship edge alone settled it — "
        "coordination required."
    )
    bb.post_finding("planner", "t1", final)
    bb.complete_task("t1")
    steps.append(("planner", "read both findings, posted the final answer, marked t1 done"))

    chain = bb.handoff_chain("t1")
    finding_texts = {f["id"]: f["text"] for f in bb.task_findings("t1")}
    return steps, final, chain, finding_texts


def create_app(store=None):
    app = Flask(__name__)
    app.jinja_loader = DictLoader({
        "base.html": BASE_HTML,
        "ask.html": ASK_HTML,
        "remember.html": REMEMBER_HTML,
        "graph.html": GRAPH_HTML,
        "blackboard.html": BLACKBOARD_HTML,
    })
    app.jinja_env.globals["css"] = CSS

    store = store or Store()
    loop = AgentLoop(store=store, user=WEB_USER)
    episodic = EpisodicMemory(store)

    @app.route("/", methods=["GET", "POST"])
    def index():
        question = request.values.get("question", "").strip()
        q_param = request.args.get("q", "").strip()
        if request.method == "GET" and q_param and not question:
            question = q_param
        answer, path, error = None, [], None
        if request.method == "POST":
            if not question:
                error = "Type a question first."
            else:
                try:
                    loop.ask(question)
                    answer = loop.last_answer
                    path = loop.last_path or []
                except Exception as e:  # never 500 on demo day
                    error = f"Agent error: {e}"
        return render_template(
            "ask.html", title="Ask", question=question,
            answer=answer, path=path, error=error,
            demo_questions=DEMO_QUESTIONS,
        )

    @app.route("/remember", methods=["GET", "POST"])
    def remember():
        episode_id, error = None, None
        if request.method == "POST":
            text = request.form.get("text", "").strip()
            if not text:
                error = "Write something to remember first."
            else:
                try:
                    episode_id = episodic.remember(WEB_USER, text)
                except Exception as e:
                    error = f"Remember failed: {e}"
        return render_template(
            "remember.html", title="Remember",
            episode_id=episode_id, error=error,
        )

    @app.route("/graph")
    def graph():
        sections = []
        for title, name in [
            ("Company brain", COMPANY_GRAPH),
            (f"Memory ({WEB_USER})", user_graph_name(WEB_USER)),
            ("Blackboard", BLACKBOARD_GRAPH),
        ]:
            labels = _label_counts(store, name)
            rels = _rel_counts(store, name)
            sections.append({
                "title": title, "name": name, "labels": labels, "rels": rels,
                "total_nodes": sum(n for _, n in labels),
                "total_rels": sum(n for _, n in rels),
            })
        return render_template("graph.html", title="Graph stats", sections=sections)

    @app.route("/blackboard", methods=["GET", "POST"])
    def blackboard():
        if request.method == "GET":
            return render_template(
                "blackboard.html", title="Blackboard demo", ran=False)
        try:
            steps, final, chain, finding_texts = run_blackboard_demo(store)
            error = None
        except Exception as e:
            steps, final, chain, finding_texts, error = [], "", [], {}, str(e)
        return render_template(
            "blackboard.html", title="Blackboard demo", ran=True,
            steps=steps, final=final, chain=chain,
            finding_texts=finding_texts, error=error,
        )

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, threaded=False)
