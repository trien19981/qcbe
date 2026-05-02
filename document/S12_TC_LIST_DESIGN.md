# S12 TC List — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Danh sách Testcase  
**Màn hình:** S12 TC list  
**Version:** 1.0  
**Ngày:** 2025-06-15  
**Tác giả:** [tên]  
**Trạng thái:** draft

---

## Changelog

| Version | Ngày | Người tạo | Nội dung |
|---|---|---|---|
| 1.0 | 2025-06-15 | [tên] | Bản khởi tạo |

---

## 1. Basic Design

### 1.1 Mô tả màn hình

Màn hình quản lý toàn bộ testcase của một project. Cho phép filter đa chiều, xem trạng thái từng TC, phát hiện TC cần review sau khi tài liệu được cập nhật, và điều hướng sang S13 TC editor để tạo mới hoặc chỉnh sửa. Là trung tâm quản lý chất lượng kiểm thử của dự án.

**Vai trò truy cập:** Admin, PM, QC, Dev (tất cả member)
**Màn hình trước:** S2 Project list (sidebar), S6 Document viewer (panel phải), S5 Version detail (tab Testcases)
**Màn hình sau:** S13 TC editor (tạo/sửa TC), S6 Document viewer (xem chunk nguồn)

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER (sticky)                                                      │
│ [Logo]  Projects › Project Demo › Testcases        [Avatar ▾]       │
├─────────────┬────────────────────────────────────────────────────────┤
│ SIDEBAR     │ MAIN CONTENT                                           │
│             │                                                        │
│   Documents │  Testcases                [Generate TC] [+ Tạo TC]    │
│ ● Testcases │                                                        │
│   Q&A Chat  │  ┌──────────────────────────────────────────────────┐ │
│   Members   │  │[Màn hình ▾][Loại ▾][Priority ▾][Status ▾][Search]│ │
│             │  │                                      [Xoá filter] │ │
│             │  └──────────────────────────────────────────────────┘ │
│             │                                                        │
│             │  ⚠ 4 testcase cần review lại (tài liệu đã cập nhật)  │
│             │                                           [Xem tất cả]│
│             │                                                        │
│             │  ┌─────────────────────────────────────────────────┐  │
│             │  │ □ │ ID     │ Tiêu đề  │ Màn │ Prior │ Status │ ··· │
│             │  ├─────────────────────────────────────────────────┤  │
│             │  │ □ │TC-001 ⚠│Login OK  │Login│ 🔴High│ Active │ ··· │
│             │  │ □ │TC-002  │Login sai │Login│ 🟡Med │ Active │ ··· │
│             │  │ □ │TC-003  │Rate limit│Login│ 🔴High│ Active │ ··· │
│             │  │ □ │TC-004  │Dashboard │Dash │ 🟢Low │ Draft  │ ··· │
│             │  └─────────────────────────────────────────────────┘  │
│             │                                                        │
│             │  Hiển thị 1-20 / 84 testcase        [< 1 2 3 4 5 >]  │
└─────────────┴────────────────────────────────────────────────────────┘
```

---

### 1.3 Filter bar

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Tất cả màn hình ▾] [Tất cả loại ▾] [Tất cả priority ▾]           │
│ [Tất cả status ▾]   [Search tiêu đề TC...    🔍]   [Xoá filter]    │
└──────────────────────────────────────────────────────────────────────┘
```

| Filter | Giá trị | Mô tả |
|---|---|---|
| Màn hình | All / Login / Dashboard / Profile / ... | Dynamic từ TC data |
| Loại TC | All / Manual / API / E2E | `tc_type` enum |
| Priority | All / Critical / High / Medium / Low | `priority` enum |
| Status | All / Active / Draft / Archived | `status` field |
| Search | Text | Tìm trong tiêu đề TC, debounce 300ms |
| Xoá filter | — | Hiện khi có ít nhất 1 filter active |

Kết hợp filter: AND logic — tất cả filter cùng lúc.

---

