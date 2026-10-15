# Demo dataset spec — "Northwind Labs" (fictional)

> Spec only. Loading this into FalkorDB (`demo_data/loader.py`) is event work
> (Oct 15–18). Designed so the demo questions need 2–4 hop traversals.

Fictional dev-tools startup, ~15 people, 8 projects. Names are invented.

## People (15)

| # | Name | Role | Team | Skills (Topic nodes) |
|---|---|---|---|---|
| 1 | Priya Nair | CTO | Platform | architecture, payments |
| 2 | Arjun Mehta | Eng Manager | Payments | payments, oncall |
| 3 | Sara Iqbal | Senior Backend | Payments | payments, ledger, postgres |
| 4 | Vikram Rao | Backend | Payments | ledger, redis |
| 5 | Meera Krishnan | Eng Manager | Infra | kubernetes, oncall |
| 6 | Dev Patel | SRE | Infra | kubernetes, incident-response |
| 7 | Ananya Das | SRE | Infra | incident-response, monitoring |
| 8 | Rohan Verma | Senior Backend | Search | search, elasticsearch |
| 9 | Kavya Reddy | Backend | Search | search, vector-db |
| 10 | Ishaan Bose | Eng Manager | Data | pipelines, warehouse |
| 11 | Tara Menon | Data Engineer | Data | pipelines, dbt |
| 12 | Nikhil Anand | Security Eng | Security | auth, pen-testing |
| 13 | Zoya Khan | Product Manager | Product | discovery, analytics |
| 14 | Aditya Kulkarni | Designer | Product | ux, research |
| 15 | Farah Sheikh | Tech Writer | Product | docs, onboarding |

Org: Priya → {Arjun, Meera, Ishaan}; Arjun → {Sara, Vikram}; Meera → {Dev, Ananya};
Ishaan → {Tara}; Zoya → {Aditya, Farah} (dotted line to eng managers).

## Projects (8)

| # | Project | Status | Lead | Depends on |
|---|---|---|---|---|
| 1 | Helios | paused | Arjun | Ledger Service, Postgres |
| 2 | Ledger Service | active | Sara | Postgres, Redis |
| 3 | Checkout API | active | Vikram | Ledger Service |
| 4 | Search v2 | active | Rohan | Elasticsearch, Vector DB |
| 5 | Pipeforge | active | Ishaan | Warehouse, Kafka |
| 6 | Oncall Copilot | shipped | Meera | PagerDuty (external), Runbook Docs |
| 7 | Auth Rework | active | Nikhil | Auth Service |
| 8 | Docs Portal | shipped | Farah | — |

Systems (System nodes): Postgres (critical), Redis (high), Elasticsearch (high),
Vector DB (medium), Kafka (high), Warehouse (medium), Auth Service (critical),
Ledger Service is both a Project and a System (model as both labels).

## Docs (12)

| # | Title | Kind | Author | About | Key content hook |
|---|---|---|---|---|---|
| 1 | Helios pause RFC | rfc | Arjun | Helios | proposes pausing; cites ledger incident |
| 2 | Ledger incident postmortem (Sep) | postmortem | Dev | Ledger Service | root cause: Redis failover; mentions Sara's fix |
| 3 | Redis failover runbook | notes | Ananya | Redis | procedure Dev followed |
| 4 | Payments architecture v3 | spec | Priya | Ledger Service, Checkout API | decision: single-writer ledger |
| 5 | Search relevance tuning log | notes | Kavya | Search v2 | vector-db recall findings |
| 6 | Pipeforge backfill plan | spec | Tara | Pipeforge | warehouse window constraints |
| 7 | Auth threat model | spec | Nikhil | Auth Service | pen-test findings |
| 8 | Oncall handoff — Diwali freeze | notes | Meera | Oncall Copilot | freeze dates, escalation |
| 9 | Checkout latency deep-dive | postmortem | Vikram | Checkout API | traces slowness to ledger lock contention |
| 10 | Helios launch retro | postmortem | Zoya | Helios | user feedback that motivated pause |
| 11 | Vector DB eval | spec | Rohan | Search v2 | why pgvector lost to dedicated vector DB |
| 12 | Postgres upgrade plan | spec | Sara | Postgres | version + downtime window |

