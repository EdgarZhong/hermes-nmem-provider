#!/usr/bin/env python3
"""Metadata/evidence adapter for nmem CLI users; preview is always the default.

This command does not implement an approval authority. --apply is an explicit
operator action and must be reached only after Secretary's existing approval.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import types
from pathlib import Path
from urllib.parse import quote

# Standalone CLI should not import the Provider or require its Agent base class.
if not __package__:
    package = types.ModuleType("_personal_nm_cli")
    package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[package.__name__] = package
    __package__ = package.__name__
PersonalMemClient = importlib.import_module(".personal_client", __package__).PersonalMemClient
MemHTTPError = importlib.import_module(".personal_client", __package__).MemHTTPError
history_rows = importlib.import_module(".personal_scope", __package__).history_rows

_MUTABLE = ("id", "title", "content", "importance", "unit_type", "source", "space_id", "metadata")


def edit_sha(memory):
    value = {key: memory.get(key) for key in _MUTABLE}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")
    allowed = set(_MUTABLE) | {"labels", "confidence", "event_start", "event_end"}
    if set(payload) - allowed:
        raise ValueError("Unknown field; NM-native Thread/Message provenance is not used")
    identity, content = payload.get("id"), payload.get("content")
    if not isinstance(identity, str) or not 1 <= len(identity) <= 200 or any(ord(c) < 32 for c in identity):
        raise ValueError("An explicit stable Memory ID is required for retry-safe writes")
    if not isinstance(content, str) or not content.strip() or len(content) > 32768:
        raise ValueError("content must contain 1..32768 characters")
    if "title" in payload and (not isinstance(payload["title"], str) or len(payload["title"]) > 200):
        raise ValueError("title must contain at most 200 characters")
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        raise ValueError("metadata is required")
    prov = meta.get("hermes_provenance")
    if not isinstance(prov, dict) or prov.get("version") != 1:
        raise ValueError("metadata.hermes_provenance.version must be 1")
    sources = prov.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 100:
        raise ValueError("At least one source Message Identity is required")
    seen = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"conversation_ref", "message_uid"}:
            raise ValueError("Sources must be exact Hermes Message Identity objects")
        for value in source.values():
            # IDs remain opaque: no UUID coercion, shortening or fabricated aliases.
            if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
                raise ValueError("Invalid opaque source identity")
        key = source["conversation_ref"], source["message_uid"]
        if key in seen:
            raise ValueError("Duplicate source identity")
        seen.add(key)
    return sources


def validate_evidence(home, sources):
    if not home:
        raise ValueError("--history-home is required for an applied write")
    by_ref = {}
    for source in sources:
        ref = source["conversation_ref"]
        if ref not in by_ref:
            by_ref[ref] = {row.get("message_uid") for row in history_rows(home, ref)}
        if source["message_uid"] not in by_ref[ref]:
            raise ValueError("Source is absent from the authorized canonical History Foreground")


def write_memory(client, payload, *, apply=False, update=False, expected_sha=None, history_home=None):
    sources = validate_payload(payload)
    if not apply:
        return {"status": "preview", "writes": 0, "evidence_verified": False, "memory_id": payload["id"],
                "source_count": len(sources), "notice": "No NM write. Apply only after existing Secretary approval."}
    validate_evidence(history_home, sources)
    identity = payload["id"]
    existing = None
    try:
        existing = client.memory_get(identity)
    except MemHTTPError as exc:
        if exc.status != 404:
            raise
    if update:
        if existing is None or not expected_sha or edit_sha(existing) != expected_sha:
            raise ValueError("Update requires matching --expected-sha from a fresh read")
    elif existing is not None:
        raise ValueError("Memory already exists; use update with its expected SHA")
    planned = dict(payload)
    if existing:
        if payload.get("space_id") is not None and payload["space_id"] != existing.get("space_id"):
            raise ValueError("This helper does not move existing memories between Spaces")
        planned["metadata"] = {**(existing.get("metadata") or {}), **payload["metadata"]}
    # No server CAS is advertised: this precondition detects stale reads, not all races.
    if update:
        if edit_sha(client.memory_get(identity)) != expected_sha:
            raise ValueError("Memory changed before write")
        client.request_json("PATCH", "/memories/" + quote(identity, safe=""), {k: v for k, v in planned.items() if k != "id"})
    else:
        client.request_json("POST", "/memories", planned)
    readback = client.memory_get(identity)
    for field in ("content", "metadata"):
        if readback.get(field) != planned[field]:
            raise RuntimeError("Write sent but readback differs; inspect Memory before retrying")
    return {"status": "verified", "memory_id": identity, "evidence_verified": True,
            "edit_sha": edit_sha(readback), "metadata": readback["metadata"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read")
    read.add_argument("memory_id")
    write = sub.add_parser("write")
    write.add_argument("--input", required=True, help="UTF-8 JSON file, or - for stdin")
    write.add_argument("--apply", action="store_true")
    write.add_argument("--update", action="store_true")
    write.add_argument("--expected-sha")
    write.add_argument("--history-home", default=os.environ.get("HERMES_HOME"))
    args = parser.parse_args(argv)
    client = PersonalMemClient(timeout=8)
    try:
        if args.command == "read":
            value = client.memory_get(args.memory_id)
            result = {"memory": value, "edit_sha": edit_sha(value)}
        else:
            if args.input == "-":
                text = sys.stdin.read(262145)
            else:
                text = Path(args.input).read_text(encoding="utf-8")
            if len(text) > 262144:
                raise ValueError("Payload file exceeds 256 KiB")
            result = write_memory(client, json.loads(text), apply=args.apply, update=args.update,
                                  expected_sha=args.expected_sha, history_home=args.history_home)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Never echo a credential-bearing response or private transcript into diagnostics.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "message": str(exc) if isinstance(exc, (ValueError, MemHTTPError)) else "Operation failed; no automatic retry"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
