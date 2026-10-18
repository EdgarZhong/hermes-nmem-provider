"""Small additions to the official CLI client: static Bundle and generic metadata."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from .client import NowledgeMemClient


class MemHTTPError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"NM HTTP {status}")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send NM credentials to a redirected origin.
        return None


class PersonalMemClient(NowledgeMemClient):
    def request_json(self, method: str, path: str, payload: dict | None = None) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Expected relative NM API path")
        base = self._api_url().rstrip("/")
        parts = parse.urlsplit(base)
        if (parts.scheme not in {"http", "https"} or not parts.netloc or parts.username
                or parts.password or parts.query or parts.fragment):
            raise ValueError("Invalid NM API URL")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        key = self._api_key()
        if key:
            headers.update(Authorization=f"Bearer {key}", **{"X-NMEM-API-Key": key})
        req = request.Request(base + path, data=body, headers=headers, method=method)
        try:
            with request.build_opener(_NoRedirect()).open(req, timeout=self._timeout) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        except error.HTTPError as exc:
            # HTTPError owns a response stream too, including refused redirects.
            status = exc.code
            exc.close()
            raise MemHTTPError(status) from None
        except (error.URLError, OSError, TimeoutError):
            raise RuntimeError("NM transport unavailable") from None
        if len(data) > 8 * 1024 * 1024:
            raise RuntimeError("NM response exceeds safe size")
        try:
            return json.loads(data) if data.strip() else {}
        except (UnicodeError, ValueError):
            raise RuntimeError("Invalid NM JSON response") from None

    def context_bundle(self, *, source_app="hermes", host_agent_id=None):
        cmd = ["context", "read", "--source-app", source_app, "--no-working-memory"]
        if host_agent_id:
            cmd.extend(["--host-agent-id", host_agent_id])
        if self._has_explicit_space and self._space:
            cmd.extend(["--space-id", self._space])
        result = self._cli(cmd)
        # Official CLI retains an omission envelope even when no WM is returned.
        # Adapt only affirmative omission with empty content for the existing parser.
        if isinstance(result, dict):
            working_memory = result.get("working_memory")
            if (isinstance(working_memory, dict) and working_memory.get("omitted") is True
                    and working_memory.get("content") in (None, "")):
                result = {**result, "working_memory": None}
        return result

    def search(self, query="", *, limit=10, filter_labels=None, mode=None, min_importance=None):
        """Reuse official CLI/config/timeout handling; the query is one literal argument.

        Terminate option parsing before untrusted text, including dash-prefixed input.
        This is Memory Search, not NM ask or an LLM query-planning operation.
        """
        if not isinstance(query, str):
            raise ValueError("NM search query must be text")
        if not query:
            return {"memories": []}
        cmd = ["m", "search"]
        if limit != 10:
            cmd.extend(["-n", str(limit)])
        for label in filter_labels or []:
            cmd.extend(["-l", label])
        if mode == "deep":
            cmd.extend(["--mode", "deep"])
        if min_importance is not None:
            cmd.extend(["--importance", str(min_importance)])
        cmd.extend(["--", query])
        return self._cli(cmd)

    def memory_get(self, memory_id: str) -> dict:
        result = self.request_json("GET", "/memories/" + parse.quote(memory_id, safe=""))
        if not isinstance(result, dict):
            raise RuntimeError("Invalid Memory response")
        result = result.get("memory", result)
        if not isinstance(result, dict) or result.get("id") != memory_id:
            raise RuntimeError("Memory ID mismatch")
        return result

    def import_thread(self, thread_id, messages, *, title=None, source="hermes",
                      expected_message_count=None, idempotency_key=None):
        """Use official file import, including its checkpointed suffix operation.

        File import sends JSON messages to remote servers; CLI append --file sends
        a server-local path, and its output discards the server's Thread identity.
        """
        if not messages:
            return {"success": True, "thread_id": thread_id, "imported": 0}
        fd, filename = tempfile.mkstemp(prefix="hermes-nmem-thread-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(messages, handle, ensure_ascii=False)
            cmd = ["threads", "import", "--file", filename, "--id", thread_id]
            if title:
                cmd.extend(["--title", title])
            if source:
                cmd.extend(["--source", source])
            if self._has_explicit_space and self._space:
                cmd.extend(["--space-id", self._space])
            if expected_message_count is not None:
                cmd.extend(["--expected-message-count", str(expected_message_count)])
            if idempotency_key:
                cmd.extend(["--idempotency-key", idempotency_key])
            return self._cli(cmd)
        finally:
            Path(filename).unlink(missing_ok=True)

    def _api_post(self, path, payload):
        # Preserve upstream import/append shapes while adding redirect and error hygiene.
        return self.request_json("POST", path, payload)
