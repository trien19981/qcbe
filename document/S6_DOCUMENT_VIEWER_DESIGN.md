# S6 Document Viewer — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Document Viewer  
**Màn hình:** S6 Document viewer  
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

Màn hình đọc tài liệu với khả năng highlight chunk, xem testcase liên quan theo từng đoạn nội dung, và tạo testcase mới từ đoạn được chọn. Đây là **bridge trung tâm** kết nối tài liệu ↔ testcase ↔ Q&A — người dùng có thể đến S6 từ nhiều điểm: từ S3 click xem, từ S10 Q&A cite, hoặc từ S12 TC list click vào chunk nguồn.

**Vai trò truy cập:** Tất cả member (Admin, PM, QC, Dev)  
**Màn hình trước:**
- S3 Document list (click tên tài liệu)
- S5 Version detail (click "Xem nội dung")
- S10 Q&A Answer (click citation badge)
- S12 TC list (click chunk nguồn)

**Màn hình sau:**
- S9 Q&A Chat (click "Hỏi AI")
- S11 TC panel (bôi chọn text → tạo TC)
- S13 TC editor (click "Sửa" trong panel phải)
- S7 Diff viewer (click "So sánh version")

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│ TOOLBAR (sticky top)                                                 │
│ ← Quay lại  [Login / Basic Design]  [v3 ▾]  [Hỏi AI] [So sánh]    │
├───────────────────────────────────────┬──────────────────────────────┤
│ CONTENT AREA (60%)                    │ SIDE PANEL (40%)             │
│                                       │                              │
│  ## Button states                     │ [Tab: TC liên quan] [Info]  │
│                                       │                              │
│  ┃ Button LOGIN cần có màu đỏ        │ Chunk đang chọn:            │
│  ┃ khi người dùng nhập sai           │ "Button LOGIN cần có..."    │
│  ┃ thông tin đăng nhập.              │                              │
│  ┃                                   │ TESTCASE LIÊN QUAN (3)      │
│  ┃ [chunk đang active — highlight]   │ ┌─────────────────────────┐ │
│                                       │ │ TC-001 Login thành công │ │
│  ## Error messages                    │ │ [High] [Active]    [Xem]│ │
│                                       │ ├─────────────────────────┤ │
│  ┃ Hiện message lỗi tương ứng       │ │ TC-002 Login sai PW     │ │
│  ┃ ngay dưới field bị lỗi           │ │ [Med]  [Active]    [Xem]│ │
│  ┃                                   │ └─────────────────────────┘ │
│                                       │                              │
│  [Bôi text → popup action]            │ [+ Tạo TC từ màn hình này]  │
│                                       │                              │
└───────────────────────────────────────┴──────────────────────────────┘
```

- **Toolbar:** Sticky top, height 48px
- **Content area:** 60% width, padding 32px, max-width 720px, scroll độc lập
- **Side panel:** 40% width, sticky top (scroll nội dung riêng), min-width 300px
- **Responsive:** Dưới 900px → side panel collapse thành bottom drawer

---

### 1.3 Toolbar chi tiết

```
┌──────────────────────────────────────────────────────────────────────┐
│ [← Quay lại]  Login / Basic Design    [v3 ▾]  [Hỏi AI] [So sánh]  │
│               S3 › Login › Basic Design                             │
└──────────────────────────────────────────────────────────────────────┘
```

| Element | Mô tả | Hành động |
|---|---|---|
| ← Quay lại | Breadcrumb / back button | Navigate về màn trước (S3 hoặc S5) |
| Tên tài liệu | "Login / Basic Design" — screen + doc_type | — |
| Breadcrumb | "S3 › Login › Basic Design" nhỏ bên dưới | Click từng phần navigate |
| Version selector | Dropdown "[v3 ▾]" — chọn version để xem | Reload content với version khác |
| Nút "Hỏi AI" | Icon chat + text | Mở S9 Q&A với scope = màn hình này |
| Nút "So sánh" | Icon diff | Mở S7 Diff (chỉ khi ≥ 2 version) |

---

### 1.4 Content area — hiển thị nội dung

#### Chunk highlight system

Mỗi chunk trong tài liệu được wrap bởi một container có thể highlight:

```
┌─────────────────────────────────────────────────────────┐
│ ## Button states                                        │
│                                                         │
│ ┌─ chunk border trái ──────────────────────────────┐   │
│ │                                                   │   │
│ │  Button LOGIN cần có màu ĐỎ khi người dùng      │   │
│ │  nhập sai thông tin đăng nhập.                   │   │
│ │                                                   │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌─ chunk border trái (active — from Q&A cite) ─────┐   │
│ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │   │  ← nền vàng nhạt
│ │  Hiện message lỗi tương ứng ngay dưới field      │   │
│ │  bị lỗi, không dùng alert popup.                │   │
│ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │   │
│ └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Các trạng thái chunk:**

