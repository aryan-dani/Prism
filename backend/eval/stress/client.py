"""Sequential HTTP client for Prism stress tests. One request at a time."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class TurnLog:
    turn_index: int
    message: str
    request: dict
    response: dict | None
    error: str | None
    latency_s: float
    timestamp: float
    render_results: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionLog:
    session_id: str
    title_after_first: str | None = None
    turns: list[TurnLog] = field(default_factory=list)


class PrismClient:
    # Server now bounds a single Ollama call at ~150s (config.OLLAMA_REQUEST_TIMEOUT_S)
    # and generate_answer retries once on invalid JSON, so a legitimately slow-but-
    # correct turn under GPU contention can take ~300s+retrieval before the server
    # itself gives up and returns an honest no-answer. Give it room to finish and
    # report real content instead of the test client aborting first and recording
    # a hard FAIL for what would otherwise be a (possibly PARTIAL-on-latency) PASS.
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 360.0,
        *,
        email: str = "alex.employee@prism.local",
        password: str = "Prism2026!",
    ):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.email = email
        self.password = password
        self._token: str | None = None
        self.login()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def login(self, email: str | None = None, password: str | None = None) -> dict:
        r = self.client.post(
            "/api/auth/login",
            json={"email": email or self.email, "password": password or self.password},
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["token"]
        return data

    def health(self) -> dict:
        r = self.client.get("/api/health")
        r.raise_for_status()
        return r.json()

    def create_session(self) -> dict:
        r = self.client.post("/api/sessions", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_session(self, session_id: str) -> dict:
        r = self.client.get(f"/api/sessions/{session_id}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def chat(self, session_id: str, message: str) -> tuple[dict, float]:
        payload = {"message": message}
        t0 = time.perf_counter()
        r = self.client.post(
            f"/api/sessions/{session_id}/chat", json=payload, headers=self._headers()
        )
        latency = time.perf_counter() - t0
        r.raise_for_status()
        return r.json(), latency

    def render(self, session_id: str, fmt: str) -> tuple[Any, float, str]:
        t0 = time.perf_counter()
        r = self.client.post(
            f"/api/sessions/{session_id}/render",
            json={"format": fmt},
            headers=self._headers(),
        )
        latency = time.perf_counter() - t0
        ctype = r.headers.get("content-type", "")
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}, latency, ctype
        if "application/vnd.openxmlformats" in ctype or "octet-stream" in ctype:
            return {"binary": True, "nbytes": len(r.content)}, latency, ctype
        return r.json(), latency, ctype

    def download(self, session_id: str, fmt: str) -> tuple[Any, float, int]:
        t0 = time.perf_counter()
        r = self.client.get(f"/api/sessions/{session_id}/download/{fmt}", headers=self._headers())
        latency = time.perf_counter() - t0
        return (
            {"status": r.status_code, "nbytes": len(r.content), "body_preview": r.text[:300]},
            latency,
            r.status_code,
        )

    def close(self) -> None:
        self.client.close()
