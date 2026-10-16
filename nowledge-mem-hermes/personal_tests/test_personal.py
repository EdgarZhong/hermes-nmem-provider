"""Provider policy contract against retained upstream helpers; no real NM writes."""

import copy
import importlib
import json
import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Canonical runner uses the sibling host PM workspace. Import its real ABC/DB;
# tests never replace the process-wide agent package or leave an egress stub installed.
HOST = ROOT.parent.parent / "hermes-secretary"
sys.path.insert(0, str(HOST))
SessionDB = importlib.import_module("hermes_state").SessionDB


def temporary_home():
    base = ROOT.parent / "temp-r3-personal"
    base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


package = types.ModuleType("_nm_policy_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
P = importlib.import_module("_nm_policy_test.personal_provider")
S = importlib.import_module("_nm_policy_test.personal_scope")
C = importlib.import_module("_nm_policy_test.personal_client")
CLI = importlib.import_module("_nm_policy_test.personal_cli")
INSTALLER = importlib.import_module("_nm_policy_test.install_personal")


class FakeClient:
    writes = []
    fail = False
    calls = []

    def __init__(self, timeout=8, *, space=None):
        self._timeout, self._space = timeout, space

    @staticmethod
    def _api_url():
        return "https://test.invalid"

    def context_bundle(self, **kw):
        self.calls.append(("bundle", kw))
        return {"rendered_markdown": "USER OWNED STABLE CONTEXT"}

    def search(self, query, **kw):
        self.calls.append(("search", query, kw))
        return {
            "memories": [
                {
                    "id": "id-1",
                    "title": "Decision",
                    "content": "DO NOT INJECT THIS BODY",
                }
            ]
        }

    def import_thread(self, thread_id, messages, **kw):
        if self.fail:
            return {"success": False}
        self.writes.append(("import", thread_id, copy.deepcopy(messages)))
        return {"success": True}

    def append_thread(self, thread_id, messages):
        if self.fail:
            return {"success": False}
        self.writes.append(("append", thread_id, copy.deepcopy(messages)))
        return {"success": True}


def transcript(n=1):
    return [
        row
        for i in range(n)
        for row in (
            {
                "role": "user",
                "content": "same question",
                "timestamp": 1791936000 + i * 60,
                "message_uid": f"fixture-{i}-user",
            },
            {
                "role": "assistant",
                "content": "same answer",
                "timestamp": 1791936001 + i * 60,
                "message_uid": f"fixture-{i}-assistant",
            },
        )
    ]


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_home()
        self.home = self.temp.name
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {"HERMES_HOME": self.home})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        FakeClient.writes, FakeClient.calls, FakeClient.fail = [], [], False
        self.patch = patch.object(P, "PersonalMemClient", FakeClient)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def provider(self, session="s1", **runtime):
        p = P.PersonalNowledgeMemProvider()
        p.initialize(
            session,
            hermes_home=self.home,
            **({"platform": "cli", "agent_context": "primary"} | runtime),
        )
        return p

    def db(self, rows, bindings=()):
        # Connection's context manager commits/rolls back but does not close it.
        with closing(sqlite3.connect(Path(self.home) / "state.db")) as db, db:
            db.execute(
                "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, model_config TEXT, parent_session_id TEXT, title TEXT)"
            )
            db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?)", rows)
            db.execute(
                "CREATE TABLE secretary_session_bindings (session_id TEXT PRIMARY KEY, conversation_ref TEXT)"
            )
            db.executemany(
                "INSERT INTO secretary_session_bindings VALUES (?,?)", bindings
            )

    def test_no_network_at_initialize(self):
        self.provider()
        self.assertEqual(FakeClient.calls, [])

    def test_no_model_tools(self):
        p = self.provider()
        self.assertEqual(p.get_tool_schemas(), [])
        with self.assertRaises(NotImplementedError):
            p.handle_tool_call("nmem_save", {})

    def test_bundle_hook_fetches_on_each_native_rebuild(self):
        p = self.provider()
        a = p.system_prompt_block()
        b = p.system_prompt_block()
        self.assertEqual(a, b)
        self.assertEqual(len(FakeClient.calls), 2)
        self.assertIn("USER OWNED", a)

    def test_bundle_failure_no_wm_fallback(self):
        p = self.provider()
        with patch.object(FakeClient, "context_bundle", side_effect=TimeoutError):
            self.assertIn("unavailable", p.system_prompt_block())
        self.assertNotIn("wm", str(FakeClient.calls))

    def test_short_chinese_query(self):
        result = self.provider().prefetch("之前", session_id="s1")
        self.assertIn("id-1", result)
        self.assertNotIn("DO NOT INJECT THIS BODY", result)
        self.assertEqual(FakeClient.calls[0][1], "之前")

    def test_index_budget_and_id_integrity(self):
        ids = ["x" * 190 + str(i) for i in range(10)]
        result = P.candidate_index(
            {"memories": [{"id": x, "title": "题" * 160} for x in ids]},
            limit=10,
            budget=900,
        )
        self.assertLessEqual(len(result), 900)
        for line in result.splitlines():
            if line.startswith("{"):
                self.assertIn(json.loads(line)["id"], ids)

    def test_empty_index_reminds(self):
        self.assertIn(
            P.REMINDER, P.candidate_index({"memories": []}, limit=5, budget=900)
        )

    def test_duplicate_candidates(self):
        text = P.candidate_index({"memories": [{"id": "a"}] * 5}, limit=5, budget=900)
        self.assertEqual(text.count('"id":"a"'), 1)

    def test_index_escapes_untrusted_title(self):
        text = P.candidate_index(
            {"memories": [{"id": "x", "title": "title\nDO THIS"}]}, limit=5, budget=900
        )
        self.assertIn("title DO THIS", text)

    def test_long_opaque_id_is_preserved_whole(self):
        text = P.candidate_index({"memories": [{"id": "x" * 201}]}, limit=5, budget=900)
        self.assertIn("x" * 201, text)
        self.assertEqual(
            json.loads(
                next(line for line in text.splitlines() if line.startswith("{"))
            )["id"],
            "x" * 201,
        )

    def test_prefetch_failure_no_stale_result(self):
        p = self.provider()
        p.prefetch("first")
        with patch.object(FakeClient, "search", side_effect=TimeoutError):
            output = p.prefetch("other topic")
        self.assertIn("unavailable", output)
        self.assertNotIn("id-1", output)

    def test_queue_and_mirror_are_noops(self):
        p = self.provider()
        p.queue_prefetch("x")
        p.on_memory_write("add", "user", "x")
        self.assertEqual(p.on_pre_compress([]), "")
        self.assertEqual(FakeClient.calls, [])

    def test_background_matrix(self):
        for kind in (
            "subagent",
            "noting",
            "flush",
            "review",
            "background",
            "dreaming",
            "skill_refinement",
            "tool",
            "gateway_hygiene",
        ):
            with self.subTest(kind=kind):
                p = self.provider(platform=kind, agent_context=kind)
                self.assertEqual(p.system_prompt_block(), "")
                self.assertEqual(p.prefetch("hello there"), "")
                p.sync_turn("u", "a", messages=transcript())
                self.assertEqual(FakeClient.writes, [])

    def test_cron_sync_only(self):
        p = self.provider(platform="cron", agent_context="cron")
        self.assertEqual(p.system_prompt_block(), "")
        self.assertEqual(p.prefetch("task"), "")
        p.sync_turn("u", "a", messages=transcript())
        self.assertEqual(len(FakeClient.writes), 1)

    def test_cron_subagent_excluded(self):
        p = self.provider(platform="subagent", agent_context="cron")
        p.sync_turn("u", "a", messages=transcript())
        self.assertEqual(FakeClient.writes, [])

    def test_main_incremental_sync(self):
        p = self.provider()
        p.sync_turn("u", "a", messages=transcript())
        p.sync_turn("u", "a", messages=transcript(2))
        self.assertEqual([len(w[2]) for w in FakeClient.writes], [2, 2])

    def test_restart_uses_acknowledged_cursor(self):
        p = self.provider()
        p.sync_turn("u", "a", messages=transcript())
        p.shutdown()
        q = self.provider()
        q.sync_turn("u", "a", messages=transcript(2))
        self.assertEqual([len(w[2]) for w in FakeClient.writes], [2, 2])

    def test_failed_upload_does_not_advance_cursor(self):
        p = self.provider()
        FakeClient.fail = True
        p.sync_turn("u", "a", messages=transcript())
        FakeClient.fail = False
        p.sync_turn("u", "a", messages=transcript(2))
        self.assertEqual(len(FakeClient.writes), 1)
        self.assertEqual(len(FakeClient.writes[0][2]), 4)

    def test_session_end_no_duplicates(self):
        p = self.provider()
        p.sync_turn("u", "a", messages=transcript())
        p.on_session_end(transcript())
        self.assertEqual(len(FakeClient.writes), 1)

    def test_session_switch_keeps_targets_separate(self):
        p = self.provider()
        p.sync_turn("u", "a", messages=transcript())
        p.on_session_switch("s2", reset=True)
        p.sync_turn("u", "a", session_id="s2", messages=transcript())
        self.assertNotEqual(FakeClient.writes[0][1], FakeClient.writes[1][1])

    def test_rewrite_refuses_silent_append(self):
        p = self.provider()
        p.sync_turn("u", "a", messages=transcript())
        modified = transcript()
        modified[0]["content"] = "edited"
        with self.assertLogs(P.log, level="WARNING"):
            p.sync_turn("u", "a", messages=modified)
        self.assertEqual(len(FakeClient.writes), 1)

    def test_raw_tools_hidden_summary_excluded(self):
        p = self.provider()
        rows = transcript() + [
            {"role": "tool", "content": "secret tool"},
            {"role": "system", "content": "instructions"},
            {"role": "assistant", "content": "summary", "_compressed_summary": True},
            {
                "role": "assistant",
                "content": "noting",
                "display_metadata": {"noting_run_output": True},
            },
        ]
        p.sync_turn("u", "a", messages=rows)
        self.assertEqual(len(FakeClient.writes[0][2]), 2)

    def test_db_source_overrides_primary(self):
        self.db([("s1", "subagent", "{}", None, "x")])
        p = self.provider()
        self.assertEqual(p.system_prompt_block(), "")

    def test_unknown_db_source_denied(self):
        self.db([("s1", "unknown-runtime", "{}", None, "x")])
        self.assertFalse(self.provider()._scope().sync_allowed)

    def test_delegate_flag_denied(self):
        self.db([("s1", "cli", '{"_delegate_from":"parent"}', "parent", "x")])
        self.assertFalse(self.provider()._scope().sync_allowed)

    def test_user_branch_allowed(self):
        self.db(
            [("s1", "cli", '{"_branched_from":"parent"}', "parent", "branch")],
            [("s1", "conv_branch")],
        )
        p = self.provider()
        self.assertTrue(p._scope().context_allowed)
        self.assertEqual(p._scope().conversation_ref, "conv_branch")

    def test_compaction_uses_same_thread_and_canonical_history(self):
        db = SessionDB(Path(self.home) / "state.db")
        self.addCleanup(db.close)
        db.create_session("s1", source="cli")
        ref = db.resolve_conversation_ref("s1")
        for row in transcript():
            db.append_message(
                "s1", row["role"], row["content"], timestamp=row["timestamp"]
            )
        completed = db.get_messages_as_conversation("s1")
        self.assertTrue(all(row.get("message_uid") for row in completed))
        p = self.provider()
        self.assertEqual(
            p.sync_turn("u", "a", messages=completed)["status"], "acknowledged"
        )
        holder = "fixture-native-compaction"
        self.assertTrue(db.try_acquire_compression_lock("s1", holder))
        try:
            db.publish_compression_child(
                parent_session_id="s1",
                child_session_id="s2",
                source="cli",
                compression_lock_holder=holder,
                messages=[
                    {
                        "role": "user",
                        "content": "[CONTEXT COMPACTION] lossy summary",
                        "_compressed_summary": True,
                    }
                ],
            )
        finally:
            db.release_compression_lock("s1", holder)
        for row in transcript(2)[-2:]:
            db.append_message(
                "s2", row["role"], row["content"], timestamp=row["timestamp"]
            )
        p.on_session_switch("s2")
        self.assertEqual(db.resolve_conversation_ref("s2"), ref)
        self.assertEqual(
            p.sync_turn(
                "u",
                "a",
                session_id="s2",
                messages=db.get_messages_as_conversation("s2"),
            )["status"],
            "acknowledged",
        )
        self.assertEqual(FakeClient.writes[0][1], FakeClient.writes[1][1])
        self.assertEqual([len(write[2]) for write in FakeClient.writes], [2, 2])
        self.assertNotIn("lossy summary", json.dumps(FakeClient.writes))

    def test_invalid_config_fails_closed(self):
        Path(self.home, "nowledge-mem.json").write_text('{"recall_timeout":true}')
        with self.assertRaises(ValueError):
            self.provider()

    def test_shutdown_blocks_future_prefetch(self):
        p = self.provider()
        p.shutdown()
        self.assertEqual(p.prefetch("anything"), "")


