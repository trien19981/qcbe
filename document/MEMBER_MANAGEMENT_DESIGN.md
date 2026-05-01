# Quản lý member — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Quản lý thành viên project  
**Màn hình:** S-Member (slide-in panel trong S2 Project list)  
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

### 1.1 Mô tả chức năng

Cho phép Admin/Owner quản lý thành viên của từng project: mời thành viên mới qua email, thay đổi role, xoá thành viên, transfer ownership. PM/QC/Dev chỉ được xem danh sách thành viên, không thể chỉnh sửa.

Chức năng không có màn hình riêng — thiết kế dưới dạng **slide-in panel** width 380px, mở từ menu "···" của project card trong S2 Project list.

**Vai trò truy cập:**

| Action | Owner | Admin (system) | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|:---:|
| Xem danh sách member | ✓ | ✓ | ✓ | ✓ | ✓ |
| Xem pending invitations | ✓ | ✓ | — | — | — |
| Mời thành viên mới | ✓ | ✓ | — | — | — |
| Thay đổi role member | ✓ | ✓ | — | — | — |
| Xoá thành viên | ✓ | ✓ | — | — | — |
| Huỷ lời mời | ✓ | ✓ | — | — | — |
| Transfer ownership | ✓ | — | — | — | — |

**Màn hình trước:** S2 Project list (menu "···" → Quản lý thành viên)  
**Màn hình liên quan:** S3 Document list (header hiện số member)

---

### 1.2 Layout — Slide-in panel

```
┌─────────────────────────────────────────────────────────────┐
│ [Overlay mờ rgba(0,0,0,0.3) — click để đóng]               │
│                                          ┌─────────────────┐│
│                                          │ Thành viên    X ││  ← header sticky
│                                          │ Project Demo    ││
│                                          ├─────────────────┤│
│                                          │ [+ Mời thành    ││  ← chỉ Admin/Owner
│                                          │   viên        ] ││
│                                          ├─────────────────┤│
│                                          │ THÀNH VIÊN (4)  ││
│                                          │                 ││
│                                          │ [Av] Admin User ││
│                                          │  admin@...      ││
│                                          │  [Owner]    [·] ││
│                                          │                 ││
│                                          │ [Av] Nguyen PM  ││
│                                          │  pm@...         ││
│                                          │  [PM/BA ▾] [🗑] ││
│                                          │                 ││
│                                          │ [Av] Tran QC    ││
│                                          │  qc@...         ││
│                                          │  [QC   ▾] [🗑]  ││
│                                          │                 ││
│                                          │ CHỜ XÁC NHẬN(1)││
│                                          │                 ││
│                                          │ new@... | QC    ││
│                                          │ Hết hạn: 7 ngày ││
│                                          │          [Huỷ]  ││
│                                          └─────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

- **Width:** 380px, slide từ phải
- **Height:** 100vh, nội dung scroll
- **Header:** sticky top — tên project + nút X
- **Overlay:** click để đóng panel

---

### 1.3 UI Elements chi tiết

#### Form mời thành viên (Admin/Owner only)

```
┌──────────────────────────────────────────────┐
│ Mời thành viên mới                           │
│ [email@company.com      ] [QC/Tester ▾]      │
│ [suggestion: user@... ]                       │
│                           [  Gửi lời mời  ]  │
└──────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Input email | Placeholder "Nhập email thành viên", tự động suggest user trong hệ thống khi gõ ≥ 2 ký tự |
| Dropdown role | PM / QC / Dev — mặc định "QC/Tester" |
| Suggestion list | Dropdown gợi ý user chưa là member, hiện avatar + tên + email |
| Button "Gửi lời mời" | Primary, disabled khi input rỗng hoặc đang submit |

#### Member row (Active)