| State | Visual | Trigger |
|---|---|---|
| Default | Border trái 2px gray nhạt | — |
| Hover | Border trái 2px info, cursor pointer | Mouse over |
| Active (click) | Border trái 3px info + nền info nhạt | User click chunk |
| Cited (từ Q&A) | Border trái 3px warning + nền warning nhạt + scroll vào view | Mở từ citation |
| Has TC | Border trái 2px success nhạt + dot xanh góc phải | Chunk đã có TC linked |

#### Figma frame display

Khi `doc_type = figma`, content area hiển thị ảnh frame thay vì text:

```
┌─────────────────────────────────────────────────────┐
│ Frame: Login Screen - Default State                 │
│ ┌─────────────────────────────────────────────────┐ │
│ │                                                 │ │
│ │          [Ảnh snapshot Figma frame]             │ │
│ │                                                 │ │
│ └─────────────────────────────────────────────────┘ │
│ [Mở trong Figma ↗]                 Sync: 2 ngày trước│
│                                                     │
│ Text layers:                                        │
│ ┃ Title: "Đăng nhập"                              │
│ ┃ Button: "Đăng nhập"                             │
│ ┃ Link: "Quên mật khẩu?"                          │
└─────────────────────────────────────────────────────┘
```

---

### 1.5 Popup action khi bôi chọn text

Khi user bôi chọn (select) bất kỳ đoạn text nào trong content area:

```
[Đoạn text được bôi chọn]
         │
    ┌────┴──────────────────────────────────┐
    │ [📋 Xem TC liên quan]                 │
    │ [➕ Tạo TC từ đoạn này]              │
    │ [💬 Hỏi AI về đoạn này]             │
    └───────────────────────────────────────┘
```

| Action | Mô tả |
|---|---|
| Xem TC liên quan | Tìm TC liên quan đến chunk chứa đoạn được chọn, hiện trong side panel |
| Tạo TC từ đoạn này | Mở S11 TC panel (slide-in) với chunk context đã điền sẵn |
| Hỏi AI về đoạn này | Mở S9 Q&A với câu hỏi pre-fill: "Giải thích đoạn: [selected text]" |

Popup biến mất khi: click nơi khác, nhấn Escape, hoặc sau khi chọn action.

---

### 1.6 Side panel — Tab "TC liên quan"

