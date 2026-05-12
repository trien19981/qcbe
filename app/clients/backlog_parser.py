"""Convert Backlog issue + comments into Markdown for chunking."""

from __future__ import annotations

import re


def _strip_html(text: str) -> str:
    """Remove basic HTML tags (Backlog sometimes returns HTML in descriptions)."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def backlog_issue_to_markdown(issue: dict, comments: list[dict]) -> str:
    """Build a markdown document from a Backlog issue dict + its comments list."""
    key = issue.get("issueKey") or issue.get("id", "")
    summary = issue.get("summary") or ""
    description = _strip_html(issue.get("description") or "")
    status = (issue.get("status") or {}).get("name") or ""
    priority = (issue.get("priority") or {}).get("name") or ""
    assignee = (issue.get("assignee") or {}).get("name") or "—"
    milestone_list = issue.get("milestone") or []
    milestones = ", ".join(m.get("name", "") for m in milestone_list) or "—"
    category_list = issue.get("category") or []
    categories = ", ".join(c.get("name", "") for c in category_list) or "—"

    lines: list[str] = [
        f"# [{key}] {summary}",
        "",
        f"**Status:** {status}  ",
        f"**Priority:** {priority}  ",
        f"**Assignee:** {assignee}  ",
        f"**Milestone:** {milestones}  ",
        f"**Category:** {categories}  ",
        "",
    ]

    if description:
        lines += ["## Description", "", description, ""]

    relevant_comments = [
        c for c in (comments or [])
        if (c.get("content") or "").strip()
    ]
    if relevant_comments:
        lines.append("## Comments")
        lines.append("")
        for c in relevant_comments:
            author = (c.get("createdUser") or {}).get("name") or "—"
            created = (c.get("created") or "")[:10]
            content = _strip_html(c.get("content") or "").strip()
            if content:
                lines.append(f"**{author}** ({created}):")
                lines.append(content)
                lines.append("")

    return "\n".join(lines).strip()
