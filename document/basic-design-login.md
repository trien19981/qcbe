# Login — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — Màn hình Login  
**Màn hình:** S1 Login  
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

Màn hình xác thực duy nhất của hệ thống QC Master. Không có sidebar, không có header — layout centered card. Sau đăng nhập thành công, hệ thống detect `role` từ response và redirect thẳng đến S2 Project list.

**Vai trò truy cập:** Tất cả (chưa đăng nhập)  
**Màn hình trước:** — (entry point)  
**Màn hình sau:** S2 Project list (redirect theo role)

---

### 1.2 Layout

```
┌─────────────────────────────────────────┐
│           [Nền background-tertiary]     │
│                                         │
│        ┌────────────────────────┐       │
│        │  [Logo] QC Master      │       │
│        │  Đăng nhập để tiếp tục│       │
│        │                        │       │
│        │  Email                 │       │
│        │  [________________]    │       │
│        │                        │       │
│        │  Mật khẩu              │       │
│        │  [____________] [●]    │       │
│        │              Quên MK?  │       │
│        │                        │       │
│        │  [  Đăng nhập  ]       │       │
│        └────────────────────────┘       │
│                                         │
└─────────────────────────────────────────┘
```

- **Container:** Card trắng, width `400px`, căn giữa cả ngang lẫn dọc
- **Nền:** `background-tertiary` toàn trang
- **Card padding:** `32px`
- **Border-radius:** `12px`
- **Không có:** sidebar, header, footer, shadow

---

### 1.3 UI Elements

| Element | Mô tả | Ghi chú |
|---|---|---|
| Logo | Icon 28×28px + text "QC Master", căn giữa | Top of card |
| Subtitle | "Đăng nhập để tiếp tục", 12px, text-tertiary | Dưới logo |
| Label Email | "Email", 11px, font-weight 500 | Trên input |
| Input Email | Full width, placeholder "email@company.com" | Type text |
| Label Mật khẩu | "Mật khẩu", 11px, font-weight 500 | Trên input |
| Input Password | Full width, placeholder "••••••••" | Type password |
| Eye icon | Toggle show/hide password, bên phải input | Icon 16px |
| Link Quên mật khẩu | "Quên mật khẩu?", 11px, text-info | Right-align, dưới input PW |
| Button Đăng nhập | Full width, primary style | Dưới link |
| Error message | 11px, text-danger, dưới field/form | Hiện khi có lỗi |

---

### 1.4 UI States

| State | Trigger | Thay đổi UI |
|---|---|---|
| **Default** | Mở màn hình | Form trống, button enabled, placeholder hiện |
| **Typing email** | Focus input email | Border xanh info, placeholder ẩn |
| **Typing password** | Focus input password | Border xanh info, eye icon toggle |
| **Client error** | Submit với field sai/trống | Border đỏ trên field lỗi + error message bên dưới |
| **Submitting** | Click button, client validate pass | Button disabled + spinner + text "Đang đăng nhập...", cả 2 input disabled |
| **Server error 401** | API trả 401 | Form enabled lại, error message "Email hoặc mật khẩu không đúng" dưới password |
| **Rate limited 429** | API trả 429 | Toast đỏ trên cùng, countdown timer, button disabled |
| **Account locked 403** | API trả 403 | Toast đỏ "Tài khoản đã bị khoá. Liên hệ Admin.", button enabled |
| **Success** | API trả 200 | Toast xanh lá, spinner, redirect S2 sau 800ms |

---

### 1.5 Redirect sau login

| Role | Redirect đến | Màn hình bị chặn |
|---|---|---|
| admin | S2 Project list | Không bị chặn |
| pm | S2 Project list | Admin panel |
| qc | S2 Project list | Admin panel, Upload tài liệu, Approve diff |
| dev | S2 Project list | Admin panel, Upload, Approve diff, Tạo/sửa TC |

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ từng bước

#### Bước 1 — User nhập form và submit

