# S9 Q&A Chat — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Q&A Chat với tài liệu dự án  
**Màn hình:** S9 Q&A Chat  
**Version:** 1.0  
**Ngày:** 2025-06-10  
**Tác giả:** [tên]  
**Trạng thái:** draft

---

## Changelog

| Version | Ngày | Người tạo | Nội dung |
|---|---|---|---|
| 1.0 | 2025-06-10 | [tên] | Bản khởi tạo |

---

## 1. Basic Design

### 1.1 Mô tả màn hình

Giao diện hỏi đáp AI cho phép nhân sự dự án đặt câu hỏi bằng ngôn ngữ tự nhiên, hệ thống tìm kiếm các đoạn tài liệu liên quan qua vector search (RAG) và dùng Claude API để tổng hợp câu trả lời có trích dẫn nguồn cụ thể. Đây là **giá trị cốt lõi** của hệ thống QC Master.

**Điểm xuất phát vào S9:**
- Sidebar global → "Q&A Chat" (scope = toàn project)
- S3 toolbar → "Hỏi AI về project" (scope = project)
- S3 row → "Hỏi AI" (scope = màn hình cụ thể)
- S6 toolbar → "Hỏi AI" (scope = màn hình + doc_type)
- S6 bôi text → "Hỏi AI về đoạn này" (scope = câu hỏi pre-fill)

**Vai trò truy cập:** Tất cả member (Admin, PM, QC, Dev)  
**Màn hình trước:** S2, S3, S6 (nhiều entry point)  
**Màn hình sau:** S6 Document viewer (click citation badge)

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER (sticky)                                                      │
│ [Logo]  Q&A Chat — Project Demo          [Avatar ▾]                 │
├─────────────────────┬────────────────────────────────────────────────┤
│ SIDEBAR TRÁI (260px)│ CHAT AREA (flex 1)                             │
│                     │                                                │
│ SCOPE               │  ┌──────────────────────────────────────────┐ │
│ ○ Toàn project      │  │ [Hôm nay]                                │ │
│ ● Màn hình cụ thể   │  │                                          │ │
│   [Login        ▾]  │  │         Xin chào! Tôi có thể giúp gì    │ │
│ ○ Loại tài liệu     │  │         cho bạn về project này?          │ │
│   [ ] Basic Design  │  │                                          │ │
│   [✓] API Design    │  │  ┌────────────────────────────────────┐  │ │
│   [ ] Detail Design │  │  │ Button lỗi nên có màu gì?          │  │ │
│                     │  │  └────────────────────────────────────┘  │ │
│ ─────────────────   │  │                                          │ │
│ LỊCH SỬ             │  │  Theo Basic Design màn hình Login...    │ │
│ + Chat mới          │  │  [Basic Design · Login · §Button]       │ │
│                     │  │                                          │ │
│ Hôm nay             │  │  Nguồn tham khảo: 2 đoạn từ 1 tài liệu │ │
│ ● Button lỗi màu gì │  │  [Hỏi tiếp] [Tạo TC] [Copy]           │ │
│                     │  └──────────────────────────────────────────┘ │
│ Hôm qua             │                                                │
│   Login flow API    │  ┌──────────────────────────────────────────┐ │
│   Validation rules  │  │ [Gợi ý câu hỏi...]                      │ │
│                     │  │ [Nhập câu hỏi...                      ↑] │ │
│                     │  └──────────────────────────────────────────┘ │
└─────────────────────┴────────────────────────────────────────────────┘
```

- **Sidebar:** Fixed left 260px, scroll lịch sử riêng
- **Chat area:** Flex 1, scroll messages
- **Input bar:** Sticky bottom trong chat area

---

### 1.3 Sidebar trái chi tiết

#### Scope selector

```
PHẠM VI TÌM KIẾM
┌─────────────────────────────────────────┐
│ ○ Toàn project                          │
│                                         │
│ ● Màn hình cụ thể                       │
│   ┌──────────────────────────────────┐  │
│   │ Login                          ▾│  │
│   └──────────────────────────────────┘  │
│                                         │
│ ○ Loại tài liệu                         │
│   [ ] Basic Design                      │
│   [✓] API Design                        │
│   [ ] Detail Design                     │
│   [ ] Testcase Manual                   │
│   [ ] Figma                             │
└─────────────────────────────────────────┘
```

| Scope option | Mô tả | Dùng khi |
|---|---|---|
| Toàn project | Tìm trong tất cả chunk của project | Câu hỏi tổng quát |
| Màn hình cụ thể | Chỉ tìm chunk có `metadata.screen = X` | Hỏi về 1 màn hình |
| Loại tài liệu | Chỉ tìm chunk có `doc_type IN [...]` | Hỏi về API hoặc testcase |

Scope được **lưu vào session** — không reset khi gửi câu hỏi mới trong cùng chat.

#### Lịch sử chat

```
+ Chat mới
─────────────
Hôm nay
● Button lỗi màu gì?       [···]
  Login flow step by step  [···]

