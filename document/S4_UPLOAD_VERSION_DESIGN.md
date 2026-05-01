# S4 Upload & Version — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Upload tài liệu & tạo version  
**Màn hình:** S4 Upload form (modal overlay)  
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

Chức năng upload tài liệu mới hoặc tạo version mới cho tài liệu đã có. Hiển thị dưới dạng **modal overlay** mở từ S3 Document list. Sau khi submit thành công, modal đóng, S3 cập nhật row tương ứng sang status `processing`, và Celery pipeline bắt đầu chunk + embed nền.

**2 entry point:**
- **Tạo document mới:** Nút "+ Upload tài liệu" trên toolbar S3 — screen_name và doc_type chưa có, user phải chọn
- **Upload version mới:** Nút "↑" trên row trong S3 — screen_name và doc_type đã có sẵn (readonly)

**Vai trò truy cập:** Owner, PM (Admin)  
**Màn hình trước:** S3 Document list  
**Màn hình sau:** S3 Document list (quay lại sau upload)

---

### 1.2 Layout — Modal overlay

```
┌─────────────────────────────────────────────────────────────────┐
│ [Overlay mờ rgba(0,0,0,0.4) — click KHÔNG đóng khi đang upload]│
│                                                                 │
│           ┌─────────────────────────────────────┐              │
│           │ Upload tài liệu mới              X  │ ← header     │
│           ├─────────────────────────────────────┤              │
│           │                                     │              │
│           │ Màn hình *                          │              │
│           │ [Login                          ▾]  │              │
│           │                                     │              │
│           │ Loại tài liệu *                     │              │
│           │ [Basic Design                   ▾]  │              │
│           │                                     │              │
│           │ File *                              │              │
│           │ ┌─────────────────────────────────┐ │              │
│           │ │                                 │ │              │
│           │ │   ↑  Kéo thả hoặc click        │ │              │
│           │ │      để chọn file               │ │              │
│           │ │   PDF · DOCX · MD · Excel       │ │              │
│           │ │   Tối đa 50MB                   │ │              │
│           │ │                                 │ │              │
│           │ └─────────────────────────────────┘ │              │
│           │                                     │              │
│           │ Ghi chú thay đổi (changelog)        │              │
│           │ [Mô tả thay đổi so với version  ]   │              │
│           │ [trước...                        ]   │              │
│           │ [Xem mẫu changelog]                 │              │
│           │                                     │              │
│           │         [Huỷ]  [Upload tài liệu]    │              │
│           └─────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

- **Modal width:** 560px
- **Modal max-height:** 90vh, nội dung scroll bên trong
- **Overlay:** Click overlay KHÔNG đóng modal (tránh mất dữ liệu đang nhập)
- **Đóng:** Chỉ đóng bằng nút X hoặc nút Huỷ (confirm nếu đã nhập data)

---

### 1.3 UI Elements chi tiết

#### Header modal

| Element | Mô tả |
|---|---|
| Title | "Upload tài liệu mới" hoặc "Upload version mới — [Tên màn hình]" |
| Nút X | Đóng modal — nếu đã nhập data thì confirm "Huỷ upload? Dữ liệu sẽ bị mất" |

#### Field: Màn hình (screen_name)

```
Màn hình *
[Login                                    ▾]
 └─ [+ Tạo màn hình mới...]
```

| Trường hợp | Xử lý |
|---|---|
| Tạo document mới | Dropdown chọn màn hình đã có, hoặc nhập tên mới |
| Upload version mới | Hiện tên màn hình readonly, không thể thay đổi |

Dropdown gợi ý danh sách màn hình từ `GET /projects/{id}/documents/screens`. Nếu gõ tên không có trong list → tạo mới.

#### Field: Loại tài liệu (doc_type)

```
Loại tài liệu *
[Basic Design                             ▾]
  ├─ Basic Design
  ├─ API Design
  ├─ Detail Design
  ├─ Testcase Manual
  └─ Figma (sync tự động — disabled)
