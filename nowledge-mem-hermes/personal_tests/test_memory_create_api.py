"""Approved creation: real native CLI reads and curl POST to loopback only."""
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import io
import json
import shutil
import subprocess
import threading
import time
import unittest
from contextlib import redirect_stderr
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import test_http as HTTP

spec = importlib.util.spec_from_file_location("_standalone_memory_test", HTTP.ROOT / "nmem_memory.py")
CLI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CLI)
SOURCES, KEY = HTTP.SOURCES, HTTP.KEY
METADATA = {"hermes_provenance": SOURCES, "project": {"kind": "synthetic"}}


class Handler(HTTP.Handler):
    mode = "ok"
    post_count = 0
    headers_seen = []

    def do_GET(self):
        self.calls.append(("GET", self.path))
        self.headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        space = {"id": "space-exact", "name": "Fixture Space", "key": "fixture",
                 "aliases": ["approved-alias"]}
        if self.path == "/spaces":
            value = {"enabled": True, "spaces": [space]}
        elif self.path == "/capabilities":
            value = {}
        elif self.path == "/spaces/space-exact":
            value = space
        elif self.path.startswith("/memories/"):
            value = copy.deepcopy(self.memory)
            if self.mode == "lost_metadata":
                value["metadata"] = {}
            elif self.mode == "wrong_scope":
                value["space_id"] = "wrong-space"
            elif self.mode == "wrong_content":
                value["content"] = "different body"
            elif self.mode == "wrong_title":
                value["title"] = "different title"
            elif self.mode == "lost_labels":
                value["labels"] = []
            elif self.mode == "wrong_id":
                value["id"] = "wrong-id"
            elif self.mode == "get_denied":
                self.respond(403, b"private response")
                return
        else:
            self.respond(404, b"{}")
            return
        self.respond(200, json.dumps(value, ensure_ascii=False).encode())

    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(("POST", self.path, value))
        self.headers_seen.append({k.lower(): v for k, v in self.headers.items()})
        type(self).post_count += 1
        self.memory.update({**value, "id": "created-exact-id"})
        if self.mode == "timeout":
            time.sleep(0.15)
        if self.mode == "invalid":
            self.respond(200, b"private invalid json")
            return
        result = {"memory": copy.deepcopy(self.memory), "action": "created",
                  "assigned_labels": value.get("labels", [])}
        if self.mode == "no_id":
            result["memory"].pop("id")
        elif self.mode == "misleading_id":
            result = {"id": "not-api-contract", "nested": {"id": "not-memory"}}
        elif self.mode == "updated":
            result["action"] = "updated"
        elif self.mode == "post_wrong_scope":
            result["memory"]["space_id"] = "wrong-space"
        elif self.mode == "post_error":
            self.respond(403, b"private-error-body")
            return
        self.respond(200, json.dumps(result, ensure_ascii=False).encode())


