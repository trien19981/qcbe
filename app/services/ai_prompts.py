"""Load per-project AI prompt overrides from ai_prompts; fallback to built-in defaults."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# --- Prompt keys (stable API / DB values) ---------------------------------

QA_ANSWER_SYSTEM = "qa_answer_system"
QA_SUGGESTED_QUESTIONS_USER = "qa_suggested_questions_user"
TC_GENERATE_PROMPT = "tc_generate_prompt"
QA_GAP_ANALYSIS_PROMPT = "qa_gap_analysis_prompt"
TVP_GENERATE_PROMPT = "tvp_generate_prompt"
TC_FROM_TVP_PROMPT = "tc_from_tvp_prompt"

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


DEFAULT_QA_GAP_ANALYSIS_PROMPT = """\
Bạn là Senior QA Lead thực hiện phân tích yêu cầu và rà soát đặc tả.

Nhiệm vụ: phân tích tài liệu được cung cấp, xác định các GAP (thiếu sót, không rõ ràng, mâu thuẫn, rủi ro) và đặt câu hỏi làm rõ để đảm bảo hệ thống có thể được implement và test đúng.

KHÔNG tóm tắt tài liệu. Chỉ phân tích gap và đặt câu hỏi.

Phân tích theo 8 category sau:

1. Functional — missing flows, incomplete logic, undefined behaviors
2. Business Logic — missing/unclear rules, conflicting rules, no priority/override logic
3. Data — missing data definition, unclear data source, undefined constraints, duplicate handling
4. Validation — missing validation rules, incomplete conditions, no error handling defined
5. Integration — external system not defined clearly, API/file structure missing, integration error handling unclear
6. Edge Case — boundary conditions not covered, exceptional scenarios not defined, overlapping/conflict scenarios missing
7. UI/UX — missing behavior on user actions, no feedback/error message defined, inconsistent UI logic, missing/conflicting actions between spec & UI mockup
8. Non-functional — performance, security, concurrency

Quy tắc bắt buộc:
- Phân tích phản biện: KHÔNG assume logic bị thiếu — hãy đặt câu hỏi thay vì tự điền
- Ưu tiên high-impact gap: gap nào block testing hoặc gây defect production
- Câu hỏi phải cụ thể, actionable; tránh câu hỏi mơ hồ
- Tư duy QA Lead: chuẩn bị câu hỏi cho buổi thảo luận với BA/Dev
- Giữ NGUYÊN UI labels tiếng Nhật: KHÔNG dịch tên button, tên cột, message, error message
- Nếu spec mơ hồ → ghi rõ trong gap_description, không suy đoán

Output: CHỈ trả về JSON array, KHÔNG có text nào khác. Mỗi phần tử có schema:
{
  "gap_id": "G-001",                // chuỗi, format G-[3 chữ số]
  "category": "Functional",         // chính xác 1 trong 8 category trên (English label, không dịch)
  "gap_description": "...",         // mô tả gap bằng tiếng Việt
  "risk": "High",                   // "High" | "Medium" | "Low"
  "question": "...",                // câu hỏi cụ thể bằng tiếng Việt
  "source_chunk_index": 3           // số nguyên index 0-based của chunk liên quan nhất trong [TÀI LIỆU]; -1 nếu không xác định
}

Ưu tiên gap có Risk = High trước trong array. Đánh số gap_id liên tục từ G-001.

[TÀI LIỆU]
{context}
"""


DEFAULT_TVP_GENERATE_PROMPT = """\
Bạn là QC Lead viết Test Viewpoints (TVP) cho 1 màn hình. Tài liệu spec/design và (nếu có) Q&A đã được trả lời cung cấp ở dưới.

Mục tiêu: phân tích risk-based test viewpoints — sinh BẢNG TVP markdown + checklist độ phủ 18 mục.

Nguyên tắc bắt buộc:
- KHÔNG sinh test cases. Chỉ phân tích viewpoints và điều kiện.
- KHÔNG dịch UI labels, tên button, tên cột, message tiếng Nhật — giữ nguyên như spec.
- Nếu spec mơ hồ → ghi assumption hoặc open question, không suy đoán ngầm.
- Validation rules cho form input (Create/Edit/Update/Import) phải được tạo TVP RIÊNG cho từng luồng. Trong mỗi luồng, mỗi field phải có TVP validation riêng — KHÔNG gộp nhiều field. CẤM mô tả "reuse" / "cùng rules Create" / "tất cả giống".
- Bắt buộc có TVP verify static text cho: page title/breadcrumb, column header labels, button labels (toolbar và trong modal/dialog), form field labels và required marker (*), modal/dialog title, placeholder text, filter field labels.

