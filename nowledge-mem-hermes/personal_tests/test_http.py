"""Formal helper HTTP roundtrips against loopback; never a real NM service."""
import copy
import importlib
import io
import json
import subprocess
import sys
import threading
import time
import types
import unittest
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT.parent.parent / "hermes-secretary"
sys.path.insert(0, str(HOST))
pkg = types.ModuleType("_nm_http_test")
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
C = importlib.import_module(pkg.__name__ + ".personal_client")
CLI = importlib.import_module(pkg.__name__ + ".personal_cli")
KEY = 'fixture-key-"\\literal'
SOURCES = {"version": 1, "sources": [
    {"conversation_ref": "conv_approved", "message_uid": "uid_approved"},
]}


class Handler(BaseHTTPRequestHandler):
    calls = []
    memory = {}
    denied = False
    ignore_metadata = False

    def log_message(self, *args):
        pass

    def respond(self, status, data, *, sized=True):
        self.send_response(status)
        if sized:
            self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.calls.append(("GET", self.path, dict(self.headers)))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", self.server.base + "/redirect-target")
            self.end_headers()
        elif self.path in {"/missing", "/forbidden"}:
            self.respond(403 if self.path == "/forbidden" else 404,
                         (KEY + " private-error-body").encode())
        elif self.path == "/timeout":
            time.sleep(0.25)
            self.respond(200, b"{}")
        elif self.path == "/invalid":
            self.respond(200, (KEY + " private-invalid-json").encode())
        elif self.path.startswith("/large"):
            self.respond(200, b" " * (C._MAX_RESPONSE + 1),
                         sized=self.path != "/large-unsized")
        elif self.path == "/exact-limit":
            self.respond(200, b"{}" + b" " * (C._MAX_RESPONSE - 2))
        elif self.path.startswith("/memories/"):
            self.respond(403 if self.denied else 200,
                         json.dumps(self.memory, ensure_ascii=False).encode())
        else:
            self.respond(200, b'{"rendered_markdown":"stable context"}')

    def do_PATCH(self):
        value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(("PATCH", self.path, value))
        if not self.ignore_metadata:
            self.memory.update(value)
        self.respond(200, json.dumps(self.memory, ensure_ascii=False).encode())

    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(("POST", self.path, value))
        self.respond(200, b'{"success":true}')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        Handler.calls = []
        Handler.memory = {"id": "created-exact-id", "content": "approved body",
                          "label_ids": ["unchanged"],
                          "metadata": {"unrelated": {"keep": [True, "原样"]}}}
        Handler.denied = False
        Handler.ignore_metadata = False
        self.url = self.server.base
        self.base = patch.object(C.PersonalMemClient, "_api_url", return_value=self.url)
        self.base.start()
        self.key = patch.object(C.PersonalMemClient, "_api_key", return_value=KEY)
        self.key.start()
        self.addCleanup(self.key.stop)
        self.addCleanup(self.base.stop)

    def test_bundle_excludes_wm_and_preserves_space(self):
        client = C.PersonalMemClient(timeout=2, space="个人 空间")
        with patch.object(C.NowledgeMemClient, "_cli", return_value={
                "rendered_markdown": "stable context"}) as cli:
            self.assertEqual(client.context_bundle(host_agent_id="edgar-test")[
                "rendered_markdown"], "stable context")
        self.assertEqual(cli.call_args.args[0], [
            "context", "read", "--source-app", "hermes", "--no-working-memory",
            "--host-agent-id", "edgar-test", "--space-id", "个人 空间"])
        self.assertEqual(Handler.calls, [])

    def test_credentials_headers_not_query_or_argv_and_default_curl_ua(self):
        with patch.object(C.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            C.PersonalMemClient().request_json("GET", "/context/bundle")
        _, path, headers = Handler.calls[0]
        self.assertNotIn(KEY, path)
        self.assertEqual(headers.get("Authorization"), "Bearer " + KEY)
        self.assertEqual(headers.get("X-NMEM-API-Key"), KEY)
        self.assertTrue(headers["User-Agent"].startswith("curl/"))
        self.assertNotIn(KEY, repr(launch.call_args))
        self.assertEqual(launch.call_count, 1)

    def test_redirect_is_not_followed(self):
        with self.assertRaises(C.MemHTTPError) as caught:
            C.PersonalMemClient().request_json("GET", "/redirect")
        self.assertEqual(caught.exception.status, 302)
        self.assertEqual(len(Handler.calls), 1)

    def test_http_errors_do_not_echo_body_or_retry(self):
        for path, status in (("/missing", 404), ("/forbidden", 403)):
            with self.subTest(path=path), self.assertRaises(C.MemHTTPError) as caught:
                C.PersonalMemClient().request_json("GET", path)
            self.assertEqual(str(caught.exception), f"NM HTTP {status}")
        self.assertEqual(len(Handler.calls), 2)

    def test_relative_path_and_endpoint_validation_before_launch(self):
        for path in ("//other.test/data", "https://other.test/data", "/newline\nnext"):
            with self.subTest(path=path), patch.object(C.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError):
                    C.PersonalMemClient().request_json("GET", path)
                launch.assert_not_called()
        for base in ("ftp://host", "https://key@host", "https://host?key=bad",
                     "https://host/#fragment", "https://host\nnext"):
            with self.subTest(base=base), patch.object(C.PersonalMemClient, "_api_url",
                                                      return_value=base):
                with self.assertRaises(ValueError):
                    C.PersonalMemClient().request_json("GET", "/memory")

    def test_upstream_append_transport_and_deduplicate(self):
        C.PersonalMemClient(space="default").append_thread(
            "conv/1", [{"role": "user", "content": "test"}])
        method, path, payload = Handler.calls[0]
        self.assertEqual((method, path), ("POST", "/threads/conv%2F1/append"))
        self.assertTrue(payload["deduplicate"])
        self.assertEqual(payload["space_id"], "default")

    def test_formal_attach_merges_metadata_and_keeps_literal_payload_private(self):
        literal = '私人\\"\n$(touch /must-not-run); `false` \t\r --next @file'
        provenance = copy.deepcopy(SOURCES)
        provenance["sources"][0]["message_uid"] = literal
        before = copy.deepcopy(Handler.memory)
        with patch.object(C.subprocess, "Popen", wraps=subprocess.Popen) as launch:
            self.assertEqual(CLI.attach_metadata(C.PersonalMemClient(),
                             "created-exact-id", provenance), "http_acknowledged")
            after = C.PersonalMemClient().memory_get("created-exact-id")
        self.assertEqual(after, {**before, "metadata": {
            **before["metadata"], "hermes_provenance": provenance}})
        self.assertEqual([call[:2] for call in Handler.calls], [
            ("GET", "/memories/created-exact-id"),
            ("PATCH", "/memories/created-exact-id"),
            ("GET", "/memories/created-exact-id")])
        self.assertNotIn(literal, repr(launch.call_args_list))
        self.assertNotIn(KEY, repr(launch.call_args_list))
        self.assertEqual(set(Handler.calls[1][2]), {"metadata"})

    def test_timeout_non_json_and_size_limit_are_sanitized(self):
        for path, error in (("/timeout", "NM transport unavailable"),
                            ("/invalid", "Invalid NM JSON response"),
                            ("/large", "NM response exceeds safe size"),
                            ("/large-unsized", "NM response exceeds safe size")):
            before = len(Handler.calls)
            with self.subTest(path=path), self.assertRaises(RuntimeError) as caught:
                C.PersonalMemClient(timeout=0.05 if path == "/timeout" else 2).request_json(
                    "GET", path)
            self.assertEqual(str(caught.exception), error)
            self.assertEqual(len(Handler.calls), before + 1)
        self.assertEqual(C.PersonalMemClient(timeout=2).request_json("GET", "/exact-limit"), {})

    def test_missing_curl_is_explicit_without_other_transport(self):
        from hermes_platform import resolver
        with patch.object(resolver, "locate_command", return_value=types.SimpleNamespace(
                command=())), patch.object(C.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "Native curl executable not found"):
                C.PersonalMemClient().request_json("GET", "/memory")
            launch.assert_not_called()
        self.assertEqual(Handler.calls, [])

    def test_creation_partial_repairs_same_id_without_recreating(self):
        Handler.denied = True
        client = CLI._BoundClient()
        completed = subprocess.CompletedProcess([], 0, b'{"id":"created-exact-id"}')
        with patch.object(CLI, "_resolve_nmem", return_value="/native/nmem"), \
                patch.object(CLI.subprocess, "run", return_value=completed) as create, \
                redirect_stderr(io.StringIO()) as receipt:
            result = CLI.create_memory(client, "approved body", SOURCES)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["memory_id"], "created-exact-id")
            self.assertEqual(json.loads(receipt.getvalue())["memory_id"], "created-exact-id")
            Handler.denied = False
            repaired = CLI._finish(client, result["memory_id"], SOURCES, created=False)
            create.assert_called_once()
        self.assertEqual(repaired["status"], "complete")
        self.assertEqual(repaired["creation"], "existing_id")
        self.assertEqual([call[0] for call in Handler.calls], ["GET", "GET", "PATCH"])
        self.assertEqual(Handler.memory["metadata"]["hermes_provenance"], SOURCES)

    def test_http_success_with_ignored_metadata_stays_partial_without_retry(self):
        Handler.ignore_metadata = True
        before = copy.deepcopy(Handler.memory)
        outcome = CLI._finish(C.PersonalMemClient(), "created-exact-id", SOURCES,
                              created=False)
        self.assertEqual(outcome["status"], "partial")
        self.assertEqual(outcome["memory_id"], "created-exact-id")
        self.assertEqual(outcome["metadata"], "unconfirmed")
        self.assertEqual(Handler.memory, before)
        self.assertEqual([call[0] for call in Handler.calls], ["GET", "PATCH"])


if __name__ == "__main__":
    unittest.main()
