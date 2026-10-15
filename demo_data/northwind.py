"""Northwind Labs fictional demo dataset — full encoding of DATASET_SPEC.md.

All content is invented for the FalkorDB Graph Hacks demo (Oct 15-18, 2026).
"""

# ---------------------------------------------------------------- people ----
# name, role, team, email, skills
PEOPLE = [
    ("Priya Nair", "CTO", "Platform", "priya@northwindlabs.io", ("architecture", "payments")),
    ("Arjun Mehta", "Eng Manager", "Payments", "arjun@northwindlabs.io", ("payments", "oncall")),
    ("Sara Iqbal", "Senior Backend", "Payments", "sara@northwindlabs.io", ("payments", "ledger", "postgres")),
    ("Vikram Rao", "Backend", "Payments", "vikram@northwindlabs.io", ("ledger", "redis")),
    ("Meera Krishnan", "Eng Manager", "Infra", "meera@northwindlabs.io", ("kubernetes", "oncall")),
    ("Dev Patel", "SRE", "Infra", "dev@northwindlabs.io", ("kubernetes", "incident-response")),
    ("Ananya Das", "SRE", "Infra", "ananya@northwindlabs.io", ("incident-response", "monitoring")),
    ("Rohan Verma", "Senior Backend", "Search", "rohan@northwindlabs.io", ("search", "elasticsearch")),
    ("Kavya Reddy", "Backend", "Search", "kavya@northwindlabs.io", ("search", "vector-db")),
    ("Ishaan Bose", "Eng Manager", "Data", "ishaan@northwindlabs.io", ("pipelines", "warehouse")),
    ("Tara Menon", "Data Engineer", "Data", "tara@northwindlabs.io", ("pipelines", "dbt")),
    ("Nikhil Anand", "Security Eng", "Security", "nikhil@northwindlabs.io", ("auth", "pen-testing")),
    ("Zoya Khan", "Product Manager", "Product", "zoya@northwindlabs.io", ("discovery", "analytics")),
    ("Aditya Kulkarni", "Designer", "Product", "aditya@northwindlabs.io", ("ux", "research")),
    ("Farah Sheikh", "Tech Writer", "Product", "farah@northwindlabs.io", ("docs", "onboarding")),
]

# --------------------------------------------------------------- projects ---
# name, status, lead, depends_on, started
PROJECTS = [
    ("Helios", "paused", "Arjun Mehta", ("Ledger Service", "Postgres"), "2026-03-02"),
    ("Ledger Service", "active", "Sara Iqbal", ("Postgres", "Redis"), "2026-01-15"),
    ("Checkout API", "active", "Vikram Rao", ("Ledger Service",), "2026-04-21"),
    ("Search v2", "active", "Rohan Verma", ("Elasticsearch", "Vector DB"), "2026-05-11"),
    ("Pipeforge", "active", "Ishaan Bose", ("Warehouse", "Kafka"), "2026-02-09"),
    ("Oncall Copilot", "shipped", "Meera Krishnan", ("PagerDuty", "Runbook Docs"), "2026-06-01"),
    ("Auth Rework", "active", "Nikhil Anand", ("Auth Service",), "2026-08-17"),
    ("Docs Portal", "shipped", "Farah Sheikh", (), "2026-07-06"),
]

# ---------------------------------------------------------------- systems ---
# name, kind, criticality; "Project" in extra_labels => dual-label node
SYSTEMS = [
    ("Postgres", "db", "critical", ()),
    ("Redis", "db", "high", ()),
    ("Elasticsearch", "db", "high", ()),
    ("Vector DB", "db", "medium", ()),
    ("Kafka", "queue", "high", ()),
    ("Warehouse", "db", "medium", ()),
    ("Auth Service", "service", "critical", ()),
    ("Ledger Service", "service", "high", ("Project",)),
]

# External (non-modelled) deps referenced by projects, kept as doc-only strings
EXTERNAL_SYSTEMS = ("PagerDuty", "Runbook Docs")