### 1.4 Banner cảnh báo TC cần review

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⚠  4 testcase cần review lại — tài liệu liên quan vừa được cập nhật │
│    Màn hình: Login (3 TC), Dashboard (1 TC)          [Xem tất cả →] │
└──────────────────────────────────────────────────────────────────────┘
```

- Hiện khi có TC có `needs_review = true`
- Background vàng nhạt, border vàng
- Click "Xem tất cả" → tự động set filter Status = "Cần review"
- Dismiss được — user click X để ẩn banner (lưu vào localStorage, không hiện lại trong session)

---

### 1.5 Table Testcase

#### Header table

| Cột | Width | Mô tả |
|---|---|---|
| Checkbox | 36px | Bulk select |
| ID | 90px | TC-001, TC-002... + icon ⚠ nếu needs_review |
| Tiêu đề | flex 1 | Title của testcase |
| Màn hình | 110px | screen_name |
| Loại | 80px | Manual / API / E2E badge |
| Priority | 90px | Critical / High / Medium / Low badge |
| Trạng thái | 100px | Active / Draft / Archived badge |
| Tài liệu | 80px | Số chunk linked (icon link + số) |
| Actions | 80px | Icon buttons + menu ··· |

#### Row testcase

```
┌──────────────────────────────────────────────────────────────────────┐
│ [□] TC-001 ⚠  Login thành công → về Dashboard   Login  Manual       │
│              [🔴 High]  [● Active]  [🔗 3]       [👁][✏][···]       │
└──────────────────────────────────────────────────────────────────────┘
```

**Icon ⚠ (needs_review):** Màu vàng, tooltip "Tài liệu liên quan đã được cập nhật — cần review lại testcase này"

**Actions per row:**
- 👁 Xem — mở S13 TC editor ở mode view (tất cả role)
- ✏ Sửa — mở S13 TC editor ở mode edit (QC/PM/Admin)
- ··· Menu: Duplicate, Archive, Xoá (confirm dialog)

**Click vào row (không phải action):** Expand inline — hiện preview steps và expected result

#### Row expand

```
┌──────────────────────────────────────────────────────────────────────┐
│ [□] TC-001 ⚠  Login thành công → về Dashboard   Login  Manual       │
│              [🔴 High]  [● Active]  [🔗 3]       [👁][✏][···]       │
│  ────────────────────────────────────────────────────────────────   │
│  Các bước:                        Kết quả mong đợi:                 │
│  1. Mở màn hình Login             Chuyển thẳng đến S2 Dashboard     │
│  2. Nhập email hợp lệ             User được xác thực thành công     │
│  3. Nhập password đúng                                               │
│  4. Click "Đăng nhập"                                                │
│                                                                      │
│  Chunk nguồn: [Basic Design · Login · §Button states] [API · §POST /login]│
└──────────────────────────────────────────────────────────────────────┘
```

---

### 1.6 Priority badge

| Priority | Màu nền | Màu text | Dot |
|---|---|---|---|
| Critical | Danger đậm | Trắng | 🔴 |
| High | Danger nhạt | Danger dark | 🔴 |
| Medium | Warning nhạt | Warning dark | 🟡 |
| Low | Gray nhạt | Gray dark | ⚪ |

---

### 1.7 Status badge

| Status | Màu | Mô tả |
|---|---|---|
| Active | Success | TC đang được dùng |
| Draft | Gray | TC chưa hoàn thiện |
| Archived | Gray đậm | TC đã lưu trữ, không hiện mặc định |
| Cần review ⚠ | Warning | `needs_review = true` |

---

### 1.8 Toolbar trên table

```
┌──────────────────────────────────────────────────────────────────────┐
│ Testcases                    [🤖 Generate TC bằng AI] [+ Tạo TC]    │
└──────────────────────────────────────────────────────────────────────┘
```

| Element | Role thấy | Hành động |
|---|---|---|
| "Generate TC bằng AI" | QC, PM, Admin | Mở modal chọn màn hình + doc_type → AI tạo hàng loạt |
| "+ Tạo TC" | QC, PM, Admin | Mở S13 TC editor mode create |

---

### 1.9 Bulk actions

Khi chọn ≥ 1 checkbox:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Đã chọn 3 testcase    [Archive]  [Xoá]  [Đổi priority ▾]  [X Bỏ chọn]│
└──────────────────────────────────────────────────────────────────────┘
```