```
┌──────────────────────────────────────────────┐
│ [Av]  Tran Thi QC                            │
│       tran@company.com                       │
│       [QC/Tester  ▾]              [🗑 Xoá]   │
└──────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Avatar | Initials circle 32px — màu theo role |
| Tên | 13px font-weight 500 |
| Email | 11px text-tertiary |
| Role dropdown | Admin/Owner: clickable dropdown đổi role. PM/QC/Dev: badge tĩnh |
| Nút Xoá | Icon trash 🗑, màu danger, chỉ Admin/Owner. Ẩn với Owner row |

#### Owner row (đặc biệt)

```
┌──────────────────────────────────────────────┐
│ [Av]  Admin User                             │
│       admin@company.com                      │
│       [Owner]              [Chuyển quyền ▾]  │
└──────────────────────────────────────────────┘
```

- Badge "Owner" cố định, không phải dropdown
- Nút "Chuyển quyền" chỉ hiện nếu `is_current_user = true` (Owner đang xem chính mình)
- Không có nút Xoá

#### Pending invitation row

```
┌──────────────────────────────────────────────┐
│ [?]  new@company.com                         │
│      Vai trò: QC/Tester                      │
│      Hết hạn sau 5 ngày        [Huỷ lời mời] │
└──────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Avatar | Icon "?" xám — chưa có tài khoản |
| Email | Email được mời |
| Vai trò | Role được chỉ định khi mời |
| Countdown | "Hết hạn sau N ngày" — đỏ khi ≤ 1 ngày |
| Nút Huỷ | Text button, màu danger |

---

### 1.4 Role badge màu

| Role | Background | Text | Ý nghĩa |
|---|---|---|---|
| Owner | Purple | Purple dark | Người sở hữu project |
| PM/BA | Info | Info dark | Quản lý tài liệu |
| QC/Tester | Success | Success dark | Viết và chạy testcase |
| Dev | Warning | Warning dark | Chỉ đọc |
| Chờ xác nhận | Gray | Gray dark | Chưa có tài khoản |

---

### 1.5 Modal xác nhận xoá member

```
┌──────────────────────────────────────────┐
│ Xoá thành viên                           │
├──────────────────────────────────────────┤
│                                          │
│  Bạn có chắc muốn xoá Tran Thi QC       │
│  khỏi project "Project Demo"?            │
│                                          │
│  Thành viên sẽ mất toàn bộ quyền        │
│  truy cập ngay lập tức.                  │
│                                          │
│           [Huỷ]  [Xoá thành viên]       │
└──────────────────────────────────────────┘
```

---

### 1.6 Modal Transfer ownership

```
┌──────────────────────────────────────────┐
│ Chuyển quyền sở hữu project             │
├──────────────────────────────────────────┤
│ Chọn thành viên nhận quyền sở hữu:      │
│                                          │
│  ○  [Av] Nguyen Van PM  (PM/BA)          │
│  ○  [Av] Tran Thi QC   (QC/Tester)      │
│  ○  [Av] Le Van Dev    (Dev)             │
│                                          │
│  Sau khi chuyển, bạn sẽ trở thành PM.   │
│                                          │
│        [Huỷ]  [Xác nhận chuyển quyền]   │
└──────────────────────────────────────────┘
```

---

### 1.7 Empty & loading states

| Tình huống | Hiển thị |
|---|---|
| Đang load | Skeleton 3 row shimmer |
| Chỉ có 1 mình Owner | "Chưa có thành viên nào. Mời thành viên để cộng tác." |
| Gửi lời mời thành công (user đã có TK) | Toast xanh lá "Đã thêm Nguyen PM vào project" |
| Gửi lời mời thành công (email mới) | Toast xanh lá "Đã gửi lời mời đến email@..." |
| Xoá thành công | Toast xanh lá "Đã xoá Tran QC khỏi project" |
| Đổi role thành công | Toast xanh lá "Đã cập nhật role thành PM/BA" |
| Email không tồn tại (và không gửi lời mời) | — (xử lý bằng cách tạo pending invitation) |

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ từng luồng

#### Luồng 1 — Mời thành viên

