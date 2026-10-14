"""Personal Hermes policy on the official Provider/client, not a second plugin."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .client import _resolve_nmem
from .provider import NowledgeMemProvider
from .personal_client import PersonalMemClient
from .personal_scope import Scope, clean_transcript, history_rows, resolve_scope

log = logging.getLogger(__name__)
VERSION = "0.6.0"
REMINDER = ("Memory check: assess whether the current conversation already supplies sufficient context. "
            "Read useful candidates with nmem CLI, or search for missing personal background when needed. "
            "Skip unnecessary lookup; candidate titles are not verified facts.")
GUIDANCE = """# Personal Hermes memory
NM owns durable personal memory and personal context. Use the nmem CLI through the existing terminal; this provider registers no nmem function tools or MCP server.
Working state stays in this Conversation's Notebook. NM Background Intelligence and automatic distillation remain disabled by operator policy. Automatic Thread capture is archival only.
Before answering, assess context sufficiency. Read relevant indexed memories when personal history is missing; proactively search NM when the candidate index does not cover the missing information. Do not force a lookup when this conversation already provides enough context.
Noting records candidates, not approved facts. Only the main Secretary conversation may carry out a user-approved Memory change after checking original Hermes evidence. Never autonomously change owner/profile/policy Context Bundle content. Use metadata.hermes_provenance for validated (conversation_ref, message_uid) sources, not the memory body or NM-native source_thread_id.
Use nmem --json m search QUERY and nmem --json m show ID for reading; consult nmem --help for other operations. CLI access and an --apply flag do not constitute user approval. Respect the existing Secretary approval gate before every durable mutation.
"""


class HistoryReconciliationRequired(RuntimeError):
    """The acknowledged prefix changed; do not silently mix history revisions."""


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


def candidate_index(result: Any, *, limit: int, budget: int) -> str:
    """Bounded, JSON-escaped pointers only. Never truncate IDs or read Memory bodies."""
    if not isinstance(result, dict):
        raise ValueError("Invalid search envelope")
    if result.get("success") is False or result.get("error"):
        raise ValueError("NM search failed")
    memories = result.get("memories", result.get("results", []))
    if not isinstance(memories, list):
        raise ValueError("Invalid search results")
    lines = ["NM candidates (references only; use CLI to read):"]
    seen = set()
    for item in memories:
        if len(seen) >= limit:
            break
        if not isinstance(item, dict):
            continue
        identity = item.get("id") or item.get("memory_id")
        if not isinstance(identity, str) or not identity or len(identity) > 200 or any(ord(c) < 32 for c in identity):
            continue
        if identity in seen:
            continue
        row = {"id": identity, "title": " ".join(str(item.get("title") or "Untitled").split())[:160]}
        for field in ("created_at", "updated_at"):
            if isinstance(item.get(field), str):
                row[field] = item[field][:48]
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        if sum(len(x) + 1 for x in lines) + len(line) + len(REMINDER) + 2 > budget:
            continue
        lines.append(line)
        seen.add(identity)
    if not seen:
        lines.append("No candidate pointers returned. This is not proof that no relevant memory exists.")
    return "\n".join([*lines, REMINDER])


class PersonalNowledgeMemProvider(NowledgeMemProvider):
    """Keep upstream normalization, Space/identity resolution and HTTP thread shapes."""
    def __init__(self):
        super().__init__()
        self._home = ""
        self._runtime: dict[str, Any] = {}
        self._physical_session = ""
        self._policy_lock = threading.RLock()
        self._bundles: dict[str, str] = {}
        self._recall_client = None
        self._config = {}
        self._disabled = True

    def is_available(self):
        # Contract: availability checks dependencies, never performs a network probe.
        return _resolve_nmem() is not None

    def initialize(self, session_id: str, **kwargs):
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
        # No Bundle/network read here: cron is sync-only, and new Session rows may not exist yet.

    def _scope(self, session_id="") -> Scope:
        if self._disabled:
            return Scope("excluded", session_id, reason="not_initialized")
        return resolve_scope(self._home, session_id or self._physical_session, self._runtime)

    def system_prompt_block(self):
        with self._policy_lock:
            scope = self._scope()
            if not scope.context_allowed:
                return ""
            if scope.thread_id not in self._bundles:
                try:
                    result = self._client.context_bundle(source_app="hermes", host_agent_id=self._agent_identity or None)
                    text = self._format_context_bundle(result)
                    if not text or len(text) > 32000:
                        raise ValueError("Bundle absent or oversized")
                    self._bundles[scope.thread_id] = text
                except Exception as exc:
                    log.warning("Personal NM Bundle unavailable (%s); no Working Memory fallback", type(exc).__name__)
                    return GUIDANCE + "\nNM Context Bundle is unavailable; do not invent personal background."
            return GUIDANCE + "\n" + self._bundles[scope.thread_id]

    def prefetch(self, query: str, *, session_id=""):
        if not self._scope(session_id).context_allowed or not isinstance(query, str) or not query.strip():
            return ""
        query = " ".join(query.split())[:2048]
        try:
            result = self._recall_client.search(query, limit=self._recall_limit)
            return candidate_index(result, limit=self._recall_limit, budget=self._recall_budget)
        except Exception as exc:
            log.warning("Personal NM recall unavailable (%s)", type(exc).__name__)
            return "NM candidate lookup unavailable this turn; no cached result substituted.\n" + REMINDER

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
            # Do not turn a branch parent locator into a delegate runtime flag.
            if reset:
                self._bundles.clear()

    def _archive(self, scope: Scope, messages):
        if not scope.sync_allowed or not messages:
            return
        if scope.conversation_ref:
            # Archive real pre-compaction evidence, not the model's lossy working list.
            rows = history_rows(self._home, scope.conversation_ref)
            # The full manager scrub propagates secrets found in one row to every
            # occurrence in the batch. A per-row scrub would miss bare repetitions.
            # A host without this facility fails closed instead of sending raw DB text.
            from agent.memory_manager import _redact_for_provider
            cleaned = _redact_for_provider(clean_transcript(rows, self._clean_session_messages))
        else:
            # Ordinary Hermes/cron: manager already scrubbed the supplied transcript.
            cleaned = clean_transcript(messages, self._clean_session_messages)
        if not cleaned:
            return
        fingerprints = [hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest() for row in cleaned]
        state_dir = Path(self._home) / "nowledge-mem-personal"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_path = state_dir / "receipts.sqlite3"
        # Acknowledgement ledger only, not a second transcript queue or scheduler.
        key = json.dumps([self._client._api_url(), self._resolved_space, scope.thread_id])
        with closing(sqlite3.connect(state_path, timeout=5)) as db, db:
            os.chmod(state_path, 0o600)
            db.execute("CREATE TABLE IF NOT EXISTS receipts (scope TEXT PRIMARY KEY, fingerprints TEXT NOT NULL, synced_at REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            stored = db.execute("SELECT fingerprints FROM receipts WHERE scope=?", (key,)).fetchone()
            previous = json.loads(stored[0]) if stored else []
            if not isinstance(previous, list) or fingerprints[:len(previous)] != previous:
                raise HistoryReconciliationRequired("Archived history was rewritten; explicit reconciliation required")
            delta = cleaned[len(previous):]
            if not delta:
                return
            if stored is None:
                result = self._client.import_thread(scope.thread_id, delta,
                    title=scope.title or self._build_thread_title(cleaned), source="hermes")
                if not self._response_succeeded(result) and self._thread_already_exists(result):
                    result = self._client.append_thread(scope.thread_id, delta)
            else:
                result = self._client.append_thread(scope.thread_id, delta)
            if not result or not self._response_succeeded(result):
                raise RuntimeError("NM did not acknowledge Thread write")
            db.execute("INSERT INTO receipts VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET fingerprints=excluded.fingerprints,synced_at=excluded.synced_at",
                       (key, json.dumps(fingerprints), time.time()))

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None, **kwargs):
        # Target Hermes invokes sync_turn on MemoryManager's serialized background worker.
        # Native lifecycle provides the full transcript; no unsupported legacy pair-only archival.
        with self._policy_lock:
            scope = self._scope(session_id)
            if not scope.sync_allowed:
                return
            if not isinstance(messages, list):
                log.warning("Personal NM sync skipped: full transcript not supplied")
                return
            try:
                self._archive(scope, messages)
            except Exception as exc:
                log.warning("Personal NM Thread sync not acknowledged (%s); retry on next lifecycle boundary", type(exc).__name__)

    def on_session_end(self, messages):
        self.sync_turn("", "", session_id=self._physical_session, messages=messages)

    def get_config_schema(self):
        return [
            {"key": "space", "description": "NM Space name/id (blank uses NM default)", "default": ""},
            {"key": "recall_timeout", "description": "Fast recall timeout seconds", "type": "number", "default": 2, "minimum": 0.1, "maximum": 5},
            {"key": "recall_limit", "description": "Maximum candidate pointers", "type": "integer", "default": 5, "minimum": 1, "maximum": 10},
        ]

    def shutdown(self):
        with self._policy_lock:
            self._bundles.clear()
            self._disabled = True
        super().shutdown()
