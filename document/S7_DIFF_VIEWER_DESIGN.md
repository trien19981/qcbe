# S7 Diff Viewer — Tài liệu thiết kế đầy đủ

**Document:** Basic Design + Detail Design + API Design — So sánh version tài liệu  
**Màn hình:** S7 Diff viewer  
**Version:** 1.1  
**Ngày:** 2025-06-10  
**Tác giả:** [tên]  
**Trạng thái:** draft

---

## Changelog

| Version | Ngày | Người tạo | Nội dung |
|---|---|---|---|
| 1.0 | 2025-06-10 | [tên] | Bản khởi tạo |
| 1.1 | 2025-06-10 | [tên] | Bổ sung: Diff history, chunk.change_history metadata, API diff-history, tab Lịch sử thay đổi trong S5 |
| 1.1 | 2025-06-10 | [tên] | Bổ sung: Diff history timeline, chunk.change_history metadata, API GET /diff-history, tab "Lịch sử thay đổi" trong S5 |

---

## 1. Basic Design

### 1.1 Mô tả màn hình

Màn hình so sánh 2 version của cùng 1 tài liệu. AI tự động phân tích sự khác biệt ở cấp độ chunk, highlight rõ ràng các đoạn thêm mới, xoá bỏ, và chỉnh sửa. PM/Owner review từng thay đổi và approve/reject trực tiếp trên màn hình này. **Chỉ các thay đổi được approve mới kích hoạt re-embedding vào pgvector.**

Đây là chức năng **quan trọng nhất** của hệ thống — kiểm soát chất lượng dữ liệu RAG.

**Vai trò truy cập:**
- Xem diff: PM, Owner, Admin
- Approve/reject: PM, Owner, Admin
- QC/Dev: không truy cập màn hình này

**Màn hình trước:**
- S3 Document list → nút "So sánh version"
- S5 Version detail → nút "So sánh với version trước"
- Notification → "Có version mới cần review"

**Màn hình sau:**
- S8 Approve panel (click "Approve đã chọn")
- S3 Document list (sau khi hoàn tất review)
- S5 Version detail (breadcrumb back)

---