# ------------------------------------------------------------------- docs ---
# title, kind, author, date, summary, about, mentions_people, mentions_topics, supersedes
DOCS = [
    (
        "Helios pause RFC",
        "rfc",
        "Arjun Mehta",
        "2026-09-27",
        "Proposes pausing Project Helios: burn is unsustainable while the team "
        "stabilizes the ledger after the September incident. Recommends a 3-month "
        "pause, keeping the repo archived but the payments integration warm.",
        ("Helios",),
        ("Priya Nair", "Sara Iqbal"),
        ("payments",),
        None,
    ),
    (
        "Ledger incident postmortem (Sep)",
        "postmortem",
        "Dev Patel",
        "2026-10-01",
        "Root cause of the September ledger outage: a Redis failover dropped the "
        "single-writer lock, letting two writers append. Sara's fix added fencing "
        "tokens to the lock. Action items: Sentinel-to-Cluster migration (accepted).",
        ("Ledger Service",),
        (),
        (),
        "Incident note (Aug)",
    ),
    (
        "Redis failover runbook",
        "notes",
        "Ananya Das",
        "2026-09-20",
        "Step-by-step Redis failover procedure Dev followed during the September "
        "incident: verify replica lag, promote with WAIT, re-check the ledger "
        "fencing token before re-enabling writers.",
        ("Redis",),
        (),
        (),
        None,
    ),
    (
        "Payments architecture v3",
        "spec",
        "Priya Nair",
        "2026-06-08",
        "Records the single-writer ledger decision: all money movement funnels "
        "through Ledger Service, which owns the append-only journal. Checkout "
        "API retries against it with idempotency keys.",
        ("Ledger Service", "Checkout API"),
        (),
        (),
        None,
    ),
    (
        "Search relevance tuning log",
        "notes",
        "Kavya Reddy",
        "2026-10-06",
        "Tuning notes for Search v2: hybrid BM25 + vector recall hits 0.91 "
        "recall@20 after re-ranking; vector-db ANN index tuned to ef=200 for "
        "the tail of rare queries.",
        ("Search v2",),
        (),
        ("search", "vector-db"),
        None,
    ),
    (
        "Pipeforge backfill plan",
        "spec",
        "Tara Menon",
        "2026-10-02",
        "Plan to backfill six months of event history into the warehouse. "
        "Constrained by the weekend warehouse window and Kafka retention; "
        "runs in idempotent batches with dbt snapshots for validation.",
        ("Pipeforge",),
        (),
        (),
        None,
    ),
    (
        "Auth threat model",
        "spec",
        "Nikhil Anand",
        "2026-09-15",
        "Threat model for the Auth Rework: documents pen-test findings on the "
        "legacy session service, token replay risks, and the migration to "
        "short-lived JWTs behind the Auth Service.",
        ("Auth Service",),
        (),
        ("auth", "pen-testing"),
        None,
    ),
    (
        "Oncall handoff — Diwali freeze",
        "notes",
        "Meera Krishnan",
        "2026-10-05",
        "Diwali freeze handoff: no deploys Oct 28 through Nov 5. Escalation "
        "rotates through the Infra team; Oncall Copilot runbooks pinned in "
        "the #oncall channel.",
        ("Oncall Copilot",),
        (),
        ("oncall",),
        None,
    ),
    (
        "Checkout latency deep-dive",
        "postmortem",
        "Vikram Rao",
        "2026-09-25",
        "Traces checkout p99 spikes to ledger lock contention under flash-sale "
        "load. Recommends a retry policy with jitter and a hot-shard split on "
        "the ledger journal.",
        ("Checkout API",),
        ("Sara Iqbal",),
        (),
        None,
    ),
    (
        "Helios launch retro",
        "postmortem",
        "Zoya Khan",
        "2026-09-24",
        "User feedback after the Helios beta: merchants loved the concept but "
        "the onboarding flow leaked 40% of signups. Feedback motivated the "
        "pause decision — fix onboarding before relaunching.",
        ("Helios",),
        (),
        ("discovery",),
        None,
    ),
    (
        "Vector DB eval",
        "spec",
        "Rohan Verma",
        "2026-07-20",
        "Evaluation that chose a dedicated vector DB over pgvector for Search "
        "v2: pgvector lost on recall at our index size and on operational "
        "maturity for ANN tuning.",
        ("Search v2",),
        (),
        ("vector-db",),
        None,
    ),
    (
        "Postgres upgrade plan",
        "spec",
        "Sara Iqbal",
        "2026-10-08",
        "Plan to upgrade Postgres to version 16 with a 30-minute downtime "
        "window. Still proposed — not yet accepted; rollback runbook included.",
        ("Postgres",),
        (),
        ("postgres",),
        None,
    ),
    (
        "Incident note (Aug)",
        "notes",
        "Dev Patel",
        "2026-08-28",
        "Short incident note on an August ledger write stall. Superseded by "
        "the September postmortem once the deeper Redis failover root cause "
        "was confirmed.",
        ("Ledger Service",),
        (),
        (),
        None,
    ),
]