Hôm qua
  Validation rules login   [···]
  API endpoint auth        [···]

Tuần trước
  TC cho màn dashboard     [···]
```

| Element | Mô tả |
|---|---|
| "+ Chat mới" | Tạo conversation mới, clear chat area |
| Conversation item | Title = câu hỏi đầu tiên (truncate 40 ký tự) |
| Dot xanh | Conversation đang active |
| Menu "···" | Đổi tên, Xoá conversation |
| Group by date | Hôm nay / Hôm qua / Tuần trước / Tháng trước |

---

### 1.4 Chat area

#### Welcome state (conversation mới)

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│              [Icon AI]                               │
│                                                      │
│    Xin chào! Tôi có thể giúp bạn tìm hiểu          │
│    tài liệu dự án và trả lời câu hỏi.               │
│                                                      │
│    Gợi ý câu hỏi:                                   │
│    ┌──────────────────────────────────────────────┐  │
│    │ Button lỗi nên hiển thị màu gì?              │  │
│    └──────────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────────┐  │
│    │ API login trả về những field nào?            │  │
│    └──────────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────────┐  │
│    │ Màn hình Login có những testcase nào?        │  │
│    └──────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

Suggested questions được generate dựa trên scope hiện tại — nếu scope = "Login", gợi ý sẽ liên quan đến màn Login.

#### Message bubble — User

```
                        ┌──────────────────────────────┐
                        │ Button lỗi nên có màu gì?    │
                        │                    10:32 AM   │
                        └──────────────────────────────┘
