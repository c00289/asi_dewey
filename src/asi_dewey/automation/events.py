"""EventBus: every state change is published here so front ends can refresh live.

Every event carries ``seq``, one counter per bus starting at 1, so a poller (the automation
server's ``GET /events?since=<n>``) can ask for what it has not seen yet; ``since(n)`` answers it.
The counter and the history are taken under a lock, because ``jira.live`` is published from the
JIRA screens' worker thread while the Tk thread may publish too; handlers run outside the lock,
on whichever thread published, so a handler decides for itself what it may touch.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

Handler = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self, history: int = 500) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=history)
        self.seq = 0  # the sequence number of the latest event; 0 before the first
        self._lock = threading.Lock()

    def subscribe(self, topic: str, handler: Handler) -> Handler:
        """Subscribe to an exact topic such as ``entity.created``, or ``*`` for everything."""
        self._handlers.setdefault(topic, []).append(handler)
        return handler

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        if topic in self._handlers and handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def publish(self, topic: str, **payload: Any) -> None:
        with self._lock:
            self.seq += 1
            event = {
                "topic": topic,
                "ts": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
                "seq": self.seq,
                **payload,
            }
            self.history.append(event)
        for handler in (*self._handlers.get(topic, ()), *self._handlers.get("*", ())):
            handler(topic, event)

    def last(self, n: int = 10) -> list[dict[str, Any]]:
        return list(self.history)[-n:]

    def since(self, n: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        """The events after sequence number ``n`` (oldest first), at most ``limit`` of them."""
        events = [e for e in self.history if e.get("seq", 0) > n]
        return events[: max(0, int(limit))]

    def oldest_seq(self) -> int | None:
        """The sequence number of the oldest event still in the history; ``None`` when it is empty."""
        return self.history[0].get("seq") if self.history else None