**Trigger:** Click button "Đăng nhập" hoặc nhấn `Enter` trong field password  
**Điều kiện submit:** Cả 2 field không rỗng + email format hợp lệ + password không rỗng

```
User click Submit
    │
    ├─ Client validate fail → hiện lỗi inline, không gọi API
    │
    └─ Client validate pass → gọi POST /api/v1/auth/login
```

#### Bước 2 — FastAPI nhận và xử lý

```
Nhận request
    │
    ├─ Rate limit: ≥ 5 lần fail trong 5 phút / IP → 429 + Retry-After header
    │
    ├─ Validate format → 422 nếu sai
    │
    ├─ Query DB: SELECT * FROM users WHERE email = ?
    │       └─ Không tìm thấy → 401 generic (không phân biệt)
    │
    ├─ Check is_active = false → 403 (không check password)
    │
    └─ bcrypt.checkpw(input_pw, stored_hash)
            ├─ Sai → 401 generic + tăng fail counter Redis
            └─ Đúng → reset fail counter → gen JWT tokens
```

**Quan trọng:** Server không phân biệt "sai email" vs "sai password" để chống user enumeration attack.

#### Bước 3 — Gen JWT và lưu Redis

```
access_token:
  - Thuật toán: HS256
  - Payload: {sub: user_id, role: "qc", iat: now, exp: now + 900}
  - TTL: 900 giây (15 phút)

refresh_token:
  - Thuật toán: HS256
  - Payload: {sub: user_id, jti: uuid4(), exp: now + 604800}
  - TTL: 604800 giây (7 ngày)
  - Redis key: refresh:{user_id}:{jti} = "valid"
  - Redis TTL: 7 ngày (đồng bộ)
```

#### Bước 4 — FE nhận response và lưu token

```
access_token  → Lưu JS memory (Zustand store) — KHÔNG localStorage
refresh_token → Server set httpOnly Secure SameSite=Strict cookie
user info     → Lưu global state: {id, email, full_name, role}
```

#### Bước 5 — Redirect theo role

Mọi role đều redirect đến S2 Project list. Route guard FE kiểm tra `role` trước khi render từng màn hình con.

---

### 2.2 Validation Rules

#### VL-001 — Email format
- **Field:** Input Email
- **Trigger:** onBlur + onSubmit
- **Rule:** `/^[^@]+@[^@]+\.[^@]+$/` (client) + RFC 5322 (server)
- **Error message:** "Email không đúng định dạng"
- **Scope:** Client + Server
- **Ghi chú:** Server validate để tránh bypass qua API trực tiếp

#### VL-002 — Email bắt buộc
- **Field:** Input Email
- **Trigger:** onSubmit
- **Rule:** Không rỗng và không chỉ toàn khoảng trắng (`.trim().length > 0`)
- **Error message:** "Vui lòng nhập email"
- **Scope:** Client + Server

#### VL-003 — Password bắt buộc
- **Field:** Input Password
- **Trigger:** onSubmit
- **Rule:** Không rỗng
- **Error message:** "Vui lòng nhập mật khẩu"
- **Scope:** Client + Server

#### VL-004 — Rate limit login
- **Field:** Toàn form
- **Trigger:** Mỗi request POST /login thất bại
- **Rule:** Max 5 lần fail trong 5 phút / IP
- **Error message:** "Quá nhiều lần thử. Vui lòng thử lại sau {X} giây."
- **Scope:** Server only
- **Ghi chú:** Counter lưu Redis `login_fail:{ip}` TTL 5 phút. Reset khi login thành công.

#### VL-005 — Account active
- **Field:** Toàn form (toast)
- **Trigger:** Sau khi tìm thấy user trong DB
- **Rule:** `user.is_active = true`
- **Error message:** "Tài khoản đã bị khoá. Liên hệ Admin."
- **Scope:** Server only