### 1.2 Layout tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│ TOOLBAR (sticky top)                                                 │
│ ← Quay lại  Login / Basic Design — So sánh version  [Xem full ▾]   │
├────────────────────────────────────────────────────────────────────  │
│ VERSION BAR                                                          │
│ [v2 (approved) ▾]  ←→  [v3 (ready_for_review) ▾]   [AI Summary]   │
├──────────┬─────────────────────────────┬─────────────────────────────┤
│ JUMP NAV │ CỘT TRÁI (version cũ)       │ CỘT PHẢI (version mới)     │
│          │                             │                             │
│ ● #1 Sửa │ ## Button states            │ ## Button states            │
│ + #2 Thêm│                             │                             │
│ - #3 Xoá │ ┃ Button cần màu ĐỎ        │ ┃ Button cần màu XANH      │
│ ● #4 Sửa │ ┃ khi nhập sai.            │ ┃ khi nhập sai.            │
│          │ [removed background]        │ [added background]          │
│          │            [✗ Reject] [✓ Approve change #1]              │
│          │─────────────────────────────│─────────────────────────────│
│          │ ## Error messages           │ ## Error messages           │
│          │                             │                             │
│          │ ┃ Hiện lỗi dưới field.     │ ┃ Hiện lỗi dưới field.     │
│          │ (không thay đổi)            │ (không thay đổi)            │
│          │─────────────────────────────│─────────────────────────────│
│          │                             │ ## OAuth section  [MỚI]    │
│          │ (không có)                  │ ┃ Thêm đăng nhập Google    │
│          │                             │ [added background]          │
│          │            [✗ Reject] [✓ Approve change #2]              │
├──────────┴─────────────────────────────┴─────────────────────────────┤
│ ACTION BAR (sticky bottom)                                           │
│ Đã chọn 1/3 thay đổi  [Reject tất cả] [Approve đã chọn]  [Approve  │
│                                                              tất cả] │
└──────────────────────────────────────────────────────────────────────┘
```

- **Toolbar:** Sticky top, 48px
- **Version bar:** Sticky dưới toolbar, 52px — chọn version để compare
- **Jump nav:** Fixed left 52px — outline các change block
- **Diff area:** 2 cột song song, scroll đồng bộ (synchronized scroll)
- **Action bar:** Sticky bottom, 56px

---

### 1.3 Toolbar chi tiết

```
┌──────────────────────────────────────────────────────────────────────┐
│ [← Quay lại]  Login / Basic Design — So sánh version    [Full ▾]   │
└──────────────────────────────────────────────────────────────────────┘
```

| Element | Mô tả | Hành động |
|---|---|---|
| ← Quay lại | Back | Navigate về màn trước |
| Breadcrumb | "Login / Basic Design — So sánh version" | — |
| Dropdown "Full" | Chế độ xem: Full diff / Chỉ thay đổi / Split / Unified | Thay đổi view mode |

**View modes:**

| Mode | Mô tả |
|---|---|
| **Full diff** (default) | 2 cột, hiện cả đoạn không thay đổi (mờ hơn) + đoạn thay đổi |
| **Chỉ thay đổi** | 2 cột, ẩn đoạn không thay đổi — chỉ hiện change blocks |
| **Unified** | 1 cột, dòng xoá gạch ngang đỏ, dòng thêm nền xanh (như git diff) |

---

### 1.4 Version bar

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  [v2 — 01/06/2025 — Nguyen PM ▾]  ←→  [v3 — 08/06/2025 ▾]        │
│  Approved                               Ready for review             │
│                                                                      │
│  [🤖 AI Summary: 3 thay đổi — 1 sửa, 1 thêm, 1 xoá    ▾]         │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

| Element | Mô tả |
|---|---|
| Dropdown trái | Chọn "version cũ" (base) — mặc định: version approved gần nhất trước version mới |
| Dropdown phải | Chọn "version mới" (head) — mặc định: version `ready_for_review` mới nhất |
| AI Summary badge | Tóm tắt AI về số lượng thay đổi, click để expand |

**AI Summary expanded:**

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🤖 Phân tích AI                                                   X │
├──────────────────────────────────────────────────────────────────────┤
│ Tìm thấy 3 thay đổi giữa v2 và v3:                                  │
│                                                                      │
│ ● 1 chỉnh sửa: Màu button lỗi đổi từ ĐỎ → XANH (#2196F3)         │
│   → Ảnh hưởng: 3 testcase liên quan cần review lại                  │
│                                                                      │
│ + 1 thêm mới: Phần OAuth Google login (section mới)                 │
│   → Chưa có testcase nào cover phần này                             │
│                                                                      │
│ - 1 xoá bỏ: Phần "Loading state" đã bị xoá                         │
│   → 1 testcase liên quan sẽ bị flag cần review                      │
│                                                                      │
│ Khuyến nghị: Approve change #1 và #2, xem xét kỹ change #3         │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 1.5 Jump navigator

```
│ THAY ĐỔI │
│ ───────── │
│ ● #1 Sửa │  ← màu warning (modified)
│ + #2 Thêm│  ← màu success (added)
│ - #3 Xoá │  ← màu danger (removed)
│           │
│ ─────── │
│ ✓ 1/3   │  ← đã approve 1, còn 2
```

Click vào item → scroll 2 cột đến change block đó đồng thời.

---

### 1.6 Diff area — Change blocks

#### Change type: MODIFIED (sửa đổi)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Change #1 — Chỉnh sửa                                    [● Sửa]   │
├──────────────────────────────┬──────────────────────────────────────┤
│ VERSION CŨ (v2)              │ VERSION MỚI (v3)                     │
│                              │                                      │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ Button LOGIN cần có màu      │ Button LOGIN cần có màu              │
│ ~~ĐỎ~~ khi người dùng nhập  │ **XANH (#2196F3)** khi người dùng   │
│ sai thông tin đăng nhập.     │ nhập sai thông tin đăng nhập.        │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ (nền đỏ nhạt)                │ (nền xanh lá nhạt)                  │
├──────────────────────────────┴──────────────────────────────────────┤
│ ⚠ 3 testcase liên quan sẽ bị flag cần review sau khi approve       │
│                              [✗ Reject]  [✓ Approve change #1]     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Change type: ADDED (thêm mới)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Change #2 — Thêm mới                                     [+ Thêm]  │
├──────────────────────────────┬──────────────────────────────────────┤
│ VERSION CŨ (v2)              │ VERSION MỚI (v3)                     │
│                              │                                      │
│ (Không có)                   │ ## OAuth Section                     │
│                              │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│                              │ Hệ thống hỗ trợ đăng nhập qua      │
│                              │ Google OAuth 2.0. User click nút    │
│                              │ "Đăng nhập bằng Google"...          │
│                              │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│                              │ (nền xanh lá nhạt)                  │
├──────────────────────────────┴──────────────────────────────────────┤
│ ℹ Chưa có testcase nào cover phần này                               │
│                              [✗ Reject]  [✓ Approve change #2]     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Change type: REMOVED (xoá bỏ)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Change #3 — Xoá bỏ                                       [- Xoá]   │
├──────────────────────────────┬──────────────────────────────────────┤
│ VERSION CŨ (v2)              │ VERSION MỚI (v3)                     │
│                              │                                      │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ (Đã bị xoá)                        │
│ ## Loading state             │                                      │
│ Khi đang xử lý request,     │                                      │
│ button hiển thị spinner...   │                                      │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░ │                                      │
│ (nền đỏ nhạt + strikethrough)│                                      │
├──────────────────────────────┴──────────────────────────────────────┤
│ ⚠ 1 testcase liên quan sẽ bị flag cần review sau khi approve       │
│                              [✗ Reject]  [✓ Approve change #3]     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 1.7 Màu sắc quy ước

| Loại thay đổi | Cột trái (cũ) | Cột phải (mới) | Badge |
|---|---|---|---|
| Modified | Nền đỏ nhạt `#FFF0F0` | Nền vàng nhạt `#FFFBEA` | ● warning |
| Added | (trống / xám nhạt) | Nền xanh lá nhạt `#F0FFF4` | + success |
| Removed | Nền đỏ nhạt `#FFF0F0` + strikethrough | (trống / xám nhạt) | - danger |
| Unchanged | Màu text mặc định, opacity 60% | Màu text mặc định, opacity 60% | — |

---

### 1.8 Action bar (sticky bottom)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Đã approve: 1 / 3 thay đổi          [Reject tất cả]                │
│                           [Approve đã chọn (1)]  [Approve tất cả]  │
└──────────────────────────────────────────────────────────────────────┘
```

| Element | Mô tả | Điều kiện hiện |
|---|---|---|
| Counter "Đã approve: N/M" | Số thay đổi đã approve / tổng | Luôn hiện |
| Nút "Reject tất cả" | Reject mọi thay đổi pending | Còn thay đổi pending |
| Nút "Approve đã chọn (N)" | Mở S8 với N thay đổi đã approve | N > 0 |
| Nút "Approve tất cả" | Approve tất cả không qua S8 | Admin shortcut |

**Trạng thái của từng change block sau action:**

| Action | Trạng thái | Visual |
|---|---|---|
| Click ✓ Approve | `approved` | Block có tick xanh góc phải, opacity giảm nhẹ |
| Click ✗ Reject | `rejected` | Block có X đỏ góc phải, opacity giảm nhiều |
| Pending | `pending` | Block bình thường |
| Đã submit | Tất cả locked | Không cho thay đổi lại |

---

### 1.9 States đặc biệt

#### Đang load diff (AI đang phân tích)

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│           [Spinner]  AI đang phân tích sự khác biệt...              │
│           Thường mất 10–30 giây tùy độ dài tài liệu                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

#### Diff đã được review (tất cả approved/rejected)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ✓ Đã hoàn tất review                                                │
│ 2 thay đổi đã approved — đang re-embedding...                        │
│ 1 thay đổi đã rejected                                              │
│                                        [Quay về danh sách tài liệu] │
└──────────────────────────────────────────────────────────────────────┘
```

#### Không có thay đổi

```
Hai version này giống nhau hoàn toàn.
Không tìm thấy sự khác biệt nào.
```

---

## 2. Detail Design

### 2.1 Logic nghiệp vụ

#### Load màn hình S7

```
Navigate vào S7
    │
    ├─ Parse URL params:
    │   - document_id (bắt buộc)
    │   - old_version_id (optional — mặc định: version approved trước)
    │   - new_version_id (optional — mặc định: version ready_for_review)
    │
    ├─ Gọi GET /api/v1/documents/{id}/diff?old={old_vid}&new={new_vid}
    │
    ├─ Nếu diff chưa có (status=pending):
    │   ├─ Hiện "AI đang phân tích..."
    │   └─ Polling GET /diff/status mỗi 3s cho đến khi ready
    │
    └─ Render diff khi data ready
```

#### Approve / reject từng change

```
User click ✓ Approve trên change block #N
    │
    ├─ Cập nhật local state: change[N].status = "approved"
    ├─ Cập nhật counter trong action bar
    ├─ Visual: block #N hiện tick xanh
    │
    └─ KHÔNG gọi API ngay — chỉ lưu local state
              (tránh N API calls riêng lẻ)
```

```
User click ✗ Reject trên change block #N
    │
    ├─ Cập nhật local state: change[N].status = "rejected"
    ├─ Visual: block #N hiện X đỏ, opacity giảm
    └─ KHÔNG gọi API ngay
```

#### Submit approve (mở S8)

```
User click "Approve đã chọn (N)"
    │
    ├─ Collect tất cả change có status="approved"
    │
    └─ Navigate đến S8 Approve panel với params:
            - diff_review_id
            - approved_change_ids: [id1, id2, ...]
            - rejected_change_ids: [id3, ...]
```

#### Approve tất cả (Admin shortcut)

```
User click "Approve tất cả"
    │
    ├─ Confirm dialog:
    │   "Approve tất cả 3 thay đổi?
    │    5 testcase sẽ bị flag cần review."
    │   [Huỷ]  [Xác nhận]
    │
    └─ POST /api/v1/diff-reviews/{id}/approve-all
            │
            └─ Server: approve tất cả changes + re-embed + flag TC
                    → Redirect về S3 với toast success
```

---

### 2.2 AI Diff algorithm — cấp độ chunk

```
Input:
  - old_chunks: list[Chunk]  (từ version cũ)
  - new_chunks: list[Chunk]  (từ version mới)

Algorithm:
  1. Embed tất cả old_chunks và new_chunks nếu chưa có
     (new_chunks đã có embedding từ pipeline upload)

  2. Với mỗi new_chunk:
     - Tìm old_chunk tương đồng nhất (cosine similarity)
     - Nếu similarity > 0.85: MODIFIED hoặc UNCHANGED
     - Nếu similarity < 0.3: ADDED (không có chunk tương ứng)

  3. Với mỗi old_chunk không có new_chunk match:
     - REMOVED

  4. UNCHANGED nếu similarity > 0.95 và nội dung gần giống hệt

  5. Text-level diff trong chunk MODIFIED:
     - Dùng Python difflib.unified_diff()
     - Highlight từng từ thay đổi trong chunk (word-level diff)

Output: list[DiffChange] với change_type + content_before + content_after
```

---

### 2.3 Word-level diff trong chunk MODIFIED

Ngoài chunk-level diff, bên trong mỗi chunk MODIFIED còn có word-level highlight:

```
Cũ:  "Button LOGIN cần có màu ĐỎ khi người dùng nhập sai"
Mới: "Button LOGIN cần có màu XANH (#2196F3) khi người dùng nhập sai"

Render:
Cũ:  Button LOGIN cần có màu [ĐỎ] khi người dùng nhập sai
Mới: Button LOGIN cần có màu [XANH (#2196F3)] khi người dùng nhập sai

[...] = highlight màu đỏ nền / xanh lá nền
```

```python
import difflib

def word_diff(old_text: str, new_text: str) -> tuple[str, str]:
    old_words = old_text.split()
    new_words = new_text.split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words)

    old_html, new_html = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            old_html.extend(old_words[i1:i2])
            new_html.extend(new_words[j1:j2])
        elif op == 'replace':
            old_html.append(f'<del>{" ".join(old_words[i1:i2])}</del>')
            new_html.append(f'<ins>{" ".join(new_words[j1:j2])}</ins>')
        elif op == 'delete':
            old_html.append(f'<del>{" ".join(old_words[i1:i2])}</del>')
        elif op == 'insert':
            new_html.append(f'<ins>{" ".join(new_words[j1:j2])}</ins>')

    return ' '.join(old_html), ' '.join(new_html)
```

---

### 2.4 Synchronized scroll

2 cột diff scroll cùng nhau:

```typescript
const leftRef = useRef<HTMLDivElement>(null)
const rightRef = useRef<HTMLDivElement>(null)
let isSyncing = false

function syncScroll(source: 'left' | 'right') {
  return (e: Event) => {
    if (isSyncing) return
    isSyncing = true
    const target = source === 'left' ? rightRef.current : leftRef.current
    const src = source === 'left' ? leftRef.current : rightRef.current
    if (target && src) {
      // Tính tỉ lệ scroll (vì 2 cột có thể khác chiều cao)
      const ratio = src.scrollTop / (src.scrollHeight - src.clientHeight)
      target.scrollTop = ratio * (target.scrollHeight - target.clientHeight)
    }
    setTimeout(() => { isSyncing = false }, 50)
  }
}

useEffect(() => {
  const left = leftRef.current
  const right = rightRef.current
  left?.addEventListener('scroll', syncScroll('left'))
  right?.addEventListener('scroll', syncScroll('right'))
  return () => {
    left?.removeEventListener('scroll', syncScroll('left'))
    right?.removeEventListener('scroll', syncScroll('right'))
  }
}, [])
```

---

### 2.5 Testcase impact analysis

Khi diff được tạo, server tự động phân tích impact đến testcase:

```python
async def analyze_tc_impact(diff_changes: list[DiffChange]) -> dict:
    impact = {}
    for change in diff_changes:
        # Tìm TC liên kết với chunk_old_id
        if change.chunk_old_id:
            linked_tcs = await get_testcases_by_chunk(change.chunk_old_id)
            impact[change.id] = {
                "affected_tc_count": len(linked_tcs),
                "affected_tc_ids": [tc.id for tc in linked_tcs],
                "tc_titles": [tc.title for tc in linked_tcs]
            }
    return impact
```

Thông tin này được hiện trong change block:
- `⚠ 3 testcase liên quan sẽ bị flag cần review`
- `ℹ Chưa có testcase nào cover phần này` (với ADDED)

---

---

### 2.6 Lưu lịch sử thay đổi — Diff history

#### 2.6.1 Mục tiêu

Mỗi lần diff được approve, hệ thống lưu lại **vĩnh viễn** toàn bộ thông tin thay đổi. Người dùng có thể xem lại bất kỳ lúc nào: "v2 khác v1 những điểm nào?", "ai đã approve?", "ảnh hưởng testcase nào?". Đây là **audit trail không thể xoá**.

`diff_reviews` + `diff_changes` không bao giờ bị xoá sau khi `status = approved`.

#### 2.6.2 Gắn change_history vào chunk metadata

Sau approve, chunk mới được gắn thêm `change_history` vào `metadata` trước khi re-embed:

```python
async def enrich_chunk_with_history(chunk, diff_change, diff_review):
    existing = chunk.metadata.get("change_history", [])
    new_entry = {
        "from_version_no": diff_review.old_version.version_no,
        "to_version_no":   diff_review.new_version.version_no,
        "from_version_id": str(diff_review.old_version_id),
        "to_version_id":   str(diff_review.new_version_id),
        "change_type":     diff_change.change_type,
        "change_summary":  diff_change.ai_change_summary,
        "approved_at":     diff_review.reviewed_at.isoformat(),
        "approved_by":     diff_review.reviewed_by_name,
        "diff_review_id":  str(diff_review.id),
    }
    chunk.metadata = {**chunk.metadata, "change_history": existing + [new_entry]}
    await db.commit()
```

**Ví dụ metadata chunk sau 2 lần approve:**

```json
{
  "screen": "Login",
  "section": "Button states",
  "doc_type": "basic_design",
  "change_history": [
    {
      "from_version_no": 1, "to_version_no": 2,
      "change_type": "modified",
      "change_summary": "Đổi màu button lỗi từ đỏ sang xanh (#2196F3)",
      "approved_at": "2025-06-01T14:00:00Z",
      "approved_by": "Nguyen PM",
      "diff_review_id": "diff-uuid-001"
    },
    {
      "from_version_no": 2, "to_version_no": 3,
      "change_type": "modified",
      "change_summary": "Thêm tooltip mô tả lỗi khi hover vào button",
      "approved_at": "2025-06-08T14:00:00Z",
      "approved_by": "Nguyen PM",
      "diff_review_id": "diff-uuid-002"
    }
  ]
}
```

**Ý nghĩa quan trọng với Q&A:** Khi RAG tìm thấy chunk này, `change_history` cho phép AI biết chunk đã thay đổi bao nhiêu lần và thay đổi gì — từ đó trả lời câu hỏi "trước đây v1 là X, bây giờ v2 là Y".

#### 2.6.3 AI change summary per change

Khi generate diff, AI tạo 1 câu tóm tắt ngắn cho từng change (lưu vào `diff_changes.ai_change_summary`):

```python
async def generate_change_summary(change: DiffChange) -> str:
    prompt = f"""Tóm tắt thay đổi trong 1 câu ngắn (tối đa 15 từ) bằng tiếng Việt.
Loại: {change.change_type}
Cũ: {(change.content_before or '')[:200]}
Mới: {(change.content_after or '')[:200]}
Chỉ trả về câu tóm tắt, không giải thích."""
    resp = await claude_client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=60,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text.strip()
# modified → "Đổi màu button lỗi từ đỏ sang xanh (#2196F3)"
# added    → "Thêm section OAuth Google login mới"
# removed  → "Xoá phần mô tả loading state"
```

#### 2.6.4 Tab "Lịch sử thay đổi" trong S5 Version detail

S5 bổ sung tab mới hiển thị toàn bộ diff timeline:

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Nội dung preview] [Chunks (12)] [Testcases (8)] [Lịch sử thay đổi] │
├──────────────────────────────────────────────────────────────────────┤
│ v3 ← v2  ·  08/06/2025  ·  Nguyen PM approve  ·  3 thay đổi        │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │ ● Sửa §Button states  Đổi màu button lỗi từ đỏ → xanh  [Xem] │   │
│ │ + Thêm §OAuth Section Thêm OAuth Google login           [Xem] │   │
│ │ - Xoá §Loading state  Xoá phần loading state            [Xem] │   │
│ └────────────────────────────────────────────────────────────────┘   │
│ v2 ← v1  ·  01/06/2025  ·  Admin User approve  ·  2 thay đổi       │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │ ● Sửa §Layout         Đổi card width từ 360px → 400px   [Xem] │   │
│ │ + Thêm §Validation    Thêm rule validate email format    [Xem] │   │
│ └────────────────────────────────────────────────────────────────┘   │
│ v1  ·  15/05/2025  ·  Admin User tạo  ·  Bản khởi tạo              │
└──────────────────────────────────────────────────────────────────────┘
```

Click "Xem" → mở S7 readonly, scroll đến change block đó.

---


### 2.7 Validation Rules

#### VL-S7-001 — Quyền xem diff
- **Trigger:** Load S7
- **Rule:** `project_members.role` IN (`owner`, `pm`) hoặc system admin
- **Xử lý:** 403 → redirect về S3 với toast "Bạn không có quyền review tài liệu"
- **Scope:** Server only (UI đã ẩn nút So sánh với QC/Dev)

#### VL-S7-002 — 2 version phải thuộc cùng document
- **Trigger:** Load diff
- **Rule:** `old_version.document_id == new_version.document_id`
- **Error message:** "Không thể so sánh 2 version thuộc tài liệu khác nhau"
- **Scope:** Server only

#### VL-S7-003 — Version mới phải mới hơn version cũ
- **Trigger:** Chọn version trong dropdown
- **Rule:** `new_version.version_no > old_version.version_no`
- **Error message:** "Version mới phải có số version lớn hơn version cũ"
- **Scope:** Client + Server

#### VL-S7-004 — Không approve khi diff đang processing
- **Trigger:** Click Approve
- **Rule:** `diff_review.status == 'ready'` (không phải `pending` hoặc `processing`)
- **Error message:** "Diff đang được AI phân tích. Vui lòng đợi."
- **Scope:** Client (disable button) + Server

#### VL-S7-005 — Phải approve/reject ít nhất 1 change
- **Trigger:** Click "Approve đã chọn"
- **Rule:** Số change có status=approved > 0
- **Error message:** Nút disabled khi không có change nào được approve
- **Scope:** Client only

#### VL-S7-006 — Không re-review diff đã complete
- **Trigger:** Load S7 với diff đã approved/rejected toàn bộ
- **Rule:** `diff_review.status != 'approved'`
- **Xử lý:** Hiện banner readonly "Đã hoàn tất review vào [ngày]" — chỉ xem, không thể thay đổi
- **Scope:** Server trả flag `is_readonly: true`

---

### 2.8 Phân quyền

| Action | Owner | PM | QC | Dev |
|---|:---:|:---:|:---:|:---:|
| Xem màn hình S7 | ✓ | ✓ | — | — |
| Chọn version để compare | ✓ | ✓ | — | — |
| Approve từng change | ✓ | ✓ | — | — |
| Reject từng change | ✓ | ✓ | — | — |
| Approve tất cả (shortcut) | ✓ | ✓ | — | — |
| Xem AI Summary | ✓ | ✓ | — | — |

---

### 2.9 URL schema

```
/projects/{project_slug}/documents/{document_id}/diff

Query params:
  old_version_id={uuid}   -- version base (trái)
  new_version_id={uuid}   -- version head (phải)
  diff_review_id={uuid}   -- nếu đã có diff_review record
  change_id={uuid}        -- scroll đến change này (từ notification)
```

---

## 3. API Design

### 3.1 Tổng quan

| Method | Endpoint | Mô tả | Auth |
|---|---|---|---|
| GET | `/api/v1/documents/{document_id}/diff` | Lấy hoặc tạo diff giữa 2 version | Bearer (pm/owner) |
| GET | `/api/v1/diff-reviews/{diff_review_id}` | Chi tiết diff review | Bearer (pm/owner) |
| GET | `/api/v1/diff-reviews/{diff_review_id}/status` | Poll trạng thái AI processing | Bearer (pm/owner) |
| PATCH | `/api/v1/diff-changes/{change_id}` | Approve/reject 1 change | Bearer (pm/owner) |
| POST | `/api/v1/diff-reviews/{diff_review_id}/submit` | Submit toàn bộ decisions → re-embed | Bearer (pm/owner) |
| POST | `/api/v1/diff-reviews/{diff_review_id}/approve-all` | Approve tất cả shortcut | Bearer (pm/owner) |

---

### 3.2 GET /api/v1/documents/{document_id}/diff

**Mô tả:** Lấy diff giữa 2 version. Nếu diff đã tồn tại trong DB → trả luôn. Nếu chưa → tạo mới và enqueue Celery job AI analysis. Trả 202 nếu đang processing.

**Auth:** Bearer (pm hoặc owner của project)  
**Rate limit:** 30 lần / phút / user  
**Idempotent:** Có (cùng params → cùng kết quả)

#### Query parameters

| Param | Type | Bắt buộc | Mô tả | Mặc định |
|---|---|---|---|---|
| `old_version_id` | UUID | Không | Version base | Latest approved version |
| `new_version_id` | UUID | Không | Version head | Latest ready_for_review version |

#### Request

```
GET /api/v1/documents/doc-uuid-001/diff?old_version_id=ver-uuid-002&new_version_id=ver-uuid-003
Authorization: Bearer eyJ...
```

#### Response 200 — Diff ready

```json
{
  "diff_review": {
    "id": "diff-uuid-001",
    "document_id": "doc-uuid-001",
    "old_version": {
      "id": "ver-uuid-002",
      "version_no": 2,
      "status": "approved",
      "created_at": "2025-06-01T09:00:00Z",
      "created_by_name": "Nguyen PM"
    },
    "new_version": {
      "id": "ver-uuid-003",
      "version_no": 3,
      "status": "ready_for_review",
      "created_at": "2025-06-08T10:00:00Z",
      "created_by_name": "Nguyen PM",
      "changelog_md": "## Changelog v3\n### Sửa đổi\n- Đổi màu button lỗi từ đỏ sang xanh"
    },
    "status": "ready",
    "is_readonly": false,
    "ai_summary": "Tìm thấy 3 thay đổi: 1 chỉnh sửa (màu button), 1 thêm mới (OAuth section), 1 xoá bỏ (loading state).",
    "total_changes": 3,
    "approved_count": 0,
    "rejected_count": 0,
    "pending_count": 3,
    "reviewed_at": null,
    "reviewed_by": null,
    "created_at": "2025-06-08T11:00:00Z"
  },
  "changes": [
    {
      "id": "change-uuid-001",
      "change_index": 1,
      "change_type": "modified",
      "approval_status": "pending",
      "chunk_old": {
        "id": "chunk-uuid-002",
        "chunk_index": 1,
        "content_text": "## Button states\n\nButton LOGIN cần có màu ĐỎ khi người dùng nhập sai thông tin đăng nhập.",
        "section": "Button states"
      },
      "chunk_new": {
        "id": "chunk-uuid-new-002",
        "chunk_index": 1,
        "content_text": "## Button states\n\nButton LOGIN cần có màu XANH (#2196F3) khi người dùng nhập sai thông tin đăng nhập.",
        "section": "Button states"
      },
      "word_diff_old": "## Button states\n\nButton LOGIN cần có màu <del>ĐỎ</del> khi người dùng nhập sai thông tin đăng nhập.",
      "word_diff_new": "## Button states\n\nButton LOGIN cần có màu <ins>XANH (#2196F3)</ins> khi người dùng nhập sai thông tin đăng nhập.",
      "similarity_score": 0.82,
      "affected_testcases": [
        {
          "id": "tc-uuid-001",
          "title": "Login sai password → hiện lỗi đỏ dưới field",
          "priority": "high"
        },
        {
          "id": "tc-uuid-002",
          "title": "Button đổi màu khi nhập sai",
          "priority": "medium"
        },
        {
          "id": "tc-uuid-007",
          "title": "UI state khi có lỗi validation",
          "priority": "high"
        }
      ]
    },
    {
      "id": "change-uuid-002",
      "change_index": 2,
      "change_type": "added",
      "approval_status": "pending",
      "chunk_old": null,
      "chunk_new": {
        "id": "chunk-uuid-new-010",
        "chunk_index": 10,
        "content_text": "## OAuth Section\n\nHệ thống hỗ trợ đăng nhập qua Google OAuth 2.0...",
        "section": "OAuth Section"
      },
      "word_diff_old": null,
      "word_diff_new": "## OAuth Section\n\n<ins>Hệ thống hỗ trợ đăng nhập qua Google OAuth 2.0...</ins>",
      "similarity_score": null,
      "affected_testcases": []
    },
    {
      "id": "change-uuid-003",
      "change_index": 3,
      "change_type": "removed",
      "approval_status": "pending",
      "chunk_old": {
        "id": "chunk-uuid-008",
        "chunk_index": 8,
        "content_text": "## Loading state\n\nKhi đang xử lý request, button hiển thị spinner...",
        "section": "Loading state"
      },
      "chunk_new": null,
      "word_diff_old": "## Loading state\n\n<del>Khi đang xử lý request, button hiển thị spinner...</del>",
      "word_diff_new": null,
      "similarity_score": null,
      "affected_testcases": [
        {
          "id": "tc-uuid-015",
          "title": "Kiểm tra spinner hiện khi đang login",
          "priority": "low"
        }
      ]
    }
  ]
}
```

#### Response 202 — Diff đang processing

```json
{
  "diff_review": {
    "id": "diff-uuid-001",
    "status": "processing",
    "estimated_seconds": 20,
    "created_at": "2025-06-08T11:00:00Z"
  },
  "changes": [],
  "message": "AI đang phân tích sự khác biệt giữa 2 version. Vui lòng chờ."
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | old_version và new_version trùng nhau | — |
| 403 | Không có quyền xem diff | Không phải pm/owner |
| 404 | Document hoặc version không tồn tại | — |
| 422 | Version không thuộc cùng document | Cross-document compare |
| 422 | Version mới phải có số lớn hơn version cũ | version_no validation |

---

### 3.3 GET /api/v1/diff-reviews/{diff_review_id}/status

**Mô tả:** Kiểm tra trạng thái AI processing. Dùng để polling khi diff đang được tạo.

**Auth:** Bearer (pm/owner)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có

#### Response 200

```json
{
  "diff_review_id": "diff-uuid-001",
  "status": "ready",
  "progress": {
    "total_chunks_old": 11,
    "total_chunks_new": 13,
    "processed_pairs": 24,
    "percentage": 100
  },
  "total_changes": 3,
  "updated_at": "2025-06-08T11:00:20Z"
}
```

**Status values:**

| Status | Mô tả |
|---|---|
| `pending` | Chờ Celery job bắt đầu |
| `processing` | AI đang so sánh chunks |
| `ready` | Diff đã hoàn thành, sẵn sàng review |
| `approved` | Toàn bộ changes đã được submit |

---

### 3.4 PATCH /api/v1/diff-changes/{change_id}

**Mô tả:** Approve hoặc reject 1 change cụ thể. **Chỉ cập nhật trạng thái local trong diff_changes, chưa trigger re-embed.** Re-embed chỉ xảy ra sau khi gọi `/submit`.

**Auth:** Bearer (pm/owner)  
**Rate limit:** 60 lần / phút / user  
**Idempotent:** Có (approve 2 lần vẫn = approved)

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `approval_status` | string | Có | `approved` \| `rejected` \| `pending` |
| `approve_note` | string | Không | Ghi chú khi reject (lý do) |

```json
{
  "approval_status": "approved"
}
```

```json
{
  "approval_status": "rejected",
  "approve_note": "Màu đỏ vẫn phù hợp với brand guideline, không nên đổi sang xanh."
}
```

#### Response 200

```json
{
  "id": "change-uuid-001",
  "approval_status": "approved",
  "approved_by": {
    "id": "uuid-pm",
    "full_name": "Nguyen PM"
  },
  "approved_at": "2025-06-10T10:00:00Z",
  "approve_note": null,
  "diff_review_summary": {
    "approved_count": 1,
    "rejected_count": 0,
    "pending_count": 2
  }
}
```

**Ghi chú `diff_review_summary`:** Trả về counter mới nhất để FE cập nhật action bar mà không cần gọi lại toàn bộ diff.

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | approval_status không hợp lệ | Không phải approved/rejected/pending |
| 403 | Không có quyền | Không phải pm/owner |
| 404 | Change không tồn tại | — |
| 409 | Diff đã được submit — không thể thay đổi | diff_review.status = approved |

---

### 3.5 POST /api/v1/diff-reviews/{diff_review_id}/submit

**Mô tả:** Submit tất cả decisions (approve/reject). Server xử lý: re-embed approved chunks vào pgvector, cập nhật version status, flag testcase liên quan. Đây là bước **kích hoạt thực sự** — trước lệnh submit, mọi approve/reject chỉ là local state.

**Auth:** Bearer (pm/owner)  
**Rate limit:** 5 lần / phút / user (tránh re-submit)  
**Idempotent:** Không

#### Request body

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `review_note` | string | Không | Ghi chú tổng thể cho lần review |

```json
{
  "review_note": "Approve đổi màu button và thêm OAuth. Reject xoá loading state."
}
```

#### Server xử lý sau submit

```
POST /submit → server xử lý:
    │
    ├─ Validate: tất cả changes phải có status approved/rejected (không pending)
    │       └─ Nếu còn pending: 400 "Còn {N} thay đổi chưa được review"
    │
    ├─ Update diff_review.status = "approved"
    ├─ Update diff_review.reviewed_by, reviewed_at, review_note
    │
    ├─ Với approved changes:
    │   ├─ Xoá embedding cũ (chunk_old) khỏi pgvector
    │   └─ Thêm embedding mới (chunk_new) vào pgvector
    │       (Celery job: re_embed_approved_chunks)
    │
    ├─ Với rejected changes:
    │   └─ Giữ nguyên chunk cũ trong pgvector
    │
    ├─ Update doc_version.status:
    │   ├─ Nếu có ít nhất 1 approved: new_version.status = "approved"
    │   └─ Nếu tất cả rejected: new_version.status = "rejected"
    │
    └─ Flag testcase:
            - Với mỗi TC liên quan đến approved/removed chunk
            - SET testcases.needs_review = true
            - Tạo notification cho QC
```

#### Response 202

```json
{
  "diff_review_id": "diff-uuid-001",
  "status": "processing",
  "summary": {
    "approved_changes": 2,
    "rejected_changes": 1,
    "chunks_to_reembed": 2,
    "testcases_flagged": 4
  },
  "new_version_status": "approved",
  "reembed_job_id": "celery-reembed-uuid",
  "message": "Đang re-embedding 2 chunk đã approve. Tài liệu sẽ sẵn sàng trong Q&A sau vài phút."
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 400 | Còn {N} thay đổi chưa được review | Phải approve/reject tất cả |
| 403 | Không có quyền | — |
| 404 | Diff review không tồn tại | — |
| 409 | Diff đã được submit trước đó | diff_review.status = approved |

---

### 3.6 POST /api/v1/diff-reviews/{diff_review_id}/approve-all

**Mô tả:** Shortcut approve tất cả changes và submit ngay. Không qua S8. Chỉ Admin/Owner.

**Auth:** Bearer (owner hoặc system admin)  
**Rate limit:** 5 lần / phút / user  
**Idempotent:** Không

#### Request body

```json
{
  "review_note": "Approve toàn bộ — kiểm tra kỹ changelog trước."
}
```

#### Response 202

```json
{
  "diff_review_id": "diff-uuid-001",
  "status": "processing",
  "summary": {
    "approved_changes": 3,
    "rejected_changes": 0,
    "chunks_to_reembed": 3,
    "testcases_flagged": 4
  },
  "new_version_status": "approved",
  "message": "Đã approve tất cả 3 thay đổi. Đang re-embedding..."
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 403 | Chỉ Owner/Admin mới dùng approve-all | PM không dùng được shortcut này |
| 404 | Diff review không tồn tại | — |
| 409 | Diff đã được submit | — |

---

### 3.7 GET /api/v1/documents/{document_id}/diff-history

**Mô tả:** Lấy toàn bộ lịch sử diff đã được approve của 1 tài liệu. Dùng cho tab "Lịch sử thay đổi" trong S5 Version detail. Chỉ trả về diff đã `approved` — không trả `pending`/`processing`.

**Auth:** Bearer (member của project)
**Rate limit:** 60 lần / phút / user
**Idempotent:** Có

#### Request

```
GET /api/v1/documents/doc-uuid-001/diff-history
Authorization: Bearer eyJ...
```

#### Response 200

```json
{
  "document_id": "doc-uuid-001",
  "screen_name": "Login",
  "doc_type": "basic_design",
  "diff_history": [
    {
      "diff_review_id": "diff-uuid-002",
      "from_version": { "id": "ver-uuid-002", "version_no": 2 },
      "to_version":   { "id": "ver-uuid-003", "version_no": 3 },
      "approved_at": "2025-06-08T14:00:00Z",
      "approved_by": { "id": "uuid-pm", "full_name": "Nguyen PM" },
      "review_note": "Approve đổi màu button và thêm OAuth",
      "total_changes": 3,
      "changes": [
        {
          "id": "change-uuid-001",
          "change_index": 1,
          "change_type": "modified",
          "section": "Button states",
          "ai_change_summary": "Đổi màu button lỗi từ đỏ sang xanh (#2196F3)",
          "chunk_old_id": "chunk-uuid-002",
          "chunk_new_id": "chunk-uuid-new-002"
        },
        {
          "id": "change-uuid-002",
          "change_index": 2,
          "change_type": "added",
          "section": "OAuth Section",
          "ai_change_summary": "Thêm section OAuth Google login mới",
          "chunk_old_id": null,
          "chunk_new_id": "chunk-uuid-new-010"
        },
        {
          "id": "change-uuid-003",
          "change_index": 3,
          "change_type": "removed",
          "section": "Loading state",
          "ai_change_summary": "Xoá phần mô tả loading state",
          "chunk_old_id": "chunk-uuid-008",
          "chunk_new_id": null
        }
      ]
    },
    {
      "diff_review_id": "diff-uuid-001",
      "from_version": { "id": "ver-uuid-001", "version_no": 1 },
      "to_version":   { "id": "ver-uuid-002", "version_no": 2 },
      "approved_at": "2025-06-01T14:00:00Z",
      "approved_by": { "id": "uuid-admin", "full_name": "Admin User" },
      "review_note": null,
      "total_changes": 2,
      "changes": [
        {
          "id": "change-uuid-old-001",
          "change_index": 1,
          "change_type": "modified",
          "section": "Layout",
          "ai_change_summary": "Đổi card width từ 360px → 400px",
          "chunk_old_id": "chunk-uuid-001-v1",
          "chunk_new_id": "chunk-uuid-001-v2"
        }
      ]
    }
  ],
  "total_diff_reviews": 2
}
```

#### Error responses

| Code | Message | Ghi chú |
|---|---|---|
| 401 | Chưa xác thực | — |
| 403 | Không có quyền | Không phải member |
| 404 | Document không tồn tại | — |

---


## 4. Database schema bổ sung

Bổ sung thêm cột vào `diff_changes` (đã có trong schema chính):

```sql
-- Thêm cột word_diff vào diff_changes
ALTER TABLE diff_changes ADD COLUMN IF NOT EXISTS
  word_diff_old  TEXT,   -- HTML với <del> tags
  word_diff_new  TEXT,   -- HTML với <ins> tags
  change_index   INT,    -- Thứ tự hiển thị
  similarity_score FLOAT; -- Cosine similarity giữa old và new chunk

-- Thêm cột vào diff_reviews
ALTER TABLE diff_reviews ADD COLUMN IF NOT EXISTS
  ai_summary     TEXT,   -- Tóm tắt AI
  total_changes  INT DEFAULT 0,
  approved_count INT DEFAULT 0,
  rejected_count INT DEFAULT 0;

-- Index
CREATE INDEX idx_diff_changes_review_status
  ON diff_changes(diff_review_id, approval_status);
CREATE INDEX idx_diff_changes_index
  ON diff_changes(diff_review_id, change_index);
```

---

## 5. Celery tasks

```python
# app/tasks/diff_tasks.py

@shared_task(bind=True, max_retries=3)
def generate_diff_task(self, diff_review_id: str):
    """Phân tích diff AI giữa 2 version"""
    try:
        with get_sync_db() as db:
            review = db.get(DiffReview, diff_review_id)
            old_chunks = get_chunks_by_version(db, review.old_version_id)
            new_chunks = get_chunks_by_version(db, review.new_version_id)

            # Algorithm: match chunks bằng embedding similarity
            changes = match_chunks_and_diff(old_chunks, new_chunks)

            # Generate AI summary
            summary = generate_ai_summary(changes)

            # Analyze TC impact
            tc_impact = analyze_tc_impact(db, changes)

            # Lưu vào DB
            save_diff_changes(db, diff_review_id, changes, tc_impact)
            update_diff_review(db, diff_review_id, summary, status='ready')

    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


@shared_task(bind=True, max_retries=3)
def reembed_approved_chunks_task(self, diff_review_id: str):
    """Re-embed các chunk được approve vào pgvector"""
    try:
        with get_sync_db() as db:
            approved_changes = get_approved_changes(db, diff_review_id)
            emb_service = EmbeddingService()

            for change in approved_changes:
                if change.change_type in ('modified', 'added'):
                    # Embed chunk mới
                    new_chunk = db.get(Chunk, change.chunk_new_id)
                    embedding = emb_service.embed(new_chunk.content_text)
                    upsert_embedding(db, new_chunk.id, embedding)

                if change.change_type in ('modified', 'removed'):
                    # Xoá embedding cũ
                    if change.chunk_old_id:
                        delete_embedding(db, change.chunk_old_id)

            # Flag affected testcases
            flag_affected_testcases(db, diff_review_id)

    except Exception as exc:
        raise self.retry(exc=exc, countdown=15)
```

---

## 6. Màn hình và component sử dụng API

| Màn hình / Component | API được dùng | Ghi chú |
|---|---|---|
| S7 load diff | `GET /documents/{id}/diff` | Tạo hoặc lấy diff |
| S7 polling status | `GET /diff-reviews/{id}/status` | Mỗi 3s khi processing |
| S7 approve 1 change | `PATCH /diff-changes/{id}` | Local state + API |
| S7 reject 1 change | `PATCH /diff-changes/{id}` | Local state + API |
| S7 "Approve đã chọn" | Navigate → S8 với params | Routing |
| S7 "Approve tất cả" | `POST /diff-reviews/{id}/approve-all` | Owner/Admin shortcut |
| S8 Approve panel | `POST /diff-reviews/{id}/submit` | Final submission |
| S3 nút "So sánh" | Navigate → S7 | Routing |
| S5 nút "So sánh với version trước" | Navigate → S7 | Routing |
| Notification click | Navigate → S7 với change_id | Scroll to change |
| S5 tab "Lịch sử thay đổi" | `GET /documents/{id}/diff-history` | Timeline tất cả diff |
| S5 click "Xem" trong history | Navigate → S7 readonly | Xem diff cụ thể |

---

## 7. Liên kết tài liệu

| Tài liệu | Liên quan |
|---|---|
| Basic Design — S3 Document list | Entry point → S7 |
| Basic Design — S5 Version detail | Entry point → S7 |
| Basic Design — S8 Approve panel | Flow tiếp theo sau S7 |
| Basic Design — S12 TC list | TC bị flag sau approve |
| Database schema — diff_reviews | status, ai_summary, counts |
| Database schema — diff_changes | change_type, word_diff, approval_status |
| Database schema — chunk_embeddings | Re-embed sau approve |
| Flow Upload & Embedding | Celery pipeline tương tự |
| API Design — S4 Upload | Auto-trigger diff sau upload version mới |

---

*Tài liệu này được tạo bởi hệ thống QC Master — phiên bản 1.0*
