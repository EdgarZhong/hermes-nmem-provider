"""Host-boundary security fixtures; these do not claim to test Hermes' redactor itself."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_personal import FakeClient, P, S, ROOT, SessionDB, temporary_home


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_home()
        self.addCleanup(self.temp.cleanup)
        self.db = SessionDB(Path(self.temp.name) / "state.db")
        self.addCleanup(self.db.close)
        self.db.create_session("s1", source="cli")
        self.ref = self.db.resolve_conversation_ref("s1")
        self.db.append_message("s1", "user", "BARE_TOKEN", timestamp=1791936000)
        self.db.append_message("s1", "tool", "api_key=BARE_TOKEN", timestamp=1791936001)
        self.db.append_message("s1", "assistant", "BARE_TOKEN", timestamp=1791936002)
        self.completed = self.db.get_messages_as_conversation("s1")
        FakeClient.writes, FakeClient.calls, FakeClient.fail = [], [], False
        self.client_patch = patch.object(P, "PersonalMemClient", FakeClient)
        self.client_patch.start()
        self.provider = P.PersonalNowledgeMemProvider()
        self.provider.initialize(
            "s1", hermes_home=self.temp.name, platform="cli", agent_context="primary"
        )

    def tearDown(self):
        self.client_patch.stop()

    def test_entire_canonical_batch_goes_through_host_egress(self):
        rows = self.completed
        original = copy.deepcopy(rows)
        calls = []

        def redact(batch):
            calls.append(copy.deepcopy(batch))
            return [
                {**row, "content": row["content"].replace("BARE_TOKEN", "[redacted]")}
                for row in batch
            ]

        with patch("agent.memory_manager._redact_for_provider", side_effect=redact):
            self.provider._archive(S.Scope("main", "s1", self.ref), rows)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 3)
        self.assertEqual(calls[0][1]["role"], "tool")
        self.assertNotIn("BARE_TOKEN", json.dumps(FakeClient.writes))
        self.assertEqual(rows, original)

    def test_missing_host_scrubber_denies_canonical_egress(self):
        boundary = types.ModuleType("agent.memory_manager")
        with patch.dict(sys.modules, {"agent.memory_manager": boundary}):
            with self.assertRaises(ImportError):
                self.provider._archive(S.Scope("main", "s1", self.ref), self.completed)
        self.assertEqual(FakeClient.writes, [])

    def test_legacy_numeric_config_is_accepted(self):
        Path(self.temp.name, "nowledge-mem.json").write_text(
            '{"timeout":"30","recall_limit":"3"}'
        )
        self.provider.initialize("s1", hermes_home=self.temp.name, platform="cli")
        self.assertEqual(self.provider._timeout, 30)
        self.assertEqual(self.provider._recall_limit, 3)

    def test_native_entry_registers_one_provider_and_no_general_hook(self):
        spec = importlib.util.spec_from_file_location(
            "_nm_entry_test",
            ROOT / "__init__.py",
            submodule_search_locations=[str(ROOT)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        native = types.SimpleNamespace(
            register_memory_provider=Mock(), register_skill=Mock()
        )
        module.register(native)
        native.register_memory_provider.assert_called_once()
        self.assertEqual(
            native.register_memory_provider.call_args.args[0].get_tool_schemas(), []
        )
        general = types.SimpleNamespace(register_hook=Mock())
        module.register(general)
        general.register_hook.assert_not_called()


if __name__ == "__main__":
    unittest.main()
