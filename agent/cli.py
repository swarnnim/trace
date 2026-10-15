"""Trace REPL: ask, remember, explain, demo, quit.

Run: ~/workspace/falkordb-graph-hacks/.venv/bin/python -m agent.cli
"""

from __future__ import annotations

import sys

from agent.loop import AgentLoop
from agent.explain import render_path

DEMO_QUESTIONS = [
    "If the ledger service goes down, what breaks?",
    "Who decided to pause Helios, and why?",
    "Who knows Redis best?",
    "What did we discuss about the payments outage?",
    "Is the Postgres upgrade done?",
    "What breaks if Redis goes down?",
]


def run_demo(loop: AgentLoop) -> None:
    for i, q in enumerate(DEMO_QUESTIONS, 1):
        print(f"\n=== demo {i}/6 ===")
        print(f"Q: {q}")
        answer, path = loop.ask(q)  # answer already embeds the evidence chain
        print(f"A: {answer}")
        print(f"[path segments: {len(path)}]")


def main() -> None:
    loop = AgentLoop()
    print("trace> Trace agent ready. Commands: ask <q> | remember <text> | explain | demo | quit")
    while True:
        try:
            line = input("trace> ")
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        line = line.strip()
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        cmd = cmd.lower()
        if cmd in ("quit", "exit"):
            print("bye.")
            return
        if cmd == "ask":
            if not rest:
                print("usage: ask <question>")
                continue
            answer, path = loop.ask(rest)
            print(answer)
        elif cmd == "remember":
            if not rest:
                print("usage: remember <text>")
                continue
            eid = loop.episodic.remember(loop.user, rest)
            print(f"remembered (episode {eid[:8]}).")
        elif cmd == "explain":
            if not loop.last_path:
                print("nothing asked yet.")
            else:
                print(render_path(loop.last_path))
        elif cmd == "demo":
            run_demo(loop)
        else:
            print(f"unknown command: {cmd}. Try: ask | remember | explain | demo | quit")


if __name__ == "__main__":
    main()