@unittest.skipUnless(shutil.which("nmem"), "Native official CLI required")
class CreationAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        Handler.calls, Handler.headers_seen = [], []
        Handler.memory, Handler.mode, Handler.post_count = {}, "ok", 0
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.patches = [patch.dict(os.environ, {"NMEM_API_URL": self.url, "NMEM_API_KEY": KEY})]
        for context in self.patches:
            context.start()
            self.addCleanup(context.stop)
        self.client = CLI.Client()
        self.body = '【合成验收】\n$(touch /must-not-run); `false` 私人\\"'
        self.title, self.labels = "Synthetic fixture", ["notebook:situation", "notebook:decision"]

    def create(self):
        with redirect_stderr(io.StringIO()) as receipt:
            result = CLI.create_memory(self.client, self.body, METADATA, title=self.title,
                                       labels=self.labels, space="approved-alias")
        self.receipt = receipt.getvalue()
        return result

    def test_api_creates_once_with_approved_payload_and_same_connection_readback(self):
        with patch.object(CLI.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            result = self.create()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(result["metadata"], "readback_confirmed")
        writes = [call for call in Handler.calls if call[0] != "GET"]
        self.assertEqual(writes, [("POST", "/memories", {
            "content": self.body, "title": self.title, "labels": self.labels,
            "space_id": "space-exact", "source": "nmem-memory",
            "metadata": METADATA})])
        self.assertEqual(Handler.post_count, 1)
        self.assertEqual(json.loads(self.receipt)["memory_id"], "created-exact-id")
        self.assertGreaterEqual(sum(call[:2] == ("GET", "/memories/created-exact-id")
                                    for call in Handler.calls), 2)
        self.assertTrue(all(h.get("x-nmem-api-key") == KEY or h.get("authorization") == "Bearer " + KEY for h in Handler.headers_seen))
        self.assertNotIn(KEY, repr(launch.call_args_list))
        self.assertNotIn(self.body, repr(launch.call_args_list))
        argv = [call.args[0] for call in launch.call_args_list]
        self.assertFalse(any("add" in args or "update" in args for args in argv))

    def test_200_without_documented_id_stays_unknown_and_has_no_readback_or_retry(self):
        for mode in ("no_id", "misleading_id", "invalid", "post_error"):
            with self.subTest(mode=mode):
                Handler.calls, Handler.mode = [], mode
                before = Handler.post_count
                result = self.create()
                self.assertEqual(result["status"], "creation_unknown", result)
                self.assertIsNone(result["memory_id"])
                self.assertEqual(Handler.post_count, before + 1)
                self.assertFalse(any(c[1].startswith("/memories/") for c in Handler.calls))

    def test_timeout_stays_unknown_without_retry_or_cli_fallback(self):
        Handler.mode = "timeout"
        self.client._timeout = 0.03
        result = self.create()
        self.assertEqual(result["status"], "creation_unknown", result)
        self.assertEqual(Handler.post_count, 1)
        self.assertFalse(any(c[1].startswith("/memories/") for c in Handler.calls))

    def test_readback_failure_or_mismatch_retains_id_and_pending_sources(self):
        for mode in ("lost_metadata", "post_wrong_scope", "wrong_scope", "wrong_content", "wrong_title",
                     "lost_labels", "wrong_id", "get_denied"):
            with self.subTest(mode=mode):
                Handler.calls, Handler.mode = [], mode
                before = Handler.post_count
                result = self.create()
                self.assertEqual(result["status"], "partial", result)
                self.assertEqual(result["memory_id"], "created-exact-id")
                self.assertEqual(result["metadata"], "unconfirmed")
                self.assertEqual(Handler.post_count, before + 1)
                self.assertFalse(any(c[0] in {"PATCH", "PUT", "DELETE"} for c in Handler.calls))

    def test_upsert_response_does_not_claim_created(self):
        Handler.mode = "updated"
        result = self.create()
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["creation"], "unconfirmed")
        self.assertEqual(result["memory_id"], "created-exact-id")
        self.assertEqual(Handler.post_count, 1)

    def test_unresolved_space_and_oversize_content_do_not_create(self):
        for reference in ("unknown-space", ""):
            with self.subTest(reference=reference):
                # A missing explicit selector is canonical Default; fixture has none.
                with self.assertRaises(ValueError):
                    CLI.create_memory(self.client, "approved", METADATA, space=reference)
        with self.assertRaises(ValueError):
            CLI.create_memory(self.client, "x" * 32769, METADATA, space="approved-alias")
        self.assertEqual(Handler.post_count, 0)

    def test_bound_connection_is_frozen_and_ambient_lane_does_not_override(self):
        import os
        with patch.dict(os.environ, {"NMEM_SPACE": "wrong", "NMEM_SPACE_ID": "wrong"}):
            bound = CLI.Client(self.url)
        self.assertNotIn("NMEM_SPACE", bound.cli_env)
        self.assertNotIn("NMEM_SPACE_ID", bound.cli_env)
        self.assertEqual(bound.cli_env["NMEM_API_KEY"], KEY)
        self.assertEqual(bound.cli_env["NMEM_API_URL"], self.url)
        with patch.dict(os.environ, {"NMEM_API_KEY": "changed"}):
            self.assertEqual(bound._api_key(), KEY)

    def test_readback_not_just_create_echo_confirms_metadata(self):
        # Both the creation response and official CLI succeed; only the actual
        # Metadata GET drops the attachment, so complete would be a false receipt.
        Handler.mode = "lost_metadata"
        outcome = self.create()
        self.assertEqual(outcome["status"], "partial")
        self.assertEqual(Handler.post_count, 1)
        self.assertEqual(sum(c[:2] == ("GET", "/memories/created-exact-id")
                             for c in Handler.calls), 2)



    def test_standard_python_outside_repo_help_preview_and_generic_metadata(self):
        python = "/usr/bin/python3"
        if not Path(python).is_file():
            self.skipTest("Standard system Python unavailable")
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder)
            entry = cwd / "nmem-memory.py"
            shutil.copy2(CLI.__file__, entry)
            body, metadata = cwd / "body.txt", cwd / "metadata.json"
            body.write_text("Approved independent synthetic Memory", encoding="utf-8")
            metadata.write_text(json.dumps({"project": "standalone", "facts": [1, True]}))
            env = {k: v for k, v in os.environ.items()
                   if k not in {"HERMES_HOME", "PYTHONPATH", "VIRTUAL_ENV"}}
            env["PATH"] = "/nonexistent"  # Help/preview cannot invoke nmem or curl.
            for args in (["--help"], ["create", "--help"],
                         ["create", "--content-file", str(body), "--metadata-file", str(metadata),
                          "--title", "Independent", "--space", "approved-alias", "--label", "test"]):
                result = subprocess.run([python, "-I", "-S", str(entry), *args],
                                        cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if "--help" in args:
                    self.assertIn("--metadata-file", result.stdout)
                    self.assertIn("any JSON object", result.stdout)
                    self.assertIn("ACTUAL_FULL_UID", result.stdout)
                else:
                    self.assertEqual(json.loads(result.stdout)["status"], "preview")
        self.assertEqual(Handler.calls, [])

    def test_generic_metadata_apply_needs_no_hermes_fields(self):
        metadata = {"project": "standalone", "facts": [1, True], "nullable": None}
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder)
            entry = cwd / "nmem-memory.py"
            shutil.copy2(CLI.__file__, entry)
            body, meta = cwd / "body.txt", cwd / "metadata.json"
            body.write_text(self.body, encoding="utf-8")
            meta.write_text(json.dumps(metadata))
            env = {k: v for k, v in os.environ.items()
                   if k not in {"HERMES_HOME", "PYTHONPATH", "VIRTUAL_ENV"}}
            result = subprocess.run(["/usr/bin/python3", "-I", "-S", str(entry),
                                     "--api-url", self.url, "create", "--content-file", str(body),
                                     "--metadata-file", str(meta), "--title", self.title,
                                     "--label", self.labels[0], "--space", "approved-alias", "--apply"],
                                    cwd=cwd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "complete")
        self.assertEqual(Handler.memory["metadata"], metadata)
        self.assertEqual(Handler.post_count, 1)
        Handler.calls, Handler.post_count, Handler.mode = [], 0, "lost_metadata"
        result = CLI.create_memory(self.client, self.body, {"nullable": None},
                                   title=self.title, labels=self.labels, space="approved-alias")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(Handler.post_count, 1)

    def test_host_shared_config_and_overrides_are_frozen(self):
        with tempfile.TemporaryDirectory(dir=HTTP.ROOT.parent / "temp-r3-personal") as folder:
            config = Path(folder) / ".nowledge-mem/config.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"apiUrl": self.url, "apiKey": KEY}))
            env = {k: v for k, v in os.environ.items() if k not in {"NMEM_API_URL", "NMEM_API_KEY"}}
            env["HOME"] = folder
            with patch.dict(os.environ, env, clear=True):
                client = CLI.Client()
                self.assertEqual((client._api_url(), client._api_key()), (self.url, KEY))
                with patch.dict(os.environ, {"NMEM_API_URL": "http://127.0.0.1:1", "NMEM_API_KEY": ""}):
                    override = CLI.Client(self.url)
                    self.assertEqual((override._api_url(), override._api_key()), (self.url, ""))
                self.assertEqual(client._api_key(), KEY)
