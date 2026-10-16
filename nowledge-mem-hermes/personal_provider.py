"""Personal Hermes policy on the official Provider/client, not a second plugin."""
from __future__ import annotations

import copy
import hashlib
from contextlib import closing
import json
import logging
import math
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .client import _resolve_nmem
from .provider import NowledgeMemProvider
from .personal_client import PersonalMemClient
from .personal_scope import (HistoryReconciliationRequired, Scope, clean_transcript,
                             completed_history_rows, resolve_scope)

log = logging.getLogger(__name__)
VERSION = "0.6.0"
REMINDER = ("Memory check: assess whether the current conversation already supplies sufficient context. "
            "Read useful candidates with nmem CLI, or search for missing personal background when needed. "
            "Skip unnecessary lookup; candidate titles are not verified facts.")
GUIDANCE = """# Personal Hermes memory
NM is this user's selected external personal memory and context provider. Use the nmem CLI through the existing terminal when needed; this provider registers no nmem function tools or MCP server. The Conversation's Notebook manages its own working indexes and Persistence Candidates; it is not NM Working Memory, and external memory is not limited to reusable skills or rules.
NM Background Intelligence and automatic distillation remain disabled by operator policy. Automatic Thread capture is archival only. The stable Context Bundle excludes NM Working Memory and follows the host's prompt lifecycle; do not independently rewrite owner-governed Personal Premise, Space or Policy.
Assess whether the current Conversation already provides the needed context. Read useful candidate IDs with nmem CLI or search for missing personal background; do not force a lookup, treat candidate titles as verified facts, or treat an NM summary as the original Conversation evidence.
Only Main may perform a specific user-approved Memory change through its authorized tools. Follow the Secretary proposal and explicit-approval process, inspect supporting and correcting original messages with conversation_history, and execute only the approved content and destination. A slash command or capacity notice starts a proposal, not a write; CLI access and --apply are not user approval.
Preserve inherited Notebook content labels using the official CLI label fields, and preserve exact conversation_ref/message_uid sources in metadata.hermes_provenance. Keep opaque source IDs out of the memory body; do not substitute NM Thread IDs or physical Session row IDs. Use the narrow creation helper to call the official nmem CLI, obtain the actual created Memory ID, and then attach the Hermes metadata to that same Memory using the host's existing NM connection configuration. Other memory operations use the official CLI directly. Report creation and metadata attachment outcomes accurately; if attachment fails after creation, retain the returned ID and repair only that attachment rather than creating another Memory. Noting settles from the Conversation's visible dispatch trajectory and does not inspect NM storage.
Use nmem --json m search QUERY and nmem --json m show ID for reading; consult nmem --help for other supported operations.
"""
_INDEX_HEADER = "NM candidates (references only; use CLI to read):"
_EMPTY_INDEX = "No candidate pointers returned. This is not proof that no relevant memory exists."
_RECALL_UNAVAILABLE = "NM candidate lookup unavailable this turn; no cached result substituted.\n" + REMINDER
_BUNDLE_UNAVAILABLE = "NM Context Bundle is unavailable; do not invent personal background."


def _number(config, key, default, low, high, *, integral=False):
    value = config.get(key, default)
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise ValueError(f"{key} must be a number") from None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{key} must be a number")
    if not low <= value <= high or (integral and int(value) != value):
        raise ValueError(f"{key} outside supported range")
    return int(value) if integral else float(value)


