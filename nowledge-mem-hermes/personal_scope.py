"""Read-only host scope and evidence adapters. No identity creation or scheduler."""
from __future__ import annotations

import json
from contextlib import closing
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DENIED = frozenset({"subagent", "delegate", "tool", "noting", "flush", "review", "background_review",
                    "background", "dreaming", "skill_refinement", "gateway_hygiene", "cron_output",
                    "kanban", "utility", "side_agent", "btw"})
_MAIN = frozenset({"cli", "tui", "gui", "desktop", "web", "api", "api_server", "acp",
                  "telegram", "discord", "slack", "signal", "whatsapp", "wechat", "feishu",
                  "dingtalk", "matrix", "email", "sms", "qq"})
_NEUTRAL_CONTEXTS = frozenset({"primary", "main", "default"})
_AUXILIARY_FLAGS = ("side_agent", "_persist_disabled", "delegate_depth", "_delegate_depth",
                    "_delegate_from", "_review_from")


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


def _object(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError("Invalid host metadata object")
    return value


def _labels(metadata: dict[str, Any]) -> set[str]:
    labels = set()
    for key in ("agent_context", "platform", "source"):
        value = metadata.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise ValueError("Invalid runtime source")
        label = value.strip().lower()
        if label and not (key == "agent_context" and label in _NEUTRAL_CONTEXTS):
            labels.add(label)
    return labels


def _metadata_facts(metadata: dict[str, Any]) -> tuple[set[str], bool]:
    """Only host-owned metadata is considered; message roles and supplied Refs are not."""
    origins = [metadata, _object(metadata.get("origin")), _object(metadata.get("origin_json"))]
    labels = set().union(*(_labels(item) for item in origins))
    objects = [*origins, _object(metadata.get("model_config"))]
    auxiliary = any(item.get(key) for item in objects for key in _AUXILIARY_FLAGS)
    return labels, bool(auxiliary or labels & _DENIED)


def _locator(value: Any) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid host identity")
    return value


def _host_rows(home: str, session_id: str, runtime_parent: str):
    """Read the row, parent and bindings in one SQLite snapshot, without initialization."""
    path = Path(home) / "state.db"
    if not path.exists():
        return {}, {}, "", ""
    if not path.is_file():
        raise OSError("Host database is not a file")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")  # Deferred read transaction; no schema/identity writes.
        found = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        row = dict(found) if found is not None else {}
        parent_id = _locator(row.get("parent_session_id")) or runtime_parent
        parent = db.execute("SELECT * FROM sessions WHERE id=?", (parent_id,)).fetchone() if parent_id else None
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='secretary_session_bindings'").fetchone()

        def binding(identity):
            if not exists or not identity:
                return ""
            result = db.execute("SELECT conversation_ref FROM secretary_session_bindings WHERE session_id=?", (identity,)).fetchone()
            return _locator(result[0]) if result else ""

        return row, dict(parent) if parent is not None else {}, binding(session_id), binding(parent_id)


def resolve_scope(home: str, session_id: str, runtime: dict[str, Any]) -> Scope:
    """Classify real host origin and parent facts; never mint an identity or infer from a Ref.

    A Main awaiting its first durable row, or ordinary Hermes without Secretary tables,
    may use explicit interactive host metadata and a physical-session Thread key. A
    persisted parent is accepted only as a marked user fork or a verified same-Ref
    continuation of an interactive parent. Unknown or contradictory metadata fails closed.
    """
    excluded = lambda reason: Scope("excluded", session_id, reason=reason)
    if not home or not isinstance(runtime, dict):
        return excluded("missing_host_scope")
    try:
        if not _locator(session_id):
            return excluded("missing_session_id")
        runtime_labels, auxiliary = _metadata_facts(runtime)
        if auxiliary:
            return excluded("auxiliary_runtime")
        runtime_parents = {_locator(runtime.get(key)) for key in ("parent_session_id", "_parent_session_id")} - {""}
        if len(runtime_parents) > 1:
            return excluded("conflicting_parent")
        runtime_parent = next(iter(runtime_parents), "")
        row, parent, ref, parent_ref = _host_rows(home, session_id, runtime_parent)
        row_labels, auxiliary = _metadata_facts(row)
        if auxiliary:
            return excluded("auxiliary_source")
        labels = runtime_labels | row_labels
        if labels - (_MAIN | _DENIED | {"cron"}):
            return excluded("unknown_source")
        config = _object(row.get("model_config"))
        row_parent = _locator(row.get("parent_session_id"))
        if runtime_parent and row_parent and runtime_parent != row_parent:
            return excluded("conflicting_parent")
        parent_id = row_parent or runtime_parent
        if ref and not row:
            return excluded("orphan_binding")
        title = str(row.get("title") or "")
        if "cron" in labels:
            # A Cron's user-role prompt and even an accidental binding never make it Main.
            return excluded("child_runtime") if parent_id else Scope("cron", session_id, title=title)
        if not labels & _MAIN:
            return excluded("unknown_runtime")
        if parent_id:
            fork_parent = _locator(config.get("_branched_from"))
            if fork_parent:
                if fork_parent != parent_id:
                    return excluded("conflicting_fork_parent")
            else:
                parent_labels, parent_auxiliary = _metadata_facts(parent)
                continuation = (ref and ref == parent_ref and parent_labels & _MAIN
                                and not parent_auxiliary and not parent_labels - _MAIN)
                if not continuation:
                    return excluded("child_runtime")
        return Scope("main", session_id, ref, title)
    except (sqlite3.Error, OSError):
        return excluded("host_scope_unavailable")
    except (TypeError, ValueError):
        return excluded("invalid_host_metadata")


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
