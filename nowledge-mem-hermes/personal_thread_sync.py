"""Profile-local Thread ACK ledger and non-destructive History fork continuation."""
from __future__ import annotations

import hashlib
import json
import time
import uuid

from .personal_scope import HistoryReconciliationRequired


class ThreadSyncUnconfirmed(RuntimeError):
    def __init__(self, category):
        self.category = category
        super().__init__("NM Thread sync is not confirmed")


def fingerprints(rows):
    return [hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            for row in rows]


def _body_fingerprints(rows):
    return fingerprints([{key: row[key] for key in ("role", "content")} for row in rows])


def common_prefix(left, right):
    return next((index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]),
                min(len(left), len(right)))


def _initial_state(thread_id, previous):
    return {"thread_id": thread_id, "remote_count": len(previous),
            "locators": [[thread_id, index] for index in range(len(previous))],
            "remote_fingerprints": None, "content_fingerprints": None,
            "remote_timestamps": [], "timestamps": [], "message_uids": None}


def _load(db, key, thread_id):
    row = db.execute("SELECT fingerprints FROM receipts WHERE scope=?", (key,)).fetchone()
    previous = json.loads(row[0]) if row else []
    if not isinstance(previous, list) or not all(isinstance(item, str) for item in previous):
        raise HistoryReconciliationRequired("Invalid NM Thread receipt")
    row = db.execute("SELECT state,pending FROM thread_sync WHERE scope=?", (key,)).fetchone()
    state = json.loads(row[0]) if row else _initial_state(thread_id, previous)
    if (len(state["locators"]) != len(previous) or not isinstance(state["remote_count"], int)
            or state["remote_count"] < 0):
        raise HistoryReconciliationRequired("Invalid NM Thread branch receipt")
    return previous, state, json.loads(row[1]) if row and row[1] else None


def _commit(db, key, pending):
    db.execute("INSERT INTO receipts VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET "
               "fingerprints=excluded.fingerprints,synced_at=excluded.synced_at",
               (key, json.dumps(pending["fingerprints"]), time.time()))
    db.execute("INSERT INTO thread_sync VALUES (?,?,NULL) ON CONFLICT(scope) DO UPDATE SET "
               "state=excluded.state,pending=NULL", (key, json.dumps(pending["state"])))


def _remote_rows(client, thread_id, cleaner, **kwargs):
    rows = client.thread_messages(thread_id, **kwargs)
    # System rows are plugin-generated continuation headers, never user prose.
    normalized = cleaner([{**row, "role": "assistant"} for row in rows])
    if len(normalized) != len(rows):
        raise ThreadSyncUnconfirmed("invalid_remote_messages")
    cleaned = [{**row, "role": original["role"]} for row, original in zip(normalized, rows)]
    return rows, cleaned


def _recover_pending(db, key, pending, client, cleaner):
    """Read-only confirmation after unknown writes; never replay an uncertain import."""
    try:
        _, actual = _remote_rows(client, pending["state"]["thread_id"], cleaner)
    except Exception as exc:
        raise ThreadSyncUnconfirmed("pending_write_unknown") from exc
    if (_body_fingerprints(actual) != pending["remote_fingerprints"]
            or any(stamp and stamp != row.get("timestamp")
                   for stamp, row in zip(pending["state"]["remote_timestamps"], actual))):
        raise ThreadSyncUnconfirmed("pending_write_unknown")
    _commit(db, key, pending)
    return pending["fingerprints"], pending["state"]


def _continuation_header(state, previous, shared, client, cleaner):
    parent = state["thread_id"]
    text = f"NM Thread同步接续说明（插件生成）\n前一NM Thread：{parent}。\n"
    if shared:
        anchor_thread, ordinal = state["locators"][shared - 1]
        try:
            rows, actual = _remote_rows(client, anchor_thread, cleaner, offset=ordinal, limit=1)
            expected = state["content_fingerprints"]
            matches = (_body_fingerprints(actual) == [expected[shared - 1]] if expected
                       else fingerprints(actual) == [previous[shared - 1]])
            expected_stamp = state["timestamps"][shared - 1] if state["timestamps"] else None
            if not rows or not matches or (expected_stamp and actual[0].get("timestamp") != expected_stamp):
                raise ValueError("NM anchor content changed")
            native_id = rows[0]["id"]
        except Exception as exc:
            raise ThreadSyncUnconfirmed("native_message_anchor_unconfirmed") from exc
        text += f"最后共同消息的NM原生Message ID：{native_id}（所属NM Thread：{anchor_thread}）。\n"
    else:
        text += "当前合法History与前一NM Thread没有共同前缀，不存在最后共同消息锚点。\n"
    text += "本Thread仅保存分叉点及其后续消息；共同前缀未重复保存。"
    return {"role": "system", "content": text}