```

#### Message bubble — AI (đang trả lời)

```
┌──────────────────────────────────────────────────────────┐
│ [AI icon]                                                │
│ ···  (typing indicator: 3 chấm nhấp nháy)               │
└──────────────────────────────────────────────────────────┘
```

#### Message bubble — AI (hoàn thành)

```
┌──────────────────────────────────────────────────────────┐
│ [AI icon]                                                │
│                                                          │
│ Theo tài liệu Basic Design màn hình Login, button        │
│ cần hiển thị màu ĐỎ (#FF0000) khi người dùng nhập      │
│ sai thông tin.                                           │
│                                                          │
│ [Basic Design · Login · §Button states]                  │  ← citation badge
│                                                          │
│ Cụ thể, button LOGIN sẽ đổi sang màu đỏ và hiện         │
│ message lỗi ngay bên dưới field tương ứng.              │
│                                                          │
│ [Basic Design · Login · §Error messages]                 │  ← citation badge
│                                                          │
│ ─────────────────────────────────────────────────────   │
│ Nguồn tham khảo: 2 đoạn từ Basic Design (Login)         │
│ [▾ Xem chi tiết nguồn]                                   │
│                                                          │
│ [Hỏi tiếp]  [Tạo TC từ câu trả lời]  [📋 Copy]         │
│                                          10:32 AM        │
└──────────────────────────────────────────────────────────┘
```

---

### 1.5 Citation badge

```
[Basic Design · Login · §Button states]
```

| Element | Mô tả |
|---|---|
| Màu | Background tím nhạt, text tím, border tím |
| Click | Mở S6 Document viewer tại đúng chunk đó |
| Hover | Hiện tooltip preview 80 ký tự nội dung chunk |
| Format | `[doc_type · screen_name · §section_name]` |

Nếu không tìm thấy chunk phù hợp:

```
┌──────────────────────────────────────────────────────────┐
│ [AI icon]                                                │
│                                                          │
│ Tôi không tìm thấy thông tin liên quan trong tài         │
│ liệu của project này.                                    │
│                                                          │
│ Bạn có thể thử:                                          │
│ • Mở rộng phạm vi tìm kiếm sang "Toàn project"          │
│ • Kiểm tra lại tài liệu đã được upload và approve chưa   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

### 1.6 Sources panel (expand)

Khi user click "▾ Xem chi tiết nguồn":

```
┌──────────────────────────────────────────────────────────┐
│ Nguồn tham khảo (2 đoạn)                              ▲  │
├──────────────────────────────────────────────────────────┤
│ 1. Basic Design · Login · §Button states                 │
│    Score: 0.94                                           │
│    "Button LOGIN cần có màu ĐỎ khi người dùng..."       │
│    [Xem trong tài liệu →]                                │
├──────────────────────────────────────────────────────────┤
│ 2. Basic Design · Login · §Error messages                │
│    Score: 0.87                                           │
│    "Hiện message lỗi tương ứng ngay dưới field..."      │
│    [Xem trong tài liệu →]                                │
└──────────────────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Score | Cosine similarity score (0.0–1.0) — không hiện với user thường, chỉ Admin |
| Preview | 80 ký tự đầu của chunk |
| Link | Mở S6 tại chunk đó |

---

### 1.7 Input bar

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  [Gợi ý: "API endpoint nào dùng để..."]                 │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Nhập câu hỏi về tài liệu dự án...              [↑] │  │
│  └────────────────────────────────────────────────────┘  │
│  Phạm vi: Màn hình Login · API Design               [X] │
└──────────────────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Textarea | Auto-expand, max 5 dòng, Enter = gửi, Shift+Enter = xuống dòng |
| Nút gửi ↑ | Disabled khi input rỗng hoặc AI đang trả lời |
| Scope indicator | Hiện scope hiện tại, click X để clear scope |
| Suggested question | Gợi ý ngẫu nhiên từ context, click để điền vào input |

---

### 1.8 Trạng thái loading & error

| Tình huống | Hiển thị |
|---|---|
| AI đang xử lý | Typing indicator 3 chấm nhấp nháy trong bubble AI |
| AI đang stream | Text xuất hiện từng từ (streaming) |
| Lỗi API | Bubble đỏ nhạt: "Đã có lỗi. Thử lại?" + nút Thử lại |
| Lỗi rate limit | "Bạn đã gửi quá nhiều câu hỏi. Thử lại sau {X} giây." |
| Không có tài liệu approved | Banner vàng: "Project chưa có tài liệu nào được duyệt. Q&A sẽ không có dữ liệu để tìm kiếm." |

---

## 2. Detail Design

### 2.1 RAG Pipeline — logic đầy đủ

```
User gửi câu hỏi
    │
    ├─ POST /api/v1/chat/conversations/{id}/messages
    │
    └─ Backend xử lý:
            │
            ├─ STEP 1: Embed câu hỏi
            │   Voyage AI embed(query_text) → query_vector [1536 dims]
            │
            ├─ STEP 2: Vector search (pgvector)
            │   SELECT chunks.* FROM chunk_embeddings
            │   JOIN chunks ON chunk_embeddings.chunk_id = chunks.id
            │   JOIN doc_versions ON chunks.doc_version_id = doc_versions.id
            │   JOIN documents ON doc_versions.document_id = documents.id
            │   WHERE documents.project_id = {project_id}
            │     AND doc_versions.status = 'approved'         -- chỉ approved
            │     AND [scope filters]                          -- screen/doc_type
            │   ORDER BY chunk_embeddings.embedding
            │             <=> query_vector                     -- cosine distance
            │   LIMIT 20                                       -- lấy top 20
            │
            ├─ STEP 3: Reranking (optional v1)
            │   Sort top 20 theo: similarity_score * 0.7
            │                   + recency_score * 0.2
            │                   + tc_count_score * 0.1
            │   Giữ top 8 chunks
            │
            ├─ STEP 4: Build context cho Claude
            │   System prompt + chunk context + conversation history
            │
            ├─ STEP 5: Gọi Claude API (streaming)
            │   claude-sonnet-4-20250514
            │   max_tokens: 1000
            │   stream: true
            │
            ├─ STEP 6: Parse citations từ response
            │   Claude trả về chunk_id references trong response
            │   Map chunk_id → citation badge data
            │
            └─ STEP 7: Lưu DB + stream về FE
                    - message record (user + assistant)
                    - cited_chunks records
                    - Stream SSE về FE
```

---

### 2.2 System prompt cho Claude

```
Bạn là trợ lý Q&A cho hệ thống quản lý tài liệu dự án phần mềm QC Master.
Nhiệm vụ của bạn là trả lời câu hỏi của nhân sự dự án DỰA TRÊN các đoạn
tài liệu được cung cấp.

QUY TẮC BẮT BUỘC:
1. Chỉ trả lời dựa trên thông tin trong [CONTEXT] bên dưới.
2. Nếu thông tin không có trong context, nói rõ: "Tôi không tìm thấy
   thông tin này trong tài liệu dự án."
3. Với mỗi thông tin quan trọng, cite nguồn bằng format:
   [[CHUNK_ID:{chunk_id}]] ngay sau câu đó.
4. Trả lời bằng tiếng Việt, rõ ràng, ngắn gọn.
5. KHÔNG tự sáng tạo thông tin ngoài context.

[CONTEXT]
{chunks_content}

[LỊCH SỬ HỘI THOẠI]
{conversation_history}

[CÂU HỎI]
{user_question}
```

---

### 2.3 Context building chi tiết

```python
def build_context(chunks: list[Chunk]) -> str:
    context_parts = []
    for chunk in chunks:
        meta = chunk.metadata
        header = (
            f"[Nguồn: {meta.get('doc_type','').replace('_',' ').title()} · "
            f"Màn hình: {meta.get('screen', '')} · "
            f"Section: {meta.get('section', '')}]\n"
            f"[CHUNK_ID: {chunk.id}]\n"
        )
        context_parts.append(header + chunk.content_text)

    return "\n\n---\n\n".join(context_parts)

# Ví dụ output:
# [Nguồn: Basic Design · Màn hình: Login · Section: Button states]
# [CHUNK_ID: chunk-uuid-002]
# Button LOGIN cần có màu ĐỎ khi người dùng nhập sai thông tin...
#
# ---
#
# [Nguồn: API Design · Màn hình: Login · Section: POST /login]
# [CHUNK_ID: chunk-uuid-015]
# POST /api/v1/auth/login
# Request: { email: string, password: string }
# Response 200: { access_token, refresh_token, user }
```

---

### 2.4 Parse citations từ Claude response

```python
import re

def parse_citations(response_text: str, chunk_map: dict) -> tuple[str, list]:
    """
    Input:  "Button cần màu đỏ [[CHUNK_ID:chunk-uuid-002]] khi lỗi."
    Output: ("Button cần màu đỏ [Basic Design · Login · §Button states] khi lỗi.",
             [{"chunk_id": "chunk-uuid-002", "position": 32}])
    """
    citations = []
    pattern = r'\[\[CHUNK_ID:([^\]]+)\]\]'

    def replace_citation(match):
        chunk_id = match.group(1)
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            return ''
        meta = chunk.metadata
        badge_text = (
            f"[{meta.get('doc_type','').replace('_',' ').title()} · "
            f"{meta.get('screen','')} · "
            f"§{meta.get('section','')}]"
        )
        citations.append({
            "chunk_id": chunk_id,
            "badge_text": badge_text,
            "doc_type": meta.get('doc_type'),
            "screen": meta.get('screen'),
            "section": meta.get('section'),
        })
        return f"CITATION_{len(citations)-1}"  # placeholder

    processed = re.sub(pattern, replace_citation, response_text)
    return processed, citations
```

---

### 2.5 Conversation history management

```python
# Giữ tối đa 10 turns (20 messages) để tránh context window quá lớn
MAX_HISTORY_TURNS = 10

def build_conversation_history(messages: list[Message]) -> list[dict]:
    # Lấy N message gần nhất
    recent = messages[-(MAX_HISTORY_TURNS * 2):]
    return [
        {
            "role": "user" if m.role == "user" else "assistant",
            "content": m.content_text  # không include citations trong history
        }
        for m in recent
    ]
```

---

### 2.6 Streaming response về FE

Backend dùng **Server-Sent Events (SSE)** để stream từng token từ Claude về FE:

```python
# app/routers/chat.py
from fastapi.responses import StreamingResponse
import anthropic, json

async def stream_chat_response(question, chunks, history):
    client = anthropic.AsyncAnthropic()
    context = build_context(chunks)
    prompt = build_prompt(context, history, question)

    async def event_generator():
        full_response = ""
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=prompt,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"

        # Sau khi stream xong, parse citations và gửi metadata
        processed, citations = parse_citations(full_response, chunk_map)
        yield f"data: {json.dumps({'type': 'done', 'citations': citations})}\n\n"

        # Lưu message vào DB
        await save_message(question, processed, citations)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**FE nhận SSE:**

```typescript
const eventSource = new EventSource(`/api/v1/chat/stream?...`)

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data)
  if (data.type === 'delta') {
    appendToCurrentBubble(data.text)
  } else if (data.type === 'done') {
    replaceCitationPlaceholders(data.citations)
    eventSource.close()
  }
}
```

---

### 2.7 Scope filter → SQL WHERE clause

```python
def build_scope_filter(scope: ChatScope) -> list:
    filters = [
        Document.project_id == scope.project_id,
        DocVersion.status == 'approved',
    ]
    if scope.screen_name:
        filters.append(
            Chunk.metadata['screen'].astext == scope.screen_name
        )
    if scope.doc_types:
        filters.append(
            Chunk.metadata['doc_type'].astext.in_(scope.doc_types)
        )
    return filters
```

---

### 2.8 Suggested questions generation

Suggested questions được generate 1 lần khi tạo conversation mới, dựa trên scope:

```python
async def generate_suggested_questions(
    project_id: str,
    scope: ChatScope
) -> list[str]:
    # Lấy random 5 chunks từ scope
    sample_chunks = await get_random_chunks(project_id, scope, limit=5)
    context = build_context(sample_chunks)

    response = await claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""Dựa trên tài liệu sau, tạo 3 câu hỏi ngắn
            (tối đa 10 từ/câu) mà nhân sự dự án thường muốn hỏi.
            Trả về JSON array: ["câu 1", "câu 2", "câu 3"]

            Tài liệu:
            {context}"""
        }]
    )

    import json
    return json.loads(response.content[0].text)
```

---

### 2.9 Validation Rules

#### VL-S9-001 — Câu hỏi không rỗng
- **Field:** Input textarea
- **Trigger:** onSubmit
- **Rule:** Không rỗng, không chỉ khoảng trắng, tối thiểu 3 ký tự
- **Error message:** Nút gửi disabled — không hiện message lỗi
- **Scope:** Client

#### VL-S9-002 — Câu hỏi max length
- **Field:** Input textarea
- **Trigger:** onChange
- **Rule:** Tối đa 2000 ký tự
- **Error message:** Counter đỏ "2050/2000", nút gửi disabled
- **Scope:** Client + Server

#### VL-S9-003 — Rate limit
- **Trigger:** Mỗi request gửi câu hỏi
- **Rule:** 30 câu hỏi / phút / user
- **Error message:** "Bạn đã gửi quá nhiều câu hỏi. Thử lại sau {X} giây."
- **Scope:** Server only

#### VL-S9-004 — Scope hợp lệ
- **Field:** Scope selector
- **Trigger:** onSubmit
- **Rule:** `screen_name` phải là màn hình tồn tại trong project (nếu có); `doc_types` phải thuộc enum hợp lệ
- **Error message:** "Phạm vi tìm kiếm không hợp lệ" — reset về "Toàn project"
- **Scope:** Server only

#### VL-S9-005 — Project có tài liệu approved
- **Trigger:** Load conversation / gửi câu hỏi
- **Rule:** Project phải có ít nhất 1 chunk được embed (từ version approved)
- **Error message:** Banner vàng "Chưa có tài liệu nào được duyệt trong project này."
- **Scope:** Server — trả 200 với warning flag, không trả lỗi

---

### 2.10 Phân quyền

| Action | Owner | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Gửi câu hỏi | ✓ | ✓ | ✓ | ✓ |
| Xem lịch sử chat của mình | ✓ | ✓ | ✓ | ✓ |
| Xem lịch sử chat của người khác | ✓ | — | — | — |
| Xoá conversation | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) |
| Tạo TC từ câu trả lời | ✓ | ✓ | ✓ | — |
| Click citation → S6 | ✓ | ✓ | ✓ | ✓ |

