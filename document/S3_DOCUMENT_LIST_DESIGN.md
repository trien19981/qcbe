# S3 Document list — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Danh sách tài liệu  
**Màn hình:** S3 Document list  
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

Màn hình trung tâm của hệ thống — hiển thị toàn bộ tài liệu của một project. Người dùng đến đây sau khi click vào project card ở S2. Đây là điểm xuất phát cho mọi hành động liên quan đến tài liệu: xem, upload, so sánh version, hỏi AI.

**Vai trò truy cập:** Admin, PM, QC, Dev (tất cả member của project)  
**Màn hình trước:** S2 Project list  
**Màn hình sau:**
- S4 Upload form (upload tài liệu mới hoặc version mới)
- S5 Version detail (click vào tài liệu)
- S7 Diff viewer (so sánh version)
- S9 Q&A chat (hỏi AI về tài liệu)

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER (sticky)                                                      │
│ [Logo]  Projects › Project Demo › Documents    [Hỏi AI] [Avatar ▾]  │
├─────────────┬────────────────────────────────────────────────────────┤
│ SIDEBAR     │ MAIN CONTENT                                           │
│             │                                                        │
│ ● Documents │  Documents                    [+ Upload tài liệu]     │
│   Q&A Chat  │                                                        │
│   Members   │  ┌──────────────────────────────────────────────────┐ │
│   Cài đặt   │  │ [Loại tài liệu ▾]  [Màn hình ▾]  [Search...  🔍]│ │
│             │  └──────────────────────────────────────────────────┘ │
│             │                                                        │
│             │  ┌────────────────────────────────────────────────┐   │
│             │  │ Màn hình  │ Loại │ Version │ Status │ Cập nhật │   │
│             │  ├────────────────────────────────────────────────┤   │
│             │  │ ▶ Login   │ BD   │  v3     │ ●aprvd │ 2 ngày   │   │
│             │  ├────────────────────────────────────────────────┤   │
│             │  │   └─ v3 [approved] [Xem] [Download]            │   │
│             │  │   └─ v2 [approved] [Xem] [Download]            │   │
│             │  │   └─ v1 [approved] [Xem] [Download]            │   │
│             │  ├────────────────────────────────────────────────┤   │
│             │  │ ▶ Login   │ API  │  v2     │ ●ready │ 1 ngày   │   │
│             │  ├────────────────────────────────────────────────┤   │
│             │  │ ▶ Dashboard│ BD  │  v1     │ ○draft │ 5 ngày   │   │
│             │  └────────────────────────────────────────────────┘   │
│             │                                                        │
└─────────────┴────────────────────────────────────────────────────────┘
```

- **Sidebar:** Fixed left 220px, giống S2
- **Breadcrumb:** Projects › Tên project › Documents
- **Main:** Full width trừ sidebar

---

### 1.3 Filter bar

```
┌──────────────────────────────────────────────────────────────────┐
│ [Tất cả loại ▾]  [Tất cả màn hình ▾]  [Search tài liệu...   🔍] │
│                                                    [Xoá filter]  │
└──────────────────────────────────────────────────────────────────┘
```

| Element | Mô tả | Giá trị |
|---|---|---|
| Dropdown "Loại tài liệu" | Filter theo `doc_type` | Tất cả / Basic Design / API Design / Detail Design / Testcase Manual / Figma |
| Dropdown "Màn hình" | Filter theo `screen_name` | Dynamic từ data — list các màn hình đã có tài liệu |
| Search | Tìm theo tên màn hình, debounce 300ms | Text input |
| Nút "Xoá filter" | Hiện khi có filter active, reset tất cả về default | Text button |

**Kết hợp filter:** AND logic — chọn "Basic Design" + "Login" → chỉ hiện Basic Design của màn Login.

---

### 1.4 Table tài liệu

#### Header table

| Cột | Width | Mô tả |
|---|---|---|
| (expand) | 32px | Mũi tên expand/collapse row |
| Màn hình | flex 1 | `screen_name` — tên màn hình |
| Loại | 140px | `doc_type` badge |
| Version | 80px | Version mới nhất: "v3" |
| Trạng thái | 130px | Status badge version mới nhất |
| Cập nhật | 120px | Relative time: "2 ngày trước" |
| Người update | 120px | Avatar + tên người upload version mới nhất |
| Actions | 120px | Icon buttons |

#### Row chính (collapsed)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▶  Login          [Basic Design]   v3   [● Approved]  2 ngày  [Av]  │
│                                              [👁] [↑] [⇄] [···]     │
└──────────────────────────────────────────────────────────────────────┘
```