```

| Trường hợp | Xử lý |
|---|---|
| Tạo document mới | Dropdown chọn đầy đủ (trừ Figma — sync qua MCP) |
| Upload version mới | Hiện loại tài liệu readonly, không thể thay đổi |

**Lý do Figma disabled:** Figma không upload file — sync tự động qua Figma MCP. User không upload Figma thủ công.

#### Field: File upload (dropzone)

```
┌──────────────────────────────────────────────┐
│                    [Icon upload]             │
│         Kéo thả hoặc click để chọn file     │
│                                              │
│    PDF · DOCX · MD · TXT · XLSX             │
│              Tối đa 50MB                     │
└──────────────────────────────────────────────┘
```

**Sau khi chọn file:**

```
┌──────────────────────────────────────────────┐
│  [Icon PDF]  Login_BasicDesign_v3.pdf        │
│              2.4 MB                    [X]   │
└──────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Dropzone | Vùng drag-and-drop, viền đứt nét border-secondary |
| Hover/drag over | Viền đổi sang info, nền info nhạt |
| File đã chọn | Hiện icon loại file + tên + dung lượng + nút X xoá |
| Validate ngay | Kiểm tra loại file và dung lượng ngay khi chọn |
| Multiple files | Không cho phép — chỉ 1 file / lần upload |

**File types được chấp nhận:**

| Extension | MIME type | Dùng cho |
|---|---|---|
| `.pdf` | `application/pdf` | Basic Design, Detail Design |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Basic Design, Detail Design |
| `.md` | `text/markdown` | API Design, Detail Design |
| `.txt` | `text/plain` | Testcase Manual |
| `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Testcase Manual |

#### Field: Changelog (textarea)

```
Ghi chú thay đổi
┌────────────────────────────────────────────┐
│ Mô tả thay đổi so với version trước...    │
│                                            │
│                                            │
└────────────────────────────────────────────┘
[Xem mẫu changelog]           0 / 2000 ký tự
```

| Element | Mô tả |
|---|---|
| Textarea | 4 dòng min-height, resize dọc được |
| Placeholder | "Mô tả thay đổi so với version trước..." |
| Counter | "0 / 2000 ký tự" — đỏ khi vượt 2000 |
| Link mẫu | "Xem mẫu changelog" → mở popover hiện template markdown |
| Bắt buộc | Không — optional cho version 1, khuyến khích từ version 2 trở đi |

**Popover mẫu changelog:**

```markdown
## Changelog v[N]

### Thêm mới
- [Mô tả thêm mới]

### Chỉnh sửa
- [Mô tả chỉnh sửa]