```
┌─────────────────────────────────────────────────┐
│ [TC liên quan (3)] [Thông tin]                  │
├─────────────────────────────────────────────────┤
│ Chunk đang xem:                                 │
│ "Button LOGIN cần có màu đỏ khi..."            │
│ [Basic Design · §Button states]                 │
├─────────────────────────────────────────────────┤
│                                                 │
│ TC-001 Login thành công → về Dashboard         │
│ [🔴 High] [● Active]              [Xem] [Sửa]  │
│                                                 │
│ TC-002 Login sai password → lỗi đỏ            │
│ [🟡 Med]  [● Active]              [Xem] [Sửa]  │
│                                                 │
│ TC-007 Login sau 5 lần sai → khoá              │
│ [🔴 High] [● Active]              [Xem] [Sửa]  │
│                                                 │
├─────────────────────────────────────────────────┤
│ [+ Tạo TC mới từ màn hình này]                 │
└─────────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Chunk preview | Hiện 80 ký tự đầu của chunk đang active + breadcrumb section |
| TC list | Mỗi TC: ID + title + priority badge + status + 2 nút action |
| Priority badge | Critical=đỏ đậm, High=đỏ, Medium=vàng, Low=xám |
| Status badge | Active=xanh lá, Draft=xám, Archived=xám đậm |
| Nút Xem | Mở S13 TC editor ở mode view |
| Nút Sửa | Mở S13 TC editor ở mode edit (chỉ QC/PM/Admin) |
| Empty state | "Chưa có testcase nào liên quan đến đoạn này" |
| Footer button | "+ Tạo TC mới từ màn hình này" → S11 TC panel |

---

### 1.7 Side panel — Tab "Thông tin"

```
┌─────────────────────────────────────────────────┐
│ [TC liên quan (3)] [Thông tin]                  │
├─────────────────────────────────────────────────┤
│ Tài liệu                                        │
│ Màn hình:    Login                              │
│ Loại:        Basic Design                       │
│ Version:     v3 (Đã duyệt)                     │
│ Approved:    10/06/2025 bởi Nguyen PM           │
│                                                 │
│ Thống kê                                        │
│ Số chunk:    12                                 │
│ Số TC liên quan: 8                              │
│                                                 │
│ Changelog v3                                    │
│ ─────────────────────────────────────────      │
│ ## Changelog v3                                 │
│ ### Thêm mới                                    │
│ - Thêm OAuth Google login                       │
│                                                 │
│ [Download file gốc ↓]                          │
└─────────────────────────────────────────────────┘
```

---

### 1.8 Chunk navigator (mini sidebar)

Thanh nhỏ bên trái content area, hiện outline các section:

```
│ ≡ │  ## Mô tả màn hình
│   │  ## Button states         ◄ (active)
│   │  ## Error messages
│   │  ## Loading states
│   │  ## Empty states
```

Click section → scroll content area đến đó. Section đang xem được highlight.

---

### 1.9 Empty & loading states

| Tình huống | Hiển thị |
|---|---|
| Đang load nội dung | Skeleton text: 3 đoạn paragraph placeholder với shimmer |
| Version đang processing | Banner vàng: "Tài liệu này đang được xử lý. Nội dung sẽ sẵn sàng sau vài phút." |
| Version bị rejected | Banner đỏ: "Version này đã bị từ chối. Xem version khác." |
| Không có chunk nào | "Không thể hiển thị nội dung tài liệu này." |
| Side panel đang load | Skeleton 3 TC card |
| Side panel không có TC | "Chưa có testcase nào. Tạo testcase đầu tiên cho màn hình này." |

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Load màn hình S6

```
Navigate vào S6 (từ S3, S5, S10, S12)
    │
    ├─ Parse URL params:
    │   - document_id (bắt buộc)
    │   - version_id (optional — mặc định version mới nhất approved)
    │   - chunk_id (optional — scroll và highlight chunk này)
    │   - highlight_source: "qa" | "tc" | "manual"
    │
    ├─ Gọi song song:
    │   ├─ GET /documents/{id}/viewer?version_id={vid}  → content + chunks
    │   └─ GET /documents/{id}/versions                 → danh sách version (cho dropdown)
    │
    ├─ Render content với chunks
    │
    └─ Nếu có chunk_id trong URL:
            └─ Scroll đến chunk đó + apply highlight state "cited"
                    └─ highlight_source="qa" → nền vàng
                    └─ highlight_source="tc" → nền xanh lá nhạt
```

#### Click vào chunk

```
User click vào 1 chunk trong content area
    │
    ├─ Set chunk đó là "active" (border + nền info nhạt)
    │
    ├─ Cập nhật URL: ?chunk_id={chunk_id} (không reload trang)
    │
    └─ Gọi GET /chunks/{chunk_id}/testcases
            │
            └─ Cập nhật side panel "TC liên quan" với kết quả