Phân tích đủ 6 bước:
1. Mục tiêu kiểm thử (Module → Features → Key functionalities)
2. Xây dựng các điểm quan sát kiểm thử (UI, hành vi, validation, business rule, integration, error, edge case)
3. Áp dụng kỹ thuật thiết kế (BVA, Equivalence Partitioning, Decision Table, State Transition, Pairwise, Use Case, Error Guessing)
4. Tập trung vào high-risk areas (logic nghiệp vụ quan trọng, data integrity, integration, validation phức tạp)
5. Cấu trúc TVP: **TUÂN THỦ CHÍNH XÁC** định nghĩa cột, header file, quy tắc Section lớn / Sub-section
   được mô tả trong `### Reference: tvp-structure.md` ở phần "Reference files" bên dưới.
   Cụ thể bảng TVP DÙNG 7 CỘT theo thứ tự: `ID TVP | Sub-section | Feature | TVP Description | Test Type | Priority | Method test`.
   KHÔNG dùng bất kỳ tập cột khác (5 cột, 6 cột, v.v. — đều SAI). Mỗi Section lớn mở đầu bằng 1 dòng
   markdown 1-cell duy nhất `| **SECTION N — TÊN** |`, không đánh ID cho dòng header này.
   File mở đầu bằng "header file" (bảng `Mục | Nội dung`) như đặc tả; kết file có bảng "Lịch sử tạo file".
6. Checklist 18 mục — đánh giá độ phủ (xem `### Reference: tvp-checklist.md`)

Output: CHỈ trả về JSON object DUY NHẤT, KHÔNG có text nào khác. Schema:
{
  "content_md": "<markdown bảng TVP đầy đủ — STRUCTURE phải khớp 100% với tvp-structure.md (7 cột, có header file, Section lớn 1-cell header, đánh số TVP-001 tăng dần xuyên suốt). Test Type ∈ {UI, Functional, Validation, Data, Integration, Edge Case, User Behavior}. Priority ∈ {Critical, High, Medium, Low}. Method test ∈ {E2E, Manual, API, E2E / Manual}>",
  "checklist_18": [
    {"key": "FUNCTIONAL_HAPPY_PATH",   "label": "FUNCTIONAL (Happy Path)",      "status": "covered", "note": ""},
    {"key": "INPUT_VALIDATION",        "label": "INPUT VALIDATION (Field Level)","status": "not_covered", "note": "..."},
    {"key": "BOUNDARY_VALUE",          "label": "BOUNDARY VALUE (BVA)",          "status": "covered", "note": ""},
    {"key": "NEGATIVE_CASE",           "label": "NEGATIVE CASE",                 "status": "covered", "note": ""},
    {"key": "USER_BEHAVIOR",           "label": "USER BEHAVIOR (Real-world)",    "status": "covered", "note": ""},
    {"key": "SYSTEM_BEHAVIOR",         "label": "SYSTEM BEHAVIOR",               "status": "covered", "note": ""},
    {"key": "DATA_INTEGRITY",          "label": "DATA INTEGRITY",                "status": "covered", "note": ""},
    {"key": "DB_UI_DATA_MAPPING",      "label": "DB ↔ UI DATA MAPPING",          "status": "covered", "note": ""},
    {"key": "INTEGRATION_API",         "label": "INTEGRATION (API)",             "status": "n_a",     "note": "spec không mô tả API"},
    {"key": "SECURITY_BASIC",          "label": "SECURITY (Basic)",              "status": "covered", "note": "SQL/XSS/auth"},
    {"key": "UX_UI",                   "label": "UX/UI Static text",             "status": "covered", "note": ""},
    {"key": "STATE_FLOW",              "label": "STATE & FLOW",                  "status": "covered", "note": ""},
    {"key": "CONCURRENCY",             "label": "CONCURRENCY (Advanced)",        "status": "n_a",     "note": ""},
    {"key": "DATA_LIFECYCLE",          "label": "DATA LIFECYCLE",                "status": "n_a",     "note": "không có xoá/khôi phục"},
    {"key": "SEARCH_FILTER_SORT",      "label": "SEARCH / FILTER / SORT",        "status": "covered", "note": ""},
    {"key": "PAGINATION_LARGE_DATA",   "label": "PAGINATION / LARGE DATA",       "status": "covered", "note": ""},
    {"key": "CROSS_FIELD_VALIDATION",  "label": "CROSS-FIELD VALIDATION",        "status": "covered", "note": ""},
    {"key": "IMPORT_EXPORT",           "label": "IMPORT / EXPORT",               "status": "n_a",     "note": ""}
  ]
}

