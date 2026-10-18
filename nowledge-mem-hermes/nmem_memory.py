#!/usr/bin/env python3
"""Create one NM Memory with metadata in a single API request; preview by default.

Only apply content and destination the caller has approved. Other NM operations
belong to the official nmem CLI. No agent framework or Python dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib import parse

_MAX_RESPONSE = 8 * 1024 * 1024





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


def _resolve_nmem() -> str | None:
    """Return the absolute path to the ``nmem`` executable, or ``None``.

    ``shutil.which`` honors PATHEXT, so on Windows it correctly resolves the
    ``nmem.CMD`` shim that ``subprocess.run(["nmem", ...], shell=False)`` would
    miss. Desktop Electron hosts often launch Python with a reduced macOS PATH
    that omits user install locations such as ``~/.local/bin`` and Homebrew, so
    keep a small executable fallback list before disabling the provider.
    """
    found = shutil.which("nmem")
    if found:
        return found

    paths: list[str] = []
    for env_name in ("NMEM_CLI_PATH", "NMEM_BIN", "NMEM_CLI"):
        configured = os.environ.get(env_name)
        if configured and configured.strip():
            paths.append(os.path.expanduser(configured.strip()))

    if sys.platform == "darwin":
        paths.extend(
            [
                "~/.local/bin/nmem",
                "/opt/homebrew/bin/nmem",
                "/usr/local/bin/nmem",
            ]
        )
    elif os.name != "nt":
        paths.extend(
            [
                "~/.local/bin/nmem",
                "/usr/local/bin/nmem",
                "/usr/bin/nmem",
            ]
        )

    for path in paths:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
    return None


class MemHTTPError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"NM HTTP {status}")


def _curl_value(value: str) -> str:
    """Quote a curl config value; private values never enter argv or a shell."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace(
        "\r", "\\r").replace("\n", "\\n").replace("\t", "\\t") + '"'


def _curl_json(config: str, timeout: float) -> bytes:
    executable = shutil.which("curl")
    command = [executable] if executable else []
    if not command or Path(command[0]).suffix.lower() in {".cmd", ".bat"}:
        raise RuntimeError("Native curl executable not found; no NM request attempted")
    # --disable must be first: an ambient curlrc must not add redirects/retries.
    argv = [*command, "--disable", "--silent", "--globoff", "--proto", "=http,https",
            "--max-time", str(timeout), "--max-filesize", str(_MAX_RESPONSE),
            "--config", "-", "--write-out", "\n%{http_code}"]
    try:
        with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, shell=False) as process:
            try:
                process.stdin.write(config.encode("utf-8"))
                process.stdin.close()
                # Four trailing bytes carry the status. Bound the read even on
                # curl versions whose max-filesize only checks Content-Length.
                data = process.stdout.read(_MAX_RESPONSE + 5)
                if len(data) > _MAX_RESPONSE + 4:
                    raise RuntimeError("NM response exceeds safe size")
                code = process.wait(timeout=timeout + 1)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("NM transport unavailable") from None
    if code == 63:
        raise RuntimeError("NM response exceeds safe size")
    if code != 0 or len(data) < 4 or data[-4:-3] != b"\n" or not data[-3:].isdigit():
        raise RuntimeError("NM transport unavailable")
    status = int(data[-3:])
    if status >= 300:
        raise MemHTTPError(status)
    if status < 200:
        raise RuntimeError("NM transport unavailable")
    return data[:-4]