```

#### Bôi chọn text → popup

```
User bôi chọn text trong content area
    │
    ├─ Detect selection bằng window.getSelection()
    │
    ├─ Xác định chunk chứa selection (theo DOM parent)
    │
    ├─ Hiện popup tại vị trí selection (getBoundingClientRect)
    │
    └─ User chọn action:
            ├─ "Xem TC liên quan"
            │       └─ Set chunk đó active + load TC trong side panel
            │
            ├─ "Tạo TC từ đoạn này"
            │       └─ Mở S11 TC panel với:
            │               - chunk_id = chunk chứa selection
            │               - selected_text = text được bôi
            │               - pre-fill AI generate
            │
            └─ "Hỏi AI về đoạn này"
                    └─ Mở S9 Q&A với:
                            - scope = màn hình này
                            - pre-fill: "Giải thích đoạn: [selected_text]"
```

#### Chuyển version

```
User chọn version khác trong dropdown toolbar
    │
    ├─ Nếu version mới khác version hiện tại:
    │       ├─ Clear active chunk
    │       ├─ Clear side panel
    │       ├─ Cập nhật URL: ?version_id={new_vid}
    │       └─ Gọi lại GET /documents/{id}/viewer?version_id={new_vid}
    │
    └─ Nếu version đang processing:
            └─ Hiện banner "Đang xử lý" thay vì content
```

---

### 2.2 Chunk highlight khi đến từ Q&A citation

Khi user click citation badge trong S10 Q&A Answer:

```
URL: /projects/{slug}/documents/{doc_id}/viewer
     ?version_id={ver_id}
     &chunk_id={chunk_id}
     &highlight_source=qa
     &scroll=true
```

FE xử lý:
1. Load content bình thường
2. Sau khi render, tìm DOM element của chunk có `data-chunk-id={chunk_id}`
3. Apply class `.chunk-cited-qa` (nền vàng nhạt, border warning)
4. `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`
5. Cập nhật side panel với TC liên quan của chunk đó

---

### 2.3 Render content theo doc_type

| doc_type | Cách render |
|---|---|
| `basic_design` | Markdown render (react-markdown) — heading, list, table, bold |
| `api_design` | Markdown + code block syntax highlight (prism.js) |
| `detail_design` | Markdown render |
| `testcase_manual` | Table render — mỗi testcase là 1 row có steps expandable |
| `figma` | Image grid — mỗi frame là 1 image card + text layers |

---

### 2.4 Chunk detection khi bôi text

```typescript
function getChunkFromSelection(): string | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return null

  // Tìm ancestor element có data-chunk-id
  let node: Node | null = selection.anchorNode
  while (node) {
    if (node instanceof HTMLElement && node.dataset.chunkId) {
      return node.dataset.chunkId
    }
    node = node.parentNode
  }
  return null
}

// DOM structure mỗi chunk:
// <div data-chunk-id="chunk-uuid-001" data-chunk-index="0" class="chunk-block">
//   <div class="chunk-content">... text content ...</div>
//   <div class="chunk-tc-indicator">● 3 TC</div>  // nếu có TC
// </div>
```

---

### 2.5 Side panel — caching

TC liên quan của từng chunk được cache trong local state để không gọi API lại khi user click qua lại các chunk:

```typescript
// Cache: { [chunk_id]: TestCase[] }
const [chunkTcCache, setChunkTcCache] = useState<Record<string, TestCase[]>>({})

async function loadChunkTestcases(chunkId: string) {
  if (chunkTcCache[chunkId]) {
    // Dùng cache
    setActiveTcs(chunkTcCache[chunkId])
    return
  }
  // Gọi API
  const tcs = await fetchChunkTestcases(chunkId)
  setChunkTcCache(prev => ({ ...prev, [chunkId]: tcs }))
  setActiveTcs(tcs)
}
```

Cache bị invalidate khi: user tạo TC mới, user xoá TC, hoặc reload trang.

---

### 2.6 Phân quyền chi tiết

| Action | Owner | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Xem nội dung tài liệu | ✓ | ✓ | ✓ | ✓ |
| Chuyển version | ✓ | ✓ | ✓ | ✓ |
| Download file gốc | ✓ | ✓ | ✓ | ✓ |
| Xem TC liên quan | ✓ | ✓ | ✓ | ✓ |
| Hỏi AI về đoạn | ✓ | ✓ | ✓ | ✓ |
| Tạo TC từ đoạn | ✓ | ✓ | ✓ | — |
| Sửa TC | ✓ | ✓ | ✓ | — |
| So sánh version (→ S7) | ✓ | ✓ | — | — |

---

### 2.7 URL schema đầy đủ

```
/projects/{project_slug}/documents/{document_id}/viewer