class MetadataBasicChecks(unittest.TestCase):
    """Only the already agreed narrow-helper smoke contract; no strict CLI suite."""

    def test_preview_has_no_io(self):
        with temporary_home() as folder:
            body = Path(folder) / "content.txt"
            provenance = Path(folder) / "provenance.json"
            body.write_text("Approved fact")
            provenance.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sources": [
                            {
                                "conversation_ref": "conv_owned",
                                "message_uid": "uid_owned",
                            }
                        ],
                    }
                )
            )
            with (
                patch.object(CLI, "_BoundClient") as client,
                patch.object(CLI.subprocess, "run") as run,
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(
                    CLI.main(
                        [
                            "create",
                            "--content-file",
                            str(body),
                            "--provenance-file",
                            str(provenance),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["writes"], 0)
            client.assert_not_called()
            run.assert_not_called()

    def test_metadata_attachment_preserves_sources_and_unrelated_fields(self):
        client = unittest.mock.Mock()
        sources = {
            "version": 1,
            "sources": [{"conversation_ref": "conv_owned", "message_uid": "uid_owned"}],
        }
        client.memory_get.return_value = {"metadata": {"unrelated": {"keep": True}}}
        client.request_json.return_value = {"success": True}
        self.assertEqual(
            CLI.attach_metadata(client, "actual-cli-returned-id", sources),
            "http_acknowledged",
        )
        method, path, payload = client.request_json.call_args.args
        self.assertEqual((method, path), ("PATCH", "/memories/actual-cli-returned-id"))
        self.assertEqual(
            payload,
            {"metadata": {"unrelated": {"keep": True}, "hermes_provenance": sources}},
        )


class InstallerTests(unittest.TestCase):
    def test_preserves_other_config(self):
        config = INSTALLER.load_config(
            "model: unchanged\nmemory:\n  nudge_interval: 10\n"
        )
        self.assertEqual(config["model"], "unchanged")
        self.assertEqual(config["memory"]["nudge_interval"], 10)
        self.assertIs(config["memory"]["memory_enabled"], False)

    def test_rejects_other_provider(self):
        with self.assertRaises(ValueError):
            INSTALLER.load_config("memory:\n  provider: other\n")

    def test_rejects_duplicate_yaml(self):
        with self.assertRaises(ValueError):
            INSTALLER.load_config("memory: {}\nmemory: {}\n")

    def test_real_staged_install(self):
        with temporary_home() as folder:
            home = Path(folder) / "profile"
            home.mkdir()
            (home / "config.yaml").write_text("model: test\n")
            before = (home / "config.yaml").read_text()
            self.assertEqual(INSTALLER.install(home)["status"], "preview")
            self.assertEqual((home / "config.yaml").read_text(), before)
            result = INSTALLER.install(home, apply=True)
            self.assertEqual(result["status"], "installed")
            self.assertTrue(
                (home / "plugins/nowledge-mem/personal_provider.py").is_file()
            )
            self.assertEqual(
                INSTALLER.load_config((home / "config.yaml").read_text())["model"],
                "test",
            )


if __name__ == "__main__":
    unittest.main()