#### VL-006 — Generic error 401
- **Field:** Dưới form
- **Trigger:** Email không tồn tại HOẶC password sai
- **Rule:** Luôn trả cùng 1 message, không phân biệt
- **Error message:** "Email hoặc mật khẩu không đúng"
- **Scope:** Server only
- **Lý do:** Chống user enumeration — attacker không biết email có tồn tại không

---

### 2.3 Security Requirements

#### Token storage
| Token | Nơi lưu | Lý do |
|---|---|---|
| access_token | JS memory (store) | Tránh XSS đọc localStorage |
| refresh_token | httpOnly cookie | JS không đọc được, chỉ browser tự gửi |

#### Security rules bắt buộc

1. **Không log password** — Server không log password ở bất kỳ level nào (debug, info, error). Chỉ log email và IP.
2. **Constant-time compare** — Dùng `bcrypt.checkpw()`, không dùng `==` so sánh string — chống timing attack.
3. **HTTPS bắt buộc** — Tất cả endpoint auth chỉ chạy HTTPS. Cookie `Secure` flag bắt buộc.
4. **CSRF protection** — `SameSite=Strict` trên cookie. API endpoint check `Origin` header.
5. **Revoke ngay khi logout** — `DEL` Redis key ngay, không đợi token hết hạn tự nhiên.
6. **Generic error 401** — Không phân biệt "sai email" vs "sai password".
7. **Rate limit per IP** — 5 lần sai / 5 phút → 429 với `Retry-After` header.

#### JWT spec
| Thuộc tính | access_token | refresh_token |
|---|---|---|
| Algorithm | HS256 | HS256 |
| TTL | 900s (15 phút) | 604800s (7 ngày) |
| Payload | sub, role, iat, exp | sub, jti, exp |
| Storage (FE) | JS memory | httpOnly cookie |
| Storage (BE) | Stateless | Redis (để revoke) |
| Secret | `SECRET_KEY` env | `SECRET_KEY` env |

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Đăng nhập | Không |
| POST | `/api/v1/auth/refresh` | Refresh access_token | Cookie |
| POST | `/api/v1/auth/logout` | Đăng xuất | Bearer |
| GET | `/api/v1/auth/me` | Lấy thông tin user | Bearer |

---

### 3.2 POST /api/v1/auth/login

**Mô tả:** Xác thực email + password. Trả về `access_token` trong JSON và set `refresh_token` qua `httpOnly cookie`. Không phân biệt lỗi "sai email" vs "sai password".

**Rate limit:** 5 lần fail / 5 phút / IP  
**Idempotent:** Không

#### Request headers

| Header | Bắt buộc | Giá trị |
|---|---|---|
| `Content-Type` | Có | `application/json` |

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `email` | string | Có | Email người dùng, validate format RFC 5322 |
| `password` | string | Có | Mật khẩu plaintext — HTTPS bắt buộc |

```json
{
  "email": "qc@qcmaster.dev",
  "password": "your_password"
}
```