**Actions icons per row:**
- 👁 Xem — mở S5 Version detail (version mới nhất)
- ↑ Upload version mới — mở S4 (chỉ PM/Admin)
- ⇄ So sánh version — mở S7 Diff (chỉ hiện khi có ≥ 2 version)
- ··· Menu: Sửa tên màn hình (Admin), Xoá tài liệu (Admin)

#### Row expanded (version history)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▼  Login          [Basic Design]   v3   [● Approved]  2 ngày  [Av]  │
│    ─────────────────────────────────────────────────────────────     │
│    v3  [● Approved]  10/06/2025  Nguyen PM   [Xem] [Download]       │
│    v2  [● Approved]  01/06/2025  Nguyen PM   [Xem] [Download]       │
│    v1  [● Approved]  15/05/2025  Admin       [Xem] [Download]       │
└──────────────────────────────────────────────────────────────────────┘
```

- Sub-row dùng nền `background-secondary` để phân biệt
- Mỗi version: số version + status badge + ngày tạo + người tạo + 2 action
- Version mới nhất: badge "Mới nhất" màu info
- Version `approved`: dot xanh lá
- Version `ready_for_review`: dot xanh dương
- Version `draft`/`processing`/`rejected`: màu tương ứng

---

### 1.5 Status badge

| Status | Màu | Label hiển thị | Ý nghĩa |
|---|---|---|---|
| `draft` | Gray | Bản nháp | Vừa upload, chưa xử lý |
| `processing` | Warning + spinner | Đang xử lý | Celery đang chunk + embed |
| `ready_for_review` | Info | Chờ duyệt | Embedding xong, chờ approve |
| `approved` | Success | Đã duyệt | Active trong RAG |
| `rejected` | Danger | Đã từ chối | Không được dùng trong RAG |

---

### 1.6 Doc type badge

| doc_type | Label | Màu |
|---|---|---|
| `basic_design` | Basic Design | Purple |
| `api_design` | API Design | Teal |
| `detail_design` | Detail Design | Amber |
| `testcase_manual` | Testcase Manual | Coral |
| `figma` | Figma | Pink |

---

### 1.7 Toolbar trên table

```
┌──────────────────────────────────────────────────────────────────┐
│ Documents                              [Hỏi AI về project] [+ Upload] │
└──────────────────────────────────────────────────────────────────┘
```

| Element | Role thấy | Hành động |
|---|---|---|
| Title "Documents" | Tất cả | — |
| Nút "Hỏi AI về project" | Tất cả | Mở S9 scope = toàn project |
| Nút "+ Upload tài liệu" | PM, Admin | Mở S4 Upload form — tạo document mới |

---

### 1.8 Empty states

#### Chưa có tài liệu nào trong project

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│              [Illustration: tập hồ sơ]               │
│                                                      │
│           Chưa có tài liệu nào trong project         │
│     Upload tài liệu đầu tiên để bắt đầu làm việc    │
│                                                      │
│                 [+ Upload tài liệu]                  │
│                 (chỉ hiện PM/Admin)                  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### Filter không có kết quả

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│         Không tìm thấy tài liệu nào                 │
│   với bộ lọc: Basic Design · Màn hình Login         │
│                                                      │
│              [Xoá bộ lọc]                           │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### Đang tải

- Skeleton table: 5 row placeholder với shimmer animation
- Mỗi skeleton row: hình chữ nhật mờ ở các cột, không hiện data thật

#### Lỗi network

- Toast đỏ: "Không thể tải danh sách tài liệu. Kiểm tra kết nối mạng."
- Nút "Thử lại" trong toast
- Table hiện data cũ (stale) nếu đã có từ trước, mờ đi 50%

---

### 1.9 Auto-polling

Khi có document ở trạng thái `processing`, frontend tự động gọi lại `GET /documents` mỗi **5 giây** để kiểm tra status mới. Dừng polling khi tất cả document không còn ở trạng thái `processing`.

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Load màn hình S3

```
Navigate vào S3 (từ S2 click project card)
    │
    ├─ Gọi song song:
    │   ├─ GET /projects/{id}/documents     → data table
    │   └─ GET /projects/{id}/documents/screens → populate dropdown màn hình
    │
    ├─ Hiện skeleton trong lúc chờ
    │
    ├─ Render table theo response
    │
    └─ Nếu có document status=processing:
            └─ Bắt đầu polling interval 5s