def _plan(state, previous, current, cleaned, client, cleaner, message_uids):
    shared = common_prefix(previous, current)
    if state["message_uids"] is not None and message_uids is not None:
        shared = min(shared, common_prefix(state["message_uids"], message_uids))
    forked = shared != len(previous)
    if forked:
        header = _continuation_header(state, previous, shared, client, cleaner)
        thread_id = state["thread_id"].split("-fork-", 1)[0] + "-fork-" + uuid.uuid4().hex
        delta, start = [header, *cleaned[shared:]], 0
        locators = [*state["locators"][:shared],
                    *[[thread_id, index + 1] for index in range(len(cleaned) - shared)]]
        next_state = {"thread_id": thread_id, "remote_count": len(delta), "locators": locators,
                      "remote_fingerprints": _body_fingerprints(delta),
                      "content_fingerprints": _body_fingerprints(cleaned),
                      "timestamps": [row.get("timestamp") for row in cleaned], "message_uids": message_uids,
                      "remote_timestamps": [row.get("timestamp") for row in delta]}
    else:
        thread_id, start = state["thread_id"], state["remote_count"]
        delta = cleaned[len(previous):]
        locators = [*state["locators"],
                    *[[thread_id, start + index] for index in range(len(delta))]]
        next_state = {"thread_id": thread_id, "remote_count": start + len(delta), "locators": locators,
                      "remote_fingerprints": state["remote_fingerprints"] + _body_fingerprints(delta),
                      "content_fingerprints": _body_fingerprints(cleaned),
                      "timestamps": [row.get("timestamp") for row in cleaned], "message_uids": message_uids,
                      "remote_timestamps": state["remote_timestamps"] + [row.get("timestamp") for row in delta]}
    return delta, next_state, forked, start


def sync_thread(db, *, key, thread_id, cleaned, client, cleaner, title, acknowledged, failure_category,
                message_uids=None):
    """Serialize providers through planning, import and ACK commit in one ledger."""
    db.execute("CREATE TABLE IF NOT EXISTS receipts (scope TEXT PRIMARY KEY, fingerprints TEXT NOT NULL, synced_at REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS thread_sync (scope TEXT PRIMARY KEY, state TEXT NOT NULL, pending TEXT)")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    previous, state, pending = _load(db, key, thread_id)
    if pending:
        previous, state = _recover_pending(db, key, pending, client, cleaner)
    current = fingerprints(cleaned)
    identities_match = (state["message_uids"] is None or message_uids is None
                        or state["message_uids"] == message_uids)
    if current == previous and identities_match:
        return {"status": "unchanged", "thread_id": state["thread_id"]}
    prefix_ids_match = (state["message_uids"] is None or message_uids is None
                        or state["message_uids"][:len(current)] == message_uids)
    if len(current) < len(previous) and current == previous[:len(current)] and prefix_ids_match:
        return {"status": "awaiting-branch-message", "thread_id": state["thread_id"]}
    if not previous:
        state["remote_fingerprints"], state["content_fingerprints"] = [], []
    if state["remote_fingerprints"] is None:
        # Adopt an existing ACK-only ledger without migrating or clearing it.
        _, remote = _remote_rows(client, state["thread_id"], cleaner)
        if fingerprints(remote) != previous:
            raise ThreadSyncUnconfirmed("legacy_remote_prefix_unconfirmed")
        state["remote_fingerprints"] = _body_fingerprints(remote)
        state["content_fingerprints"] = _body_fingerprints(remote)
        state["remote_timestamps"] = state["timestamps"] = [row.get("timestamp") for row in remote]
    delta, next_state, forked, start = _plan(state, previous, current, cleaned, client, cleaner, message_uids)
    if not delta:
        return {"status": "unchanged", "thread_id": state["thread_id"]}
    pending = {"state": next_state, "fingerprints": current,
               "remote_fingerprints": next_state["remote_fingerprints"]}
    # Durable intent precedes network I/O. A crash/timeout cannot erase the fact
    # that a write may have happened. Other providers see it and only read back.
    db.execute("INSERT INTO thread_sync VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET "
               "pending=excluded.pending", (key, json.dumps(state), json.dumps(pending)))
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    # A competing provider may already have confirmed the exact pending write.
    _, _, existing = _load(db, key, thread_id)
    if existing != pending:
        raise ThreadSyncUnconfirmed("concurrent_sync_changed")
    checkpoint = {}
    if start:
        checkpoint = {"expected_message_count": start,
                      "idempotency_key": hashlib.sha256(json.dumps([key, pending]).encode()).hexdigest()}
    result = client.import_thread(next_state["thread_id"], delta, title=title, source="hermes", **checkpoint)
    if not acknowledged(result, next_state["thread_id"]):
        raise ThreadSyncUnconfirmed(failure_category(result, next_state["thread_id"]))
    _commit(db, key, pending)
    return {"status": "acknowledged", "thread_id": next_state["thread_id"],
            "appended": len(delta), "forked": forked}