# -------------------------------------------------------------- decisions ---
# title, made_by, date, recorded_in, affects, status, summary
DECISIONS = [
    (
        "Pause Project Helios",
        "Priya Nair",
        "2026-09-28",
        "Helios pause RFC",
        ("Helios",),
        "accepted",
        "Helios paused for ~3 months after Zoya's retro showed onboarding "
        "leaking 40% of signups; team refocuses on ledger stability first.",
    ),
    (
        "Single-writer ledger",
        "Priya Nair",
        "2026-06-10",
        "Payments architecture v3",
        ("Ledger Service",),
        "accepted",
        "All money movement goes through Ledger Service as the single source "
        "of truth with an append-only journal.",
    ),
    (
        "Redis Sentinel → Cluster",
        "Meera Krishnan",
        "2026-09-30",
        "Ledger incident postmortem (Sep)",
        ("Redis",),
        "accepted",
        "Migrate Redis from Sentinel to Cluster to prevent the failover split-"
        "brain that caused the September ledger incident.",
    ),
    (
        "Dedicated vector DB over pgvector",
        "Rohan Verma",
        "2026-07-22",
        "Vector DB eval",
        ("Search v2",),
        "accepted",
        "Search v2 uses a dedicated vector DB; pgvector lost on recall at "
        "scale and ANN operational maturity.",
    ),
    (
        "Diwali code freeze dates",
        "Meera Krishnan",
        "2026-10-05",
        "Oncall handoff — Diwali freeze",
        ("Ledger Service", "Checkout API", "Search v2", "Pipeforge", "Auth Rework"),
        "accepted",
        "No deploys Oct 28–Nov 5 across all active projects; Infra owns "
        "escalation during the freeze.",
    ),
    (
        "Postgres 16 upgrade",
        "Sara Iqbal",
        "2026-10-08",
        "Postgres upgrade plan",
        ("Postgres",),
        "proposed",
        "Upgrade Postgres to v16 with a 30-minute window. Proposed Oct 8 — "
        "not yet accepted; do not describe as done.",
    ),
    (
        "Checkout retry policy",
        "Vikram Rao",
        "2026-08-14",
        "Checkout latency deep-dive",
        ("Checkout API",),
        "accepted",
        "Checkout API retries against Ledger Service with jitter and "
        "idempotency keys to ride out lock contention.",
    ),
    (
        "Drop Helios entirely (rejected)",
        "Arjun Mehta",
        "2026-10-02",
        "Helios pause RFC",
        ("Helios",),
        "reverted",
        "Arjun briefly proposed dropping Helios entirely; reverted after "
        "Priya confirmed the pause-not-cancel direction.",
    ),
]

# -------------------------------------------------------------------- org ---
# person -> manager
REPORTS_TO = [
    ("Arjun Mehta", "Priya Nair"),
    ("Meera Krishnan", "Priya Nair"),
    ("Ishaan Bose", "Priya Nair"),
    ("Sara Iqbal", "Arjun Mehta"),
    ("Vikram Rao", "Arjun Mehta"),
    ("Dev Patel", "Meera Krishnan"),
    ("Ananya Das", "Meera Krishnan"),
    ("Tara Menon", "Ishaan Bose"),
    ("Aditya Kulkarni", "Zoya Khan"),
    ("Farah Sheikh", "Zoya Khan"),
]

