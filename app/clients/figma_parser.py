"""Convert a Figma node tree (from /files/{key}/nodes) into Markdown.

Strategy: depth-first traversal, collecting text layers, component names,
and structural frames. Output is a structured markdown document suitable
for chunking and embedding.
"""

from __future__ import annotations

_SECTION_TYPES = {"FRAME", "GROUP", "SECTION", "COMPONENT_SET"}
_TEXT_TYPE = "TEXT"
_SKIP_TYPES = {"VECTOR", "ELLIPSE", "POLYGON", "STAR", "LINE", "BOOLEAN_OPERATION"}


def _traverse(node: dict, depth: int, lines: list[str]) -> None:
    node_type = node.get("type", "")
    name = (node.get("name") or "").strip()

    if node_type == _TEXT_TYPE:
        text = (node.get("characters") or "").strip()
        if text:
            lines.append(text)
        return

    if node_type in _SKIP_TYPES:
        return

    if node_type in _SECTION_TYPES and name and depth <= 4:
        heading = "#" * min(depth + 1, 4)
        lines.append(f"\n{heading} {name}\n")

    for child in node.get("children", []):
        _traverse(child, depth + 1, lines)


def _collect_instance_component_ids(node: dict, out: set[str]) -> None:
    node_type = node.get("type", "")
    if node_type == "INSTANCE":
        cid = node.get("componentId") or node.get("component_id")
        if cid:
            out.add(str(cid))
    for child in node.get("children", []):
        _collect_instance_component_ids(child, out)


def figma_node_to_markdown(
    node: dict,
    *,
    file_components: list[dict] | None = None,
    screenshot_url: str | None = None,
) -> str:
    """Convert a Figma node dict (document field from /nodes response) to markdown.

    Optional enrichments:
    - file_components: result of GET /files/{key}/components, used to map instance componentId -> component name/key.
    - screenshot_url: result of GET /images/{key}?ids={node_id}&format=png for visual reference.
    """
    frame_name = (node.get("name") or "Figma Frame").strip()
    lines: list[str] = [f"# {frame_name}\n"]
    for child in node.get("children", []):
        _traverse(child, depth=1, lines=lines)

    # Enrich: screenshot URL
    if screenshot_url:
        lines.append("\n## Screenshot\n")
        lines.append(screenshot_url)

    # Enrich: component types used in this frame (best-effort)
    if file_components:
        comp_by_node_id = {
            str(c.get("node_id") or ""): c
            for c in file_components
            if (c.get("node_id") or "").strip()
        }
        used: set[str] = set()
        _collect_instance_component_ids(node, used)
        names: list[str] = []
        for cid in sorted(used):
            c = comp_by_node_id.get(cid)
            if not c:
                continue
            name = (c.get("name") or "").strip()
            key = (c.get("key") or "").strip()
            if name and key:
                names.append(f"- {name} (`{key}`)")
            elif name:
                names.append(f"- {name}")
            elif key:
                names.append(f"- `{key}`")
        if names:
            lines.append("\n## Components used (instances)\n")
            lines.extend(names)

    md = "\n".join(lines)
    # Collapse 3+ consecutive blank lines → 2
    import re
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()