### Xoá bỏ
- [Mô tả xoá bỏ]
```

#### Footer modal

| Element | Mô tả |
|---|---|
| Nút "Huỷ" | Secondary, đóng modal (confirm nếu đã nhập data) |
| Nút "Upload tài liệu" | Primary, submit form |

---

### 1.4 States của modal

#### State: Default (tạo document mới)

- Tất cả field trống
- Dropzone hiện idle
- Button "Upload" enabled nhưng validate khi submit

#### State: Đã chọn file — ready to submit

```
┌─────────────────────────────────────────────┐
│ Upload tài liệu mới                      X  │
├─────────────────────────────────────────────┤
│ Màn hình *                                  │
│ [Login                                  ▾]  │
│                                             │
│ Loại tài liệu *                             │
│ [Basic Design                           ▾]  │
│                                             │
│ File *                                      │
│ ┌─────────────────────────────────────────┐ │
│ │ [PDF] Login_BasicDesign_v3.pdf    [X]   │ │
│ │       2.4 MB                            │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Ghi chú thay đổi                           │
│ [Thêm OAuth Google login...             ]   │
│                                             │
│              [Huỷ]  [Upload tài liệu]       │
└─────────────────────────────────────────────┘
```

#### State: Đang upload (submitting)

```
┌─────────────────────────────────────────────┐
│ Upload tài liệu mới                      —  │ ← X disabled
├─────────────────────────────────────────────┤
│ [Tất cả field disabled]                     │
│                                             │
│ ████████████████░░░░░░░  68%               │
│ Đang tải lên... (1.6 MB / 2.4 MB)          │
│                                             │
│         [Huỷ disabled]  [Đang tải lên...]  │
└─────────────────────────────────────────────┘
```

- Progress bar hiện % upload thực tế (từ axios onUploadProgress)
- Tất cả field và nút disabled
- Nút X disabled — không cho đóng khi đang upload

#### State: Upload xong — đang xử lý backend

```
│ ✓ File đã tải lên thành công               │
│                                             │
│ [Spinner] Đang tạo version và xử lý...     │
│ Bạn có thể đóng cửa sổ này,               │
│ hệ thống sẽ tiếp tục xử lý nền.           │
│                                             │
│                            [Đóng]          │
```

- File đã lên R2 + `doc_version` record đã tạo
- Celery job đang chạy nền (chunk + embed)
- User có thể đóng — S3 sẽ polling tự động

#### State: Thành công hoàn toàn (sau khi đóng modal)

- Modal đóng
- Toast xanh lá: "Upload thành công! Đang xử lý tài liệu..."
- S3: row cập nhật status → `processing` với spinner

#### State: Lỗi

```
│ ✗ Upload thất bại                           │
│ Lỗi: File vượt quá giới hạn 50MB           │
│                                             │
│         [Huỷ]  [Thử lại]                   │
```

---

### 1.5 Upload version mới — khác biệt so với tạo mới

Khi mở từ nút "↑" trên row trong S3:

```
┌─────────────────────────────────────────────┐
│ Upload version mới — Login / Basic Design X │
├─────────────────────────────────────────────┤
│ Màn hình          [Login]  (readonly)       │
│ Loại tài liệu     [Basic Design] (readonly) │
│ Version hiện tại  v3 (approved)             │
│ Version mới       v4 (sẽ tạo)              │
│                                             │
│ File *                                      │
│ [Dropzone]                                  │
│                                             │
│ Ghi chú thay đổi * (bắt buộc từ v2+)      │
│ [Mô tả thay đổi so với v3...]              │
│                                             │
│         [Huỷ]  [Upload version mới]        │
└─────────────────────────────────────────────┘
```

**Khác biệt chính:**
- Title modal thay đổi theo context
- `screen_name` và `doc_type` readonly
- Hiện "Version hiện tại" và "Version mới sẽ tạo"
- Changelog **bắt buộc** từ version 2 trở đi
- Sau upload → trigger so sánh Diff tự động với version trước

---

### 1.6 Confirm khi đóng modal có data

Khi user đã nhập data và click X hoặc Huỷ:

```
┌─────────────────────────────┐
│ Huỷ upload?                 │
│                             │
│ Dữ liệu bạn đã nhập        │
│ sẽ bị mất.                  │
│                             │
│ [Tiếp tục nhập]  [Huỷ upload]│
└─────────────────────────────┘
```

Điều kiện hiện confirm: bất kỳ field nào đã có giá trị (screen_name đã chọn, file đã chọn, changelog đã nhập).

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Luồng tạo document mới

```
PM click "+ Upload tài liệu" trên S3
    │
    └─ Mở modal (mode = "new_document")
            │
            ├─ User chọn screen_name (dropdown / nhập mới)
            ├─ User chọn doc_type
            ├─ User chọn file (validate ngay)
            ├─ User nhập changelog (optional)
            │
            └─ Click "Upload tài liệu"
                    │
                    ├─ Client validate tất cả field
                    │       └─ Fail → lỗi inline, không submit
                    │
                    └─ POST /api/v1/projects/{id}/documents/upload
                            │
                            ├─ Server tạo document record
                            ├─ Server tạo doc_version record (status=draft)
                            ├─ Upload file lên R2
                            ├─ Enqueue Celery job (chunk + embed)
                            │
                            ├─ Response 202 → hiện "đang xử lý" state
                            │
                            └─ User click Đóng
                                    └─ S3 row xuất hiện với status=processing
