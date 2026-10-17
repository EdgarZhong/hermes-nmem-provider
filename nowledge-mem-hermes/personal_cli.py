#!/usr/bin/env python3
"""Create with official nmem, then attach Hermes metadata; preview by default.

Only Main may apply specifically approved content and destination. --apply is
an execution switch, not an approval authority. Other management uses nmem.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

# Standalone use must not load the Provider or require Hermes Agent classes.
if not __package__:
    package = types.ModuleType("_personal_nm_cli")
    package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[package.__name__] = package
    __package__ = package.__name__
PersonalMemClient = importlib.import_module(".personal_client", __package__).PersonalMemClient
_resolve_nmem = importlib.import_module(".client", __package__)._resolve_nmem


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's normal error may echo private arguments or a mistaken key.
        raise ValueError("Invalid arguments; consult --help (arguments not echoed)")


def _identity(value: Any) -> str:
    if (not isinstance(value, str) or not value.strip()
            or value in {".", ".."} or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("A complete, nonempty opaque identity is required")
    return value


def read_text(path: str) -> str:
    """Read at most 256 KiB without newline rewriting or content normalization."""
    with Path(path).open("rb") as handle:
        data = handle.read(262145)
    if len(data) > 262144:
        raise ValueError("Input file exceeds 256 KiB")
    return data.decode("utf-8")


def read_provenance(path: str) -> dict[str, Any]:
    """Structural checks only: no History access, inference or approval check."""
    value = json.loads(read_text(path))
    if (not isinstance(value, dict) or set(value) != {"version", "sources"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["sources"], list) or not value["sources"]):
        raise ValueError("Expected version 1 provenance with nonempty sources")
    for source in value["sources"]:
        if not isinstance(source, dict) or set(source) != {"conversation_ref", "message_uid"}:
            raise ValueError("Each source needs conversation_ref and message_uid")
        _identity(source["conversation_ref"])
        _identity(source["message_uid"])
    return value


class _BoundClient(PersonalMemClient):
    """Freeze existing host resolution for both subprocess and metadata HTTP.

    Reuse client.py's env/config/default rules; --api-url is the official
    one-off override. No helper config, hardcoded endpoint or global env edits.
    """
    def __init__(self, api_url: str | None = None):
        super().__init__(timeout=8)
        self._bound_url = (api_url if api_url is not None else super()._api_url()).strip().rstrip("/")
        self._bound_key = super()._api_key()
        parts = urlsplit(self._bound_url)
        if (parts.scheme not in {"http", "https"} or not parts.netloc
                or parts.username or parts.password or parts.query or parts.fragment
                or any(ord(c) < 33 or ord(c) == 127 for c in self._bound_url)):
            raise ValueError("Invalid NM endpoint; credentials belong in host configuration")
        self.cli_env = os.environ.copy()
        self.cli_env["NMEM_API_URL"] = self._bound_url
        # Pin even an empty key so CLI cannot pick up a different config later.
        self.cli_env["NMEM_API_KEY"] = self._bound_key

    def _api_url(self) -> str:
        return self._bound_url

    def _api_key(self) -> str:
        return self._bound_key


def parse_created_id(output: bytes | str) -> str:
    """Official CLI docs: `nmem --json m add ... | jq -r '.id'`.

    https://mem.nowledge.co/docs/cli#json-output (reviewed 2026-10-16).
    Accept only that top-level ID after exit 0; never scrape text, nested IDs,
    supplied IDs, search results, timeout output or another command's result.
    """
    value = json.loads(output)
    if (not isinstance(value, dict) or value.get("success") is False
            or value.get("error") or value.get("status") in {"error", "failed"}):
        raise ValueError("Unconfirmed official CLI creation result")
    return _identity(value.get("id"))


def attach_metadata(client: PersonalMemClient, memory_id: str,
                    provenance: dict[str, Any]) -> str:
    """GET existing metadata, PATCH only metadata.hermes_provenance.

    The narrow HTTP contract is isolated here for the deferred local basic
    check. This is not a server CAS or a full write/readback verification.
    """
    _identity(memory_id)
    memory = client.memory_get(memory_id)
    metadata = memory.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("Existing Memory metadata is not an object")
    if metadata.get("hermes_provenance") == provenance:
        return "already_present"
    merged = {**metadata, "hermes_provenance": provenance}
    response = client.request_json(
        "PATCH", "/memories/" + quote(memory_id, safe=""), {"metadata": merged},
    )
    # HTTP acknowledgement is not a new guarantee of durable server behavior.
    if not isinstance(response, dict) or response.get("success") is False or response.get("error"):
        raise RuntimeError("Metadata was not acknowledged")
    returned = response.get("memory", response)
    if not isinstance(returned, dict):
        raise RuntimeError("Unexpected metadata response")
    if "id" in returned and returned["id"] != memory_id:
        raise RuntimeError("Metadata response identity differs")
    if "metadata" in returned and returned["metadata"] != merged:
        raise RuntimeError("Metadata response differs from submitted metadata")
    return "http_acknowledged"


def _finish(client: PersonalMemClient, memory_id: str, provenance: dict[str, Any],
            *, created: bool) -> dict[str, Any]:
    creation = "confirmed" if created else "existing_id"
    try:
        if created:
            # Emit the real ID before step two, so an interrupted PATCH does
            # not hide the receipt. Never print the body, key or raw CLI output.
            print(json.dumps({"status": "created", "memory_id": memory_id,
                              "metadata": "pending"}), file=sys.stderr, flush=True)
        status = attach_metadata(client, memory_id, provenance)
        return {"status": "complete", "memory_id": memory_id,
                "creation": creation, "metadata": status}
    except (Exception, KeyboardInterrupt) as exc:
        return {"status": "partial", "memory_id": memory_id, "creation": creation,
                "metadata": "unconfirmed", "error_type": type(exc).__name__,
                "next_action": "Use attach with this ID and the same destination; do not create again"}


def create_memory(client: _BoundClient, content: str, provenance: dict[str, Any],
                  *, title: str | None = None, labels: list[str] | None = None,
                  space: str | None = None) -> dict[str, Any]:
    exe = _resolve_nmem()
    if not exe:
        raise ValueError("Official nmem executable not found; no creation attempted")
    if Path(exe).suffix.lower() in {".cmd", ".bat"}:
        # shell=False still invokes cmd.exe for batch shims. Do not interpolate
        # arguments: cloud/native executables are the supported narrow path.
        raise ValueError("Use a native nmem executable, not a batch shim; no creation attempted")
    argv = [exe, "--json", "--api-url", client._api_url()]
    if space is not None:
        argv.extend(["--space", space])
    argv.extend(["m", "add", "--stdin", "--source", "hermes-secretary"])
    if title is not None:
        argv.extend(["--title", title])
    for label in labels or []:
        argv.extend(["-l", label])
    memory_id = None
    try:
        result = subprocess.run(argv, input=content.encode("utf-8"), capture_output=True,
                                env=client.cli_env, timeout=60, shell=False)
        if result.returncode != 0:
            raise ValueError("CLI exited without confirmed creation")
        memory_id = parse_created_id(result.stdout)
        return _finish(client, memory_id, provenance, created=True)
    except (Exception, KeyboardInterrupt) as exc:
        # Communication can fail after launch too. Never report such an OS
        # error as proof that creation did not happen, or retry automatically.
        if memory_id is not None:
            return {"status": "partial", "memory_id": memory_id, "creation": "confirmed",
                    "metadata": "unconfirmed", "error_type": type(exc).__name__,
                    "next_action": "Use attach with this ID and the same destination; do not create again"}
        return {"status": "creation_unknown", "memory_id": None, "metadata": "not_attempted",
                "error_type": type(exc).__name__,
                "next_action": "Inspect with official nmem; do not blindly repeat create"}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--api-url", help="Official one-off URL override, shared by both steps")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Official CLI creation, followed by metadata attachment")
    create.add_argument("--content-file", required=True, help="Approved UTF-8 body, passed unchanged to CLI stdin")
    create.add_argument("--title")
    create.add_argument("--label", "-l", action="append", default=[])
    create.add_argument("--space", help="Bound profile Space; pass explicitly, do not rely on ambient NMEM_SPACE")
    attach = sub.add_parser("attach", help="Repair metadata only for a known created Memory ID")
    attach.add_argument("memory_id")
    for command in (create, attach):
        command.add_argument("--provenance-file", required=True, help="UTF-8 JSON: version and sources only")
        command.add_argument("--apply", action="store_true", help="Execute only after specific user approval")
    try:
        args = parser.parse_args(argv)
        provenance = read_provenance(args.provenance_file)
        if args.command == "create":
            content = read_text(args.content_file)
            if not content.strip():
                raise ValueError("Approved body must not be empty")
        else:
            _identity(args.memory_id)
        if not args.apply:
            result = {"status": "preview", "writes": 0, "operation": args.command,
                      "source_count": len(provenance["sources"]),
                      "notice": "No CLI or network calls. --apply is not user approval."}
        else:
            client = _BoundClient(args.api_url)
            if args.command == "create":
                result = create_memory(client, content, provenance, title=args.title,
                                       labels=args.label, space=args.space)
            else:
                result = _finish(client, args.memory_id, provenance, created=False)
    except (Exception, KeyboardInterrupt) as exc:
        # Only input/preparation failures reach here, before a write is sent.
        result = {"status": "failed", "creation": "not_attempted", "metadata": "not_attempted",
                  "error_type": type(exc).__name__,
                  "message": "Preparation failed; check inputs, executable and host NM configuration"}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return {"preview": 0, "complete": 0, "partial": 2, "creation_unknown": 3}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