Mỗi user chỉ thấy conversation của chính mình. Admin thấy tất cả.

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/chat/conversations` | Danh sách conversation | Bearer (member) |
| POST | `/api/v1/projects/{project_id}/chat/conversations` | Tạo conversation mới | Bearer (member) |
| GET | `/api/v1/chat/conversations/{conversation_id}/messages` | Lịch sử messages | Bearer (member/owner) |
| POST | `/api/v1/chat/conversations/{conversation_id}/messages` | Gửi câu hỏi (có stream) | Bearer (member) |
| DELETE | `/api/v1/chat/conversations/{conversation_id}` | Xoá conversation | Bearer (own/admin) |
| GET | `/api/v1/chat/conversations/{conversation_id}/suggested-questions` | Câu hỏi gợi ý | Bearer (member) |

---

### 3.2 GET /api/v1/projects/{project_id}/chat/conversations

**Mô tả:** Danh sách conversation của user trong project, group by date. Admin có thể xem của tất cả user qua query param `user_id`.

**Auth:** Bearer (member)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Mô tả | Mặc định |
|---|---|---|---|
| `page` | int | Trang | `1` |
| `per_page` | int | Số item / trang | `20` |
| `user_id` | UUID | Filter theo user (Admin only) | current user |

#### Response 200

```json
{
  "conversations": [
    {
      "id": "conv-uuid-001",
      "title": "Button lỗi nên có màu gì?",
      "scope": {
        "type": "screen",
        "screen_name": "Login",
        "doc_types": null
      },
      "message_count": 6,
      "last_message_at": "2025-06-10T10:35:00Z",
      "created_at": "2025-06-10T10:30:00Z",
      "created_by": {
        "id": "uuid-qc",
        "full_name": "Tran QC"
      }
    }
  ],
  "pagination": {
    "total": 15,
    "page": 1,
    "per_page": 20,
    "total_pages": 1
  }
}
```

---

### 3.3 POST /api/v1/projects/{project_id}/chat/conversations

**Mô tả:** Tạo conversation mới với scope. Generate suggested questions async.

**Auth:** Bearer (member)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `scope_type` | string | Có | `project` \| `screen` \| `doc_type` |
| `screen_name` | string | Không | Tên màn hình (khi scope_type=screen) |
| `doc_types` | array | Không | List doc_type (khi scope_type=doc_type) |

```json
{
  "scope_type": "screen",
  "screen_name": "Login",
  "doc_types": null
}
```

#### Response 201

```json
{
  "id": "conv-uuid-002",
  "title": null,
  "scope": {
    "type": "screen",
    "screen_name": "Login",
    "doc_types": null
  },
  "suggested_questions": [
    "Button lỗi nên hiển thị màu gì?",
    "Validation email dùng regex nào?",
    "API login trả về những field nào?"
  ],
  "has_approved_documents": true,
  "message_count": 0,
  "created_at": "2025-06-10T11:00:00Z"
}
```

**Ghi chú `has_approved_documents`:** `false` nếu scope không có chunk nào đã embed — FE hiện warning banner.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field | scope_type không có |
| 403 | Không có quyền | Không phải member |
| 404 | Project không tồn tại | — |
| 422 | scope_type không hợp lệ | Không phải project/screen/doc_type |

---

### 3.4 POST /api/v1/chat/conversations/{conversation_id}/messages

**Mô tả:** Gửi câu hỏi và nhận câu trả lời. Hỗ trợ 2 mode: **streaming** (SSE) và **non-streaming** (JSON thường). FE nên dùng streaming cho UX tốt hơn.

**Auth:** Bearer (member, phải là owner của conversation hoặc admin)  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `content` | string | Có | Câu hỏi, 3–2000 ký tự |
| `stream` | boolean | Không | `true` = SSE stream | `false` |

```json
{
  "content": "Button lỗi nên có màu gì?",
  "stream": true
}
```

#### Response — Non-streaming (stream=false)

**Status 200:**

```json
{
  "user_message": {
    "id": "msg-uuid-001",
    "role": "user",
    "content": "Button lỗi nên có màu gì?",
    "created_at": "2025-06-10T10:32:00Z"
  },
  "assistant_message": {
    "id": "msg-uuid-002",
    "role": "assistant",
    "content": "Theo tài liệu Basic Design màn hình Login, button cần hiển thị màu ĐỎ (#FF0000) khi người dùng nhập sai thông tin. CITATION_0\n\nCụ thể, button LOGIN sẽ đổi sang màu đỏ và hiện message lỗi ngay bên dưới field tương ứng. CITATION_1",
    "citations": [
      {
        "index": 0,
        "chunk_id": "chunk-uuid-002",
        "badge_text": "[Basic Design · Login · §Button states]",
        "doc_type": "basic_design",
        "screen": "Login",
        "section": "Button states",
        "document_id": "doc-uuid-001",
        "version_id": "ver-uuid-003",
        "preview": "Button LOGIN cần có màu ĐỎ khi người dùng nhập sai..."
      },
      {
        "index": 1,
        "chunk_id": "chunk-uuid-003",
        "badge_text": "[Basic Design · Login · §Error messages]",
        "doc_type": "basic_design",
        "screen": "Login",
        "section": "Error messages",
        "document_id": "doc-uuid-001",
        "version_id": "ver-uuid-003",
        "preview": "Hiện message lỗi tương ứng ngay dưới field..."
      }
    ],
    "sources_count": 2,
    "chunks_searched": 8,
    "created_at": "2025-06-10T10:32:05Z"
  },
  "conversation_title": "Button lỗi nên có màu gì?"
}
```

**Ghi chú `conversation_title`:** Lần đầu gửi message → server tự set title = câu hỏi đầu tiên (truncate 50 ký tự). FE cập nhật sidebar.

#### Response — Streaming (stream=true)

**Status 200, Content-Type: text/event-stream**

```
data: {"type": "user_message", "id": "msg-uuid-001", "created_at": "2025-06-10T10:32:00Z"}