```

#### Luồng upload version mới

```
PM click "↑" trên row trong S3
    │
    └─ Mở modal (mode = "new_version", document_id đã có)
            │
            ├─ screen_name + doc_type readonly (từ document)
            ├─ User chọn file
            ├─ User nhập changelog (bắt buộc)
            │
            └─ Click "Upload version mới"
                    │
                    └─ POST /api/v1/documents/{id}/versions
                            │
                            ├─ Server tính version_no = current_max + 1
                            ├─ Tạo doc_version record (status=draft)
                            ├─ Upload file lên R2
                            ├─ Enqueue Celery job: chunk + embed
                            ├─ Enqueue Celery job: auto-diff với version trước
                            │
                            └─ Response 202
                                    └─ S3 row status = processing
                                    └─ Sau embed xong → status = ready_for_review
                                    └─ Notification cho PM/Owner: "Có version mới cần review"
```

#### Luồng Celery pipeline sau upload

```
Celery job: process_document_task(version_id)
    │
    ├─ Download file từ R2
    │
    ├─ Extract text (theo file type):
    │   ├─ PDF  → pymupdf
    │   ├─ DOCX → python-docx
    │   ├─ MD   → raw text
    │   ├─ TXT  → raw text
    │   └─ XLSX → openpyxl
    │
    ├─ Chunk theo strategy của doc_type:
    │   ├─ basic_design   → split theo heading H2/H3
    │   ├─ api_design     → split theo endpoint block
    │   ├─ detail_design  → split theo component/feature
    │   ├─ testcase_manual→ split theo testcase ID
    │   └─ figma          → không áp dụng (sync MCP)
    │
    ├─ Lưu chunks vào DB (chunks table)
    │
    ├─ Embed batch (Voyage AI voyage-3):
    │   └─ Batch size 64, retry 3 lần với exponential backoff
    │
    ├─ Lưu embeddings vào pgvector (chunk_embeddings)
    │
    └─ Update doc_version.status = "ready_for_review"
            └─ Push notification cho PM/Owner
```

---

### 2.2 Validation Rules

#### VL-S4-001 — Screen name bắt buộc
- **Field:** Dropdown screen_name
- **Trigger:** onSubmit
- **Rule:** Không rỗng
- **Error message:** "Vui lòng chọn hoặc nhập tên màn hình"
- **Scope:** Client + Server

#### VL-S4-002 — Screen name format
- **Field:** Dropdown screen_name (khi nhập mới)
- **Trigger:** onChange + onSubmit
- **Rule:** 1–100 ký tự, không chỉ khoảng trắng
- **Error message:** "Tên màn hình phải từ 1 đến 100 ký tự"
- **Scope:** Client + Server

#### VL-S4-003 — Doc type bắt buộc
- **Field:** Dropdown doc_type
- **Trigger:** onSubmit
- **Rule:** Phải chọn 1 trong: `basic_design`, `api_design`, `detail_design`, `testcase_manual`
- **Error message:** "Vui lòng chọn loại tài liệu"
- **Scope:** Client + Server

#### VL-S4-004 — Document không trùng
- **Field:** Dropdown screen_name + doc_type
- **Trigger:** onSubmit (server check)
- **Rule:** Khi tạo document mới: `UNIQUE(project_id, screen_name, doc_type)` chưa tồn tại
- **Error message:** "Tài liệu [doc_type] cho màn hình [screen_name] đã tồn tại. Hãy upload version mới thay thế."
- **Scope:** Server only

#### VL-S4-005 — File bắt buộc
- **Field:** Dropzone
- **Trigger:** onSubmit
- **Rule:** Phải có file được chọn
- **Error message:** "Vui lòng chọn file để upload"
- **Scope:** Client + Server

#### VL-S4-006 — File type hợp lệ
- **Field:** Dropzone
- **Trigger:** Ngay khi chọn file (onChange)
- **Rule:** MIME type phải thuộc: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `text/markdown`, `text/plain`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **Error message:** "Loại file không được hỗ trợ. Chấp nhận: PDF, DOCX, MD, TXT, XLSX"
- **Scope:** Client + Server (server validate lại MIME type thực sự)

#### VL-S4-007 — File size
- **Field:** Dropzone
- **Trigger:** Ngay khi chọn file (onChange)
- **Rule:** File size ≤ 50MB (52,428,800 bytes)
- **Error message:** "File vượt quá giới hạn 50MB. File của bạn: {X}MB"
- **Scope:** Client + Server

#### VL-S4-008 — Changelog bắt buộc từ version 2+
- **Field:** Textarea changelog
- **Trigger:** onSubmit
- **Rule:** Khi `version_no ≥ 2`: changelog không được rỗng, tối thiểu 10 ký tự
- **Error message:** "Vui lòng mô tả thay đổi so với version trước (tối thiểu 10 ký tự)"
- **Scope:** Client + Server

#### VL-S4-009 — Changelog max length
- **Field:** Textarea changelog
- **Trigger:** onChange
- **Rule:** Tối đa 2000 ký tự
- **Error message:** Counter đỏ "2050/2000" — button disabled khi vượt
- **Scope:** Client + Server

#### VL-S4-010 — Quyền upload
- **Field:** Form submit
- **Trigger:** onSubmit (server check)
- **Rule:** `project_members.role` IN (`owner`, `pm`)
- **Error message:** "Bạn không có quyền upload tài liệu cho project này"
- **Scope:** Server only (UI đã ẩn nút Upload với QC/Dev)

---

### 2.3 Upload progress tracking

FE dùng axios `onUploadProgress` callback để hiện progress bar:

```typescript
const formData = new FormData()
formData.append('file', file)
formData.append('screen_name', screenName)
formData.append('doc_type', docType)
formData.append('changelog_md', changelogMd)

