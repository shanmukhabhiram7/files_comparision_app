"""Server-side replacement for Streamlit's ``st.session_state["last_result"]``.

Each browser session gets a token stored in a signed cookie. The comparison
result itself stays in process memory so the browser only ever receives HTML,
exactly like the Streamlit version did.
"""

from __future__ import annotations

import threading
import time

from comparison_engine import ComparisonResult

# Results are only useful while the tab that produced them is open.
TTL_SECONDS = 6 * 60 * 60
MAX_SESSIONS = 64


class ResultStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, ComparisonResult]] = {}

    def _purge(self) -> None:
        """Caller must hold the lock."""
        now = time.time()
        expired = [
            token
            for token, (stamp, _) in self._items.items()
            if now - stamp > TTL_SECONDS
        ]
        for token in expired:
            self._items.pop(token, None)

        # Drop the oldest sessions if a long-running server accumulates too many.
        while len(self._items) > MAX_SESSIONS:
            oldest = min(self._items, key=lambda key: self._items[key][0])
            self._items.pop(oldest, None)

    def set(self, token: str, result: ComparisonResult) -> None:
        with self._lock:
            self._items[token] = (time.time(), result)
            self._purge()

    def get(self, token: str) -> ComparisonResult | None:
        with self._lock:
            item = self._items.get(token)
            if item is None:
                return None
            # Refresh the timestamp so an actively used session is not purged.
            self._items[token] = (time.time(), item[1])
            return item[1]

    def pop(self, token: str) -> ComparisonResult | None:
        with self._lock:
            item = self._items.pop(token, None)
            return item[1] if item else None


store = ResultStore()
