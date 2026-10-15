"""Trace explainability — render a traversed path as a human evidence chain."""


def render_path(path):
    """Render path segments as an indented 'Because:' evidence chain.

    ``path`` is a list of segments, each a dict like
    ``{"from": {"label": ..., "name": ...}, "rel": "TYPE",
      "to": {"label": ..., "name": ...}}``.
    Plain ASCII arrows keep it readable everywhere.
    """
    if not path:
        return "(direct lookup — no graph traversal needed)"
    lines = ["Because:"]
    for seg in path:
        frm = seg.get("from", {})
        to = seg.get("to", {})
        rel = seg.get("rel", "")
        lines.append(
            f'  {frm.get("label", "?")} "{frm.get("name", "")}" '
            f'-[{rel}]-> {to.get("label", "?")} "{to.get("name", "")}"'
        )
    return "\n".join(lines)


def render_answer(answer, path):
    """answer text + rendered evidence chain."""
    return f"{answer}\n{render_path(path)}"