const response = await api.post(
  `/projects/${projectId}/documents/upload`,
  formData,
  {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (progressEvent) => {
      const percent = Math.round(
        (progressEvent.loaded * 100) / (progressEvent.total ?? 1)
      )
      setUploadProgress(percent)
    },
  }
)
```

**Lưu ý:** Progress bar chỉ track việc upload file lên server (0→100%). Sau khi upload xong (100%), chuyển sang "đang xử lý" state — không có progress cho Celery job vì chạy nền.

---

### 2.4 Xử lý file duplicate name trên R2

R2 key được generate với UUID để tránh collision:

```python
import uuid

r2_key = (
    f"{project_id}/{document_id}"
    f"/v{version_no}/{uuid.uuid4().hex}_{sanitize_filename(original_filename)}"
)

# sanitize_filename: xoá ký tự đặc biệt, giữ extension
# Ví dụ: "Login Basic Design v3 (final).pdf"
#      → "Login_Basic_Design_v3_final.pdf"
```

---

### 2.5 Sau khi upload — notification flow

```
Celery job hoàn thành chunk + embed
    │
    ├─ Update doc_version.status = "ready_for_review"
    │
    └─ Tạo notification records cho:
            - Tất cả member có role owner/pm trong project
            - Type: "version_ready_for_review"
            - Message: "Version {N} của [doc_type] màn hình [screen] đã sẵn sàng để duyệt"
            - Link: /projects/{slug}/documents/{doc_id}/versions/{ver_id}

FE nhận notification:
    └─ Bell icon trên header hiện badge số
    └─ Nếu đang ở S3: row tự cập nhật qua polling
```

---

### 2.6 Conflict — document đã tồn tại

Khi PM upload tài liệu mới nhưng combination `(project_id, screen_name, doc_type)` đã tồn tại:

```
Server trả 409 CONFLICT với thông tin document đã tồn tại:
{
  "error": "DOCUMENT_EXISTS",
  "message": "Tài liệu Basic Design cho màn hình Login đã tồn tại (3 version).",
  "existing_document": {
    "id": "doc-uuid-001",
    "version_count": 3,
    "latest_version_no": 3,
    "latest_status": "approved"
  }
}

FE xử lý:
    └─ Hiện inline message trong modal:
       "Tài liệu này đã tồn tại với 3 version.
        Bạn muốn tạo version 4?"
       [Huỷ]  [Upload version mới]
       
       → Nếu chọn "Upload version mới": chuyển mode sang new_version
         với document_id từ response, giữ nguyên file và changelog đã nhập
