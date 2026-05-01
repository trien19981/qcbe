# S2 Project list — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Màn hình Project list  
**Màn hình:** S2 Project list  
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

Màn hình dashboard tổng sau khi đăng nhập. Hiển thị toàn bộ project mà người dùng được phân quyền tham gia. Là điểm xuất phát chính cho mọi luồng làm việc trong hệ thống.

**Vai trò truy cập:** Admin, PM, QC, Dev  
**Màn hình trước:** S1 Login (redirect sau đăng nhập thành công)  
**Màn hình sau:** S3 Document list (click vào project card)

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────┐
│ HEADER                                                           │
│ [Logo QC Master]          [Q&A Chat]  [Tên user ▾] [Role badge] │
├─────────────┬────────────────────────────────────────────────────┤
│ SIDEBAR     │ MAIN CONTENT                                       │
│             │                                                    │
│ ● Projects  │  Projects                    [+ Tạo project]      │
│   Q&A Chat  │  ┌──────────────────────────────────────────────┐ │
│   Cài đặt   │  │ [Search...                              🔍 ] │ │
│   (admin)   │  └──────────────────────────────────────────────┘ │
│             │                                                    │
│             │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│             │  │ Card     │ │ Card     │ │ Card     │          │
│             │  │ Project  │ │ Project  │ │ Project  │          │
│             │  │ A        │ │ B        │ │ C        │          │
│             │  └──────────┘ └──────────┘ └──────────┘          │
│             │                                                    │
│             │  ┌──────────┐ ┌──────────┐                        │
│             │  │ Card     │ │ Card     │                        │
│             │  └──────────┘ └──────────┘                        │
└─────────────┴────────────────────────────────────────────────────┘
```

---

### 1.3 Chi tiết từng vùng

#### Header (sticky top)

| Element | Mô tả | Ghi chú |
|---|---|---|
| Logo + tên | "QC Master" bên trái | Click → reload S2 |
| Nút Q&A Chat | Icon + text, giữa-phải | Shortcut mở S9 |
| Avatar | Ảnh hoặc initials circle 32px | Góc phải |
| Tên user | Tên đầy đủ, 14px | Cạnh avatar |
| Role badge | "Admin" / "PM" / "QC" / "Dev" | Màu theo role |
| Dropdown avatar | Click avatar → menu: Profile, Đăng xuất | — |

**Role badge màu:**
- Admin → đỏ (danger)
- PM → xanh dương (info)
- QC → xanh lá (success)
- Dev → vàng (warning)

#### Sidebar (fixed left, 220px)

| Item | Icon | Hiển thị với role |
|---|---|---|
| Projects | 📁 | Tất cả (active trên S2) |
| Q&A Chat | 💬 | Tất cả |
| Cài đặt | ⚙️ | Admin only |

Active state: background info nhạt, text info, border trái 2px info.

#### Main content

| Element | Mô tả |
|---|---|
| Page title | "Projects", 22px font-weight 500 |
| Nút "+ Tạo project" | Góc phải, primary, chỉ Admin |
| Search bar | Full width dưới title, placeholder "Tìm kiếm project..." |
| Project grid | 3 cột auto-fit, gap 16px, responsive |
| Empty state | Minh họa + "Chưa có project nào" khi list rỗng |

---

### 1.4 Project Card

```
┌────────────────────────────────────┐
│ [Active]                     [···] │  ← status badge + menu
│                                    │
│ Tên Project A                      │  ← tên, 15px font-weight 500
│ Mô tả ngắn của dự án tối đa       │  ← 2 dòng, text-secondary
│ 2 dòng rồi ellipsis...            │
│                                    │
│ ┌────────┐ ┌───────────┐          │
│ │ 12 docs│ │ 84 TC     │          │  ← stats
│ └────────┘ └───────────┘          │
│                                    │
│ Cập nhật: 2 ngày trước    [Chat →]│  ← footer
└────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Status badge | "Active" (xanh lá) / "Archived" (xám) — góc trái trên |
| Menu "···" | Dropdown: Xem, Sửa (Admin/PM), Archive (Admin) |
| Tên project | 15px, font-weight 500, tối đa 1 dòng + ellipsis |
| Mô tả | 13px, text-secondary, tối đa 2 dòng + ellipsis |
| Stat docs | Số tài liệu, icon file |
| Stat TC | Số testcase, icon check |
| Footer | Ngày cập nhật cuối + nút "Chat →" mở S9 |
| Hover | Border đậm hơn, cursor pointer |
| Click card | → S3 Document list của project đó |

---

### 1.5 Empty States