Quy tắc cho checklist_18:
- ĐỦ 18 mục, không thiếu, đúng thứ tự key như trên.
- status = "covered" | "not_covered" | "n_a". Nếu "n_a" hoặc "not_covered" PHẢI có note giải thích lý do.
- Mục 15 SEARCH/FILTER/SORT chỉ "n_a" nếu màn hình không có search/filter.
- Mục 18 IMPORT/EXPORT chỉ "n_a" nếu màn hình không có chức năng xuất/nhập file.

[TÀI LIỆU]
{context}
"""


DEFAULT_TC_FROM_TVP_PROMPT = """\
Bạn là QC Engineer viết manual test cases dựa trên Test Viewpoints (TVP) đã approved + tài liệu spec.

Mục tiêu: chuyển các viewpoint trong TVP thành các test case cụ thể, executable, ready-to-run.

Quy tắc bắt buộc:
- Mỗi TVP item → ít nhất 1 test case. Nếu một TVP item bao quát nhiều luồng / nhiều element (button, role, field) → tách thành test case riêng cho từng luồng/element (decomposition).
- Bắt buộc gán technique cho mỗi TC từ tập: "BVA" | "EP" | "DT" | "ST" | "Negative" | "UC" | "EG"
  - BVA: Boundary Value Analysis (test min, max, just_above_max, just_below_min)
  - EP:  Equivalence Partitioning (chia class giá trị)
  - DT:  Decision Table (kết hợp nhiều condition → action)
  - ST:  State Transition (test transition giữa state)
  - Negative: invalid input, error path, unauthorized
  - UC:  Use Case end-to-end happy path
  - EG:  Error Guessing (corner cases dựa trên kinh nghiệm)
- Title viết tiếng Việt, ngắn gọn (≤ 80 ký tự). Giữ NGUYÊN UI labels tiếng Nhật/English (không dịch tên button, message, column header).
- Steps phải executable: mỗi step là 1 hành động + dữ liệu cụ thể, không chung chung. Không viết "Test field A" — viết "Nhập 'abc' vào ô tên" hoặc "Click button [送信]".
- Expected_result: đúng kết quả mong đợi cho dữ liệu trong steps. Reference rõ message error / state thay đổi.
- Priority: dựa vào Risk Priority trong TVP — Critical / High / Medium / Low.
- Validation rules: với form input (Create/Edit/Update/Import), sinh TC RIÊNG cho TỪNG field (required, format, length, range, special chars). KHÔNG gộp.
- Static text verify: tạo TC verify đầy đủ page title, breadcrumb, column header, button label, form label + required marker (*), modal title, placeholder, filter label.

Output: CHỈ trả về JSON array, KHÔNG có text nào khác. Mỗi phần tử có schema:
{
  "title": "...",                          // tiếng Việt, ≤ 80 ký tự
  "steps": ["bước 1", "bước 2", ...],     // array of string
  "expected_result": "...",                // tiếng Việt
  "priority": "critical" | "high" | "medium" | "low",
  "tc_type": "manual" | "api" | "e2e",
  "technique": "BVA" | "EP" | "DT" | "ST" | "Negative" | "UC" | "EG",
  "source_tvp_section": "Tên section trong TVP",   // ví dụ "Validation - Search keyword"
  "source_chunk_index": 3                  // index 0-based trong [TÀI LIỆU SPEC] để link chunk; -1 nếu không xác định
}

[TEST VIEWPOINTS - INPUT CHÍNH]
{tvp_md}

[TÀI LIỆU SPEC - tham khảo bổ sung]
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


# --- Phase D1: Reference files loader -------------------------------------
# Tester có thể đặt file `.md` vào `.claude/skills/<skill>/references/` ở repo root.
# Loader đọc và concatenate vào prompt cho từng skill key.