#### Response 200

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "qc@qcmaster.dev",
    "full_name": "Tran QC",
    "role": "qc",
    "avatar_url": null
  }
}
```

> **Đồng thời server SET cookie:**  
> `Set-Cookie: refresh_token=eyJ...; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=604800`

> **Lưu ý:** `refresh_token` KHÔNG trả trong JSON body — chỉ qua `httpOnly` cookie. FE không cần xử lý.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Thiếu field bắt buộc | `email` hoặc `password` không có trong body |
| 401 | Email hoặc mật khẩu không đúng | Email không tồn tại HOẶC sai password — không phân biệt |
| 403 | Tài khoản đã bị khoá | `is_active = false` — hiện: "Liên hệ Admin để mở khoá" |
| 422 | Email không đúng định dạng | Validate format trước khi query DB |
| 429 | Quá nhiều lần thử | Header `Retry-After: 300` — FE hiện countdown timer |

#### Error response body mẫu

```json
{
  "error": "UNAUTHORIZED",
  "message": "Email hoặc mật khẩu không đúng",
  "status_code": 401
}
```

---

### 3.3 POST /api/v1/auth/refresh

**Mô tả:** Dùng `refresh_token` (từ `httpOnly` cookie, browser tự gửi) để lấy `access_token` mới. FE gọi tự động khi nhận 401 từ bất kỳ API nào — trong suốt với người dùng.

**Rate limit:** 20 lần / phút / user  
**Idempotent:** Không (mỗi lần gen token mới)

#### Request

```
// Không có request body
// Browser tự gửi Cookie: refresh_token=eyJ...
```

#### Response 200

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | refresh_token không hợp lệ hoặc đã hết hạn | Cookie không có, token hết hạn, hoặc đã bị revoke (key không còn trong Redis) |
| 403 | Tài khoản bị khoá | `is_active = false` được set sau khi user đã login |

> **Ghi chú:** Khi nhận 401 từ `/refresh`: FE xoá `access_token` trong memory và redirect về S1 Login.

---

### 3.4 POST /api/v1/auth/logout

**Mô tả:** Revoke `refresh_token` ngay lập tức bằng cách xoá key trong Redis. FE xoá `access_token` khỏi memory và clear cookie. Redirect về S1 Login.

**Rate limit:** Không áp dụng  
**Idempotent:** Có (gọi nhiều lần không gây lỗi)

#### Request headers

| Header | Bắt buộc | Giá trị |
|---|---|---|
| `Authorization` | Có | `Bearer {access_token}` |
| `Cookie` | Không | Browser tự gửi `refresh_token` cookie |

#### Request body

```
// Không có request body
```

#### Response 200

```json
{
  "message": "Đăng xuất thành công"
}
```

> **Server đồng thời:**  
> 1. `DEL Redis key: refresh:{user_id}:{jti}`  
> 2. `Set-Cookie: refresh_token=; Max-Age=0` (xoá cookie)

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | access_token không hợp lệ | Token hết hạn hoặc sai — server vẫn cố xoá cookie |

> **Ghi chú:** Nếu `access_token` đã hết hạn khi logout, server vẫn cố xoá Redis key từ `jti` trong cookie. Logout phải luôn thành công.

---

### 3.5 GET /api/v1/auth/me

**Mô tả:** Lấy thông tin user đang đăng nhập. Gọi 1 lần sau login để populate header và global state. Không cần gọi lại nếu đã có trong memory.

**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có (GET thuần túy)

#### Request headers

| Header | Bắt buộc | Giá trị |
|---|---|---|
| `Authorization` | Có | `Bearer {access_token}` |

#### Request body

```
// Không có request body
```

#### Response 200

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "qc@qcmaster.dev",
  "full_name": "Tran QC",
  "role": "qc",
  "is_active": true,
  "avatar_url": null,
  "created_at": "2025-01-15T08:00:00Z"
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | access_token hết hạn hoặc không hợp lệ | FE tự động gọi `/refresh` rồi retry |
| 403 | Tài khoản bị khoá | `is_active = false` — redirect về Login với thông báo |

> **Ghi chú:** FE cache response này trong memory. Chỉ gọi lại khi user chủ động reload hoặc sau khi đổi profile.

---

## 4. Màn hình sử dụng chức năng Login

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S1 Login | `POST /login` | Màn hình chính |
| S2 Project list (header) | `GET /me` | Populate tên, role, avatar |
| Header tất cả màn | `GET /me`, `POST /logout` | Avatar dropdown |
| Mọi API call (ngầm) | `POST /refresh` | FE interceptor tự gọi khi nhận 401 |
| Route guard (FE) | `POST /refresh` (nếu cần) | Check trước khi render màn hình có auth |

---

## 5. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S2 Project list | Màn hình sau redirect |
| Detail Design — Quản lý user | `is_active`, role management |
| API Design — Project list | API đầu tiên gọi sau login |
| Database schema — `users` table | `email`, `password_hash`, `is_active`, `role` |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*