def _connection(api_url=None):
    # Same official shared config and override precedence used by the nmem CLI.
    url = api_url if api_url is not None else os.environ.get("NMEM_API_URL")
    key = os.environ.get("NMEM_API_KEY")
    config = {}
    if not url or key is None:
        try:
            config = json.loads((Path.home() / ".nowledge-mem/config.json").read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                config = {}
        except (OSError, ValueError):
            config = {}
    if url is None or (api_url is None and not url):
        url = config.get("apiUrl") or config.get("api_url") or "http://127.0.0.1:14242"
    if key is None:
        key = config.get("apiKey") or config.get("api_key") or ""
    return str(url).strip().rstrip("/"), str(key).strip()


class Client:
    def __init__(self, api_url=None, timeout=8):
        self._timeout = timeout
        self._bound_url, self._bound_key = _connection(api_url)
        parts = parse.urlsplit(self._bound_url)
        if (parts.scheme not in {"http", "https"} or not parts.netloc
                or parts.username or parts.password or parts.query or parts.fragment
                or any(ord(c) < 33 or ord(c) == 127 for c in self._bound_url)):
            raise ValueError("Invalid NM endpoint; credentials belong in host configuration")
        self.cli_env = os.environ.copy()
        self.cli_env["NMEM_API_URL"] = self._bound_url
        self.cli_env["NMEM_API_KEY"] = self._bound_key
        self.cli_env.pop("NMEM_SPACE", None)
        self.cli_env.pop("NMEM_SPACE_ID", None)

    def _api_url(self):
        return self._bound_url

    def _api_key(self):
        return self._bound_key

    def request_json(self, method: str, path: str, payload: dict | None = None) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Expected relative NM API path")
        base = self._api_url().rstrip("/")
        parts = parse.urlsplit(base)
        if (parts.scheme not in {"http", "https"} or not parts.netloc or parts.username
                or parts.password or parts.query or parts.fragment
                or any(ord(c) < 33 or ord(c) == 127 for c in base + path)):
            raise ValueError("Invalid NM API URL")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        key = self._api_key()
        if key:
            if any(ord(c) < 32 or ord(c) == 127 for c in key):
                raise ValueError("Invalid NM authentication header")
            headers.update(Authorization=f"Bearer {key}", **{"X-NMEM-API-Key": key})
        config = ["url = " + _curl_value(base + path), "request = " + _curl_value(method)]
        config.extend("header = " + _curl_value(f"{name}: {value}")
                      for name, value in headers.items())
        if body is not None:
            config.append("data-binary = " + _curl_value(body))
        data = _curl_json("\n".join(config) + "\n", self._timeout)
        try:
            return json.loads(data) if data.strip() else {}
        except (UnicodeError, ValueError):
            raise RuntimeError("Invalid NM JSON response") from None

    def memory_get(self, memory_id: str) -> dict:
        result = self.request_json("GET", "/memories/" + parse.quote(memory_id, safe=""))
        if not isinstance(result, dict):
            raise RuntimeError("Invalid Memory response")
        result = result.get("memory", result)
        if not isinstance(result, dict) or result.get("id") != memory_id:
            raise RuntimeError("Memory ID mismatch")
        return result


def _bound_cli(client: Client, args: list[str]) -> dict[str, Any]:
    """Official read operations, pinned to the same resolved HTTP connection."""
    exe = _resolve_nmem()
    if not exe or Path(exe).suffix.lower() in {".cmd", ".bat"}:
        raise ValueError("Native official nmem executable required; no creation attempted")
    result = subprocess.run([exe, "--json", "--api-url", client._api_url(), *args],
                            capture_output=True, env=client.cli_env, timeout=client._timeout,
                            shell=False)
    if result.returncode != 0:
        raise ValueError("Official NM read was not confirmed")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("success") is False or value.get("error"):
        raise ValueError("Invalid official NM read response")
    return value


def _creation_space(client: Client, space: str | None) -> str:
    # Preserve the existing name/alias selector via the official resolver. Do
    # not send a display name as space_id or inherit an ambient CLI lane.
    reference = "default" if space is None or not space.strip() else space
    value = _bound_cli(client, ["spaces", "show", "--", reference])
    selected = value.get("space", value)
    if not isinstance(selected, dict):
        raise ValueError("Invalid official Space response")
    return _identity(selected.get("id"))


def _created_api_memory(response: Any) -> dict[str, Any]:
    # Official POST /memories returns {memory: {id: ...}, action: ...}.
    # CLI's top-level ID belongs to its different output contract.
    if (not isinstance(response, dict) or response.get("success") is False
            or response.get("error") or response.get("status") in {"error", "failed"}
            or not isinstance(response.get("memory"), dict)):
        raise ValueError("Unconfirmed official API creation result")
    memory = response["memory"]
    _identity(memory.get("id"))
    return memory


def _verify_created(client: Client, memory_id: str, payload: dict[str, Any]) -> None:
    # CLI preserves display label names but omits arbitrary Metadata. Read both
    # official views; the POST response alone cannot prove durable attachment.
    shown = _bound_cli(client, ["m", "show", "--", memory_id])
    labels = shown.get("labels")
    if (shown.get("id") != memory_id or not isinstance(labels, list)
            or not all(label in labels for label in payload["labels"])):
        raise ValueError("Created Memory identity or labels differ")
    stored = client.memory_get(memory_id)
    for value in (shown, stored):
        for field in ("content", "space_id", "title"):
            if field in payload and value.get(field) != payload[field]:
                raise ValueError("Created Memory scope or approved content differs")
    metadata = stored.get("metadata")
    if (not isinstance(metadata, dict)
            or any(key not in metadata or metadata[key] != value for key, value in payload["metadata"].items())):
        raise ValueError("Created Memory metadata was not confirmed by readback")


def create_memory(client: Client, content: str, metadata: dict[str, Any],
                  *, title: str | None = None, labels: list[str] | None = None,
                  space: str | None = None, source: str = "nmem-memory") -> dict[str, Any]:
    # Official create schema limits; failures here and in Space resolution are
    # preparation failures, before the only write attempt.
    if not isinstance(content, str) or not content.strip() or len(content) > 32768:
        raise ValueError("Approved body must contain 1–32768 characters")
    if title is not None and (not isinstance(title, str) or len(title) > 200):
        raise ValueError("Approved title must contain at most 200 characters")
    if labels is not None and (not isinstance(labels, list)
                               or any(not isinstance(label, str) or not label for label in labels)):
        raise ValueError("Labels must be nonempty text values")
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a JSON object")
    json.dumps(metadata, allow_nan=False)
    payload = {"content": content, "source": source, "labels": labels or [],
               "space_id": _creation_space(client, space),
               "metadata": metadata}
    if title is not None:
        payload["title"] = title
    memory_id = None
    creation = "unconfirmed"
    try:
        response = client.request_json("POST", "/memories", payload)
        memory = _created_api_memory(response)
        memory_id = memory["id"]
        print(json.dumps({"status": "created", "memory_id": memory_id,
                          "metadata": "pending"}), file=sys.stderr, flush=True)
        if response.get("action") != "created":
            raise ValueError("API did not confirm a newly created Memory")
        creation = "confirmed"
        if memory.get("space_id") != payload["space_id"]:
            raise ValueError("Creation response Space differs")
        _verify_created(client, memory_id, payload)
        return {"status": "complete", "memory_id": memory_id, "creation": creation,
                "metadata": "readback_confirmed"}
    except (Exception, KeyboardInterrupt) as exc:
        if memory_id is not None:
            return {"status": "partial", "memory_id": memory_id, "creation": creation,
                    "metadata": "unconfirmed", "error_type": type(exc).__name__,
                    "next_action": "Inspect this ID with official nmem; retain pending sources; do not create again"}
        return {"status": "creation_unknown", "memory_id": None, "metadata": "unconfirmed",
                "error_type": type(exc).__name__,
                "next_action": "Inspect with official nmem; retain pending sources; do not blindly repeat create"}


_HELP = """Files are UTF-8: BODY contains the approved plain-text Memory body (not a JSON string);
METADATA contains any JSON object, e.g. {"project":"synthetic-demo"}.
The complete metadata object is submitted with content/title/labels/space in one POST.
Caller-owned source metadata can also be supplied, for example:
{"hermes_provenance":{"version":1,"sources":[{"conversation_ref":"ACTUAL_FULL_REF","message_uid":"ACTUAL_FULL_UID"}]}}
Supply real source identities from your application's original evidence; this tool
never reads agent history, infers sources, or grants approval.

Example (preview; zero CLI/network calls):
  python3 ~/scrips/nmem-memory.py create --content-file approved.txt --title 'Approved title' --label notebook:situation --space 'Exact Space' --metadata-file metadata.json
Add --apply only for the specifically approved create; repeat --label for multiple labels.
Use the exact Space name/alias/ID; --space '' selects Default and ignores ambient NMEM_SPACE.
Connection: --api-url (before create), then NMEM_API_URL, then the official
~/.nowledge-mem/config.json apiUrl/api_url, then http://127.0.0.1:14242;
NMEM_API_KEY (including empty) overrides apiKey/api_key in that same config.
Credentials remain on the running host; never put them in arguments or metadata.
Requires official native nmem and curl on this host; Python uses only the standard library.

One creation attempt only: complete requires same-ID CLI and GET readback of approved
fields and supplied metadata (a POST echo is insufficient); partial retains a known ID,
creation_unknown has no confirmed ID. Neither retries, repairs, updates, or deletes.
Exit codes: 0 preview/complete, 1 preparation failed, 2 partial, 3 creation_unknown.
"""


def main(argv=None):
    parser = _Parser(description=__doc__, epilog=_HELP,
                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", help="One-off official API URL override; use before create")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="One creation with metadata, followed by same-ID readback",
                                 epilog=_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    create.add_argument("--content-file", required=True, metavar="BODY", help="Approved UTF-8 plain-text body, unchanged")
    create.add_argument("--metadata-file", required=True, metavar="METADATA", help="UTF-8 JSON object; sent unchanged, including caller-owned provenance")
    create.add_argument("--title", help="Approved title (at most 200 characters)")
    create.add_argument("--label", "-l", action="append", default=[], help="Approved native label; repeat for multiple labels")
    create.add_argument("--space", help="Exact Space name/alias/ID; pass explicitly, empty string selects Default")
    create.add_argument("--apply", action="store_true", help="Perform the specifically approved attempt; absent means offline preview")
    try:
        args = parser.parse_args(argv)
        content = read_text(args.content_file)
        metadata = json.loads(read_text(args.metadata_file))
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a JSON object")
        json.dumps(metadata, allow_nan=False)
        if not content.strip() or len(content) > 32768:
            raise ValueError("Body must contain 1–32768 characters")
        if args.title is not None and len(args.title) > 200:
            raise ValueError("Title exceeds 200 characters")
        if not args.apply:
            result = {"status": "preview", "writes": 0, "operation": "create",
                      "metadata_field_count": len(metadata), "notice": "No CLI or network calls; --apply is not approval"}
        else:
            result = create_memory(Client(args.api_url), content, metadata, title=args.title,
                                   labels=args.label, space=args.space)
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "failed", "creation": "not_attempted", "metadata": "not_attempted",
                  "error_type": type(exc).__name__,
                  "message": "Preparation failed; consult --help and host NM configuration"}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return {"preview": 0, "complete": 0, "partial": 2, "creation_unknown": 3}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
