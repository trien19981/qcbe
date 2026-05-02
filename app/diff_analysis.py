"""Semantic diff analysis using chunk embeddings (pgvector).

Matches chunks between two document versions by cosine similarity, then
classifies each pair as unchanged / modified / added / removed.

Thresholds (BAAI/bge-m3, normalized → cosine = 1 - L2²/2):
  cosine >= 0.97  → unchanged   (skip — not shown to reviewer)
  cosine  0.65–0.97 → modified  (show diff)
  no match (cosine < 0.65) → added or removed
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UNCHANGED_THRESHOLD = 0.97
_MATCH_THRESHOLD = 0.65


async def _count_chunks_with_embeddings(session: AsyncSession, version_id: uuid.UUID) -> tuple[int, int]:
    """Return (total_chunks, chunks_with_embeddings) for a version."""
    total = (
        await session.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_version_id = :vid"),
            {"vid": version_id},
        )
    ).scalar_one()
    with_emb = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM chunks c"
                " JOIN chunk_embeddings ce ON ce.chunk_id = c.id"
                " WHERE c.doc_version_id = :vid"
            ),
            {"vid": version_id},
        )
    ).scalar_one()
    return int(total or 0), int(with_emb or 0)


async def analyze_diff_semantic_async(diff_review_id: str) -> None:
    """Compute semantic diff between two document versions using chunk embeddings.

    Reads old_version_id / new_version_id from diff_reviews, queries pgvector for
    pairwise cosine similarities, runs greedy chunk matching, then writes the
    results to diff_changes and updates diff_reviews.total_changes.

    Falls back silently (no writes) when embeddings are incomplete so the router's
    basic-diff fallback can take over after the 5-minute window.
    """
    from app.database import AsyncSessionLocal

    diff_review_uuid = uuid.UUID(diff_review_id)

    async with AsyncSessionLocal() as session:
        rev = (
            await session.execute(
                text("SELECT id, old_version_id, new_version_id FROM diff_reviews WHERE id = :id"),
                {"id": diff_review_uuid},
            )
        ).first()
        if rev is None:
            return

        old_ver_id: uuid.UUID = rev.old_version_id
        new_ver_id: uuid.UUID = rev.new_version_id

        # Guard: both versions must have full embedding coverage
        old_total, old_emb = await _count_chunks_with_embeddings(session, old_ver_id)
        new_total, new_emb = await _count_chunks_with_embeddings(session, new_ver_id)
        if old_total == 0 or new_total == 0 or old_emb < old_total or new_emb < new_total:
            return

        # Load chunk metadata (content + index) for both versions
        old_chunks = (
            await session.execute(
                text(
                    "SELECT id, chunk_index, content_text"
                    " FROM chunks WHERE doc_version_id = :vid ORDER BY chunk_index"
                ),
                {"vid": old_ver_id},
            )
        ).all()
        new_chunks = (
            await session.execute(
                text(
                    "SELECT id, chunk_index, content_text"
                    " FROM chunks WHERE doc_version_id = :vid ORDER BY chunk_index"
                ),
                {"vid": new_ver_id},
            )
        ).all()

        if not old_chunks or not new_chunks:
            return

        # Compute pairwise cosine similarities via pgvector.
        # For normalized bge-m3 vectors: cosine_sim = 1 − (L2_dist² / 2).
        # Cross-join is acceptable for typical document sizes (< 200 chunks/version).
        pairs = (
            await session.execute(
                text(
                    "SELECT"
                    "  oc.id              AS old_id,"
                    "  oc.chunk_index     AS old_idx,"
                    "  oc.content_text    AS old_content,"
                    "  nc.id              AS new_id,"
                    "  nc.chunk_index     AS new_idx,"
                    "  nc.content_text    AS new_content,"
                    "  1.0 - (POWER(oe.embedding <-> ne.embedding, 2) / 2.0) AS cosine_sim"
                    " FROM chunks oc"
                    " JOIN chunk_embeddings oe ON oe.chunk_id = oc.id"
                    " CROSS JOIN chunks nc"
                    " JOIN chunk_embeddings ne ON ne.chunk_id = nc.id"
                    " WHERE oc.doc_version_id = :old_ver_id"
                    "   AND nc.doc_version_id = :new_ver_id"
                    " ORDER BY cosine_sim DESC"
                ),
                {"old_ver_id": old_ver_id, "new_ver_id": new_ver_id},
            )
        ).all()

        # ── Greedy matching ───────────────────────────────────────────────────
        # Consume pairs sorted by similarity DESC; each chunk matched at most once.
        matched_old: dict[uuid.UUID, dict] = {}
        matched_new: set[uuid.UUID] = set()

        for row in pairs:
            sim = float(row.cosine_sim)
            if sim < _MATCH_THRESHOLD:
                break
            old_id = row.old_id
            new_id = row.new_id
            if old_id not in matched_old and new_id not in matched_new:
                matched_old[old_id] = {
                    "new_id": new_id,
                    "new_idx": int(row.new_idx),
                    "sim": sim,
                    "old_content": row.old_content,
                    "new_content": row.new_content,
                }
                matched_new.add(new_id)

        old_map = {r.id: r for r in old_chunks}
        new_map = {r.id: r for r in new_chunks}
        unmatched_old = set(old_map.keys()) - set(matched_old.keys())
        unmatched_new = set(new_map.keys()) - matched_new

        # ── Collect change items with sort key (new-document reading order) ──
        items: list[dict] = []

        for old_id, m in matched_old.items():
            if m["sim"] >= _UNCHANGED_THRESHOLD:
                continue  # identical content — skip
            items.append(
                {
                    "sort_key": m["new_idx"],
                    "change_type": "modified",
                    "chunk_old_id": old_id,
                    "chunk_new_id": m["new_id"],
                    "content_before": m["old_content"],
                    "content_after": m["new_content"],
                    "similarity_score": m["sim"],
                }
            )

        for new_id in unmatched_new:
            nc = new_map[new_id]
            items.append(
                {
                    "sort_key": int(nc.chunk_index),
                    "change_type": "added",
                    "chunk_old_id": None,
                    "chunk_new_id": new_id,
                    "content_before": None,
                    "content_after": nc.content_text,
                    "similarity_score": None,
                }
            )

        for old_id in unmatched_old:
            oc = old_map[old_id]
            items.append(
                {
                    # Use old index as position hint — interleaves with new-doc order
                    "sort_key": int(oc.chunk_index),
                    "change_type": "removed",
                    "chunk_old_id": old_id,
                    "chunk_new_id": None,
                    "content_before": oc.content_text,
                    "content_after": None,
                    "similarity_score": None,
                }
            )

        items.sort(key=lambda x: x["sort_key"])

        # ── Insert diff_changes in reading order ──────────────────────────────
        # Stagger timestamps by 1 ms so created_at order matches sort_key order.
        now = datetime.now(UTC)
        for i, item in enumerate(items):
            ts = now + timedelta(microseconds=i * 1000)
            await session.execute(
                text(
                    "INSERT INTO diff_changes"
                    "  (id, diff_review_id, chunk_old_id, chunk_new_id, change_type,"
                    "   content_before, content_after, similarity_score,"
                    "   approval_status, created_at)"
                    " VALUES"
                    "  (:id, :diff_review_id, :chunk_old_id, :chunk_new_id, :change_type,"
                    "   :content_before, :content_after, :similarity_score,"
                    "   'pending'::diff_status, :created_at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "diff_review_id": diff_review_uuid,
                    "chunk_old_id": item["chunk_old_id"],
                    "chunk_new_id": item["chunk_new_id"],
                    "change_type": item["change_type"],
                    "content_before": item["content_before"],
                    "content_after": item["content_after"],
                    "similarity_score": item["similarity_score"],
                    "created_at": ts,
                },
            )

        n = len(items)
        await session.execute(
            text(
                "UPDATE diff_reviews"
                " SET total_changes = :total,"
                "     approved_count = 0,"
                "     rejected_count = 0,"
                "     ai_summary = :summary"
                " WHERE id = :id"
            ),
            {
                "total": n,
                "summary": f"Semantic diff: {n} thay đổi được phát hiện.",
                "id": diff_review_uuid,
            },
        )
        await session.commit()