```

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| POST | `/api/v1/projects/{project_id}/documents/upload` | Tạo document mới + upload file | Bearer (owner/pm) |
| POST | `/api/v1/documents/{document_id}/versions` | Upload version mới cho document đã có | Bearer (owner/pm) |
| GET | `/api/v1/documents/{document_id}/versions/{version_id}/status` | Poll trạng thái processing | Bearer (member) |
| DELETE | `/api/v1/documents/{document_id}/versions/{version_id}` | Xoá version (chỉ draft/rejected) | Bearer (owner) |

---

### 3.2 POST /api/v1/projects/{project_id}/documents/upload

**Mô tả:** Tạo document mới đồng thời tạo version 1 và upload file. Nếu `(project_id, screen_name, doc_type)` đã tồn tại → trả 409 với thông tin document cũ.

**Auth:** Bearer (project owner hoặc pm)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Không  
**Content-Type:** `multipart/form-data`

#### Request — multipart/form-data

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `screen_name` | string | Có | Tên màn hình, 1–100 ký tự |
| `doc_type` | string | Có | `basic_design` \| `api_design` \| `detail_design` \| `testcase_manual` |
| `file` | file | Có | File upload, max 50MB |
| `changelog_md` | string | Không | Ghi chú thay đổi (version 1 optional) |
| `description` | string | Không | Mô tả tài liệu, max 500 ký tự |

```
POST /api/v1/projects/550e8400/documents/upload
Authorization: Bearer eyJ...
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="screen_name"
Login

--boundary
Content-Disposition: form-data; name="doc_type"
basic_design

--boundary
Content-Disposition: form-data; name="file"; filename="Login_BD_v1.pdf"
Content-Type: application/pdf
[binary data]

--boundary
Content-Disposition: form-data; name="changelog_md"
Bản khởi tạo
--boundary--
```

#### Response 202 — Accepted

```json
{
  "document": {
    "id": "doc-uuid-001",
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "screen_name": "Login",
    "doc_type": "basic_design",
    "description": null
  },
  "version": {
    "id": "ver-uuid-001",
    "version_no": 1,
    "status": "processing",
    "r2_key": "550e8400/doc-uuid-001/v1/abc123_Login_BD_v1.pdf",
    "created_at": "2025-06-10T09:00:00Z"
  },
  "job_id": "celery-task-uuid",
  "message": "File đã được tải lên. Đang xử lý tài liệu..."
}
```

**Lý do 202 thay vì 201:** Xử lý chưa hoàn thành — file đã lên R2 nhưng Celery chưa chunk xong. FE dùng `job_id` hoặc polling để biết khi nào xong.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | screen_name, doc_type, hoặc file không có |
| 403 | Không có quyền upload | Không phải owner/pm |
| 404 | Project không tồn tại | — |
| 409 | Tài liệu đã tồn tại | Trả kèm `existing_document` object |
| 413 | File vượt quá 50MB | — |
| 415 | Loại file không hỗ trợ | MIME type không hợp lệ |
| 422 | Dữ liệu không hợp lệ | Tên màn hình quá dài, doc_type sai enum |

#### Response 409 body

```json
{
  "error": "DOCUMENT_EXISTS",
  "message": "Tài liệu Basic Design cho màn hình Login đã tồn tại.",
  "status_code": 409,
  "existing_document": {
    "id": "doc-uuid-001",
    "screen_name": "Login",
    "doc_type": "basic_design",
    "version_count": 3,
    "latest_version_no": 3,
    "latest_status": "approved"
  }
}
```

---

### 3.3 POST /api/v1/documents/{document_id}/versions

**Mô tả:** Upload version mới cho document đã tồn tại. Server tự tính `version_no = current_max + 1`. Enqueue Celery job chunk+embed và job auto-diff với version trước.

**Auth:** Bearer (project owner hoặc pm)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Không  
**Content-Type:** `multipart/form-data`

#### Request — multipart/form-data

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `file` | file | Có | File upload, max 50MB |
| `changelog_md` | string | Có (version ≥ 2) | Mô tả thay đổi, min 10 ký tự |

```
POST /api/v1/documents/doc-uuid-001/versions
Authorization: Bearer eyJ...
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="file"; filename="Login_BD_v4.pdf"
Content-Type: application/pdf
[binary data]

--boundary
Content-Disposition: form-data; name="changelog_md"
## Changelog v4

### Thêm mới
- Thêm nút "Đăng nhập bằng Google"

