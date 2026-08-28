from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import urllib.error
import urllib.request
import base64
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from comparison_engine import ComparisonResult, FileComparison

MAX_SHARED_RESULTS = 5
_KEY_PREFIX = "filecompare:share:"
_HISTORY_KEY = "filecompare:shares"
_SESSION_PREFIX = "filecompare:session:"
SESSION_TTL_SECONDS = 6 * 60 * 60


def _pack_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return "z1:" + base64.urlsafe_b64encode(compressed).decode("ascii")


def _unpack_json(raw: str) -> Any:
    if raw.startswith("z1:"):
        compressed = base64.urlsafe_b64decode(raw[3:].encode("ascii"))
        return json.loads(zlib.decompress(compressed).decode("utf-8"))
    return json.loads(raw)


def _file_to_dict(item: FileComparison) -> dict[str, Any]:
    return {
        "relative_path": item.relative_path,
        "status": item.status,
        "is_text": item.is_text,
        "message": item.message,
        "left_lines": item.left_lines,
        "right_lines": item.right_lines,
    }


def result_to_dict(result: ComparisonResult) -> dict[str, Any]:
    return {
        "matched_files": [_file_to_dict(item) for item in result.matched_files],
        "mismatched_files": [_file_to_dict(item) for item in result.mismatched_files],
        "only_in_left_files": list(result.only_in_left_files),
        "only_in_right_files": list(result.only_in_right_files),
        "only_in_left_folders": list(result.only_in_left_folders),
        "only_in_right_folders": list(result.only_in_right_folders),
    }


def _file_from_dict(data: dict[str, Any]) -> FileComparison:
    return FileComparison(
        relative_path=str(data.get("relative_path", "")),
        status=str(data.get("status", "")),
        is_text=bool(data.get("is_text", False)),
        message=str(data.get("message", "")),
        left_lines=list(data.get("left_lines") or []),
        right_lines=list(data.get("right_lines") or []),
    )


def result_from_dict(data: dict[str, Any]) -> ComparisonResult:
    return ComparisonResult(
        matched_files=[_file_from_dict(item) for item in data.get("matched_files", [])],
        mismatched_files=[_file_from_dict(item) for item in data.get("mismatched_files", [])],
        only_in_left_files=list(data.get("only_in_left_files") or []),
        only_in_right_files=list(data.get("only_in_right_files") or []),
        only_in_left_folders=list(data.get("only_in_left_folders") or []),
        only_in_right_folders=list(data.get("only_in_right_folders") or []),
    )


class _RedisRestBackend:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    def command(self, *parts: Any) -> Any:
        request_body = json.dumps(list(parts), separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Shared-result storage is unavailable: {exc}") from exc
        if payload.get("error"):
            raise RuntimeError(f"Shared-result storage error: {payload['error']}")
        return payload.get("result")

    def save(self, share_id: str, payload_json: str) -> None:
        existing = self.command("LRANGE", _HISTORY_KEY, 0, -1) or []
        oldest = existing[-1] if len(existing) >= MAX_SHARED_RESULTS else None
        self.command("SET", _KEY_PREFIX + share_id, payload_json)
        self.command("LPUSH", _HISTORY_KEY, share_id)
        self.command("LTRIM", _HISTORY_KEY, 0, MAX_SHARED_RESULTS - 1)
        if oldest:
            self.command("DEL", _KEY_PREFIX + oldest)

    def get(self, share_id: str) -> str | None:
        value = self.command("GET", _KEY_PREFIX + share_id)
        return value if isinstance(value, str) else None

    def save_session(self, token: str, payload_json: str) -> None:
        self.command("SET", _SESSION_PREFIX + token, payload_json, "EX", SESSION_TTL_SECONDS)

    def get_session(self, token: str) -> str | None:
        value = self.command("GET", _SESSION_PREFIX + token)
        return value if isinstance(value, str) else None


class _LocalFileBackend:
    def __init__(self) -> None:
        self.root = Path(tempfile.gettempdir()) / "file_compare_shared_results_v1"
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_path = self.root / "history.json"
        self.lock = threading.Lock()

    def _history(self) -> list[str]:
        try:
            value = json.loads(self.history_path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return [str(item) for item in value]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def save(self, share_id: str, payload_json: str) -> None:
        with self.lock:
            history = [item for item in self._history() if item != share_id]
            history.insert(0, share_id)
            removed = history[MAX_SHARED_RESULTS:]
            history = history[:MAX_SHARED_RESULTS]
            (self.root / f"{share_id}.json").write_text(payload_json, encoding="utf-8")
            self.history_path.write_text(json.dumps(history), encoding="utf-8")
            for old_id in removed:
                try:
                    (self.root / f"{old_id}.json").unlink()
                except FileNotFoundError:
                    pass

    def get(self, share_id: str) -> str | None:
        try:
            return (self.root / f"{share_id}.json").read_text(encoding="utf-8")
        except OSError:
            return None

    def save_session(self, token: str, payload_json: str) -> None:
        session_dir = self.root / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / f"{token}.json").write_text(payload_json, encoding="utf-8")

    def get_session(self, token: str) -> str | None:
        try:
            return (self.root / "sessions" / f"{token}.json").read_text(encoding="utf-8")
        except OSError:
            return None


class SharedResultStore:
    def __init__(self) -> None:
        url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
        token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and token:
            self.backend: _RedisRestBackend | _LocalFileBackend = _RedisRestBackend(url, token)
            self.is_durable = True
        else:
            self.backend = _LocalFileBackend()
            self.is_durable = False

    def save(
        self,
        result: ComparisonResult,
        *,
        mode: str,
        show_spaces: bool,
        left_label: str,
        right_label: str,
    ) -> tuple[str, dict[str, Any]]:
        share_id = secrets.token_urlsafe(9).replace("-", "A").replace("_", "B")
        payload = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "show_spaces": bool(show_spaces),
            "left_label": left_label,
            "right_label": right_label,
            "result": result_to_dict(result),
        }
        self.backend.save(share_id, _pack_json(payload))
        return share_id, payload

    def get(self, share_id: str) -> dict[str, Any] | None:
        raw = self.backend.get(share_id)
        if not raw:
            return None
        try:
            payload = _unpack_json(raw)
        except (json.JSONDecodeError, ValueError, zlib.error):
            return None
        return payload if isinstance(payload, dict) else None

    def save_session_result(self, token: str, result: ComparisonResult) -> None:
        self.backend.save_session(
            token,
            _pack_json(result_to_dict(result)),
        )

    def get_session_result(self, token: str) -> ComparisonResult | None:
        if not token:
            return None
        raw = self.backend.get_session(token)
        if not raw:
            return None
        try:
            payload = _unpack_json(raw)
        except (json.JSONDecodeError, ValueError, zlib.error):
            return None
        if not isinstance(payload, dict):
            return None
        return result_from_dict(payload)


shared_store = SharedResultStore()
