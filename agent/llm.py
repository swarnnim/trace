"""Trace LLM interface — $0 offline by default.

MockLLM (deterministic, template-based) is the demo path. RealLLMAdapter is a
STUB: it only constructs when TRACE_LLM_API_KEY is set, otherwise raises.
"""

from __future__ import annotations

import os


class LLM:
    def compose(self, question: str, tool_outputs: list[dict]) -> str:
        """Compose a final answer from per-tool outputs.

        tool_outputs entries: {"tool": name, "answer": str, "path": list}.
        """
        raise NotImplementedError


class MockLLM(LLM):
    """Deterministic template-based composer. Never invents facts."""

    def compose(self, question: str, tool_outputs: list[dict]) -> str:
        if not tool_outputs:
            return "I couldn't find anything in the graph for that."
        parts = []
        for out in tool_outputs:
            ans = (out.get("answer") or "").strip()
            if not ans:
                continue
            parts.append(f"{ans} (via {out.get('tool', 'graph tool')})")
        if not parts:
            return "I couldn't find anything in the graph for that."
        text = " ".join(parts)
        # Keep it concise: 2-4 sentences. Truncate runaway templates.
        raw = text.replace("! ", ". ").replace("? ", ". ").split(". ")
        sentences = []
        for s in raw:
            s = s.strip().rstrip(".")
            if s:
                sentences.append(s + ".")
        return " ".join(sentences[:4])


class RealLLMAdapter(LLM):
    """STUB — real LLM behind env config. Never used in the demo path."""

    def __init__(self) -> None:
        key = os.environ.get("TRACE_LLM_API_KEY")
        if not key:
            raise RuntimeError("real LLM not configured")
        self.api_key = key

    def compose(self, question: str, tool_outputs: list[dict]) -> str:
        raise RuntimeError("real LLM not configured for demo use")


def get_llm() -> LLM:
    """MockLLM unless TRACE_LLM=real and a key is present."""
    if os.environ.get("TRACE_LLM") == "real" and os.environ.get("TRACE_LLM_API_KEY"):
        return RealLLMAdapter()
    return MockLLM()
