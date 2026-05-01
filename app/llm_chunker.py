"""LLM-powered semantic chunking for Markdown documents (Option B).

Primary  : Claude Haiku — tool_use để đảm bảo output JSON có cấu trúc.
Fallback : Markdown-aware rule-based chunker (heading split + bảo vệ code/table).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SemanticChunk:
    content: str                          # text đầy đủ, kể cả heading breadcrumb
    section_path: list[str] = field(default_factory=list)  # ["Screen", "Section"]
    chunk_type: str = "other"             # description|api_spec|flow|testcase|schema|table|other
    summary: str = ""                     # tóm tắt 1 dòng cho hybrid search
    chunker: str = "llm"                  # "llm" | "rule"


# ── Claude tool schema ────────────────────────────────────────────────────────

_CHUNK_TOOL: dict = {
    "name": "output_chunks",
    "description": "Output the document split into semantic chunks optimised for RAG retrieval.",
    "input_schema": {
        "type": "object",
        "properties": {
            "chunks": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["content", "section_path", "chunk_type", "summary"],
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": (
                                "Nội dung đầy đủ của chunk, bắt đầu bằng heading breadcrumb "
                                "(ví dụ: '# Login\\n## API\\n\\nnội dung...')"
                            ),
                        },
                        "section_path": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Danh sách heading cha → con, ví dụ ['Login Screen', 'API Endpoints']",
                        },
                        "chunk_type": {
                            "type": "string",
                            "enum": ["description", "api_spec", "flow", "testcase", "schema", "table", "other"],
                        },
                        "summary": {
                            "type": "string",
                            "description": "Tóm tắt 1 dòng (tiếng Việt hoặc Anh) về nội dung chunk — dùng cho keyword search",
                        },
                    },
                },
            }
        },
        "required": ["chunks"],
    },
}

# System prompt cố định → cache với prompt caching để tiết kiệm token.
_SYSTEM_PROMPT = """\
Bạn là chuyên gia phân tích tài liệu thiết kế phần mềm.
Nhiệm vụ: chia tài liệu Markdown thành các chunks tối ưu cho RAG (Retrieval-Augmented Generation).

NGUYÊN TẮC BẮT BUỘC:
1. Mỗi chunk phải TỰ ĐỦ NGHĨA — đọc độc lập mà không cần context bên ngoài.
2. KHÔNG BAO GIỜ cắt ngang code block (```...```), bảng (|...|), hoặc ASCII diagram.
3. Thêm HEADING BREADCRUMB làm prefix của mỗi chunk:
     # Tên màn hình
     ## Tên section

     {nội dung chunk}