```

#### Filter tài liệu

```
User thay đổi filter (dropdown hoặc search)
    │
    ├─ Debounce 300ms (search text)
    │
    ├─ Nếu tổng documents ≤ 100:
    │       └─ Filter client-side trên data đã load
    │
    └─ Nếu tổng documents > 100:
            └─ Gọi API với query params mới
                    GET /documents?doc_type=X&screen=Y&search=Z
```

#### Expand row xem version history

```
User click mũi tên expand trên row
    │
    ├─ Nếu đã có version data trong local state → expand ngay
    │
    └─ Nếu chưa có → gọi GET /documents/{id}/versions
            │
            ├─ Hiện skeleton sub-rows trong lúc chờ
            │
            └─ Render sub-rows với version list
```

**Lý do lazy load:** Không load tất cả version của tất cả document khi vào màn hình — tốn bandwidth. Chỉ load khi user cần xem.

#### Upload version mới từ S3

```
PM/Admin click "↑ Upload version mới" trên row
    │
    └─ Mở S4 Upload form với:
            - document_id đã điền sẵn
            - screen_name đã điền sẵn (readonly)
            - doc_type đã điền sẵn (readonly)
            - version_no = current_max + 1 (server tính)

Sau khi S4 submit thành công:
    │
    └─ Navigate về S3
            └─ Row tương ứng cập nhật status → "processing"
                    └─ Bắt đầu polling
```

#### Xoá tài liệu (Admin only)

```
Admin click "···" → "Xoá tài liệu"
    │
    └─ Modal confirm:
            "Xoá tài liệu này sẽ xoá tất cả {N} version và chunk embedding liên quan.
             Các testcase đã link sẽ bị unlink. Không thể hoàn tác."
            │
            └─ Xác nhận → DELETE /documents/{id}
                    │
                    ├─ Success → xoá row khỏi table + toast
                    └─ Fail → giữ nguyên + toast error
```

---

### 2.2 Validation Rules

#### VL-S3-001 — Quyền upload
- **Trigger:** Click nút Upload
- **Rule:** `current_user.project_role` phải là `owner`, `pm`
- **Xử lý:** Nút ẩn với QC/Dev — không hiện trong UI
- **Scope:** UI + Server

#### VL-S3-002 — Quyền xoá tài liệu
- **Trigger:** Click Xoá trong menu "···"
- **Rule:** `current_user.role` phải là system `admin` hoặc project `owner`
- **Xử lý:** Menu item ẩn với PM/QC/Dev
- **Scope:** UI + Server

#### VL-S3-003 — So sánh cần ≥ 2 version
- **Trigger:** Click nút So sánh
- **Rule:** Document phải có ít nhất 2 version
- **Xử lý:** Icon So sánh disabled + tooltip "Cần ít nhất 2 version để so sánh"
- **Scope:** UI only

#### VL-S3-004 — Filter hợp lệ
- **Trigger:** Query params trong URL
- **Rule:** `doc_type` phải thuộc enum hợp lệ nếu có truyền
- **Xử lý:** Server trả 422 nếu sai — FE reset filter về default
- **Scope:** Server only

---

### 2.3 Phân quyền chi tiết

| Action | Owner | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Xem danh sách tài liệu | ✓ | ✓ | ✓ | ✓ |
| Xem version history (expand) | ✓ | ✓ | ✓ | ✓ |
| Download file gốc | ✓ | ✓ | ✓ | ✓ |
| Filter và search | ✓ | ✓ | ✓ | ✓ |
| Upload tài liệu mới | ✓ | ✓ | — | — |
| Upload version mới | ✓ | ✓ | — | — |
| Sửa tên màn hình | ✓ | — | — | — |
| Xoá tài liệu | ✓ | — | — | — |
| Mở Q&A Chat | ✓ | ✓ | ✓ | ✓ |

---

### 2.4 URL state — filter persist trong URL

Filter được lưu vào URL query params để user có thể copy/share link, back/forward hoạt động đúng:

```
/projects/project-demo/documents?doc_type=basic_design&screen=login&search=button
```

Khi load trang với query params có sẵn, FE tự động apply filter tương ứng.

---

### 2.5 Polling logic chi tiết

```typescript
// Polling chỉ chạy khi có document processing
function startPollingIfNeeded(documents: Document[]) {
  const hasProcessing = documents.some(d =>
    d.latest_version?.status === 'processing'
  )
  if (hasProcessing && !pollingRef.current) {
    pollingRef.current = setInterval(async () => {
      const fresh = await fetchDocuments()
      setDocuments(fresh)
      // Dừng khi không còn processing
      const stillProcessing = fresh.some(d =>
        d.latest_version?.status === 'processing'
      )
      if (!stillProcessing) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }, 5000)
  }
}