data: {"type": "delta", "text": "Theo "}

data: {"type": "delta", "text": "tài liệu "}

data: {"type": "delta", "text": "Basic Design "}

data: {"type": "delta", "text": "màn hình Login, "}

data: {"type": "citation_inline", "index": 0, "chunk_id": "chunk-uuid-002"}

data: {"type": "delta", "text": " button cần hiển thị màu ĐỎ..."}

data: {"type": "done", "message_id": "msg-uuid-002", "citations": [...], "conversation_title": "Button lỗi nên có màu gì?"}
```

**SSE event types:**

| Type | Mô tả |
|---|---|
| `user_message` | Xác nhận user message đã lưu |
| `delta` | Token tiếp theo từ Claude stream |
| `citation_inline` | Citation xuất hiện tại vị trí này trong text |
| `done` | Stream kết thúc, kèm full citations array |
| `error` | Lỗi xảy ra — kết thúc stream |

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Câu hỏi quá ngắn hoặc quá dài | < 3 hoặc > 2000 ký tự |
| 403 | Không có quyền | Không phải owner của conversation |
| 404 | Conversation không tồn tại | — |
| 429 | Quá nhiều câu hỏi | Rate limit 30/phút |
| 503 | Claude API không khả dụng | Fallback: trả non-streaming với cached response nếu có |

#### Error body

```json
{
  "error": "RATE_LIMITED",
  "message": "Bạn đã gửi quá nhiều câu hỏi. Thử lại sau 45 giây.",
  "status_code": 429,
  "retry_after": 45
}
```

---

### 3.5 GET /api/v1/chat/conversations/{conversation_id}/messages

**Mô tả:** Lấy toàn bộ message history của conversation. Dùng khi user click vào conversation cũ trong sidebar.

**Auth:** Bearer (owner của conversation hoặc Admin)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Mô tả | Mặc định |
|---|---|---|---|
| `page` | int | Trang (mới nhất trước) | `1` |
| `per_page` | int | Số message / trang | `50` |

#### Response 200

```json
{
  "conversation": {
    "id": "conv-uuid-001",
    "title": "Button lỗi nên có màu gì?",
    "scope": {
      "type": "screen",
      "screen_name": "Login",
      "doc_types": null
    },
    "created_at": "2025-06-10T10:30:00Z"
  },
  "messages": [
    {
      "id": "msg-uuid-001",
      "role": "user",
      "content": "Button lỗi nên có màu gì?",
      "citations": [],
      "created_at": "2025-06-10T10:32:00Z"
    },
    {
      "id": "msg-uuid-002",
      "role": "assistant",
      "content": "Theo tài liệu Basic Design màn hình Login...",
      "citations": [
        {
          "index": 0,
          "chunk_id": "chunk-uuid-002",
          "badge_text": "[Basic Design · Login · §Button states]",
          "doc_type": "basic_design",
          "screen": "Login",
          "section": "Button states",
          "document_id": "doc-uuid-001",
          "version_id": "ver-uuid-003",
          "preview": "Button LOGIN cần có màu ĐỎ khi..."
        }
      ],
      "created_at": "2025-06-10T10:32:05Z"
    }
  ],
  "pagination": {
    "total": 6,
    "page": 1,
    "per_page": 50,
    "total_pages": 1
  }
}
```

---

### 3.6 DELETE /api/v1/chat/conversations/{conversation_id}

**Mô tả:** Xoá conversation và tất cả messages. Chỉ owner của conversation hoặc Admin.

**Auth:** Bearer  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Có

#### Response 200

```json
{
  "message": "Đã xoá conversation",
  "conversation_id": "conv-uuid-001",
  "deleted_messages": 6
}
```

---

### 3.7 GET /api/v1/chat/conversations/{conversation_id}/suggested-questions

**Mô tả:** Lấy danh sách câu hỏi gợi ý cho conversation. Được generate async sau khi tạo conversation. Trả cache nếu đã có.

**Auth:** Bearer  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Có

#### Response 200

```json
{
  "conversation_id": "conv-uuid-001",
  "scope_label": "Màn hình Login",
  "questions": [
    "Button lỗi nên hiển thị màu gì?",
    "Validation email sử dụng regex nào?",
    "API login trả về những field nào?",
    "Rate limit login được set ở đâu?"
  ],
  "generated_at": "2025-06-10T11:00:05Z"
}
```

**Ghi chú:** Nếu questions chưa được generate (async chưa xong), trả `questions: []` và FE không hiện gợi ý.

---

## 4. Database schema bổ sung

```sql
CREATE TABLE chat_conversations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_by   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        TEXT,
  scope_type   TEXT NOT NULL CHECK (scope_type IN ('project','screen','doc_type')),
  scope_config JSONB NOT NULL DEFAULT '{}',
  -- scope_config examples:
  -- {"screen_name": "Login"}
  -- {"doc_types": ["api_design", "basic_design"]}
  -- {}  (for project scope)
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_citations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id      UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  chunk_id        UUID REFERENCES chunks(id) ON DELETE SET NULL,
  citation_index  INT NOT NULL,
  badge_text      TEXT NOT NULL,
  doc_type        TEXT,
  screen_name     TEXT,
  section_name    TEXT,
  preview_text    TEXT,
  similarity_score FLOAT
);