```
Admin nhập email + chọn role → click "Gửi lời mời"
    │
    ├─ Client validate: email format, không rỗng
    │       └─ Fail → lỗi inline, không gọi API
    │
    └─ POST /api/v1/projects/{id}/members
            │
            ├─ Email đã là member → 409
            │
            ├─ Email là chính mình → 422
            │
            ├─ Email có tài khoản trong hệ thống
            │       └─ Thêm vào project_members ngay (status=active)
            │               → Response type="added"
            │               → Thêm row vào list ngay (optimistic)
            │               → Toast "Đã thêm thành viên"
            │
            └─ Email CHƯA có tài khoản
                    └─ Tạo pending_invitations record
                            → Celery task gửi email với link token
                            → Response type="invited"
                            → Thêm vào section "Chờ xác nhận"
                            → Toast "Đã gửi lời mời"
```

#### Luồng 2 — Thay đổi role

```
Admin click dropdown role → chọn role mới
    │
    └─ PATCH /api/v1/projects/{id}/members/{user_id}
            │
            ├─ Target là Owner → 403
            │
            ├─ Success → update row UI ngay (optimistic update)
            │               → Toast "Đã cập nhật role"
            │
            └─ Fail → rollback UI về role cũ → Toast error
```

**Lưu ý quan trọng:** Role trong project được query từ `project_members` table mỗi request, không lưu trong JWT. Vì vậy khi đổi role, hiệu lực ngay lập tức mà không cần user logout/login lại.

#### Luồng 3 — Xoá thành viên

```
Admin click Xoá → Modal confirm hiện
    │
    └─ Xác nhận → DELETE /api/v1/projects/{id}/members/{user_id}
            │
            ├─ Target là Owner → 403
            │
            ├─ Success → xoá row khỏi list ngay
            │               → User mất quyền truy cập ngay lập tức
            │               → Toast "Đã xoá thành viên"
            │
            └─ Fail → giữ nguyên list → Toast error
```

#### Luồng 4 — Transfer ownership

```
Owner click "Chuyển quyền" → Modal chọn người nhận
    │
    ├─ Chọn thành viên → click "Xác nhận"
    │
    └─ POST /api/v1/projects/{id}/transfer-owner
            │
            ├─ Người nhận không phải member → 404
            ├─ Người nhận là chính mình → 422
            │
            └─ Success:
                    - Người nhận: role → "owner"
                    - Current user: role → "pm"
                    - Reload toàn bộ member list
                    - Toast "Đã chuyển quyền sở hữu thành công"
                    - Nút "Chuyển quyền" ẩn đi (không còn là owner)
```

#### Luồng 5 — Accept invitation (user mới)

```
User nhận email → click link → trang đăng ký
    │
    ├─ Đăng ký tài khoản thành công
    │
    └─ POST /api/v1/invitations/{token}/accept
            │
            ├─ Token hết hạn (> 7 ngày) → 400
            ├─ Đã là member rồi → 409
            │
            └─ Success → thêm vào project_members
                            → Xoá pending_invitations record
                            → Redirect đến project
```

---

### 2.2 Validation Rules

#### VL-MEM-001 — Email format
- **Field:** Input email mời
- **Trigger:** onBlur + onSubmit
- **Rule:** `/^[^@]+@[^@]+\.[^@]+$/`
- **Error message:** "Email không đúng định dạng"
- **Scope:** Client + Server

#### VL-MEM-002 — Email bắt buộc
- **Field:** Input email mời
- **Trigger:** onSubmit
- **Rule:** Không rỗng, không chỉ khoảng trắng
- **Error message:** "Vui lòng nhập email thành viên"
- **Scope:** Client

#### VL-MEM-003 — Không tự mời chính mình
- **Trigger:** Server check
- **Rule:** `email ≠ current_user.email`
- **Error message:** "Bạn không thể mời chính mình"
- **Scope:** Server only

#### VL-MEM-004 — Không trùng member
- **Trigger:** Server check
- **Rule:** Email chưa là member active hoặc pending của project
- **Error message:** "Thành viên này đã có trong project"
- **Scope:** Server only

#### VL-MEM-005 — Role mời hợp lệ
- **Field:** Dropdown role
- **Trigger:** onSubmit
- **Rule:** Role phải thuộc `["pm", "qc", "dev"]`
- **Error message:** "Role không hợp lệ"
- **Scope:** Client + Server
- **Ghi chú:** Không thể mời với role "owner" — chỉ có thể transfer

