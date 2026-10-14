"""Read-only host scope and evidence adapters. No identity creation or scheduler."""
from __future__ import annotations

import json
from contextlib import closing
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DENIED = frozenset({"subagent", "tool", "noting", "flush", "review", "background_review",
                    "background", "dreaming", "skill_refinement", "gateway_hygiene", "cron_output", "kanban"})
_MAIN = frozenset({"cli", "tui", "gui", "desktop", "web", "api", "api_server", "acp",
                  "telegram", "discord", "slack", "signal", "whatsapp", "wechat", "feishu",
                  "dingtalk", "matrix", "email", "sms", "qq"})


@dataclass(frozen=True)
class Scope:
    kind: str
    session_id: str
    conversation_ref: str = ""
    title: str = ""
    reason: str = ""

    @property
    def context_allowed(self) -> bool:
        return self.kind == "main"

    @property
    def sync_allowed(self) -> bool:
        return self.kind in {"main", "cron"}

    @property
    def thread_id(self) -> str:
        # Separate namespace avoids overwriting an older upstream-provider archive.
        identity = self.conversation_ref if self.kind == "main" and self.conversation_ref else self.session_id
        return "hermes-personal-" + identity


def resolve_scope(home: str, session_id: str, runtime: dict[str, Any]) -> Scope:
    """Use real host metadata when present. A missing database is ordinary Hermes mode."""
    labels = {str(runtime.get(k) or "").strip().lower() for k in ("agent_context", "platform")}
    if labels & _DENIED or runtime.get("side_agent") or runtime.get("delegate_depth"):
        return Scope("excluded", session_id, reason="auxiliary_runtime")
    if not session_id:
        return Scope("excluded", "", reason="missing_session_id")
    row: dict[str, Any] = {}
    ref = ""
    path = Path(home) / "state.db"
    if home and path.is_file():
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25)) as db:
                db.row_factory = sqlite3.Row
                found = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                if found is not None:
                    row = dict(found)
                # Do not mint Secretary identity; the host owns lifecycle registration.
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='secretary_session_bindings'").fetchone()
                if exists:
                    binding = db.execute("SELECT conversation_ref FROM secretary_session_bindings WHERE session_id=?", (session_id,)).fetchone()
                    ref = str(binding[0]) if binding else ""
        except (sqlite3.Error, OSError):
            return Scope("excluded", session_id, reason="host_scope_unavailable")
    source = str(row.get("source") or "").lower()
    if source in _DENIED:
        return Scope("excluded", session_id, reason="auxiliary_source")
    try:
        config = row.get("model_config") or {}
        config = json.loads(config) if isinstance(config, str) else config
        if not isinstance(config, dict):
            raise ValueError("model_config must be an object")
    except (TypeError, ValueError):
        return Scope("excluded", session_id, reason="invalid_host_metadata")
    if config.get("_delegate_from") or config.get("_review_from"):
        return Scope("excluded", session_id, reason="delegate_or_review")
    # A real branch can have parent_session_id: it is not a subagent.
    if runtime.get("parent_session_id") and not config.get("_branched_from"):
        return Scope("excluded", session_id, reason="child_runtime")
    if "cron" in labels or source == "cron":
        return Scope("cron", session_id, title=str(row.get("title") or ""))
    if source and source not in _MAIN:
        return Scope("excluded", session_id, reason="unknown_source")
    if source in _MAIN or labels & _MAIN:
        return Scope("main", session_id, ref, str(row.get("title") or ""))
    return Scope("excluded", session_id, reason="unknown_runtime")


def history_rows(home: str, conversation_ref: str) -> list[dict[str, Any]]:
    """Use Secretary's canonical projection, never SQL guesses about branch ancestry."""
    from hermes_state import SessionDB
    db = SessionDB(db_path=Path(home) / "state.db", read_only=True)
    try:
        with db._read_ctx() as conn:
            return list(db.get_history_foreground_conn(conn, conversation_ref))
    finally:
        db.close()


def clean_transcript(messages: list[dict[str, Any]], cleaner) -> list[dict[str, Any]]:
    """Keep authentic prose; use upstream text/timestamp normalization unchanged."""
    selected = []
    for row in messages:
        if not isinstance(row, dict) or row.get("role") not in {"user", "assistant"}:
            continue
        metadata = row.get("display_metadata") or {}
        if row.get("_compressed_summary") or row.get("is_compaction") or row.get("display_kind") == "hidden":
            continue
        if isinstance(metadata, dict) and metadata.get("noting_run_output"):
            continue
        if row.get("active") in (0, False) and row.get("compacted") in (0, False):
            continue
        content = row.get("content")
        if isinstance(content, str) and content.lstrip().startswith(("[CONTEXT COMPACTION", "[CONTEXT SUMMARY]:")):
            continue
        selected.append(row)
    return cleaner(selected)
