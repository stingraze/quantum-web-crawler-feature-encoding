from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

import networkx as nx


class AppState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._condition = threading.Condition(self.lock)
        self.graph = nx.DiGraph()
        self.running = False
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.last_message = "Idle"
        self.queued_count = 0
        self.visited_count = 0
        self.error_count = 0
        self.config: Dict[str, Any] = {}
        self.latest_circuit_png: Optional[bytes] = None
        self.latest_circuit_meta: Optional[Dict[str, Any]] = None
        self._events: List[Dict[str, Any]] = []
        self._next_event_id = 0

    def reset(self, config: Dict[str, Any]) -> None:
        with self.lock:
            self.graph = nx.DiGraph()
            self.running = True
            self.started_at = time.time()
            self.finished_at = None
            self.last_message = "Crawler starting"
            self.queued_count = 0
            self.visited_count = 0
            self.error_count = 0
            self.config = dict(config)
            self.latest_circuit_png = None
            self.latest_circuit_meta = None
            self._events = []
            self._next_event_id = 0
            self._condition.notify_all()

    def stop(self) -> None:
        with self.lock:
            self.running = False
            self.last_message = "Stopping crawler"
            self._condition.notify_all()

    def finish(self, message: str) -> None:
        with self.lock:
            self.running = False
            self.finished_at = time.time()
            self.last_message = message
            self._condition.notify_all()

    def snapshot_meta(self) -> Dict[str, Any]:
        with self.lock:
            now = time.time()
            duration = 0.0
            if self.started_at is not None:
                end = now if self.running else (self.finished_at or now)
                duration = max(0.0, end - self.started_at)
            return {
                "running": self.running,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_sec": round(duration, 2),
                "queued_count": self.queued_count,
                "visited_count": self.visited_count,
                "error_count": self.error_count,
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges(),
                "last_message": self.last_message,
                "config": dict(self.config),
            }

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            event = dict(payload)
            event["id"] = self._next_event_id
            event.setdefault("ts", time.time())
            self._next_event_id += 1
            self._events.append(event)
            self.last_message = str(event.get("message", self.last_message))
            if len(self._events) > 1000:
                self._events = self._events[-400:]
            self._condition.notify_all()
            return event

    def wait_for_events(self, last_id: int, timeout: float = 10.0) -> List[Dict[str, Any]]:
        with self.lock:
            deadline = time.time() + timeout
            while True:
                pending = [event for event in self._events if event["id"] > last_id]
                if pending:
                    return pending
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)

    def set_latest_circuit(self, png: bytes, meta: Dict[str, Any]) -> None:
        with self.lock:
            self.latest_circuit_png = png
            self.latest_circuit_meta = dict(meta)
            self._condition.notify_all()