4. Kích thước tối ưu: 200–800 từ/chunk. Ghép đoạn ngắn cùng chủ đề, tách đoạn khác chủ đề.
5. KHÔNG tách quá nhỏ: sub-heading (H3/H4) cùng một section cha nên gộp lại trừ khi > 600 từ.
6. summary: ngắn gọn, cùng ngôn ngữ với tài liệu.\
"""

# Hướng dẫn bổ sung theo loại tài liệu.
_DOC_TYPE_HINTS: dict[str, str] = {
    "api_design": (
        "QUY TẮC ĐẶC BIỆT cho API Design:\n"
        "- Mỗi API endpoint (ví dụ ### 3.2 GET /api/...) là MỘT chunk duy nhất — "
        "KHÔNG tách Query params / Request / Response / Error responses ra chunk riêng.\n"
        "- Bảng tổng quan endpoints (danh sách Method + Endpoint + Mô tả) là 1 chunk riêng.\n"
        "- JSON example, bảng params, code snippet PHẢI ở cùng chunk với mô tả endpoint của nó."
    ),
    "basic_design": (
        "QUY TẮC ĐẶC BIỆT cho Basic Design:\n"
        "- Mỗi section H2 là 1 chunk; chỉ tách thêm khi section > 600 từ.\n"
        "- ASCII layout diagram giữ nguyên cùng chunk với bảng mô tả phía dưới nó.\n"
        "- Bảng trạng thái / phân quyền gộp vào section chứa nó, không tách riêng."
    ),
    "detail_design": (
        "QUY TẮC ĐẶC BIỆT cho Detail Design:\n"
        "- Mỗi flow/logic block (H3) là 1 chunk; code snippet TypeScript/SQL ở cùng chunk với mô tả.\n"
        "- Pseudo-code trong code fence KHÔNG được cắt."
    ),
    "testcase_manual": (
        "QUY TẮC ĐẶC BIỆT cho Testcase Manual:\n"
        "- Nhóm testcase theo feature/module (H2); mỗi testcase ngắn (< 100 từ) gộp cùng nhóm.\n"
        "- Testcase dài (có nhiều steps) có thể là 1 chunk riêng."
    ),
}


# ── LLM chunker (primary) ─────────────────────────────────────────────────────

# Tài liệu lớn hơn ngưỡng này sẽ được chia batch theo H1/H2 trước.
# ~8 000 ký tự ≈ 2 000 tokens input → output ≤ 6 000 tokens → an toàn với max_tokens=8192.
_BATCH_CHAR_LIMIT = 8_000

_H1_H2_RE = re.compile(r"^(#{1,2})\s+.+$", re.MULTILINE)


def _split_into_batches(text: str, limit: int = _BATCH_CHAR_LIMIT) -> list[str]:
    """Chia văn bản thành các batch ≤ limit ký tự, cắt tại ranh giới H1/H2."""
    if len(text) <= limit:
        return [text]

    # Tìm tất cả vị trí bắt đầu của H1/H2
    cut_points = [m.start() for m in _H1_H2_RE.finditer(text)]
    if not cut_points:
        # Không có H1/H2 → chia đều theo paragraph
        batches, buf = [], ""
        for para in text.split("\n\n"):
            candidate = f"{buf}\n\n{para}".strip() if buf else para
            if len(candidate) > limit and buf:
                batches.append(buf)
                buf = para
            else:
                buf = candidate
        if buf:
            batches.append(buf)
        return batches or [text]

    batches: list[str] = []
    batch_start = 0

    for cp in cut_points[1:]:  # bỏ qua cut_point đầu (= 0)
        segment = text[batch_start:cp]
        if len(segment) >= limit:
            batches.append(segment)
            batch_start = cp

    # Phần còn lại
    tail = text[batch_start:]
    if tail.strip():
        batches.append(tail)

    return batches if batches else [text]


async def _llm_call_single(
    client: AsyncAnthropic,
    text: str,
    *,
    doc_type: str,
) -> list[SemanticChunk]:
    """Một lần gọi LLM cho đoạn văn bản đã được cắt nhỏ."""
    hint = _DOC_TYPE_HINTS.get(doc_type, "")
    user_content = (
        f"Hãy chia tài liệu loại **{doc_type}** sau thành các chunks ngữ nghĩa.\n\n"
        + (f"{hint}\n\n" if hint else "")
        + f"---\n{text}\n---"
    )

    logger.debug(
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║  [CLAUDE PROMPT]  STEP 1 — LLM CHUNKING             ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
        "  model       : claude-haiku-4-5-20251001\n"
        "  max_tokens  : 8192\n"
        "  tool_choice : output_chunks (forced)\n"
        "  doc_type    : %s\n"
        "  doc_length  : %d chars\n"
        "\n── SYSTEM PROMPT (cached) ──────────────────────────────\n"
        "%s\n"
        "\n── USER PROMPT ─────────────────────────────────────────\n"
        "%s\n"
        "════════════════════════════════════════════════════════",
        doc_type,
        len(text),
        _SYSTEM_PROMPT,
        user_content,
    )

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_CHUNK_TOOL],
        tool_choice={"type": "tool", "name": "output_chunks"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "output_chunks":
            chunks = [
                SemanticChunk(
                    content=c["content"],
                    section_path=c.get("section_path", []),
                    chunk_type=c.get("chunk_type", "other"),
                    summary=c.get("summary", ""),
                    chunker="llm",
                )
                for c in block.input["chunks"]
                if c.get("content", "").strip()
            ]
            logger.debug(
                "[CLAUDE RESPONSE] STEP 1 — LLM CHUNKING: %d chunks returned "
                "(input_tokens=%s, output_tokens=%s)",
                len(chunks),
                getattr(response.usage, "input_tokens", "?"),
                getattr(response.usage, "output_tokens", "?"),
            )
            return chunks

    raise RuntimeError("Claude did not return output_chunks — unexpected response format")


async def llm_chunk_markdown(text: str, *, doc_type: str) -> list[SemanticChunk]:
    """Dùng Claude Haiku để chia Markdown thành semantic chunks.

    Tài liệu lớn được chia batch theo H1/H2 trước để tránh vượt max_tokens.
    Raises RuntimeError nếu API key thiếu, timeout, hoặc response sai format.
    Caller nên fallback sang rule_chunk_markdown().
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY — cannot use LLM chunker")

    client_kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url
    client = AsyncAnthropic(**client_kwargs)

    batches = _split_into_batches(text)

    if len(batches) == 1:
        return await _llm_call_single(client, text, doc_type=doc_type)

    # Xử lý từng batch tuần tự (giữ thứ tự tài liệu)
    all_chunks: list[SemanticChunk] = []
    for batch in batches:
        try:
            chunks = await _llm_call_single(client, batch, doc_type=doc_type)
            all_chunks.extend(chunks)
        except Exception:
            # Batch lỗi → dùng rule-based cho batch đó, không bỏ nội dung
            all_chunks.extend(rule_chunk_markdown(batch))

    return all_chunks