Query params:
  version_id={uuid}           -- version cụ thể (mặc định: latest approved)
  chunk_id={uuid}             -- scroll và highlight chunk này
  highlight_source=qa|tc      -- source của highlight (ảnh hưởng màu)
  scroll=true                 -- có scroll vào chunk không
  tc_panel=open               -- tự mở side panel TC
```

---

### 2.8 Performance — virtual scroll

Với tài liệu dài (> 50 chunks), content area dùng virtual scrolling để không render tất cả chunk cùng lúc:

- Chỉ render chunks trong viewport + 5 chunk buffer trên/dưới
- Chunk ngoài viewport được placeholder với chiều cao ước tính
- Khi scroll đến → render thực tế

Thư viện đề xuất: `@tanstack/react-virtual`

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/documents/{document_id}/viewer` | Nội dung + chunks để render | Bearer (member) |
| GET | `/api/v1/chunks/{chunk_id}/testcases` | TC liên quan đến 1 chunk | Bearer (member) |
| GET | `/api/v1/documents/{document_id}/chunks` | Danh sách chunk (outline) | Bearer (member) |
| POST | `/api/v1/chunks/{chunk_id}/testcase-links` | Link TC vào chunk | Bearer (qc/pm/owner) |
| DELETE | `/api/v1/chunks/{chunk_id}/testcase-links/{tc_id}` | Unlink TC khỏi chunk | Bearer (qc/pm/owner) |

---

### 3.2 GET /api/v1/documents/{document_id}/viewer

**Mô tả:** Lấy toàn bộ nội dung tài liệu đã được chia thành chunks, kèm metadata để render và highlight. Đây là API chính của S6.

**Auth:** Bearer (member của project)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Bắt buộc | Mô tả | Mặc định |
|---|---|---|---|---|
| `version_id` | UUID | Không | Version cụ thể muốn xem | Latest approved version |
| `include_tc_count` | boolean | Không | Thêm số TC liên quan vào mỗi chunk | `true` |

#### Request

```
GET /api/v1/documents/doc-uuid-001/viewer?version_id=ver-uuid-003
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "document": {
    "id": "doc-uuid-001",
    "screen_name": "Login",
    "doc_type": "basic_design",
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "version": {
    "id": "ver-uuid-003",
    "version_no": 3,
    "status": "approved",
    "changelog_md": "## Changelog v3\n### Thêm mới\n- OAuth Google login",
    "created_at": "2025-06-08T10:00:00Z",
    "created_by": {
      "id": "uuid-pm",
      "full_name": "Nguyen PM"
    },
    "approved_at": "2025-06-08T14:00:00Z"
  },
  "all_versions": [
    { "id": "ver-uuid-003", "version_no": 3, "status": "approved", "is_current": true },
    { "id": "ver-uuid-002", "version_no": 2, "status": "approved", "is_current": false },
    { "id": "ver-uuid-001", "version_no": 1, "status": "approved", "is_current": false }
  ],
  "chunks": [
    {
      "id": "chunk-uuid-001",
      "chunk_index": 0,
      "content_text": "## Mô tả màn hình\n\nMàn hình xác thực duy nhất của hệ thống QC Master...",
      "metadata": {
        "screen": "Login",
        "section": "Mô tả màn hình",
        "doc_type": "basic_design",
        "chunk_start_token": 0
      },
      "token_count": 120,
      "tc_count": 0
    },
    {
      "id": "chunk-uuid-002",
      "chunk_index": 1,
      "content_text": "## Button states\n\nButton LOGIN cần có màu ĐỎ khi người dùng nhập sai...",
      "metadata": {
        "screen": "Login",
        "section": "Button states",
        "doc_type": "basic_design",
        "chunk_start_token": 120
      },
      "token_count": 95,
      "tc_count": 3
    }
  ],
  "total_chunks": 12,
  "figma_frames": null
}
```