| Action | Confirm | Mô tả |
|---|---|---|
| Archive | Không | Chuyển status → archived |
| Xoá | Có — "Xoá 3 testcase? Không thể hoàn tác." | Xoá vĩnh viễn |
| Đổi priority | Không | Dropdown chọn priority mới |

---

### 1.10 Modal "Generate TC bằng AI"

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🤖 Generate Testcase bằng AI                                      X  │
├──────────────────────────────────────────────────────────────────────┤
│ Màn hình *                                                           │
│ [Login                                                           ▾]  │
│                                                                      │
│ Loại tài liệu làm nguồn                                             │
│ [✓] Basic Design (v3 — approved)                                    │
│ [✓] API Design (v2 — approved)                                      │
│ [ ] Detail Design (chưa có)                                          │
│                                                                      │
│ Loại testcase cần tạo                                               │
│ [✓] Manual   [ ] API   [ ] E2E                                      │
│                                                                      │
│ Ước tính: ~8 testcase sẽ được tạo                                   │
│                                                                      │
│                        [Huỷ]  [🤖 Generate ngay]                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 1.11 Empty & loading states

| Tình huống | Hiển thị |
|---|---|
| Đang load | Skeleton table 5 row shimmer |
| Chưa có TC nào | Illustration + "Chưa có testcase nào. Tạo TC đầu tiên hoặc generate bằng AI." |
| Filter không có kết quả | "Không tìm thấy TC nào với bộ lọc hiện tại." + nút Xoá filter |
| Generate đang chạy | Progress bar + "Đang tạo testcase từ tài liệu..." |
| Generate xong | Toast "Đã tạo 8 testcase mới cho màn hình Login" |

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Load màn hình S12

```
Navigate vào S12
    │
    ├─ Gọi song song:
    │   ├─ GET /projects/{id}/testcases    → data table
    │   └─ GET /projects/{id}/testcases/screens → populate dropdown màn hình
    │
    ├─ Check needs_review count → hiện/ẩn banner cảnh báo
    │
    └─ Apply URL query params nếu có (filter persist)
```

#### Filter testcase

```
User thay đổi filter
    │
    ├─ Debounce 300ms (search text)
    │
    ├─ Cập nhật URL query params
    │
    ├─ Nếu tổng TC ≤ 200: filter client-side
    │
    └─ Nếu tổng TC > 200: gọi API với params mới
```

#### Xoá testcase (single)

```
Click ··· → Xoá
    │
    └─ Confirm dialog → DELETE /testcases/{id}
            │
            ├─ Success → xoá row + toast + cập nhật counter
            └─ Fail → giữ nguyên + toast error
```

#### Bulk archive

```
Chọn N TC → click Archive
    │
    └─ PATCH /projects/{id}/testcases/bulk
            body: { action: "archive", ids: [...] }
            │
            └─ Success → cập nhật status tất cả row → archived
                       → Nếu filter đang = Active thì các row này ẩn đi
```

#### AI Generate TC

```
PM/QC mở modal → chọn màn hình + doc_type + tc_type → click Generate
    │
    └─ POST /projects/{id}/testcases/generate
            │
            ├─ Server: lấy chunks approved của màn hình + doc_type đã chọn
            ├─ Build RAG context
            ├─ Gọi Claude API → parse JSON response → tạo TC records
            ├─ Auto-link TC ↔ chunk nguồn (testcase_chunk_links)
            │
            └─ Response 202 → polling job status mỗi 2s
                    └─ Khi done → reload table + toast + scroll lên top
```

#### Đánh dấu TC đã review