| Tình huống | Hiển thị |
|---|---|
| Chưa có project nào | Illustration + "Chưa có project nào" + nút "Tạo project đầu tiên" (Admin) |
| Search không có kết quả | "Không tìm thấy project nào với từ khóa '{keyword}'" + nút "Xoá tìm kiếm" |
| Đang tải | Skeleton loader: 6 card placeholder với shimmer animation |

---

### 1.6 Modal tạo project mới (Admin only)

```
┌──────────────────────────────────────┐
│ Tạo project mới                   X  │
├──────────────────────────────────────┤
│ Tên project *                        │
│ [________________________________]   │
│                                      │
│ Slug (URL) *                         │
│ [________________________________]   │
│ Auto-generate từ tên, có thể sửa    │
│                                      │
│ Mô tả                                │
│ [________________________________]   │
│ [________________________________]   │
│                                      │
│             [Huỷ]  [Tạo project]     │
└──────────────────────────────────────┘
```

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Bước 1 — Load màn hình S2

```
Vào S2 (sau login hoặc navigate)
    │
    ├─ Gọi GET /api/v1/auth/me → populate header (tên, role, avatar)
    │       └─ 401 → gọi POST /refresh → retry
    │               └─ /refresh 401 → redirect S1 Login
    │
    ├─ Gọi GET /api/v1/projects → load project list
    │       └─ Lọc theo role: user chỉ thấy project mình là member
    │
    └─ Render grid theo response
```

#### Bước 2 — Tìm kiếm project

```
User gõ vào search bar
    │
    ├─ Debounce 300ms
    │
    ├─ Filter client-side (nếu < 50 projects đã load)
    │       └─ Match theo: tên project, mô tả
    │
    └─ Kết quả hiện realtime, không cần submit
```

**Quyết định:** Search client-side (filter trên data đã fetch) thay vì gọi API riêng, trừ khi user có > 50 projects → sẽ thêm `?search=` query param ở v2.

#### Bước 3 — Tạo project mới (Admin)

```
Click "+ Tạo project"
    │
    └─ Mở modal
            │
            ├─ User nhập tên → slug auto-generate (lowercase, dấu cách → gạch ngang)
            │
            ├─ Validate → POST /api/v1/projects
            │
            ├─ Success → đóng modal → thêm card mới vào grid (optimistic update)
            │
            └─ Error → hiện lỗi inline trong modal
```

#### Bước 4 — Navigate vào project

```
Click card project (bất kỳ vùng nào trừ menu "···")
    │
    └─ Navigate → S3 Document list
                  URL: /projects/{project_slug}/documents
```

---

### 2.2 Validation Rules

#### VL-S2-001 — Tên project bắt buộc
- **Field:** Input tên project (modal)
- **Trigger:** onSubmit
- **Rule:** Không rỗng, tối thiểu 3 ký tự, tối đa 100 ký tự
- **Error message:** "Tên project phải từ 3 đến 100 ký tự"
- **Scope:** Client + Server

#### VL-S2-002 — Slug unique
- **Field:** Input slug (modal)
- **Trigger:** onSubmit (server check)
- **Rule:** Chỉ gồm `a-z`, `0-9`, `-`. Unique trong toàn hệ thống.
- **Error message:** "Slug này đã được sử dụng. Vui lòng chọn slug khác."
- **Scope:** Server only
- **Ghi chú:** Client auto-generate từ tên nhưng user có thể sửa thủ công.

#### VL-S2-003 — Slug format
- **Field:** Input slug (modal)
- **Trigger:** onChange + onSubmit
- **Rule:** `/^[a-z0-9-]+$/`, không bắt đầu hoặc kết thúc bằng `-`
- **Error message:** "Slug chỉ được chứa chữ thường, số và dấu gạch ngang"
- **Scope:** Client + Server

#### VL-S2-004 — Mô tả tối đa
- **Field:** Textarea mô tả (modal)
- **Trigger:** onChange
- **Rule:** Tối đa 500 ký tự
- **Error message:** Hiện counter "480/500" khi gần đạt giới hạn, đỏ khi vượt
- **Scope:** Client + Server

---

### 2.3 Phân quyền chi tiết

| Action | Admin | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Xem danh sách project (của mình) | ✓ | ✓ | ✓ | ✓ |
| Click vào project → S3 | ✓ | ✓ | ✓ | ✓ |
| Tạo project mới | ✓ | — | — | — |
| Sửa thông tin project | ✓ | — | — | — |
| Archive project | ✓ | — | — | — |
| Xem project archived | ✓ | — | — | — |
| Mở Q&A Chat | ✓ | ✓ | ✓ | ✓ |

**Ghi chú:** PM, QC, Dev chỉ thấy project mà họ đã được thêm vào qua `project_members`. Admin thấy tất cả project trong hệ thống.

---

### 2.4 Auto-generate slug