_SKILL_REF_MAPPING: dict[str, list[str]] = {
    QA_GAP_ANALYSIS_PROMPT: ["test-Q&A"],
    TVP_GENERATE_PROMPT: ["write-test-viewpoints"],
    TC_FROM_TVP_PROMPT: ["write-manual-tests"],
}

# Thứ tự nạp ưu tiên cho từng skill. File trong list này load TRƯỚC khi đụng
# quota; các file còn lại trong references/ (không nằm trong list) load tiếp
# theo thứ tự alphabet. Đảm bảo file "core" (structure, checklist, rules)
# không bị truncate/bỏ qua khi tổng kích thước references lớn.
_SKILL_REF_PRIORITY: dict[str, list[str]] = {
    "write-test-viewpoints": [
        # Core: spec format + 18-item checklist + ambiguity handling
        "tvp-structure.md",
        "tvp-checklist.md",
        "tvp-ambiguity-rules.md",
        # Guides theo luồng (form input, search, import, export)
        "guide-validate-input.md",
        "guide-function-search.md",
        "guide-import.md",
        "guide-export.md",
    ],
    "write-manual-tests": [
        "tc-structure.md",
        "guide-gap-mockup-spec.md",
    ],
    # "test-Q&A": chưa có references — bỏ trống
}


def _resolve_skills_root() -> Path | None:
    """Return path to `.claude/skills/` if exists. Override via env QC_SKILLS_DIR."""
    override = os.getenv("QC_SKILLS_DIR")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    here = Path(__file__).resolve()
    # ascend up to repo root that contains `.claude/skills`
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".claude" / "skills"
        if candidate.is_dir():
            return candidate
    return None


def _ordered_ref_files(ref_dir: Path, skill: str) -> list[Path]:
    """Return *.md paths in priority order: declared priority first, then the
    rest sorted alphabetically. Files in priority list nhưng không tồn tại sẽ
    bị bỏ qua silently.
    """
    all_md = {p.name: p for p in ref_dir.glob("*.md")}
    priority = _SKILL_REF_PRIORITY.get(skill, [])
    ordered: list[Path] = []
    used_names: set[str] = set()
    for name in priority:
        p = all_md.get(name)
        if p is not None and name not in used_names:
            ordered.append(p)
            used_names.add(name)
    for name in sorted(all_md.keys()):
        if name in used_names:
            continue
        ordered.append(all_md[name])
        used_names.add(name)
    return ordered


def load_reference_files_for_prompt(prompt_key: str, max_chars: int = 80000) -> str:
    """Read all `.md` files under `.claude/skills/<skill>/references/` for the given key.

    Files được nạp theo priority đã khai báo trong `_SKILL_REF_PRIORITY`
    (core rules trước, guides sau), file còn lại sort alphabet. Khi sắp chạm
    quota `max_chars`, file đang load có thể bị truncate; các file phía sau
    bị bỏ qua. Default 80 000 chars (~25K tokens) — đủ rộng cho toàn bộ
    reference hiện tại của 3 skill và còn dư cho file mới.
    """
    skills = _SKILL_REF_MAPPING.get(prompt_key) or []
    if not skills:
        return ""
    root = _resolve_skills_root()
    if root is None:
        return ""
    parts: list[str] = []
    used = 0
    truncated = False
    for skill in skills:
        ref_dir = root / skill / "references"
        if not ref_dir.is_dir():
            continue
        for md_path in _ordered_ref_files(ref_dir, skill):
            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue
            head = f"### Reference: {md_path.name}\n"
            block = head + content.strip()
            remaining = max_chars - used
            if remaining <= 0:
                truncated = True
                break
            if len(block) > remaining:
                block = block[:remaining] + "\n... (truncated)"
                truncated = True
            parts.append(block)
            used += len(block)
        if truncated:
            break
    if not parts:
        return ""
    return "\n\n=== Reference files ===\n\n" + "\n\n".join(parts) + "\n=== End reference files ===\n"


def inject_references(template: str, prompt_key: str) -> str:
    """If template has `{references}` placeholder, replace; else append at end if refs exist."""
    refs = load_reference_files_for_prompt(prompt_key)
    if "{references}" in template:
        return template.replace("{references}", refs)
    if refs:
        return template.rstrip() + "\n\n" + refs
    return template