#### VL-MEM-006 — Không xoá Owner
- **Trigger:** Server check
- **Rule:** `target_member.role ≠ "owner"`
- **Error message:** "Không thể xoá Owner. Hãy transfer ownership trước."
- **Scope:** Server only (UI đã ẩn nút Xoá với Owner row)

#### VL-MEM-007 — Transfer: người nhận là member
- **Trigger:** Server check
- **Rule:** `new_owner_id` phải có trong `project_members` với status active
- **Error message:** "Người nhận không phải thành viên của project"
- **Scope:** Server only

#### VL-MEM-008 — Transfer: không chuyển cho chính mình
- **Trigger:** Server check
- **Rule:** `new_owner_id ≠ current_user.id`
- **Error message:** "Không thể chuyển quyền cho chính mình"
- **Scope:** Server only

---

### 2.3 Role hierarchy

```
owner > pm > qc > dev
```

| Role | project_members | Mô tả quyền trong project |
|---|---|---|
| `owner` | Duy nhất 1/project | Toàn quyền. Không bị xoá hay đổi role |
| `pm` | Nhiều | Upload tài liệu, approve diff, tạo TC |
| `qc` | Nhiều | Tạo và chạy testcase, xem tài liệu |
| `dev` | Nhiều | Chỉ đọc — xem tài liệu, hỏi Q&A |

**Phân biệt `users.role` và `project_members.role`:**
- `users.role = "admin"` → system admin, thấy và quản lý mọi project
- `project_members.role = "owner"` → chủ sở hữu của project cụ thể

---

### 2.4 Pending invitation schema

```sql
CREATE TABLE pending_invitations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  email       TEXT NOT NULL,
  role        project_member_role NOT NULL DEFAULT 'qc',
  invited_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  token       UUID NOT NULL DEFAULT gen_random_uuid(),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days'),
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE(project_id, email)
);

CREATE INDEX idx_pending_inv_token   ON pending_invitations(token);
CREATE INDEX idx_pending_inv_project ON pending_invitations(project_id);
CREATE INDEX idx_pending_inv_expires ON pending_invitations(expires_at);
```

**Celery task dọn dẹp hàng ngày:**

```python
@shared_task
def cleanup_expired_invitations():
    with get_sync_db() as db:
        db.execute(
            delete(PendingInvitation)
            .where(PendingInvitation.expires_at < datetime.now(timezone.utc))
        )
        db.commit()
```

---

### 2.5 Email template lời mời

**Subject:** `[QC Master] Bạn được mời tham gia project {project_name}`

**Body:**