# -------------------------------------------------------------- staffing ---
# person -> project (leads per PROJECTS; others on their team's main project)
WORKS_ON = [
    ("Priya Nair", "Ledger Service"),
    ("Arjun Mehta", "Helios"),
    ("Sara Iqbal", "Ledger Service"),
    ("Vikram Rao", "Checkout API"),
    ("Meera Krishnan", "Oncall Copilot"),
    ("Dev Patel", "Oncall Copilot"),
    ("Ananya Das", "Oncall Copilot"),
    ("Rohan Verma", "Search v2"),
    ("Kavya Reddy", "Search v2"),
    ("Ishaan Bose", "Pipeforge"),
    ("Tara Menon", "Pipeforge"),
    ("Nikhil Anand", "Auth Rework"),
    ("Zoya Khan", "Helios"),
    ("Aditya Kulkarni", "Docs Portal"),
    ("Farah Sheikh", "Docs Portal"),
]

# --------------------------------------------------------------- episodes ---
# text, ts, kind, involves ((name, kind) tuples), topics
EPISODES_SAM = [
    (
        "Discussed the Sep ledger outage; root cause was Redis failover, Dev ran the runbook.",
        "2026-10-10",
        "note",
        (("Dev Patel", "Person"), ("Ledger Service", "System"), ("Redis", "System")),
        ("incident-response",),
    ),
    (
        "Sam prefers concise answers with sources cited.",
        "2026-10-11",
        "note",
        (),
        (),
    ),
    (
        "Helios pause decision — Priya decided Sep 28 after Zoya's retro.",
        "2026-10-11",
        "note",
        (("Priya Nair", "Person"), ("Helios", "Project")),
        (),
    ),
    (
        "Ananya is the Redis expert; wrote the failover runbook.",
        "2026-10-12",
        "note",
        (("Ananya Das", "Person"), ("Redis", "System")),
        ("redis",),
    ),
    (
        "Postgres 16 upgrade still proposed, not accepted — don't state it as done.",
        "2026-10-12",
        "note",
        (("Sara Iqbal", "Person"), ("Postgres", "System")),
        ("postgres",),
    ),
    (
        "Sam asked about checkout latency; traced to ledger lock contention (Vikram's deep-dive).",
        "2026-10-13",
        "note",
        (("Vikram Rao", "Person"), ("Checkout API", "Project")),
        (),
    ),
    # --- plausible filler (standup notes / doc shared) ---
    (
        "Standup: Search v2 relevance tuning on track; Kavya shared the vector-db recall findings.",
        "2026-10-09",
        "standup",
        (("Kavya Reddy", "Person"), ("Search v2", "Project")),
        ("search", "vector-db"),
    ),
    (
        "Shared the Pipeforge backfill plan doc with Ishaan; warehouse window is tight this weekend.",
        "2026-10-09",
        "note",
        (("Ishaan Bose", "Person"), ("Pipeforge", "Project")),
        ("warehouse",),
    ),
    (
        "Standup: Oncall Copilot handoff scheduled; Diwali freeze starts Oct 28.",
        "2026-10-13",
        "standup",
        (("Meera Krishnan", "Person"),),
        ("oncall",),
    ),
    (
        "Read Nikhil's auth threat model; pen-test findings look solid, no blockers.",
        "2026-10-13",
        "doc-shared",
        (("Nikhil Anand", "Person"), ("Auth Service", "System")),
        ("auth",),
    ),
]

# ---------------------------------------------------------------- beliefs ---
# text, confidence, source, ts
BELIEFS_SAM = [
    ("Ledger Service is the payments single source of truth.", 0.95, "Payments architecture v3", "2026-10-10"),
    ("Redis Cluster migration accepted Sep 30.", 0.9, "Ledger incident postmortem (Sep)", "2026-10-10"),
    ("Helios is cancelled", 0.3, "team rumor", "2026-10-01"),  # older, will be contradicted
    ("Helios is paused, not cancelled.", 0.95, "Helios pause RFC", "2026-10-11"),
    ("Sam prefers concise, sourced answers.", 0.9, "episode 2026-10-11", "2026-10-11"),
    ("Checkout API depends on Ledger Service.", 1.0, "Payments architecture v3", "2026-10-12"),
    ("Diwali freeze: no deploys Oct 28-Nov 5.", 0.9, "Oncall handoff — Diwali freeze", "2026-10-13"),
]

# (new belief text, old belief text) pairs for CONTRADICTS edges
BELIEF_CONTRADICTIONS = [
    ("Helios is paused, not cancelled.", "Helios is cancelled"),
]