def _pointer_json(row: dict[str, Any]) -> str:
    # ASCII escaping also encodes bidi controls and Unicode line separators. Escape
    # markup delimiters so host memory-context sanitization cannot eat an opaque ID
    # or interpret a malicious title as a new context fence. JSON decoding is lossless.
    return (json.dumps(row, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def candidate_index(result: Any, *, limit: int, budget: int) -> str:
    """Bounded, JSON-escaped pointers only. Omit whole rows rather than truncate IDs/dates."""
    if not isinstance(result, dict) or result.get("success") is False or result.get("error"):
        raise ValueError("Invalid or failed NM search envelope")
    memories = result.get("memories", result.get("results"))
    if not isinstance(memories, list):
        raise ValueError("Invalid search results")
    minimum = len("\n".join((_INDEX_HEADER, _EMPTY_INDEX, REMINDER)))
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("Invalid candidate limit")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < minimum:
        raise ValueError("Candidate budget cannot hold the required reminder")
    lines = [_INDEX_HEADER]
    used = len(_INDEX_HEADER) + len(REMINDER) + 1
    seen = set()
    for item in memories:
        if len(seen) >= limit:
            break
        if not isinstance(item, dict):
            continue
        identity = item.get("id") or item.get("memory_id")
        if not isinstance(identity, str) or not identity.strip() or len(identity) > budget or any(ord(c) < 32 for c in identity):
            continue
        if identity in seen:
            continue
        title = item.get("title")
        title = " ".join(title.split())[:160] if isinstance(title, str) else ""
        row = {"id": identity, "title": title or "Untitled"}
        for field in ("created_at", "updated_at"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                row[field] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                row[field] = value
        line = _pointer_json(row)
        if used + len(line) + 1 > budget:
            continue
        lines.append(line)
        used += len(line) + 1
        seen.add(identity)
    if not seen:
        lines.append(_EMPTY_INDEX)
    return "\n".join([*lines, REMINDER])


def stable_bundle_text(result: Any) -> str:
    """Accept the existing rendered Bundle envelope, never a stringified object or WM fallback."""
    if not isinstance(result, dict) or result.get("success") is False or result.get("error"):
        raise ValueError("Invalid or failed Context Bundle")
    if result.get("include_working_memory") is True or result.get("working_memory"):
        raise ValueError("Working Memory is not part of the stable Bundle")
    text = result.get("rendered_markdown") or result.get("content")
    if not isinstance(text, str) or not text.strip() or len(text) > 32000:
        raise ValueError("Bundle absent, invalid or oversized")
    return text.strip()


class PersonalNowledgeMemProvider(NowledgeMemProvider):
    """Keep upstream normalization, Space/identity resolution and HTTP thread shapes."""
    def __init__(self):
        super().__init__()
        self._home = ""
        self._runtime: dict[str, Any] = {}
        self._physical_session = ""
        self._policy_lock = threading.RLock()
        self._context_epoch = 0
        self._recall_client = None
        self._config = {}
        self._disabled = True
        self._accepted_archive = None

    def is_available(self):
        # Contract: availability checks dependencies, never performs a network probe.
        return _resolve_nmem() is not None

    def initialize(self, session_id: str, **kwargs):
        with self._policy_lock:
            # Failed reinitialization must not leave another profile's live clients behind.
            self._disabled = True
            self._accepted_archive = None
            self._context_epoch += 1
            self._client = self._recall_client = None
            self._resolved_space = None
            self._home = str(kwargs.get("hermes_home") or "")
            self._physical_session = session_id or ""
            self._runtime = dict(kwargs)
            if not self._home:
                raise ValueError("Hermes must supply profile-scoped hermes_home")
            path = Path(self._home) / "nowledge-mem.json"
            config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if not isinstance(config, dict):
                raise ValueError("nowledge-mem.json must be an object")
            self._config = config
            self._timeout = _number(config, "timeout", 8, 1, 60)
            self._recall_timeout = _number(config, "recall_timeout", 2, 0.1, 5)
            self._recall_limit = _number(config, "recall_limit", 5, 1, 10, integral=True)
            self._recall_budget = _number(config, "recall_max_chars", 2400, 700, 8000, integral=True)
            self._agent_identity = self._resolve_agent_identity(config, kwargs)
            self._resolved_space = self._resolve_space(config, self._agent_identity)
            self._client = PersonalMemClient(timeout=self._timeout, space=self._resolved_space)
            self._recall_client = PersonalMemClient(timeout=self._recall_timeout, space=self._resolved_space)
            self._disabled = False
            # No Bundle/network read here: cron is sync-only; new rows may not exist yet.

    def _scope(self, session_id="") -> Scope:
        if self._disabled:
            return Scope("excluded", session_id, reason="not_initialized")
        return resolve_scope(self._home, session_id or self._physical_session, self._runtime)

    def _context_still_current(self, epoch: int, scope: Scope) -> bool:
        # Caller holds _policy_lock. Also catches a changed read-only host binding.
        return (not self._disabled and epoch == self._context_epoch
                and scope == self._scope(scope.session_id))

    def system_prompt_block(self):
        """Contribute at a native prompt build/rebuild, not at every Turn.

        Hermes caches/restores the assembled root. Do not put a second per-Thread
        cache here: the same Thread survives native compression rebuilds. A cold
        restore of a valid root does not call this hook; a real rebuild must read
        a fresh Bundle. This hook does not invalidate or rewrite a host root.
        """
        with self._policy_lock:
            scope = self._scope()
            if not scope.context_allowed:
                return ""
            epoch, client, identity = self._context_epoch, self._client, self._agent_identity
        try:
            result = client.context_bundle(source_app="hermes", host_agent_id=identity or None)
            text = stable_bundle_text(result)
        except Exception as exc:
            log.warning("Personal NM Bundle unavailable (%s); no Working Memory fallback", type(exc).__name__)
            text = _BUNDLE_UNAVAILABLE
        with self._policy_lock:
            if not self._context_still_current(epoch, scope):
                return ""
            return GUIDANCE + "\n" + text

    def prefetch(self, query: str, *, session_id=""):
        """Search host-admitted input once; api_content may still be replayed by Hermes."""
        if not isinstance(query, str) or not query.strip():
            return ""
        with self._policy_lock:
            scope = self._scope(session_id)
            if not scope.context_allowed:
                return ""
            epoch, client = self._context_epoch, self._recall_client
            limit, budget = self._recall_limit, self._recall_budget
        # No second minimum-length gate: short CJK can carry meaningful intent.
        # Never interpolate the query into shell commands or the returned context.
        query = " ".join(query.split())[:2048]
        try:
            result = client.search(query, limit=limit)
            text = candidate_index(result, limit=limit, budget=budget)
        except Exception as exc:
            log.warning("Personal NM recall unavailable (%s)", type(exc).__name__)
            text = _RECALL_UNAVAILABLE
        with self._policy_lock:
            if not self._context_still_current(epoch, scope):
                return ""
            return text

    def get_tool_schemas(self):
        return []

    def handle_tool_call(self, tool_name, args, **kwargs):
        raise NotImplementedError("This Provider registers no model-callable NM tools; use CLI")

    def queue_prefetch(self, query, *, session_id=""):
        pass

    def on_memory_write(self, action, target, content, metadata=None):
        pass

    def on_pre_compress(self, messages):
        return ""

    def _report_skill_outcomes(self, messages):
        pass

    def recall_status(self):
        # Host's standard label says 'recalled memories'; these are only candidate pointers.
        return None

    def on_session_switch(self, new_session_id, *, parent_session_id="", reset=False, **kwargs):
        with self._policy_lock:
            self._physical_session = new_session_id
            self._accepted_archive = None
            self._context_epoch += 1
            # The named parent argument is a branch locator, not execution ownership.
            # Keep existing host runtime facts unless the host explicitly replaces them.
            self._runtime.update({key: value for key, value in kwargs.items() if key != "hermes_home"})

    @staticmethod
    def _archive_acknowledged(result, thread_id):
        """Require affirmative service acknowledgement, never truthy/empty JSON."""
        if (not isinstance(result, dict) or result.get("success") is not True
                or result.get("error") or result.get("thread_id", thread_id) != thread_id):
            return False
        results = result.get("results")
        return results is None or (isinstance(results, list) and all(
            isinstance(item, dict) and item.get("success") is True and not item.get("error")
            for item in results))

    def _archive(self, scope: Scope, messages):
        if not scope.sync_allowed:
            return
        if scope.conversation_ref:
            # Bound the canonical path to the exact completed snapshot; the worker
            # may run after the next user input has already reached the database.
            rows = completed_history_rows(self._home, scope.conversation_ref, messages)
            from agent.memory_manager import _redact_for_provider
            # Scrub the ENTIRE batch before dropping tools: secrets detected in a
            # tool row must also be masked when repeated bare in assistant prose.
            cleaned = clean_transcript(_redact_for_provider(rows), self._clean_session_messages)
        else:
            # Ordinary Hermes/Cron: manager already batch-scrubbed its snapshot.
            cleaned = clean_transcript(messages, self._clean_session_messages)
        return self._archive_cleaned(scope, cleaned)

    def _archive_cleaned(self, scope: Scope, cleaned):
        fingerprints = [hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest() for row in cleaned]
        state_dir = Path(self._home) / "nowledge-mem-personal"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_path = state_dir / "receipts.sqlite3"
        key = json.dumps([self._client._api_url(), self._resolved_space, scope.thread_id])
        # This is only an ACK ledger, using the existing database. The transaction
        # serializes separate Provider instances through upload and receipt commit.
        with closing(sqlite3.connect(state_path, timeout=5)) as db, db:
            os.chmod(state_path, 0o600)
            db.execute("CREATE TABLE IF NOT EXISTS receipts (scope TEXT PRIMARY KEY, fingerprints TEXT NOT NULL, synced_at REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            stored = db.execute("SELECT fingerprints FROM receipts WHERE scope=?", (key,)).fetchone()
            previous = json.loads(stored[0]) if stored else []
            if not isinstance(previous, list) or fingerprints[:len(previous)] != previous:
                raise HistoryReconciliationRequired("Archived history was rewritten; reconciliation-required")
            delta = cleaned[len(previous):]
            if not delta:
                return {"status": "unchanged", "thread_id": scope.thread_id}
            if stored is None:
                result = self._client.import_thread(scope.thread_id, delta,
                    title=scope.title or self._build_thread_title(cleaned), source="hermes")
                if not self._archive_acknowledged(result, scope.thread_id) and self._thread_already_exists(result):
                    result = self._client.append_thread(scope.thread_id, delta)
            else:
                result = self._client.append_thread(scope.thread_id, delta)
            if not self._archive_acknowledged(result, scope.thread_id):
                raise RuntimeError("NM did not explicitly acknowledge Thread write")
            db.execute("INSERT INTO receipts VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET fingerprints=excluded.fingerprints,synced_at=excluded.synced_at",
                       (key, json.dumps(fingerprints), time.time()))
        return {"status": "acknowledged", "thread_id": scope.thread_id, "appended": len(delta)}

    def _attempt_archive(self, scope, messages):
        try:
            return self._archive(scope, messages)
        except HistoryReconciliationRequired:
            log.warning("Personal NM Thread reconciliation-required; acknowledged prefix differs; no write attempted")
            return {"status": "reconciliation-required", "thread_id": scope.thread_id}
        except Exception as exc:
            log.warning("Personal NM Thread sync not acknowledged (%s); retry on next completed boundary", type(exc).__name__)
            return {"status": "unacknowledged", "thread_id": scope.thread_id}

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None,
                  completed=True, interrupted=False, failed=False, **kwargs):
        # The native completed hook is the admission authority. Optional verdicts
        # let explicit callers fail closed; no pair-only or session-end admission.
        with self._policy_lock:
            if completed is not True or interrupted or failed:
                return {"status": "skipped"}
            scope = self._scope(session_id)
            if not scope.sync_allowed:
                return {"status": "skipped"}
            if not isinstance(messages, list):
                log.warning("Personal NM sync skipped: full transcript not supplied")
                return {"status": "skipped"}
            snapshot = copy.deepcopy(messages)
            self._accepted_archive = (scope, snapshot)
            return self._attempt_archive(scope, snapshot)

    def on_session_end(self, messages):
        # End/close can follow a failed or interrupted Turn. Only retry a snapshot
        # admitted by sync_turn, never treat the arbitrary closing tail as complete.
        with self._policy_lock:
            if self._accepted_archive is None:
                return
            scope, snapshot = self._accepted_archive
            if scope == self._scope(scope.session_id):
                return self._attempt_archive(scope, snapshot)

    def get_config_schema(self):
        return [
            {"key": "space", "description": "NM Space name/id (blank uses NM default)", "default": ""},
            {"key": "agent_identity", "description": "Optional NM agent identity", "default": ""},
            {"key": "timeout", "description": "Bundle/archive timeout seconds", "type": "number", "default": 8, "minimum": 1, "maximum": 60},
            {"key": "recall_timeout", "description": "Fast recall timeout seconds", "type": "number", "default": 2, "minimum": 0.1, "maximum": 5},
            {"key": "recall_limit", "description": "Maximum candidate pointers", "type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            {"key": "recall_max_chars", "description": "Candidate index character budget including reminder", "type": "integer", "default": 2400, "minimum": 700, "maximum": 8000},
        ]

    def shutdown(self):
        with self._policy_lock:
            self._context_epoch += 1
            self._disabled = True
            self._client = self._recall_client = None
            self._accepted_archive = None
            super().shutdown()
