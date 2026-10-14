"""Host-boundary security fixtures; these do not claim to test Hermes' redactor itself."""
import copy
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_personal import FakeClient, P, S, ROOT, transcript

# The actual host egress implementation is unavailable in this isolated plugin
# suite. Supply its signature for canonical-history fixtures, then verify the
# provider hands the entire batch to that boundary, not each row independently.
_egress = types.ModuleType('agent.memory_manager')
_egress._redact_for_provider = lambda rows: copy.deepcopy(rows)
sys.modules.setdefault('agent.memory_manager', _egress)


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        FakeClient.writes, FakeClient.calls, FakeClient.fail = [], [], False
        self.client_patch = patch.object(P, 'PersonalMemClient', FakeClient)
        self.client_patch.start()
        self.provider = P.PersonalNowledgeMemProvider()
        self.provider.initialize('s1', hermes_home=self.temp.name, platform='cli', agent_context='primary')
    def tearDown(self):
        self.client_patch.stop(); self.temp.cleanup()
    def test_entire_canonical_batch_goes_through_host_egress(self):
        rows = transcript()
        rows[0]['content'] = 'BARE_TOKEN'
        rows[1]['content'] = 'api_key=BARE_TOKEN'
        original = copy.deepcopy(rows)
        calls = []
        def redact(batch):
            calls.append(copy.deepcopy(batch))
            return [{**row, 'content': row['content'].replace('BARE_TOKEN', '[redacted]')} for row in batch]
        boundary = types.ModuleType('agent.memory_manager'); boundary._redact_for_provider = redact
        with patch.dict(sys.modules, {'agent.memory_manager': boundary}), patch.object(P, 'history_rows', return_value=rows):
            self.provider._archive(S.Scope('main', 's1', 'conv_original'), transcript())
        self.assertEqual(len(calls), 1); self.assertEqual(len(calls[0]), 2)
        self.assertNotIn('BARE_TOKEN', json.dumps(FakeClient.writes))
        self.assertEqual(rows, original)
    def test_missing_host_scrubber_denies_canonical_egress(self):
        boundary = types.ModuleType('agent.memory_manager')
        with patch.dict(sys.modules, {'agent.memory_manager': boundary}), patch.object(P, 'history_rows', return_value=transcript()):
            with self.assertRaises(ImportError):
                self.provider._archive(S.Scope('main', 's1', 'conv_original'), transcript())
        self.assertEqual(FakeClient.writes, [])
    def test_legacy_numeric_config_is_accepted(self):
        Path(self.temp.name, 'nowledge-mem.json').write_text('{"timeout":"30","recall_limit":"3"}')
        self.provider.initialize('s1', hermes_home=self.temp.name, platform='cli')
        self.assertEqual(self.provider._timeout, 30)
        self.assertEqual(self.provider._recall_limit, 3)
    def test_native_entry_registers_one_provider_and_no_general_hook(self):
        spec = importlib.util.spec_from_file_location('_nm_entry_test', ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
        native = types.SimpleNamespace(register_memory_provider=Mock(), register_skill=Mock())
        module.register(native)
        native.register_memory_provider.assert_called_once()
        self.assertEqual(native.register_memory_provider.call_args.args[0].get_tool_schemas(), [])
        general = types.SimpleNamespace(register_hook=Mock())
        module.register(general); general.register_hook.assert_not_called()


if __name__ == '__main__': unittest.main()