```
User mở TC có ⚠ → xem xét → click "Đánh dấu đã review"
    │
    └─ PATCH /testcases/{id}
            body: { needs_review: false }
            │
            └─ Success → xoá icon ⚠ trên row + cập nhật banner counter
```

---

### 2.2 AI Generate TC — Chi tiết pipeline

```python
# app/services/tc_generate_service.py

GENERATE_SYSTEM_PROMPT = """
Bạn là chuyên gia QA. Dựa trên tài liệu dưới đây, hãy tạo danh sách testcase
đầy đủ theo format JSON.

Mỗi testcase gồm:
- title: tiêu đề ngắn gọn (tối đa 80 ký tự)
- steps: danh sách bước thực hiện (array of string)
- expected_result: kết quả mong đợi
- priority: "critical" | "high" | "medium" | "low"
- tc_type: "manual" | "api" | "e2e"
- source_chunk_index: index của chunk tài liệu liên quan nhất

Chỉ trả về JSON array, không có text nào khác.
Tạo đủ testcase để cover tất cả case: happy path, error path,
edge case, boundary value.

[TÀI LIỆU]
{context}
"""

async def generate_testcases(
    project_id: str,
    screen_name: str,
    doc_types: list[str],
    tc_type: str,
    created_by: str,
    db: AsyncSession
) -> list[dict]:
    # 1. Lấy chunks của màn hình + doc_types đã chọn
    chunks = await get_approved_chunks(db, project_id, screen_name, doc_types)
    context = build_context(chunks)

    # 2. Gọi Claude
    response = await claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": GENERATE_SYSTEM_PROMPT.format(context=context)
        }]
    )

    # 3. Parse JSON
    import json, re
    raw = response.content[0].text
    clean = re.sub(r'```json|```', '', raw).strip()
    tc_list = json.loads(clean)

    # 4. Tạo TC records + auto-link chunk
    created = []
    for tc_data in tc_list:
        tc = Testcase(
            project_id=project_id,
            screen_name=screen_name,
            title=tc_data["title"],
            tc_type=tc_data.get("tc_type", tc_type),
            steps=tc_data["steps"],
            expected_result=tc_data["expected_result"],
            priority=tc_data.get("priority", "medium"),
            status="draft",
            created_by=created_by,
        )
        db.add(tc)
        await db.flush()  # get tc.id

        # Auto-link với chunk nguồn
        chunk_idx = tc_data.get("source_chunk_index", 0)
        if chunk_idx < len(chunks):
            link = TestcaseChunkLink(
                testcase_id=tc.id,
                chunk_id=chunks[chunk_idx].id,
                link_type=doc_types[0],
                is_primary=True,
                relevance_score=1.0,
            )
            db.add(link)

        created.append(tc)

    await db.commit()
    return created
```

---

### 2.3 Validation Rules

#### VL-S12-001 — Quyền tạo TC
- **Trigger:** Click "+ Tạo TC" hoặc "Generate TC"
- **Rule:** `project_members.role` IN (`owner`, `pm`, `qc`)
- **Xử lý:** Nút ẩn với Dev
- **Scope:** UI + Server

#### VL-S12-002 — Quyền xoá TC
- **Trigger:** Click Xoá trong menu ···
- **Rule:** `project_members.role` IN (`owner`, `pm`, `qc`)
- **Xử lý:** Menu item ẩn với Dev
- **Scope:** UI + Server

#### VL-S12-003 — Bulk action cần chọn ít nhất 1
- **Trigger:** Click bulk action button
- **Rule:** Số TC được chọn > 0
- **Xử lý:** Bulk action bar ẩn khi không có gì được chọn
- **Scope:** Client only

#### VL-S12-004 — Generate cần có tài liệu approved
- **Trigger:** Click "Generate ngay" trong modal
- **Rule:** Phải chọn ít nhất 1 doc_type có tài liệu approved
- **Error message:** "Chưa có tài liệu approved cho lựa chọn này"
- **Scope:** Client (disable option) + Server