**Ghi chú `figma_frames`:** Chỉ có data khi `doc_type = figma`. Khi đó `chunks` vẫn chứa text layers, còn `figma_frames` chứa thêm URL ảnh snapshot.

**Ghi chú `all_versions`:** Dùng để populate version dropdown trên toolbar. Chỉ trả version có status `approved`, `ready_for_review`, `processing` — không trả `draft` và `rejected` với QC/Dev.

#### Response 200 — khi doc_type = figma

```json
{
  "document": { "...": "..." },
  "version": { "...": "..." },
  "chunks": [
    {
      "id": "chunk-uuid-010",
      "chunk_index": 0,
      "content_text": "Title: Đăng nhập\nButton: Đăng nhập\nLink: Quên mật khẩu?",
      "metadata": {
        "screen": "Login",
        "frame_id": "123:456",
        "frame_name": "Login Screen - Default",
        "snapshot_url": "https://r2.qcmaster.dev/figma/snapshots/123_456.png",
        "doc_type": "figma"
      },
      "token_count": 45,
      "tc_count": 2
    }
  ],
  "figma_frames": [
    {
      "chunk_id": "chunk-uuid-010",
      "frame_id": "123:456",
      "frame_name": "Login Screen - Default",
      "figma_url": "https://www.figma.com/file/xxx?node-id=123:456",
      "snapshot_url": "https://r2.qcmaster.dev/figma/snapshots/123_456.png",
      "synced_at": "2025-06-08T08:00:00Z"
    }
  ]
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền xem tài liệu | Không phải member của project |
| 404 | Document không tồn tại | — |
| 404 | Không tìm thấy version approved | Document chưa có version nào được approve |
| 422 | version_id không hợp lệ | UUID sai format |

#### Error body — chưa có version approved

```json
{
  "error": "NO_APPROVED_VERSION",
  "message": "Tài liệu này chưa có version nào được duyệt.",
  "status_code": 404,
  "latest_version": {
    "id": "ver-uuid-001",
    "version_no": 1,
    "status": "processing"
  }
}
```

---

### 3.3 GET /api/v1/chunks/{chunk_id}/testcases

**Mô tả:** Lấy danh sách testcase đã được link với chunk cụ thể. Gọi khi user click vào chunk trong S6. Có cache TTL 60s ở server (Redis).

**Auth:** Bearer (member của project chứa chunk)  
**Rate limit:** 120 lần / phút / user  
**Idempotent:** Có

#### Request

```
GET /api/v1/chunks/chunk-uuid-002/testcases
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "chunk_id": "chunk-uuid-002",
  "chunk_preview": "Button LOGIN cần có màu ĐỎ khi người dùng nhập sai...",
  "chunk_section": "Button states",
  "testcases": [
    {
      "id": "tc-uuid-001",
      "title": "Login thành công → chuyển về Dashboard",
      "tc_type": "manual",
      "priority": "high",
      "status": "active",
      "steps_count": 4,
      "link_type": "basic_design",
      "relevance_score": 0.95,
      "is_primary_link": true,
      "created_by": {
        "full_name": "Tran QC"
      },
      "updated_at": "2025-06-09T10:00:00Z"
    },
    {
      "id": "tc-uuid-002",
      "title": "Login sai password → hiện lỗi đỏ dưới field",
      "tc_type": "manual",
      "priority": "medium",
      "status": "active",
      "steps_count": 3,
      "link_type": "basic_design",
      "relevance_score": 0.88,
      "is_primary_link": false,
      "created_by": {
        "full_name": "Tran QC"
      },
      "updated_at": "2025-06-08T14:00:00Z"
    }
  ],
  "total": 2
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | Chunk thuộc project khác |
| 404 | Chunk không tồn tại | — |

---

### 3.4 GET /api/v1/documents/{document_id}/chunks