CREATE TABLE chat_suggested_questions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  question        TEXT NOT NULL,
  display_order   INT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_chat_conv_project  ON chat_conversations(project_id);
CREATE INDEX idx_chat_conv_user     ON chat_conversations(created_by);
CREATE INDEX idx_chat_msg_conv      ON chat_messages(conversation_id);
CREATE INDEX idx_chat_citations_msg ON chat_citations(message_id);
CREATE INDEX idx_chat_citations_chunk ON chat_citations(chunk_id);
```

---

## 5. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S9 Sidebar — load conversations | `GET /conversations` | Khi vào S9 |
| S9 Tạo conversation mới | `POST /conversations` | Nút "+ Chat mới" |
| S9 Load conversation cũ | `GET /conversations/{id}/messages` | Click conversation |
| S9 Gửi câu hỏi | `POST /conversations/{id}/messages` | Stream=true |
| S9 Câu hỏi gợi ý | `GET /conversations/{id}/suggested-questions` | Welcome state |
| S9 Xoá conversation | `DELETE /conversations/{id}` | Menu "···" |
| S9 Citation badge → S6 | URL với chunk_id params | Client-side routing |
| S3 nút "Hỏi AI về project" | `POST /conversations` scope=project | Tạo conv mới |
| S6 nút "Hỏi AI" | `POST /conversations` scope=screen | Pre-set scope |
| S6 bôi text → Hỏi AI | `POST /conversations/{id}/messages` | Pre-fill câu hỏi |

---

## 6. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S3 Document list | Entry point vào S9 (scope=project/screen) |
| Basic Design — S6 Document viewer | Citation click → S6 với chunk highlight |
| Basic Design — S10 Q&A Answer | Bubble câu trả lời — component riêng |
| Basic Design — S11 TC panel | "Tạo TC từ câu trả lời" → S11 |
| Database schema — chunks + chunk_embeddings | Data source cho RAG |
| Flow Upload & Embedding | Cần chunk được embed trước khi Q&A hoạt động |
| API Design — S6 Document viewer | `GET /chunks/{id}/testcases` dùng chung |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
