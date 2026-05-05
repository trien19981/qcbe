"""Load per-project AI prompt overrides from ai_prompts; fallback to built-in defaults."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# --- Prompt keys (stable API / DB values) ---------------------------------

QA_ANSWER_SYSTEM = "qa_answer_system"
QA_SUGGESTED_QUESTIONS_USER = "qa_suggested_questions_user"
TC_GENERATE_PROMPT = "tc_generate_prompt"

# --- Defaults (mirror previous hardcoded strings) -------------------------

DEFAULT_QA_ANSWER_SYSTEM = (
    "Bạn là trợ lý Q&A cho tài liệu dự án.\n"
    "Chỉ trả lời dựa trên CONTEXT. Nếu không đủ thông tin, nói rõ không tìm thấy.\n"
    "Khi sử dụng 1 đoạn trong CONTEXT, chèn token CITATION_i đúng index, ví dụ: ... CITATION_0\n"
    "\n"
    "Khi CONTEXT chứa thông tin từ NHIỀU VERSION của cùng tài liệu, hãy trả lời theo cấu trúc:\n"
    "1. Dẫn chứng từng phiên bản: 'Theo tài liệu đã approved (vX): ...' và 'Tuy nhiên, phiên bản đang review (vY) mô tả lại: ...'\n"
    "2. Kết luận: version đã approved là tài liệu chính thức hiện tại.\n"
    "3. Đánh dấu điểm khác biệt bằng 🔴 **Thay đổi:** <nội dung> để người đọc chú ý.\n"
)

DEFAULT_QA_SUGGESTED_QUESTIONS_USER = (
    "Dựa trên tài liệu sau, tạo 3 câu hỏi ngắn để người dùng hỏi AI. "
    "Mỗi câu hỏi 1 dòng.\n\n---\n{context}\n---"
)

DEFAULT_TC_GENERATE_PROMPT = """\
Bạn là chuyên gia QA. Dựa trên tài liệu dưới đây, hãy tạo danh sách testcase đầy đủ theo format JSON.
Toàn bộ nội dung (title, steps, expected_result) phải viết bằng tiếng Việt.

Mỗi testcase gồm:
- title: tiêu đề ngắn gọn bằng tiếng Việt (tối đa 80 ký tự)
- steps: danh sách bước thực hiện bằng tiếng Việt (array of string)
- expected_result: kết quả mong đợi bằng tiếng Việt
- priority: "critical" | "high" | "medium" | "low"
- tc_type: "manual" | "api" | "e2e"
- source_chunk_index: số nguyên index (0-based) của đoạn tài liệu liên quan nhất trong danh sách [TÀI LIỆU] (mỗi đoạn bắt đầu bằng dòng "--- Chunk N ---")

Chỉ trả về JSON array, không có text nào khác.
Tạo đủ testcase để cover: happy path, error path, edge case, boundary value.

[TÀI LIỆU]
{context}
"""


async def get_ai_prompt(
    session: AsyncSession,
    project_id: uuid.UUID,
    prompt_key: str,
    default: str,
) -> str:
    """Return DB content for (project_id, prompt_key) if non-empty; else default."""
    r = await session.execute(
        text(
            """
            SELECT content FROM ai_prompts
            WHERE project_id = CAST(:pid AS uuid) AND prompt_key = :pk
            LIMIT 1
            """
        ),
        {"pid": str(project_id), "pk": prompt_key},
    )
    row = r.scalar_one_or_none()
    if row is None:
        return default
    s = str(row).strip()
    return s if s else default


def inject_context(template: str, context: str) -> str:
    """Substitute {context}; avoids str.format KeyError if template has other braces."""
    return template.replace("{context}", context)