Doc relations: D2 SUPERSEDES an older incident note (add `Incident note (Aug)` as
Doc 13, superseded); D1 MENTIONS Priya, Sara, Topic(payments); D9 MENTIONS Sara.

## Decisions (8)

| # | Decision | Made by | Date | Recorded in | Affects | Status |
|---|---|---|---|---|---|---|
| 1 | Pause Project Helios | Priya | 2026-09-28 | D1 | Helios | accepted |
| 2 | Single-writer ledger | Priya | 2026-06-10 | D4 | Ledger Service | accepted |
| 3 | Redis Sentinel → Cluster | Meera | 2026-09-30 | D2 | Redis | accepted |
| 4 | Dedicated vector DB over pgvector | Rohan | 2026-07-22 | D11 | Search v2 | accepted |
| 5 | Diwali code freeze dates | Meera | 2026-10-05 | D8 | (all active projects) | accepted |
| 6 | Postgres 16 upgrade | Sara | 2026-10-08 | D12 | Postgres | proposed |
| 7 | Checkout retry policy | Vikram | 2026-08-14 | D9 | Checkout API | accepted |
| 8 | Drop Helios entirely (rejected) | Arjun | 2026-10-02 | D1 | Helios | reverted |

## Episodes (seed memory, ~10 for demo user "sam")

1. 2026-10-10: "Discussed the Sep ledger outage; root cause was Redis failover, Dev ran the runbook." → INVOLVES Dev, Ledger Service, Redis
2. 2026-10-11: "Sam prefers concise answers with sources cited." → (preference Belief, confidence 0.9)
3. 2026-10-11: "Helios pause decision — Priya decided Sep 28 after Zoya's retro." → INVOLVES Priya, Helios
4. 2026-10-12: "Ananya is the Redis expert; wrote the failover runbook." → INVOLVES Ananya, Redis
5. 2026-10-12: "Postgres 16 upgrade still proposed, not accepted — don't state it as done." → (Belief, guards hallucination)
6. 2026-10-13: "Sam asked about checkout latency; traced to ledger lock contention (Vikram's deep-dive)." → INVOLVES Vikram, Checkout API

Plus 4 filler episodes (standup notes, doc shared) to make recall non-trivial.

## Beliefs (seed semantic memory, ~6)

1. "Ledger Service is the payments single source of truth." (conf 0.95, source D4)
2. "Redis Cluster migration accepted Sep 30." (conf 0.9, source D2)
3. "Helios is paused, not cancelled." (conf 0.95, source D1) + CONTRADICTS older belief "Helios is cancelled" (conf 0.3, demonstrates revision)
4. "Sam prefers concise, sourced answers." (conf 0.9, source episode 2)
5. "Checkout API depends on Ledger Service." (conf 1.0, source D4)
6. "Diwali freeze: no deploys Oct 28–Nov 5." (conf 0.9, source D8)

## Demo questions this dataset is built to answer

1. *"If the ledger service goes down, what breaks?"*
   → Ledger Service ← DEPENDS_ON ← {Checkout API, Helios} (+ Postgres/Redis upstream);
   3-hop blast radius, PageRank-ordered.
2. *"Who decided to pause Helios, and why?"*
   → Decision(1) ← MADE ← Priya; DECIDED_IN → D1; D1 MENTIONS Zoya's retro (D10).
   3-hop evidence chain.
3. *"Who knows Redis best?"*
   → Topic(redis) ← KNOWS ← {Vikram, Ananya}; PageRank on KNOWS edges +
   AUTHORED runbook → Ananya wins.
4. *"What did we discuss about the payments outage?"* (memory)
   → Episode(1) via ABOUT Topic(payments) + INVOLVES Ledger Service; shows
   prior-session recall with timestamp.
5. *"Is the Postgres upgrade done?"* (anti-hallucination)
   → Decision(6) status=proposed → correct answer: "No — proposed Oct 8 by
   Sara, not yet accepted." Belief 5 guards it.
6. *"What breaks if Redis goes down?"*
   → Redis ← DEPENDS_ON ← Ledger Service ← DEPENDS_ON ← {Checkout API, Helios};
   2-hop cascade demo.