// Cleanup khi unmount
useEffect(() => {
  return () => {
    if (pollingRef.current) clearInterval(pollingRef.current)
  }
}, [])
```

---

### 2.6 Loading states chi tiết

| Tình huống | Skeleton / Indicator |
|---|---|
| Load lần đầu | Skeleton table 5 row, shimmer toàn bộ cột |
| Expand row (lazy load versions) | 3 skeleton sub-row dưới row đó |
| Filter đang áp dụng (server-side) | Spinner nhỏ trong filter bar, table mờ 50% |
| Document đang processing | Spinner 12px trong status badge, row highlight nhạt |
| Đang xoá | Row mờ + spinner trong nút Xoá, bảng lock interaction |

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/documents` | Danh sách tài liệu + filter | Bearer (member) |
| GET | `/api/v1/projects/{project_id}/documents/screens` | List màn hình có tài liệu | Bearer (member) |
| GET | `/api/v1/documents/{document_id}/versions` | Version history của 1 tài liệu | Bearer (member) |
| GET | `/api/v1/documents/{document_id}/versions/{version_id}/download` | Presigned URL download file gốc | Bearer (member) |
| PATCH | `/api/v1/documents/{document_id}` | Sửa thông tin document | Bearer (owner) |
| DELETE | `/api/v1/documents/{document_id}` | Xoá tài liệu và tất cả version | Bearer (owner/admin) |

---

### 3.2 GET /api/v1/projects/{project_id}/documents

**Mô tả:** Danh sách tài liệu của project. Mỗi item là 1 document kèm thông tin version mới nhất. Hỗ trợ filter và pagination.

**Auth:** Bearer (phải là member của project)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Bắt buộc | Mô tả | Mặc định |
|---|---|---|---|---|
| `doc_type` | string | Không | `basic_design` \| `api_design` \| `detail_design` \| `testcase_manual` \| `figma` | — (tất cả) |
| `screen` | string | Không | Tên màn hình, exact match hoặc partial | — |
| `search` | string | Không | Tìm trong screen_name | — |
| `status` | string | Không | Filter theo status version mới nhất | — |
| `page` | int | Không | Trang hiện tại | `1` |
| `per_page` | int | Không | Số item / trang, max 100 | `50` |

#### Request

```
GET /api/v1/projects/550e8400/documents?doc_type=basic_design&page=1
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "data": [
    {
      "id": "doc-uuid-001",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "screen_name": "Login",
      "doc_type": "basic_design",
      "description": "Basic design màn hình đăng nhập",
      "version_count": 3,
      "latest_version": {
        "id": "ver-uuid-003",
        "version_no": 3,
        "status": "approved",
        "changelog_md": "## Changelog v3\n- Thêm OAuth login",
        "created_at": "2025-06-08T10:00:00Z",
        "created_by": {
          "id": "uuid-pm",
          "full_name": "Nguyen PM",
          "avatar_url": null
        },
        "approved_at": "2025-06-08T14:00:00Z"
      },
      "created_at": "2025-05-15T08:00:00Z",
      "updated_at": "2025-06-08T14:00:00Z"
    },
    {
      "id": "doc-uuid-002",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "screen_name": "Login",
      "doc_type": "api_design",
      "description": null,
      "version_count": 2,
      "latest_version": {
        "id": "ver-uuid-005",
        "version_no": 2,
        "status": "processing",
        "changelog_md": null,
        "created_at": "2025-06-09T09:00:00Z",
        "created_by": {
          "id": "uuid-pm",
          "full_name": "Nguyen PM",
          "avatar_url": null
        },
        "approved_at": null
      },
      "created_at": "2025-05-20T08:00:00Z",
      "updated_at": "2025-06-09T09:00:00Z"
    }
  ],
  "pagination": {
    "total": 12,
    "page": 1,
    "per_page": 50,
    "total_pages": 1
  },
  "has_processing": true
}
```

**Ghi chú field `has_processing`:** FE dùng field này để quyết định có bắt đầu polling hay không, không cần scan toàn bộ array.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền truy cập project | Không phải member |
| 404 | Project không tồn tại | — |
| 422 | Tham số không hợp lệ | `doc_type` sai enum |

---

### 3.3 GET /api/v1/projects/{project_id}/documents/screens

