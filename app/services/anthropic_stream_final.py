"""Streaming completion + robust JSON extraction for long Anthropic requests."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
import uuid
from typing import Any

import httpx
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


def build_anthropic_client(
    *,
    api_key: str,
    base_url: str | None = None,
    request_timeout_seconds: float = 1800.0,
    connect_timeout_seconds: float = 30.0,
) -> AsyncAnthropic:
    """Tạo AsyncAnthropic client với timeout dài (mặc định 30 phút) — phù hợp
    cho prompt lớn (references + spec + Q&A) và stream lâu. Nếu chạy qua proxy
    (Cloudflare, OpenRouter, v.v.) đặt giới hạn ngắn hơn, lỗi sẽ vẫn xảy ra ở
    proxy chứ không phải ở client phía ta.
    """
    # Anthropic SDK tự đọc env ANTHROPIC_BASE_URL nếu kwarg `base_url` không
    # truyền. Khi docker-compose injects `ANTHROPIC_BASE_URL=""` (rỗng) do
    # `${ANTHROPIC_BASE_URL:-}`, SDK lấy "" làm base URL → request URL thiếu
    # scheme → httpx báo `UnsupportedProtocol`. Pop env nếu rỗng để SDK fallback
    # về default https://api.anthropic.com.
    env_burl = os.environ.get("ANTHROPIC_BASE_URL")
    if env_burl is not None and not env_burl.strip():
        os.environ.pop("ANTHROPIC_BASE_URL", None)

    timeout = httpx.Timeout(
        request_timeout_seconds,
        connect=connect_timeout_seconds,
        read=request_timeout_seconds,
        write=request_timeout_seconds,
        pool=connect_timeout_seconds,
    )
    kw: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
    if base_url and base_url.strip():
        kw["base_url"] = base_url.strip()
    return AsyncAnthropic(**kw)


async def _stream_once(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    user_text: str,
    thinking: dict[str, Any] | None,
) -> tuple[str, Any | None, int]:
    """Single streaming attempt. Returns (text, final_message, bytes_received).

    Raises whatever the SDK / network layer raises so caller can decide retry.
    """
    parts: list[str] = []
    received = 0
    final_msg: Any | None = None
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user_text}],
        **({"thinking": thinking} if thinking is not None else {}),
    ) as stream:
        async for event in stream:
            et = getattr(event, "type", None)
            if et == "text" and getattr(event, "text", None):
                parts.append(event.text)
                received += len(event.text)
            elif et == "input_json" and getattr(event, "partial_json", None):
                s = str(event.partial_json)
                parts.append(s)
                received += len(s)

        final_msg = await stream.get_final_message()
        if not parts and final_msg is not None:
            for block in getattr(final_msg, "content", []) or []:
                if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                    parts.append(block.text)
                    received += len(block.text)
    return "".join(parts), final_msg, received


async def stream_user_message_text(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    user_text: str,
    thinking: dict[str, Any] | None = None,
    max_attempts: int = 2,
    retry_backoff_seconds: float = 5.0,
) -> str:
    """Accumulate assistant content via Messages Streaming API with retry.

    Auto-retries up to `max_attempts` lần khi gặp lỗi network/timeout. Mỗi lần
    fail log đầy đủ exception type + message + thời gian + bytes nhận được để
    debug nguyên nhân thực (Cloudflare 524, upstream channel down, SDK timeout, …).
    """
    last_exc: BaseException | None = None
    final_msg: Any | None = None
    out_text = ""
    prompt_len = len(user_text)

    for attempt in range(1, max_attempts + 1):
        t0 = time.monotonic()
        try:
            out_text, final_msg, received = await _stream_once(
                client,
                model=model,
                max_tokens=max_tokens,
                user_text=user_text,
                thinking=thinking,
            )
            elapsed = time.monotonic() - t0
            stop_reason = getattr(final_msg, "stop_reason", None) if final_msg is not None else None
            logger.info(
                "anthropic stream OK attempt=%d elapsed=%.1fs prompt_chars=%d "
                "received_chars=%d model=%s stop_reason=%s",
                attempt,
                elapsed,
                prompt_len,
                received,
                model,
                stop_reason,
            )
            if stop_reason == "max_tokens":
                logger.warning(
                    "anthropic stream hit max_tokens=%d — output likely TRUNCATED. "
                    "Increase max_tokens or shorten prompt (prompt_chars=%d, received_chars=%d).",
                    max_tokens,
                    prompt_len,
                    received,
                )
            break
        except Exception as exc:
            elapsed = time.monotonic() - t0
            last_exc = exc
            logger.warning(
                "anthropic stream FAIL attempt=%d/%d elapsed=%.1fs prompt_chars=%d "
                "model=%s exc_type=%s exc=%s",
                attempt,
                max_attempts,
                elapsed,
                prompt_len,
                model,
                type(exc).__name__,
                str(exc)[:500],
                exc_info=True,
            )
            if attempt < max_attempts:
                await asyncio.sleep(retry_backoff_seconds * attempt)
                continue
            # Out of attempts — surface a richer error including the underlying cause.
            raise ValueError(
                f"LLM streaming request failed after {max_attempts} attempts "
                f"(elapsed={elapsed:.1f}s, prompt_chars={prompt_len}). "
                f"Underlying error: {type(exc).__name__}: {str(exc)[:300]}. "
                "If you're routing through a gateway/proxy (e.g., Cloudflare), "
                "it may be cutting the connection (idle timeout / 524). "
                "Possible fixes: increase ANTHROPIC client timeout, switch to direct "
                "Anthropic endpoint, reduce prompt size (references / chunks)."
            ) from exc

    out = out_text.strip()
    if not out:
        diag = ""
        if final_msg is not None:
            block_types = [getattr(b, "type", None) for b in (getattr(final_msg, "content", []) or [])]
            stop_reason = getattr(final_msg, "stop_reason", None)
            diag = f" stop_reason={stop_reason!r} content_block_types={block_types!r}"
        raise ValueError(
            "LLM output is empty (no text blocks produced)."
            + diag
            + " Likely causes: upstream timed out/was cut off (e.g., Cloudflare 524), "
            "or the model returned only non-text blocks (e.g., thinking) and no final answer."
        )
    # Squelch unused-var lint for `last_exc` in success path.
    _ = last_exc
    return out


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_code_fences(s: str) -> str:
    return s.replace("```json", "").replace("```", "").strip()


def _balance_brackets(s: str) -> str:
    """Đếm bracket bỏ qua nội dung trong string, append closer còn thiếu.

    Chỉ dùng làm last-resort khi JSON có vẻ bị cắt giữa chừng (LLM hit
    max_tokens). Không repair string chưa đóng quote.
    """
    stack: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    if in_str:
        # nếu đang giữa 1 string thì có khả năng JSON cắt dở giữa chuỗi → đóng quote luôn
        s += '"'
    closers = {"{": "}", "[": "]"}
    return s + "".join(closers[c] for c in reversed(stack))


def _dump_failed_output(raw: str, *, kind: str, error: str) -> str | None:
    """Ghi raw LLM output ra file tạm để debug. Trả về path file (hoặc None)."""
    try:
        tmpdir = os.getenv("QC_LLM_DUMP_DIR") or tempfile.gettempdir()
        os.makedirs(tmpdir, exist_ok=True)
        fname = f"qcmaster-llm-failed-{kind}-{int(time.time())}-{uuid.uuid4().hex[:8]}.txt"
        path = os.path.join(tmpdir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=== JSON parse error ({kind}) ===\n{error}\n\n=== Raw LLM output ===\n")
            f.write(raw)
        return path
    except OSError:
        return None


def _error_preview(s: str, pos: int, *, window: int = 200) -> str:
    """Trả về đoạn ±window chars quanh `pos`, escape newline cho dễ đọc trong log."""
    a = max(0, pos - window)
    b = min(len(s), pos + window)
    head = "..." if a > 0 else ""
    tail = "..." if b < len(s) else ""
    snippet = s[a:b].replace("\n", "\\n")
    return f"{head}{snippet}{tail}"


def _try_parse_json(s: str, *, kind: str) -> tuple[Any, str]:
    """Thử nhiều chiến lược parse JSON từ output LLM bẩn / bị cắt.

    `kind` ("object" | "array") quyết định mở đầu mong đợi (`{` hay `[`) khi
    dò vị trí JSON trong chuỗi có trailing/leading text.

    Returns (value, strategy_used). Raise json.JSONDecodeError cuối cùng nếu
    không strategy nào thành công.
    """
    last_err: Exception | None = None

    try:
        return json.loads(s), "direct"
    except json.JSONDecodeError as e:
        last_err = e

    expected_open = "[" if kind == "array" else "{"
    decoder = json.JSONDecoder()
    idx = s.find(expected_open)
    if idx >= 0:
        try:
            val, _ = decoder.raw_decode(s[idx:])
            return val, f"raw_decode({expected_open})"
        except json.JSONDecodeError as e:
            last_err = e

    cleaned = _TRAILING_COMMA_RE.sub(r"\1", s)
    if cleaned != s:
        try:
            return json.loads(cleaned), "strip_trailing_comma"
        except json.JSONDecodeError as e:
            last_err = e

    balanced = _balance_brackets(cleaned)
    if balanced != cleaned:
        try:
            return json.loads(balanced), "balance_brackets"
        except json.JSONDecodeError as e:
            last_err = e

    assert last_err is not None
    raise last_err


def _loads_llm_json(raw_text: str, *, kind: str) -> Any:
    if not (raw_text and raw_text.strip()):
        raise ValueError("LLM output is empty")
    s = _strip_code_fences(raw_text)
    try:
        val, strategy = _try_parse_json(s, kind=kind)
        if strategy != "direct":
            logger.warning(
                "JSON parse recovered via strategy=%s kind=%s raw_len=%d",
                strategy,
                kind,
                len(s),
            )
        return val
    except json.JSONDecodeError as e:
        dump_path = _dump_failed_output(raw_text, kind=kind, error=str(e))
        preview = _error_preview(s, e.pos)
        end_tail = s[-300:].replace("\n", "\\n")
        logger.error(
            "LLM JSON parse FAILED kind=%s err=%s pos=%d (line=%d col=%d) raw_len=%d "
            "dump=%s\n  context_around_error: %s\n  raw_tail(last 300): %s",
            kind,
            e.msg,
            e.pos,
            e.lineno,
            e.colno,
            len(s),
            dump_path or "(failed to dump)",
            preview,
            end_tail,
        )
        hint = (
            "If output looks cut off near the end → LLM hit max_tokens; increase max_tokens "
            "or shorten prompt. "
            "If error mentions unescaped quote/newline mid-string → ask model to JSON-escape "
            "string content (especially markdown with \" or newlines)."
        )
        raise ValueError(
            f"LLM output is not valid JSON ({kind}): {e.msg} at pos={e.pos} "
            f"(line {e.lineno}, col {e.colno}). raw_len={len(s)}. "
            f"Dumped raw output to: {dump_path or '(dump failed)'}. {hint}"
        ) from e


def loads_llm_json_object(raw_text: str) -> dict[str, Any]:
    val = _loads_llm_json(raw_text, kind="object")
    if not isinstance(val, dict):
        raise ValueError("LLM output is not a JSON object")
    return val


def loads_llm_json_array(raw_text: str) -> list[Any]:
    val = _loads_llm_json(raw_text, kind="array")
    if not isinstance(val, list):
        raise ValueError("LLM output is not a JSON array")
    return val