#### VL-S12-005 — Filter screen_name hợp lệ
- **Trigger:** Query param từ URL
- **Rule:** screen_name phải tồn tại trong project
- **Xử lý:** Reset về All nếu không hợp lệ
- **Scope:** Client

#### VL-S12-006 — Không xoá TC đang linked với chunk approved
- **Trigger:** Click Xoá
- **Rule:** TC có thể xoá bất kể linked hay không — nhưng cần confirm rõ: "TC này đang linked với N đoạn tài liệu"
- **Xử lý:** Confirm dialog hiện thêm thông tin linked chunks
- **Scope:** Server trả warning trong response

---

### 2.4 Phân quyền chi tiết

| Action | Owner | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Xem danh sách TC | ✓ | ✓ | ✓ | ✓ |
| Xem chi tiết TC (expand) | ✓ | ✓ | ✓ | ✓ |
| Filter và search | ✓ | ✓ | ✓ | ✓ |
| Tạo TC mới | ✓ | ✓ | ✓ | — |
| Sửa TC | ✓ | ✓ | ✓ | — |
| Xoá TC | ✓ | ✓ | ✓ | — |
| Archive TC | ✓ | ✓ | ✓ | — |
| Generate TC bằng AI | ✓ | ✓ | ✓ | — |
| Đánh dấu đã review | ✓ | ✓ | ✓ | — |
| Bulk actions | ✓ | ✓ | ✓ | — |

---

### 2.5 URL state — filter persist

```
/projects/project-demo/testcases
  ?screen=login
  &tc_type=manual
  &priority=high
  &status=active
  &needs_review=true
  &search=button
  &page=2
```

---

### 2.6 Pagination

- Mặc định 20 TC / trang
- User có thể đổi: 20 / 50 / 100 per page
- Hiện "Hiển thị 1–20 / 84 testcase"
- Giữ filter khi chuyển trang

---

### 2.7 TC ID naming convention