**Mô tả:** Danh sách chunk rút gọn (chỉ id, index, section name, tc_count) — dùng để render chunk navigator outline bên trái content area. Không bao gồm full content text.

**Auth:** Bearer (member)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Mô tả |
|---|---|---|
| `version_id` | UUID | Version cụ thể |

#### Response 200

```json
{
  "document_id": "doc-uuid-001",
  "version_id": "ver-uuid-003",
  "chunks": [
    {
      "id": "chunk-uuid-001",
      "chunk_index": 0,
      "section": "Mô tả màn hình",
      "token_count": 120,
      "tc_count": 0
    },
    {
      "id": "chunk-uuid-002",
      "chunk_index": 1,
      "section": "Button states",
      "token_count": 95,
      "tc_count": 3
    },
    {
      "id": "chunk-uuid-003",
      "chunk_index": 2,
      "section": "Error messages",
      "token_count": 88,
      "tc_count": 2
    }
  ],
  "total": 12
}
```

---

### 3.5 POST /api/v1/chunks/{chunk_id}/testcase-links

**Mô tả:** Link một testcase vào chunk. Dùng khi QC muốn thủ công liên kết TC với đoạn nội dung. Thường được gọi tự động từ S11 TC panel sau khi tạo TC mới.

**Auth:** Bearer (qc, pm, owner)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có (link 2 lần không tạo duplicate — UNIQUE constraint)

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `testcase_id` | UUID | Có | TC cần link vào chunk |
| `link_type` | string | Có | `basic_design` \| `api_design` \| `detail_design` \| `testcase_manual` \| `figma` |
| `is_primary` | boolean | Không | Chunk này là nguồn chính của TC | Mặc định `false` |
| `relevance_score` | float | Không | 0.0–1.0, mặc định 1.0 khi link thủ công | Mặc định `1.0` |

```json
{
  "testcase_id": "tc-uuid-010",
  "link_type": "basic_design",
  "is_primary": true
}
```

#### Response 201

```json
{
  "id": "link-uuid-001",
  "chunk_id": "chunk-uuid-002",
  "testcase_id": "tc-uuid-010",
  "link_type": "basic_design",
  "is_primary": true,
  "relevance_score": 1.0,
  "created_at": "2025-06-10T10:00:00Z"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | — |
| 403 | Không có quyền | Dev không được link |
| 404 | Chunk hoặc testcase không tồn tại | — |
| 409 | Link đã tồn tại | UNIQUE(chunk_id, testcase_id) |
| 422 | TC và chunk thuộc project khác nhau | Cross-project link không được phép |

---

### 3.6 DELETE /api/v1/chunks/{chunk_id}/testcase-links/{testcase_id}

**Mô tả:** Xoá link giữa TC và chunk. Không xoá TC — chỉ unlink.

**Auth:** Bearer (qc, pm, owner)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Request

```
DELETE /api/v1/chunks/chunk-uuid-002/testcase-links/tc-uuid-010
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "message": "Đã xoá liên kết giữa testcase và đoạn nội dung",
  "chunk_id": "chunk-uuid-002",
  "testcase_id": "tc-uuid-010"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền | Dev không được unlink |
| 404 | Link không tồn tại | — |

---

## 4. Frontend implementation notes

### 4.1 Popup action component