# ── Rule-based chunker (fallback) ─────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.DOTALL)
_TABLE_RE = re.compile(r"(?:^\|[^\n]+\n)+", re.MULTILINE)


def rule_chunk_markdown(text: str, *, max_chars: int = 1500) -> list[SemanticChunk]:
    """Markdown-aware rule-based chunker — fallback khi LLM không khả dụng.

    Chiến lược:
    1. Bảo vệ code block và bảng (atomic — không bị cắt).
    2. Split tại heading H1/H2/H3 → mỗi section là 1 chunk candidate.
    3. Mỗi chunk giữ heading breadcrumb làm prefix.
    4. Section quá lớn → tách thêm theo paragraph (không cắt giữa từ).
    """
    # 1. Bảo vệ các block atomic bằng placeholder
    atomics: dict[str, str] = {}

    def _protect(m: re.Match) -> str:  # type: ignore[type-arg]
        key = f"\x00ATOM{len(atomics)}\x00"
        atomics[key] = m.group(0)
        return key

    protected = _CODE_FENCE_RE.sub(_protect, text)
    protected = _TABLE_RE.sub(_protect, protected)

    # 2. Split tại heading — kết quả: [pre, level, title, body, level, title, body, ...]
    parts = _HEADING_RE.split(protected)
    segments: list[tuple[list[str], str]] = []

    if parts[0].strip():
        segments.append(([], parts[0]))

    heading_stack: list[str] = []
    i = 1
    while i + 2 < len(parts) + 1 and i + 2 <= len(parts):
        level_str, title, body = parts[i], parts[i + 1], parts[i + 2]
        level = len(level_str)
        heading_stack = heading_stack[: level - 1]
        heading_stack.append(title.strip())
        segments.append((list(heading_stack), body))
        i += 3

    # 3. Xây dựng chunks từ segments
    chunks: list[SemanticChunk] = []

    for path, body in segments:
        for key, original in atomics.items():
            body = body.replace(key, original)

        body = body.strip()
        if not body:
            continue

        prefix = "\n".join(f"{'#' * (j + 1)} {h}" for j, h in enumerate(path))
        full = (f"{prefix}\n\n{body}").strip() if prefix else body

        if len(full) <= max_chars:
            chunks.append(_make_rule_chunk(full, path))
            continue

        # Section quá lớn → tách theo paragraph, giữ prefix trên mỗi sub-chunk
        buf = ""
        for para in (p.strip() for p in body.split("\n\n") if p.strip()):
            candidate = f"{buf}\n\n{para}".strip() if buf else para
            full_candidate = (f"{prefix}\n\n{candidate}").strip() if prefix else candidate

            if len(full_candidate) > max_chars and buf:
                out = (f"{prefix}\n\n{buf}").strip() if prefix else buf
                chunks.append(_make_rule_chunk(out, path))
                buf = para
            else:
                buf = candidate

        if buf:
            out = (f"{prefix}\n\n{buf}").strip() if prefix else buf
            chunks.append(_make_rule_chunk(out, path))

    if not chunks:
        chunks.append(_make_rule_chunk(text[:max_chars], []))

    return chunks


def _make_rule_chunk(content: str, path: list[str]) -> SemanticChunk:
    return SemanticChunk(
        content=content,
        section_path=path,
        chunk_type="other",
        summary=path[-1] if path else "",
        chunker="rule",
    )