```python
# Auto-generate TC ID theo project
# Format: TC-{project_prefix}-{sequential_number}
# Ví dụ: TC-QCM-001, TC-QCM-002, ...

async def generate_tc_id(db: AsyncSession, project_id: str) -> str:
    project = await db.get(Project, project_id)
    prefix = project.slug[:3].upper()  # "project-demo" → "PRO"
    last = await db.execute(
        select(func.max(Testcase.tc_sequential))
        .where(Testcase.project_id == project_id)
    )
    next_num = (last.scalar() or 0) + 1
    return f"TC-{prefix}-{next_num:03d}"
```

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/testcases` | Danh sách TC + filter + pagination | Bearer (member) |
| GET | `/api/v1/projects/{project_id}/testcases/screens` | Danh sách màn hình có TC | Bearer (member) |
| GET | `/api/v1/projects/{project_id}/testcases/stats` | Thống kê TC theo status/priority | Bearer (member) |
| POST | `/api/v1/projects/{project_id}/testcases/generate` | AI generate TC hàng loạt | Bearer (qc/pm/owner) |
| GET | `/api/v1/projects/{project_id}/testcases/generate/{job_id}/status` | Poll trạng thái generate | Bearer (member) |
| PATCH | `/api/v1/projects/{project_id}/testcases/bulk` | Bulk action (archive/delete/priority) | Bearer (qc/pm/owner) |
| DELETE | `/api/v1/testcases/{testcase_id}` | Xoá 1 TC | Bearer (qc/pm/owner) |

---

### 3.2 GET /api/v1/projects/{project_id}/testcases

**Mô tả:** Danh sách TC với filter đa chiều, pagination, kèm thông tin chunk linked và needs_review count.

**Auth:** Bearer (member)
**Rate limit:** 60 lần / phút / user
**Idempotent:** Có

#### Query parameters

| Param | Type | Mô tả | Mặc định |
|---|---|---|---|
| `screen` | string | Filter theo screen_name | — |
| `tc_type` | string | `manual` \| `api` \| `e2e` | — |
| `priority` | string | `critical` \| `high` \| `medium` \| `low` | — |
| `status` | string | `active` \| `draft` \| `archived` | `active,draft` |
| `needs_review` | boolean | Chỉ TC cần review | — |
| `search` | string | Tìm trong title | — |
| `page` | int | Trang hiện tại | `1` |
| `per_page` | int | Số TC / trang, max 100 | `20` |
| `sort_by` | string | `created_at` \| `updated_at` \| `priority` | `updated_at` |
| `sort_dir` | string | `asc` \| `desc` | `desc` |

#### Request

```
GET /api/v1/projects/550e8400/testcases?screen=login&priority=high&page=1
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "data": [
    {
      "id": "tc-uuid-001",
      "tc_id": "TC-PRO-001",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "screen_name": "Login",
      "title": "Login thành công → chuyển về Dashboard",
      "tc_type": "manual",
      "priority": "high",
      "status": "active",
      "needs_review": true,
      "steps_count": 4,
      "steps_preview": ["Mở màn hình Login", "Nhập email hợp lệ", "..."],
      "expected_result": "Chuyển thẳng đến S2 Dashboard, hiện tên user trên header",
      "linked_chunks": [
        {
          "chunk_id": "chunk-uuid-002",
          "doc_type": "basic_design",
          "section": "Button states",
          "is_primary": true
        },
        {
          "chunk_id": "chunk-uuid-015",
          "doc_type": "api_design",
          "section": "POST /login",
          "is_primary": false
        }
      ],
      "linked_chunks_count": 2,
      "created_at": "2025-05-20T08:00:00Z",
      "updated_at": "2025-06-09T10:00:00Z",
      "created_by": {
        "id": "uuid-qc",
        "full_name": "Tran QC"
      }
    }
  ],
  "pagination": {
    "total": 84,
    "page": 1,
    "per_page": 20,
    "total_pages": 5
  },
  "summary": {
    "total": 84,
    "needs_review_count": 4,
    "by_status": {
      "active": 72,
      "draft": 8,
      "archived": 4
    },
    "by_priority": {
      "critical": 5,
      "high": 23,
      "medium": 41,
      "low": 15
    }
  }
}
```

**Ghi chú `summary`:** Luôn trả về tổng thống kê theo project (không bị ảnh hưởng bởi filter hiện tại) — dùng để FE hiện banner cảnh báo và badge số trên sidebar.

**Ghi chú `steps_preview`:** Chỉ 2 bước đầu + "..." — dùng cho expand inline. Full steps gọi `GET /testcases/{id}` trong S13.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền truy cập project | Không phải member |
| 404 | Project không tồn tại | — |
| 422 | Tham số không hợp lệ | tc_type/priority/status sai enum |

---

### 3.3 GET /api/v1/projects/{project_id}/testcases/screens

**Mô tả:** Danh sách màn hình đã có TC. Dùng populate dropdown filter "Màn hình".

**Auth:** Bearer (member)
**Rate limit:** 60 lần / phút / user

#### Response 200

```json
{
  "screens": [
    { "screen_name": "Login", "tc_count": 12, "needs_review_count": 3 },
    { "screen_name": "Dashboard", "tc_count": 8, "needs_review_count": 1 },
    { "screen_name": "Profile", "tc_count": 5, "needs_review_count": 0 }
  ],
  "total": 3
}
```

---

### 3.4 GET /api/v1/projects/{project_id}/testcases/stats

**Mô tả:** Thống kê tổng hợp TC của project. Dùng cho dashboard và header badges.

**Auth:** Bearer (member)
**Rate limit:** 30 lần / phút / user

#### Response 200

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_testcases": 84,
  "needs_review": 4,
  "by_status": {
    "active": 72,
    "draft": 8,
    "archived": 4
  },
  "by_priority": {
    "critical": 5,
    "high": 23,
    "medium": 41,
    "low": 15
  },
  "by_tc_type": {
    "manual": 60,
    "api": 18,
    "e2e": 6
  },
  "by_screen": [
    { "screen_name": "Login", "count": 12 },
    { "screen_name": "Dashboard", "count": 8 }
  ],
  "coverage": {
    "screens_with_tc": 7,
    "screens_total": 10,
    "coverage_percent": 70
  }
}
```