**Mô tả:** Lấy danh sách tên màn hình đã có tài liệu trong project. Dùng để populate dropdown filter "Màn hình".

**Auth:** Bearer (phải là member của project)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Request

```
GET /api/v1/projects/550e8400/documents/screens
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "screens": [
    {
      "screen_name": "Login",
      "doc_count": 3
    },
    {
      "screen_name": "Dashboard",
      "doc_count": 2
    },
    {
      "screen_name": "Profile",
      "doc_count": 1
    }
  ],
  "total": 3
}
```

**Ghi chú:** Kết quả sort theo alphabet. `doc_count` là số loại tài liệu (không phải version) của màn hình đó.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | Không phải member |
| 404 | Project không tồn tại | — |

---

### 3.4 GET /api/v1/documents/{document_id}/versions

**Mô tả:** Toàn bộ version history của 1 document. Gọi khi user expand row trong S3. Lazy load — không gọi khi load S3 lần đầu.

**Auth:** Bearer (phải là member của project chứa document)  
**Rate limit:** 120 lần / phút / user  
**Idempotent:** Có

#### Request

```
GET /api/v1/documents/doc-uuid-001/versions
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "document_id": "doc-uuid-001",
  "screen_name": "Login",
  "doc_type": "basic_design",
  "versions": [
    {
      "id": "ver-uuid-003",
      "version_no": 3,
      "status": "approved",
      "r2_url": "https://r2.qcmaster.dev/project/.../v3/original.pdf",
      "changelog_md": "## Changelog v3\n### Thêm mới\n- OAuth Google login",
      "created_at": "2025-06-08T10:00:00Z",
      "created_by": {
        "id": "uuid-pm",
        "full_name": "Nguyen PM",
        "avatar_url": null
      },
      "approved_by": {
        "id": "uuid-owner",
        "full_name": "Admin User"
      },
      "approved_at": "2025-06-08T14:00:00Z",
      "chunk_count": 12,
      "is_latest": true
    },
    {
      "id": "ver-uuid-002",
      "version_no": 2,
      "status": "approved",
      "r2_url": "https://r2.qcmaster.dev/project/.../v2/original.pdf",
      "changelog_md": "## Changelog v2\n### Sửa đổi\n- Đổi màu button lỗi từ đỏ sang xanh",
      "created_at": "2025-06-01T09:00:00Z",
      "created_by": {
        "id": "uuid-pm",
        "full_name": "Nguyen PM",
        "avatar_url": null
      },
      "approved_by": {
        "id": "uuid-owner",
        "full_name": "Admin User"
      },
      "approved_at": "2025-06-01T14:00:00Z",
      "chunk_count": 11,
      "is_latest": false
    },
    {
      "id": "ver-uuid-001",
      "version_no": 1,
      "status": "approved",
      "r2_url": "https://r2.qcmaster.dev/project/.../v1/original.pdf",
      "changelog_md": null,
      "created_at": "2025-05-15T08:00:00Z",
      "created_by": {
        "id": "uuid-admin",
        "full_name": "Admin User",
        "avatar_url": null
      },
      "approved_by": {
        "id": "uuid-admin",
        "full_name": "Admin User"
      },
      "approved_at": "2025-05-15T10:00:00Z",
      "chunk_count": 10,
      "is_latest": false
    }
  ],
  "total_versions": 3
}
```

**Ghi chú field `r2_url`:** Đây là URL public nếu R2 bucket public, hoặc cần gọi `/download` để lấy presigned URL nếu bucket private. Recommend dùng presigned URL ở môi trường production.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | Không phải member của project chứa document |
| 404 | Document không tồn tại | — |

---

### 3.5 GET /api/v1/documents/{document_id}/versions/{version_id}/download

**Mô tả:** Tạo presigned URL để download file gốc từ R2. URL có hiệu lực trong 15 phút.

**Auth:** Bearer (phải là member của project)  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Có (mỗi lần tạo URL mới nhưng không thay đổi data)

#### Request

```
GET /api/v1/documents/doc-uuid-001/versions/ver-uuid-003/download
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "download_url": "https://r2.cloudflare.com/bucket/key?X-Amz-Signature=...&Expires=1717920000",
  "filename": "Login_BasicDesign_v3.pdf",
  "content_type": "application/pdf",
  "expires_in": 900
}
```

**FE xử lý:** Dùng URL này để `window.open(download_url)` hoặc tạo `<a href download>` để browser tự download.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | — |
| 404 | Version không tồn tại | — |
| 500 | Lỗi tạo presigned URL | R2 không phản hồi |