```typescript
// components/TextSelectionPopup.tsx
import { useEffect, useState } from 'react'

interface PopupPosition { top: number; left: number }

export function TextSelectionPopup({
  onViewTC, onCreateTC, onAskAI
}: {
  onViewTC: (chunkId: string) => void
  onCreateTC: (chunkId: string, text: string) => void
  onAskAI: (text: string) => void
}) {
  const [pos, setPos] = useState<PopupPosition | null>(null)
  const [chunkId, setChunkId] = useState<string | null>(null)
  const [selectedText, setSelectedText] = useState('')

  useEffect(() => {
    const handleSelectionChange = () => {
      const sel = window.getSelection()
      if (!sel || sel.isCollapsed || !sel.toString().trim()) {
        setPos(null)
        return
      }
      const text = sel.toString().trim()
      const range = sel.getRangeAt(0)
      const rect = range.getBoundingClientRect()
      const chunk = getChunkFromSelection(sel)

      setSelectedText(text)
      setChunkId(chunk)
      setPos({
        top: rect.top + window.scrollY - 48,
        left: rect.left + rect.width / 2,
      })
    }

    document.addEventListener('selectionchange', handleSelectionChange)
    return () => document.removeEventListener('selectionchange', handleSelectionChange)
  }, [])

  if (!pos) return null

  return (
    <div style={{ position: 'absolute', top: pos.top, left: pos.left }}
         className="selection-popup">
      <button onClick={() => chunkId && onViewTC(chunkId)}>
        📋 Xem TC liên quan
      </button>
      <button onClick={() => chunkId && onCreateTC(chunkId, selectedText)}>
        ➕ Tạo TC từ đoạn này
      </button>
      <button onClick={() => onAskAI(selectedText)}>
        💬 Hỏi AI về đoạn này
      </button>
    </div>
  )
}
```

### 4.2 Chunk renderer với data attributes

```typescript
// components/ChunkBlock.tsx
interface ChunkBlockProps {
  chunk: Chunk
  isActive: boolean
  isCited: boolean
  citedSource?: 'qa' | 'tc'
  onClick: (chunkId: string) => void
}

export function ChunkBlock({ chunk, isActive, isCited, citedSource, onClick }: ChunkBlockProps) {
  const className = [
    'chunk-block',
    isActive ? 'chunk-active' : '',
    isCited && citedSource === 'qa' ? 'chunk-cited-qa' : '',
    isCited && citedSource === 'tc' ? 'chunk-cited-tc' : '',
    chunk.tc_count > 0 ? 'chunk-has-tc' : '',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={className}
      data-chunk-id={chunk.id}
      data-chunk-index={chunk.chunk_index}
      onClick={() => onClick(chunk.id)}
    >
      <div className="chunk-content">
        <ReactMarkdown>{chunk.content_text}</ReactMarkdown>
      </div>
      {chunk.tc_count > 0 && (
        <div className="chunk-tc-indicator">
          ● {chunk.tc_count} TC
        </div>
      )}
    </div>
  )
}
```

---

## 5. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S6 load lần đầu | `GET /documents/{id}/viewer` | Load content + chunks |
| S6 chunk navigator | `GET /documents/{id}/chunks` | Outline sidebar |
| S6 click chunk | `GET /chunks/{id}/testcases` | Side panel TC |
| S6 chuyển version | `GET /documents/{id}/viewer?version_id=X` | Reload content |
| S6 bôi text → Tạo TC | → Mở S11 TC panel | Pass chunk_id + text |
| S6 bôi text → Hỏi AI | → Mở S9 Q&A | Pass selected text |
| S6 link TC thủ công | `POST /chunks/{id}/testcase-links` | Từ side panel |
| S6 unlink TC | `DELETE /chunks/{id}/testcase-links/{tc_id}` | Từ side panel |
| S10 Q&A → S6 | `GET /viewer?chunk_id=X&highlight_source=qa` | Scroll + highlight |
| S12 TC list → S6 | `GET /viewer?chunk_id=X&highlight_source=tc` | Xem chunk nguồn |

---

## 6. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S3 Document list | Entry point chính vào S6 |
| Basic Design — S5 Version detail | Entry point thứ 2 vào S6 |
| Basic Design — S9 Q&A chat | Citation click → S6 với chunk highlight |
| Basic Design — S10 Q&A Answer | Citation badge → S6 |
| Basic Design — S11 TC panel | Bôi text → Tạo TC |
| Basic Design — S12 TC list | Click chunk nguồn → S6 |
| Basic Design — S13 TC editor | Sửa TC từ side panel |
| Basic Design — S7 Diff viewer | Nút So sánh trên toolbar |
| Database schema — chunks | chunk_index, content_text, metadata |
| Database schema — testcase_chunk_links | link_type, relevance_score, is_primary |
| Flow Upload & Embedding | Chunks được tạo từ pipeline này |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