```python
# Logic auto-generate slug từ tên project
def generate_slug(name: str) -> str:
    import re, unicodedata
    # Normalize unicode (tiếng Việt → ASCII)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    # Lowercase + replace khoảng trắng/ký tự đặc biệt bằng '-'
    name = re.sub(r'[^\w\s-]', '', name.lower())
    name = re.sub(r'[\s_-]+', '-', name)
    name = name.strip('-')
    return name

# Ví dụ:
# "Project Quản Lý Tài Liệu" → "project-quan-ly-tai-lieu"
# "E-Commerce 2025"          → "e-commerce-2025"
```

---

### 2.5 Trạng thái loading và error

| Tình huống | UI xử lý |
|---|---|
| Đang fetch project list | Skeleton 6 card, shimmer animation |
| Fetch thất bại (network) | Toast đỏ "Không thể tải danh sách project. Thử lại?" + nút Retry |
| Tạo project đang xử lý | Button modal disabled + spinner |
| Tạo project thất bại | Lỗi inline trong modal, không đóng modal |
| Tạo project thành công | Modal đóng + card mới xuất hiện đầu grid + toast "Tạo project thành công" |

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/projects` | Lấy danh sách project | Bearer |
| POST | `/api/v1/projects` | Tạo project mới | Bearer (Admin) |
| GET | `/api/v1/projects/{project_id}` | Lấy chi tiết 1 project | Bearer |
| PATCH | `/api/v1/projects/{project_id}` | Cập nhật thông tin project | Bearer (Admin) |
| PATCH | `/api/v1/projects/{project_id}/archive` | Archive project | Bearer (Admin) |

---

### 3.2 GET /api/v1/projects

**Mô tả:** Lấy danh sách project mà user hiện tại có quyền truy cập. Admin thấy tất cả, các role khác chỉ thấy project mình là member.

**Auth:** Bearer access_token  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Query parameters

| Param | Type | Bắt buộc | Mô tả | Mặc định |
|---|---|---|---|---|
| `status` | string | Không | `active` \| `archived` \| `all` | `active` |
| `search` | string | Không | Tìm theo tên project | — |
| `page` | int | Không | Trang hiện tại | `1` |
| `per_page` | int | Không | Số item mỗi trang, max 100 | `50` |

#### Request

```
GET /api/v1/projects?status=active&page=1&per_page=50
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Project Demo",
      "slug": "project-demo",
      "description": "Dự án mẫu để test hệ thống QC Master",
      "status": "active",
      "stats": {
        "document_count": 12,
        "testcase_count": 84
      },
      "my_role": "qc",
      "created_at": "2025-01-15T08:00:00Z",
      "updated_at": "2025-06-08T14:30:00Z",
      "created_by": {
        "id": "uuid",
        "full_name": "Admin User"
      }
    }
  ],
  "pagination": {
    "total": 5,
    "page": 1,
    "per_page": 50,
    "total_pages": 1
  }
}
```

**Ghi chú field `my_role`:** Role của user hiện tại trong project đó. Dùng để FE hiển thị đúng action trong menu card.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | access_token hết hạn hoặc không hợp lệ |
| 422 | Tham số không hợp lệ | `status` không phải `active`/`archived`/`all` |

---

### 3.3 POST /api/v1/projects

**Mô tả:** Tạo project mới. Chỉ Admin được phép. Người tạo tự động được thêm vào `project_members` với role `owner`.

**Auth:** Bearer access_token (role = admin)  
**Rate limit:** 10 lần / phút / user  
**Idempotent:** Không

#### Request headers

| Header | Bắt buộc | Giá trị |
|---|---|---|
| `Authorization` | Có | `Bearer {access_token}` |
| `Content-Type` | Có | `application/json` |

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `name` | string | Có | Tên project, 3–100 ký tự |
| `slug` | string | Có | URL slug, chỉ `a-z0-9-`, unique |
| `description` | string | Không | Mô tả, tối đa 500 ký tự |

```json
{
  "name": "Project E-Commerce 2025",
  "slug": "e-commerce-2025",
  "description": "Dự án thương mại điện tử phiên bản 2025"
}
```

#### Response 201

```json
{
  "id": "661f9511-f30b-52e5-b827-557766551111",
  "name": "Project E-Commerce 2025",
  "slug": "e-commerce-2025",
  "description": "Dự án thương mại điện tử phiên bản 2025",
  "status": "active",
  "stats": {
    "document_count": 0,
    "testcase_count": 0
  },
  "my_role": "owner",
  "created_at": "2025-06-10T09:00:00Z",
  "updated_at": "2025-06-10T09:00:00Z",
  "created_by": {
    "id": "uuid-admin",
    "full_name": "Admin User"
  }
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | `name` hoặc `slug` không có |
| 403 | Không có quyền tạo project | Role không phải admin |
| 409 | Slug đã tồn tại | `slug` trùng với project khác |
| 422 | Dữ liệu không hợp lệ | Sai format slug, tên quá ngắn/dài, v.v. |

#### Error response body mẫu

```json
{
  "error": "CONFLICT",
  "message": "Slug 'e-commerce-2025' đã được sử dụng. Vui lòng chọn slug khác.",
  "status_code": 409,
  "field": "slug"
}
```

---

### 3.4 GET /api/v1/projects/{project_id}

**Mô tả:** Lấy chi tiết 1 project. Dùng khi cần thông tin đầy đủ hơn list (ví dụ: danh sách member).

**Auth:** Bearer access_token (phải là member của project)  
**Rate limit:** 120 lần / phút / user  
**Idempotent:** Có

#### Request

```
GET /api/v1/projects/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Project Demo",
  "slug": "project-demo",
  "description": "Dự án mẫu để test hệ thống QC Master",
  "status": "active",
  "stats": {
    "document_count": 12,
    "testcase_count": 84,
    "member_count": 5
  },
  "my_role": "qc",
  "members": [
    {
      "user_id": "uuid",
      "full_name": "Admin User",
      "email": "admin@qcmaster.dev",
      "role": "owner",
      "avatar_url": null,
      "joined_at": "2025-01-15T08:00:00Z"
    }
  ],
  "created_at": "2025-01-15T08:00:00Z",
  "updated_at": "2025-06-08T14:30:00Z",
  "created_by": {
    "id": "uuid",
    "full_name": "Admin User"
  }
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền truy cập project này | Không phải member |
| 404 | Project không tồn tại | `project_id` sai hoặc đã bị xoá |

---

### 3.5 PATCH /api/v1/projects/{project_id}

**Mô tả:** Cập nhật thông tin project. Chỉ Admin. Slug không thể thay đổi sau khi tạo (để tránh broken URL).

**Auth:** Bearer access_token (role = admin)  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Có (PATCH idempotent nếu cùng data)

#### Request body (tất cả field optional)

| Field | Type | Mô tả |
|---|---|---|
| `name` | string | Tên mới, 3–100 ký tự |
| `description` | string | Mô tả mới, tối đa 500 ký tự |

```json
{
  "name": "Project E-Commerce 2025 v2",
  "description": "Cập nhật mô tả mới"
}
```

#### Response 200

Trả về object project đã cập nhật (cùng format với GET `/projects/{id}`).

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Không có field nào để cập nhật | Body rỗng hoặc chỉ có field không hợp lệ |
| 403 | Không có quyền | Role không phải admin |
| 404 | Project không tồn tại | — |
| 422 | Dữ liệu không hợp lệ | Tên quá ngắn/dài, v.v. |

---

### 3.6 PATCH /api/v1/projects/{project_id}/archive

**Mô tả:** Archive hoặc unarchive project. Project archived vẫn còn dữ liệu, chỉ ẩn khỏi danh sách mặc định. Chỉ Admin.

**Auth:** Bearer access_token (role = admin)  
**Rate limit:** 10 lần / phút / user  
**Idempotent:** Có

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `status` | string | Có | `archived` \| `active` |

```json
{
  "status": "archived"
}
```

#### Response 200

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "archived",
  "message": "Project đã được archive thành công"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | `status` không hợp lệ | Chỉ chấp nhận `active` hoặc `archived` |
| 403 | Không có quyền | Role không phải admin |
| 404 | Project không tồn tại | — |
| 409 | Project đã ở trạng thái này | Cố archive project đã archived |

---

## 4. Màn hình và component sử dụng

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S2 Project list (load) | `GET /projects` | Load ngay khi vào màn |
| S2 Header | `GET /auth/me` | Tên, role, avatar |
| S2 Modal tạo project | `POST /projects` | Admin only |
| S2 Menu "···" → Sửa | `PATCH /projects/{id}` | Admin only |
| S2 Menu "···" → Archive | `PATCH /projects/{id}/archive` | Admin only |
| S2 Click card → S3 | `GET /projects/{id}` | Lấy detail trước khi vào S3 |
| Header avatar → Đăng xuất | `POST /auth/logout` | Tất cả màn |

---

## 5. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S1 Login | Màn hình trước — redirect đến S2 sau login |
| Basic Design — S3 Document list | Màn hình sau — click project card |
| Basic Design — S9 Q&A chat | Shortcut từ header và card |
| Database schema — `projects` table | `name`, `slug`, `status`, `created_by` |
| Database schema — `project_members` | Phân quyền member trong project |
| API Design — S1 Login | `GET /auth/me` dùng chung |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*