---

### 3.6 PATCH /api/v1/documents/{document_id}

**Mô tả:** Cập nhật thông tin metadata của document. Hiện tại chỉ cho phép sửa `screen_name` và `description`. Không thể đổi `doc_type`.

**Auth:** Bearer (project owner hoặc system admin)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Có

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `screen_name` | string | Không | Tên màn hình mới, 1–100 ký tự |
| `description` | string | Không | Mô tả mới, tối đa 500 ký tự |

```json
{
  "screen_name": "Login v2",
  "description": "Basic design màn hình đăng nhập phiên bản mới"
}
```

#### Response 200

```json
{
  "id": "doc-uuid-001",
  "screen_name": "Login v2",
  "doc_type": "basic_design",
  "description": "Basic design màn hình đăng nhập phiên bản mới",
  "updated_at": "2025-06-10T10:00:00Z"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Không có field nào để cập nhật | Body rỗng |
| 403 | Không có quyền | Không phải owner/admin |
| 404 | Document không tồn tại | — |
| 409 | Tên màn hình đã tồn tại với loại tài liệu này | Trùng `UNIQUE(project_id, screen_name, doc_type)` |
| 422 | Dữ liệu không hợp lệ | Tên quá dài, v.v. |

---

### 3.7 DELETE /api/v1/documents/{document_id}

**Mô tả:** Xoá tài liệu và toàn bộ version, chunk, embedding liên quan. Cascade xoá file trên R2. Testcase đã link sẽ bị unlink (không xoá testcase). Không thể hoàn tác.

**Auth:** Bearer (project owner hoặc system admin)  
**Rate limit:** 10 lần / phút / user  
**Idempotent:** Có

#### Request

```
DELETE /api/v1/documents/doc-uuid-001
Authorization: Bearer eyJ...
```

**Cascade xoá (theo thứ tự):**
1. `testcase_chunk_links` WHERE `chunk_id` IN chunks của document
2. `chunk_embeddings` WHERE `chunk_id` IN chunks của document
3. `chunks` WHERE `doc_version_id` IN versions của document
4. `diff_changes` liên quan
5. `diff_reviews` liên quan
6. `doc_versions` của document
7. `document` record
8. Celery task: xoá file trên R2 (async, không block response)
9. Celery task: cập nhật vector index (xoá orphan vectors)

#### Response 200

```json
{
  "message": "Đã xoá tài liệu và 3 version liên quan",
  "document_id": "doc-uuid-001",
  "deleted_versions": 3,
  "deleted_chunks": 36,
  "unlinked_testcases": 5
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền xoá tài liệu | Không phải owner/admin |
| 404 | Document không tồn tại | — |

#### Error body mẫu

```json
{
  "error": "FORBIDDEN",
  "message": "Không có quyền xoá tài liệu. Chỉ Owner và Admin mới có thể xoá.",
  "status_code": 403
}
```

---

## 4. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S3 load lần đầu | `GET /documents` + `GET /screens` | Gọi song song |
| S3 filter thay đổi | `GET /documents?doc_type=X&screen=Y` | Client-side nếu ≤ 100 docs |
| S3 polling processing | `GET /documents` mỗi 5s | Chỉ khi `has_processing=true` |
| S3 expand row | `GET /documents/{id}/versions` | Lazy load |
| S3 download version | `GET /versions/{id}/download` | Presigned URL |
| S3 menu Sửa | `PATCH /documents/{id}` | Owner/Admin |
| S3 menu Xoá | `DELETE /documents/{id}` | Owner/Admin |
| S3 nút Upload | Dẫn đến S4 | Routing |
| S3 click tên | Dẫn đến S5 | Routing |
| S3 nút So sánh | Dẫn đến S7 | Routing |
| S3 nút Hỏi AI | Dẫn đến S9 | Routing + scope param |

---

## 5. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S2 Project list | Màn hình trước — click project card vào S3 |
| Basic Design — S4 Upload form | Upload tài liệu mới / version mới |
| Basic Design — S5 Version detail | Click tên tài liệu hoặc version trong expand |
| Basic Design — S7 Diff viewer | Nút So sánh version |
| Basic Design — S9 Q&A chat | Nút Hỏi AI |
| Database schema — `documents` | `screen_name`, `doc_type` |
| Database schema — `doc_versions` | `version_no`, `status`, `r2_key` |
| Flow Upload & Embedding | Celery pipeline sau khi upload |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