```
Xin chào,

{inviter_name} đã mời bạn tham gia project "{project_name}" 
với vai trò {role_label} trong hệ thống QC Master.

Nhấn vào link dưới để chấp nhận lời mời:
[Tham gia project] → https://qcmaster.dev/invite?token={token}

Link này có hiệu lực trong 7 ngày (hết hạn: {expires_at}).

Nếu bạn chưa có tài khoản, hệ thống sẽ hướng dẫn bạn đăng ký.

Trân trọng,
QC Master Team
```

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/members` | Danh sách member + pending | Bearer (member) |
| POST | `/api/v1/projects/{project_id}/members` | Mời thành viên | Bearer (owner/admin) |
| PATCH | `/api/v1/projects/{project_id}/members/{user_id}` | Đổi role | Bearer (owner/admin) |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | Xoá thành viên | Bearer (owner/admin) |
| POST | `/api/v1/projects/{project_id}/transfer-owner` | Chuyển ownership | Bearer (owner) |
| DELETE | `/api/v1/projects/{project_id}/invitations/{invitation_id}` | Huỷ lời mời | Bearer (owner/admin) |
| POST | `/api/v1/invitations/{token}/accept` | Accept lời mời | Không cần auth |

---

### 3.2 GET /api/v1/projects/{project_id}/members

**Mô tả:** Danh sách member active + pending invitations. Pending chỉ trả về với Owner/Admin.

**Auth:** Bearer (phải là member của project)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Response 200

```json
{
  "members": [
    {
      "user_id": "uuid-owner",
      "email": "admin@qcmaster.dev",
      "full_name": "Admin User",
      "avatar_url": null,
      "role": "owner",
      "joined_at": "2025-01-15T08:00:00Z",
      "is_current_user": true
    },
    {
      "user_id": "uuid-pm",
      "email": "pm@qcmaster.dev",
      "full_name": "Nguyen PM",
      "avatar_url": null,
      "role": "pm",
      "joined_at": "2025-01-16T09:00:00Z",
      "is_current_user": false
    }
  ],
  "pending_invitations": [
    {
      "id": "uuid-inv",
      "email": "new@company.com",
      "role": "qc",
      "invited_by_name": "Admin User",
      "expires_at": "2025-06-17T08:00:00Z",
      "created_at": "2025-06-10T08:00:00Z"
    }
  ],
  "total_members": 2,
  "total_pending": 1
}
```

**Ghi chú:** `pending_invitations` trả `[]` với PM/QC/Dev.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền truy cập project | Không phải member |
| 404 | Project không tồn tại | — |

---

### 3.3 POST /api/v1/projects/{project_id}/members

**Mô tả:** Mời thành viên. Nếu email có tài khoản → thêm ngay. Nếu chưa → tạo pending + gửi email.

**Auth:** Bearer (owner hoặc system admin)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `email` | string | Có | Email thành viên |
| `role` | string | Có | `pm` \| `qc` \| `dev` |

```json
{
  "email": "newmember@company.com",
  "role": "qc"
}
```

#### Response 201 — user đã có tài khoản

```json
{
  "type": "added",
  "message": "Đã thêm thành viên vào project thành công",
  "member": {
    "user_id": "uuid-new",
    "email": "newmember@company.com",
    "full_name": "New Member",
    "avatar_url": null,
    "role": "qc",
    "joined_at": "2025-06-10T09:00:00Z"
  }
}
```

#### Response 201 — email chưa có tài khoản

```json
{
  "type": "invited",
  "message": "Đã gửi lời mời đến newmember@company.com",
  "invitation": {
    "id": "uuid-inv",
    "email": "newmember@company.com",
    "role": "qc",
    "expires_at": "2025-06-17T09:00:00Z"
  }
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | — |
| 403 | Không có quyền mời thành viên | Không phải owner/admin |
| 404 | Project không tồn tại | — |
| 409 | Thành viên đã có trong project | Đã là member hoặc pending |
| 422 | Dữ liệu không hợp lệ | Email sai format, role không hợp lệ, tự mời mình |

#### Error body mẫu

```json
{
  "error": "CONFLICT",
  "message": "Thành viên này đã có trong project",
  "status_code": 409,
  "field": "email"
}
```

---

### 3.4 PATCH /api/v1/projects/{project_id}/members/{user_id}

**Mô tả:** Thay đổi role thành viên. Không thể đổi role Owner.

**Auth:** Bearer (owner hoặc system admin)  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Có

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `role` | string | Có | `pm` \| `qc` \| `dev` |

```json
{ "role": "pm" }
```

#### Response 200

```json
{
  "user_id": "uuid-member",
  "email": "member@company.com",
  "full_name": "Tran QC",
  "role": "pm",
  "updated_at": "2025-06-10T09:30:00Z"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Role không hợp lệ | Chỉ nhận pm, qc, dev |
| 403 | Không có quyền | Không phải owner/admin |
| 403 | Không thể đổi role Owner | Target là owner |
| 404 | Thành viên không tồn tại | user_id không có trong project |

---

### 3.5 DELETE /api/v1/projects/{project_id}/members/{user_id}

**Mô tả:** Xoá thành viên. Hiệu lực ngay lập tức. Không thể xoá Owner.

**Auth:** Bearer (owner hoặc system admin)  
**Rate limit:** 20 lần / phút / user  
**Idempotent:** Có

#### Response 200

```json
{
  "message": "Đã xoá thành viên khỏi project",
  "user_id": "uuid-member"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền xoá | Không phải owner/admin |
| 403 | Không thể xoá Owner | Phải transfer owner trước |
| 404 | Thành viên không tồn tại | — |

---

### 3.6 POST /api/v1/projects/{project_id}/transfer-owner

**Mô tả:** Chuyển ownership. Owner hiện tại → PM. Người nhận → Owner. Chỉ Owner thực hiện được.

**Auth:** Bearer (phải là owner của project)  
**Rate limit:** 5 lần / giờ / user  
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `new_owner_id` | UUID | Có | user_id của thành viên nhận ownership |

```json
{ "new_owner_id": "uuid-pm-user" }
```

#### Response 200

```json
{
  "message": "Đã chuyển quyền sở hữu thành công",
  "new_owner": {
    "user_id": "uuid-pm-user",
    "full_name": "Nguyen PM",
    "role": "owner"
  },
  "previous_owner": {
    "user_id": "uuid-current",
    "full_name": "Admin User",
    "role": "pm"
  }
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Chỉ Owner mới được chuyển quyền | Current user không phải owner |
| 404 | Người nhận không phải thành viên | new_owner_id không có trong project |
| 422 | Không thể chuyển cho chính mình | new_owner_id = current user |

---

### 3.7 DELETE /api/v1/projects/{project_id}/invitations/{invitation_id}

**Mô tả:** Huỷ lời mời đang pending. Token vô hiệu hoá ngay.

**Auth:** Bearer (owner hoặc system admin)  
**Rate limit:** 20 lần / phút  
**Idempotent:** Có

#### Response 200

```json
{
  "message": "Đã huỷ lời mời",
  "invitation_id": "uuid-inv-1"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Không có quyền huỷ lời mời | — |
| 404 | Lời mời không tồn tại hoặc đã hết hạn | — |

---

### 3.8 POST /api/v1/invitations/{token}/accept

**Mô tả:** User mới click link trong email → đăng ký → gọi API này để join project. Không cần Bearer token.

**Auth:** Không cần (dùng token trong path)  
**Rate limit:** 10 lần / phút / IP  
**Idempotent:** Có

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `user_id` | UUID | Có | UUID của user vừa đăng ký thành công |

```json
{ "user_id": "uuid-newly-registered" }
```

#### Response 200

```json
{
  "message": "Đã tham gia project thành công",
  "project": {
    "id": "uuid-project",
    "name": "Project Demo",
    "slug": "project-demo"
  },
  "role": "qc"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Token không hợp lệ hoặc đã hết hạn | Token sai hoặc quá 7 ngày |
| 409 | Bạn đã là thành viên của project này | Đã join rồi |
| 422 | user_id không hợp lệ | — |

---

## 4. Màn hình và component sử dụng

| Màn hình / Component | Tính năng | API được dùng |
|---|---|---|
| S2 Project list — menu "···" | Mở Member panel | `GET /members` |
| Member panel — danh sách | Xem member + pending | `GET /members` |
| Member panel — form mời | Mời thành viên | `POST /members` |
| Member panel — dropdown role | Thay đổi role | `PATCH /members/{user_id}` |
| Member panel — nút Xoá | Xoá thành viên | `DELETE /members/{user_id}` |
| Member panel — transfer | Chuyển ownership | `POST /transfer-owner` |
| Member panel — nút Huỷ lời mời | Huỷ pending | `DELETE /invitations/{id}` |
| Email invite link | Accept lời mời | `POST /invitations/{token}/accept` |
| S3 Document list — header | Số member | `GET /members` → `total_members` |

---

## 5. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S1 Login | Auth flow, JWT, role |
| Basic Design — S2 Project list | Entry point mở Member panel |
| Basic Design — S3 Document list | Hiện `total_members` trong header |
| Database schema — `project_members` | role, joined_at |
| Database schema — `users` | email, full_name, avatar_url |
| Database schema — `pending_invitations` | Bảng mới bổ sung |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