### Chỉnh sửa
- Đổi font placeholder từ 14px → 13px
--boundary--
```

#### Response 202

```json
{
  "document_id": "doc-uuid-001",
  "version": {
    "id": "ver-uuid-004",
    "version_no": 4,
    "status": "processing",
    "r2_key": "550e8400/doc-uuid-001/v4/def456_Login_BD_v4.pdf",
    "changelog_md": "## Changelog v4\n...",
    "created_at": "2025-06-10T10:00:00Z"
  },
  "previous_version": {
    "id": "ver-uuid-003",
    "version_no": 3,
    "status": "approved"
  },
  "diff_job_id": "celery-diff-task-uuid",
  "embed_job_id": "celery-embed-task-uuid",
  "message": "Version 4 đang được xử lý. Diff với version 3 sẽ sẵn sàng sau khi hoàn thành."
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu changelog | version ≥ 2 mà không có changelog |
| 400 | Changelog quá ngắn | Ít hơn 10 ký tự |
| 403 | Không có quyền | Không phải owner/pm |
| 404 | Document không tồn tại | — |
| 409 | Đang có version đang processing | Phải chờ version trước xong mới upload tiếp |
| 413 | File vượt quá 50MB | — |
| 415 | Loại file không hỗ trợ | — |

#### Response 409 — version đang processing

```json
{
  "error": "VERSION_PROCESSING",
  "message": "Version 3 đang được xử lý. Vui lòng chờ hoàn thành trước khi upload version mới.",
  "status_code": 409,
  "processing_version": {
    "id": "ver-uuid-003",
    "version_no": 3,
    "status": "processing"
  }
}
```

---

### 3.4 GET /api/v1/documents/{document_id}/versions/{version_id}/status

**Mô tả:** Lấy trạng thái xử lý của 1 version. Dùng để polling từ FE hoặc từ modal "đang xử lý". Nhẹ hơn gọi `GET /documents` toàn bộ.

**Auth:** Bearer (member của project)  
**Rate limit:** 120 lần / phút / user  
**Idempotent:** Có

#### Request

```
GET /api/v1/documents/doc-uuid-001/versions/ver-uuid-004/status
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "version_id": "ver-uuid-004",
  "version_no": 4,
  "status": "ready_for_review",
  "chunk_count": 14,
  "embed_progress": {
    "total_chunks": 14,
    "embedded_chunks": 14,
    "percentage": 100
  },
  "diff_ready": true,
  "diff_review_id": "diff-uuid-001",
  "updated_at": "2025-06-10T10:05:00Z"
}
```

**Ghi chú field `embed_progress`:** Chỉ có khi đang processing. Khi `status = approved/rejected` thì bỏ qua.

**Ghi chú field `diff_ready`:** `true` khi diff với version trước đã được tạo (Celery diff job xong). FE dùng để hiện nút "Xem diff" trong notification.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | — |
| 404 | Version không tồn tại | — |

---

### 3.5 DELETE /api/v1/documents/{document_id}/versions/{version_id}

**Mô tả:** Xoá một version cụ thể. Chỉ được xoá version ở trạng thái `draft` hoặc `rejected`. Không thể xoá version `approved` hoặc đang `processing`. Không thể xoá version 1 nếu là version duy nhất (xoá cả document luôn).

**Auth:** Bearer (project owner hoặc system admin)  
**Rate limit:** 10 lần / phút / user  
**Idempotent:** Có

#### Request

```
DELETE /api/v1/documents/doc-uuid-001/versions/ver-uuid-004
Authorization: Bearer eyJ...
```

**Cascade xoá:**
1. `diff_changes` liên quan đến version này
2. `diff_reviews` có `new_version_id` = version này
3. `testcase_chunk_links` liên quan đến chunks của version này
4. `chunk_embeddings` của chunks version này
5. `chunks` của version này
6. `doc_version` record
7. Celery task: xoá file R2 (async)

#### Response 200

```json
{
  "message": "Đã xoá version 4",
  "version_id": "ver-uuid-004",
  "deleted_chunks": 14,
  "document_id": "doc-uuid-001",
  "remaining_versions": 3
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền | Không phải owner/admin |
| 404 | Version không tồn tại | — |
| 409 | Không thể xoá version approved | Chỉ xoá draft hoặc rejected |
| 409 | Không thể xoá version đang xử lý | Status = processing |
| 409 | Không thể xoá version duy nhất | Dùng DELETE /documents/{id} để xoá cả document |

---

## 4. Backend implementation notes

### 4.1 Multipart upload handler (FastAPI)

```python
# app/routers/documents.py
from fastapi import APIRouter, UploadFile, File, Form, Depends
from app.core.deps import get_db, require_project_role

router = APIRouter()

@router.post("/projects/{project_id}/documents/upload", status_code=202)
async def upload_new_document(
    project_id: str,
    screen_name: str = Form(...),
    doc_type: str = Form(...),
    changelog_md: str = Form(""),
    description: str = Form(""),
    file: UploadFile = File(...),
    db=Depends(get_db),
    current_user=Depends(require_project_role("owner", "pm")),
):
    # 1. Validate
    validate_file(file)  # type + size
    validate_doc_type(doc_type)

    # 2. Check duplicate
    existing = await DocumentService(db).find(project_id, screen_name, doc_type)
    if existing:
        raise HTTPException(409, detail={
            "error": "DOCUMENT_EXISTS",
            "existing_document": existing.to_dict()
        })

    # 3. Read file content
    content = await file.read()

    # 4. Create document + version + upload R2
    svc = DocumentService(db)
    document, version = await svc.create_with_version(
        project_id=project_id,
        screen_name=screen_name,
        doc_type=doc_type,
        description=description,
        file_content=content,
        filename=file.filename,
        content_type=file.content_type,
        changelog_md=changelog_md,
        created_by=current_user.id,
    )

    # 5. Enqueue Celery
    job = process_document_task.delay(str(version.id))

    return {
        "document": document,
        "version": version,
        "job_id": job.id,
        "message": "File đã được tải lên. Đang xử lý tài liệu..."
    }
```

### 4.2 R2 upload helper

```python
# app/services/storage_service.py
import boto3, uuid
from app.core.config import settings

class StorageService:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT,
            aws_access_key_id=settings.R2_ACCESS_KEY,
            aws_secret_access_key=settings.R2_SECRET_KEY,
            region_name="auto",
        )

    def upload(self, project_id: str, doc_id: str,
               version_no: int, content: bytes,
               filename: str, content_type: str) -> str:
        safe_name = self._sanitize(filename)
        key = f"{project_id}/{doc_id}/v{version_no}/{uuid.uuid4().hex}_{safe_name}"
        self.client.put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return key

    def presigned_url(self, key: str, expires: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET, "Key": key},
            ExpiresIn=expires,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=settings.R2_BUCKET, Key=key)

    @staticmethod
    def _sanitize(filename: str) -> str:
        import re
        name = re.sub(r'[^\w\s\-.]', '', filename)
        name = re.sub(r'[\s]+', '_', name.strip())
        return name[:100]
```

---

## 5. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S3 nút "+ Upload tài liệu" | `POST /documents/upload` | Tạo document mới |
| S3 nút "↑ Upload version mới" | `POST /documents/{id}/versions` | Version mới |
| S4 Modal — polling status | `GET /versions/{id}/status` | Mỗi 3s sau khi upload |
| S3 polling table | `GET /documents` | Mỗi 5s khi có processing |
| S5 Version detail | `GET /versions/{id}/status` | Hiện embed progress |
| S5 Version detail — xoá draft | `DELETE /versions/{id}` | Owner only |

---

## 6. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S3 Document list | Màn hình trước — entry point vào S4 |
| Basic Design — S5 Version detail | Xem chi tiết sau upload |
| Basic Design — S7 Diff viewer | Auto-diff sau upload version mới |
| Flow Upload & Embedding | Celery pipeline chi tiết |
| Database schema — `doc_versions` | `version_no`, `status`, `r2_key` |
| Database schema — `chunks` + `chunk_embeddings` | Output của Celery pipeline |
| API Design — S3 Document list | `GET /documents/screens` dùng chung |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