---

### 3.5 POST /api/v1/projects/{project_id}/testcases/generate

**Mô tả:** Enqueue Celery job AI generate TC từ tài liệu. Trả 202 ngay, FE polling job status.

**Auth:** Bearer (qc, pm, owner)
**Rate limit:** 5 lần / phút / user
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `screen_name` | string | Có | Màn hình cần generate TC |
| `doc_types` | array | Có | List doc_type làm nguồn, ít nhất 1 |
| `tc_type` | string | Có | `manual` \| `api` \| `e2e` |
| `overwrite_existing` | boolean | Không | Nếu true: xoá TC draft cũ trước khi tạo mới | Mặc định `false` |

```json
{
  "screen_name": "Login",
  "doc_types": ["basic_design", "api_design"],
  "tc_type": "manual",
  "overwrite_existing": false
}
```

#### Response 202

```json
{
  "job_id": "generate-job-uuid-001",
  "screen_name": "Login",
  "doc_types": ["basic_design", "api_design"],
  "estimated_tc_count": 8,
  "estimated_seconds": 15,
  "message": "Đang generate testcase. Vui lòng chờ..."
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | — |
| 403 | Không có quyền | Không phải qc/pm/owner |
| 404 | Màn hình không có tài liệu approved | doc_types không có chunk nào |
| 409 | Đang có job generate đang chạy | Chờ job trước xong |
| 422 | doc_types không hợp lệ | — |

---

### 3.6 GET /api/v1/projects/{project_id}/testcases/generate/{job_id}/status

**Mô tả:** Poll trạng thái job generate TC.

**Auth:** Bearer (member)
**Rate limit:** 60 lần / phút / user

#### Response 200

```json
{
  "job_id": "generate-job-uuid-001",
  "status": "done",
  "progress": {
    "total_chunks": 12,
    "processed_chunks": 12,
    "percentage": 100
  },
  "result": {
    "created_count": 8,
    "testcase_ids": [
      "tc-uuid-new-001",
      "tc-uuid-new-002"
    ]
  },
  "updated_at": "2025-06-15T10:05:00Z"
}
```

**Status values:** `queued` → `processing` → `done` | `failed`

---

### 3.7 PATCH /api/v1/projects/{project_id}/testcases/bulk

**Mô tả:** Thực hiện action hàng loạt trên nhiều TC cùng lúc.

**Auth:** Bearer (qc, pm, owner)
**Rate limit:** 20 lần / phút / user
**Idempotent:** Có (archive 2 lần = archive)

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `action` | string | Có | `archive` \| `delete` \| `set_priority` \| `mark_reviewed` |
| `testcase_ids` | array | Có | List TC UUID, tối đa 100 |
| `priority` | string | Khi action=set_priority | `critical` \| `high` \| `medium` \| `low` |

```json
{
  "action": "archive",
  "testcase_ids": ["tc-uuid-001", "tc-uuid-002", "tc-uuid-003"]
}
```

```json
{
  "action": "set_priority",
  "testcase_ids": ["tc-uuid-004", "tc-uuid-005"],
  "priority": "high"
}
```

#### Response 200

```json
{
  "action": "archive",
  "affected_count": 3,
  "testcase_ids": ["tc-uuid-001", "tc-uuid-002", "tc-uuid-003"],
  "skipped_ids": [],
  "message": "Đã archive 3 testcase"
}
```

**Ghi chú `skipped_ids`:** TC không thể thực hiện action (ví dụ: xoá TC đang linked với chunk approved — cần confirm riêng).

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | action không hợp lệ | — |
| 400 | testcase_ids rỗng hoặc quá 100 | — |
| 403 | Không có quyền | — |
| 404 | Một số TC không tồn tại | Trả list ids không tìm thấy |

---

### 3.8 DELETE /api/v1/testcases/{testcase_id}

**Mô tả:** Xoá 1 TC. Cascade xoá chunk links và TC embeddings. Không xoá chunk.

**Auth:** Bearer (qc, pm, owner)
**Rate limit:** 30 lần / phút / user
**Idempotent:** Có

#### Request

```
DELETE /api/v1/testcases/tc-uuid-001
Authorization: Bearer eyJ...
```

**Cascade xoá:**
1. `testcase_chunk_links` WHERE `testcase_id`
2. `testcase_embeddings` WHERE `testcase_id`
3. `chat_citations` WHERE `chunk_id` IN linked chunks (soft — set chunk_id=null)
4. `testcase` record

#### Response 200

```json
{
  "message": "Đã xoá testcase TC-PRO-001",
  "testcase_id": "tc-uuid-001",
  "unlinked_chunks": 2
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền xoá | Dev không xoá được |
| 404 | Testcase không tồn tại | — |

---

## 4. Database schema bổ sung

```sql
-- Thêm cột tc_sequential và tc_id vào testcases
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS
  tc_sequential  INT,
  tc_id          TEXT GENERATED ALWAYS AS (
    'TC-' || UPPER(LEFT(
      (SELECT slug FROM projects WHERE id = project_id), 3
    )) || '-' || LPAD(tc_sequential::TEXT, 3, '0')
  ) STORED;

-- Index để tìm kiếm nhanh
CREATE INDEX idx_testcases_needs_review
  ON testcases(project_id, needs_review)
  WHERE needs_review = true;

CREATE INDEX idx_testcases_screen_status
  ON testcases(project_id, screen_name, status);

CREATE INDEX idx_testcases_priority
  ON testcases(project_id, priority);

CREATE INDEX idx_testcases_search
  ON testcases USING GIN(to_tsvector('simple', title));

-- Bảng generate jobs
CREATE TABLE tc_generate_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name  TEXT NOT NULL,
  doc_types    TEXT[] NOT NULL,
  tc_type      tc_type_enum NOT NULL,
  status       TEXT NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued','processing','done','failed')),
  progress     JSONB DEFAULT '{}',
  result       JSONB DEFAULT '{}',
  created_by   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tc_generate_jobs_project
  ON tc_generate_jobs(project_id, status);
```

---

## 5. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S12 load lần đầu | `GET /testcases` + `GET /screens` | Song song |
| S12 filter thay đổi | `GET /testcases?...` | Client-side ≤200, API >200 |
| S12 banner cảnh báo | `summary.needs_review_count` từ GET /testcases | Không cần API riêng |
| S12 stats header | `GET /testcases/stats` | Badge số trên sidebar |
| S12 generate modal | `POST /testcases/generate` | Trả 202 |
| S12 generate polling | `GET /generate/{job_id}/status` | Mỗi 2s |
| S12 bulk action | `PATCH /testcases/bulk` | Tối đa 100 TC |
| S12 xoá 1 TC | `DELETE /testcases/{id}` | Confirm dialog |
| S12 row click "Sửa" | Navigate → S13 | Routing |
| S12 "Tạo TC" | Navigate → S13 mode create | Routing |
| S6 panel phải | `GET /testcases?screen=X` | Lọc theo màn hình |
| S5 tab Testcases | `GET /testcases?screen=X` | Lọc theo màn hình |

---

## 6. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S2 Project list | Sidebar navigate vào S12 |
| Basic Design — S6 Document viewer | Panel phải TC liên quan, bôi text → tạo TC |
| Basic Design — S5 Version detail | Tab Testcases |
| Basic Design — S7 Diff viewer | Approve diff → flag TC needs_review |
| Basic Design — S8 Approve panel | Trigger needs_review sau approve |
| Basic Design — S13 TC editor | Màn hình sau S12 |
| Basic Design — S11 TC panel | Tạo TC nhanh từ S6 |
| Database schema — testcases | tc_type, priority, status, needs_review |
| Database schema — testcase_chunk_links | Liên kết TC ↔ chunk |
| API Design — S6 Document viewer | GET /chunks/{id}/testcases dùng chung |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
