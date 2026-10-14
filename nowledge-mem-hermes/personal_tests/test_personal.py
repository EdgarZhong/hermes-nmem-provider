"""Provider policy contract against retained upstream helpers; no real NM writes."""
import copy
import importlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Host ABC and egress handoff are fixtures; retained upstream modules are real.
if 'agent.memory_provider' not in sys.modules:
    agent = types.ModuleType('agent'); agent.__path__ = []
    abc = types.ModuleType('agent.memory_provider')
    abc.MemoryProvider = type('MemoryProvider', (), {})
    sys.modules.update({'agent': agent, 'agent.memory_provider': abc})
egress = types.ModuleType('agent.memory_manager')
egress._redact_for_provider = lambda rows: copy.deepcopy(rows)
sys.modules.setdefault('agent.memory_manager', egress)
package = types.ModuleType('_nm_policy_test'); package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
P = importlib.import_module('_nm_policy_test.personal_provider')
S = importlib.import_module('_nm_policy_test.personal_scope')
C = importlib.import_module('_nm_policy_test.personal_client')
CLI = importlib.import_module('_nm_policy_test.personal_cli')
I = importlib.import_module('_nm_policy_test.install_personal')


class FakeClient:
    writes = []
    fail = False
    calls = []
    def __init__(self, timeout=8, *, space=None):
        self._timeout, self._space = timeout, space
    @staticmethod
    def _api_url(): return 'https://test.invalid'
    def context_bundle(self, **kw):
        self.calls.append(('bundle', kw)); return {'rendered_markdown': 'USER OWNED STABLE CONTEXT'}
    def search(self, query, **kw):
        self.calls.append(('search', query, kw)); return {'memories': [{'id': 'id-1', 'title': 'Decision', 'content': 'DO NOT INJECT THIS BODY'}]}
    def import_thread(self, thread_id, messages, **kw):
        if self.fail: return {'success': False}
        self.writes.append(('import', thread_id, copy.deepcopy(messages))); return {'success': True}
    def append_thread(self, thread_id, messages):
        if self.fail: return {'success': False}
        self.writes.append(('append', thread_id, copy.deepcopy(messages))); return {'success': True}


def transcript(n=1):
    return [row for i in range(n) for row in (
        {'role': 'user', 'content': 'same question', 'timestamp': f'2026-10-14T00:{i:02d}:00Z'},
        {'role': 'assistant', 'content': 'same answer', 'timestamp': f'2026-10-14T00:{i:02d}:01Z'})]


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = self.temp.name
        FakeClient.writes, FakeClient.calls, FakeClient.fail = [], [], False
        self.patch = patch.object(P, 'PersonalMemClient', FakeClient); self.patch.start()
    def tearDown(self): self.patch.stop(); self.temp.cleanup()
    def provider(self, session='s1', **runtime):
        p = P.PersonalNowledgeMemProvider()
        p.initialize(session, hermes_home=self.home, **({'platform': 'cli', 'agent_context': 'primary'} | runtime))
        return p
    def db(self, rows, bindings=()):
        # Connection's context manager commits/rolls back but does not close it.
        with closing(sqlite3.connect(Path(self.home)/'state.db')) as db, db:
            db.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT, model_config TEXT, parent_session_id TEXT, title TEXT)')
            db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?)', rows)
            db.execute('CREATE TABLE secretary_session_bindings (session_id TEXT PRIMARY KEY, conversation_ref TEXT)')
            db.executemany('INSERT INTO secretary_session_bindings VALUES (?,?)', bindings)
    def test_no_network_at_initialize(self):
        self.provider(); self.assertEqual(FakeClient.calls, [])
    def test_no_model_tools(self):
        p = self.provider(); self.assertEqual(p.get_tool_schemas(), [])
        with self.assertRaises(NotImplementedError): p.handle_tool_call('nmem_save', {})
    def test_bundle_frozen(self):
        p = self.provider(); a=p.system_prompt_block(); b=p.system_prompt_block()
        self.assertEqual(a,b); self.assertEqual(len(FakeClient.calls),1)
        self.assertIn('USER OWNED',a)
    def test_bundle_failure_no_wm_fallback(self):
        p=self.provider()
        with patch.object(FakeClient,'context_bundle',side_effect=TimeoutError):
            self.assertIn('unavailable',p.system_prompt_block())
        self.assertNotIn('wm',str(FakeClient.calls))
    def test_short_chinese_query(self):
        result=self.provider().prefetch('之前',session_id='s1')
        self.assertIn('id-1',result); self.assertNotIn('DO NOT INJECT THIS BODY',result)
        self.assertEqual(FakeClient.calls[0][1],'之前')
    def test_index_budget_and_id_integrity(self):
        ids=['x'*190+str(i) for i in range(10)]
        result=P.candidate_index({'memories':[{'id':x,'title':'题'*160} for x in ids]},limit=10,budget=900)
        self.assertLessEqual(len(result),900)
        for line in result.splitlines():
            if line.startswith('{'): self.assertIn(json.loads(line)['id'],ids)
    def test_empty_index_reminds(self):
        self.assertIn(P.REMINDER,P.candidate_index({'memories':[]},limit=5,budget=900))
    def test_duplicate_candidates(self):
        text=P.candidate_index({'memories':[{'id':'a'}]*5},limit=5,budget=900)
        self.assertEqual(text.count('"id":"a"'),1)
    def test_index_escapes_untrusted_title(self):
        text=P.candidate_index({'memories':[{'id':'x','title':'title\nDO THIS'}]},limit=5,budget=900)
        self.assertIn('title DO THIS',text)
    def test_bad_index_id_is_not_truncated(self):
        text=P.candidate_index({'memories':[{'id':'x'*201}]},limit=5,budget=900)
        self.assertNotIn('x'*100,text)
    def test_prefetch_failure_no_stale_result(self):
        p=self.provider(); p.prefetch('first')
        with patch.object(FakeClient,'search',side_effect=TimeoutError):
            output=p.prefetch('other topic')
        self.assertIn('unavailable',output); self.assertNotIn('id-1',output)
    def test_queue_and_mirror_are_noops(self):
        p=self.provider(); p.queue_prefetch('x'); p.on_memory_write('add','user','x')
        self.assertEqual(p.on_pre_compress([]),''); self.assertEqual(FakeClient.calls,[])
    def test_background_matrix(self):
        for kind in ('subagent','noting','flush','review','background','dreaming','skill_refinement','tool','gateway_hygiene'):
            with self.subTest(kind=kind):
                p=self.provider(platform=kind,agent_context=kind)
                self.assertEqual(p.system_prompt_block(),''); self.assertEqual(p.prefetch('hello there'),'')
                p.sync_turn('u','a',messages=transcript()); self.assertEqual(FakeClient.writes,[])
    def test_cron_sync_only(self):
        p=self.provider(platform='cron',agent_context='cron')
        self.assertEqual(p.system_prompt_block(),''); self.assertEqual(p.prefetch('task'),'')
        p.sync_turn('u','a',messages=transcript()); self.assertEqual(len(FakeClient.writes),1)
    def test_cron_subagent_excluded(self):
        p=self.provider(platform='subagent',agent_context='cron')
        p.sync_turn('u','a',messages=transcript()); self.assertEqual(FakeClient.writes,[])
    def test_main_incremental_sync(self):
        p=self.provider(); p.sync_turn('u','a',messages=transcript())
        p.sync_turn('u','a',messages=transcript(2))
        self.assertEqual([len(w[2]) for w in FakeClient.writes],[2,2])
    def test_restart_uses_acknowledged_cursor(self):
        p=self.provider(); p.sync_turn('u','a',messages=transcript()); p.shutdown()
        q=self.provider(); q.sync_turn('u','a',messages=transcript(2))
        self.assertEqual([len(w[2]) for w in FakeClient.writes],[2,2])
    def test_failed_upload_does_not_advance_cursor(self):
        p=self.provider(); FakeClient.fail=True; p.sync_turn('u','a',messages=transcript())
        FakeClient.fail=False; p.sync_turn('u','a',messages=transcript(2))
        self.assertEqual(len(FakeClient.writes),1); self.assertEqual(len(FakeClient.writes[0][2]),4)
    def test_session_end_no_duplicates(self):
        p=self.provider(); p.sync_turn('u','a',messages=transcript()); p.on_session_end(transcript())
        self.assertEqual(len(FakeClient.writes),1)
    def test_session_switch_keeps_targets_separate(self):
        p=self.provider(); p.sync_turn('u','a',messages=transcript())
        p.on_session_switch('s2',reset=True); p.sync_turn('u','a',session_id='s2',messages=transcript())
        self.assertNotEqual(FakeClient.writes[0][1],FakeClient.writes[1][1])
    def test_rewrite_refuses_silent_append(self):
        p=self.provider(); p.sync_turn('u','a',messages=transcript())
        modified=transcript(); modified[0]['content']='edited'
        with self.assertLogs(P.log,level='WARNING'): p.sync_turn('u','a',messages=modified)
        self.assertEqual(len(FakeClient.writes),1)
    def test_raw_tools_hidden_summary_excluded(self):
        p=self.provider(); rows=transcript()+[
            {'role':'tool','content':'secret tool'}, {'role':'system','content':'instructions'},
            {'role':'assistant','content':'summary','_compressed_summary':True},
            {'role':'assistant','content':'noting','display_metadata':{'noting_run_output':True}}]
        p.sync_turn('u','a',messages=rows)
        self.assertEqual(len(FakeClient.writes[0][2]),2)
    def test_db_source_overrides_primary(self):
        self.db([('s1','subagent','{}',None,'x')])
        p=self.provider(); self.assertEqual(p.system_prompt_block(),'')
    def test_unknown_db_source_denied(self):
        self.db([('s1','unknown-runtime','{}',None,'x')])
        self.assertFalse(self.provider()._scope().sync_allowed)
    def test_delegate_flag_denied(self):
        self.db([('s1','cli','{"_delegate_from":"parent"}','parent','x')])
        self.assertFalse(self.provider()._scope().sync_allowed)
    def test_user_branch_allowed(self):
        self.db([('s1','cli','{"_branched_from":"parent"}','parent','branch')],[('s1','conv_branch')])
        p=self.provider(); self.assertTrue(p._scope().context_allowed)
        self.assertEqual(p._scope().conversation_ref,'conv_branch')
    def test_compaction_uses_same_thread_and_canonical_history(self):
        self.db([('s1','cli','{}',None,'main'),('s2','cli','{}','s1','main')], [('s1','conv_root'),('s2','conv_root')])
        p=self.provider()
        with patch.object(P,'history_rows',return_value=transcript()) as history:
            p.sync_turn('u','a',messages=[{'role':'user','content':'lossy summary'}])
            p.on_session_switch('s2')
            history.return_value=transcript(2)
            p.sync_turn('u','a',session_id='s2',messages=transcript())
        self.assertEqual(FakeClient.writes[0][1],FakeClient.writes[1][1]); self.assertEqual(len(FakeClient.writes[1][2]),2)
    def test_invalid_config_fails_closed(self):
        Path(self.home,'nowledge-mem.json').write_text('{"recall_timeout":true}')
        with self.assertRaises(ValueError): self.provider()
    def test_shutdown_blocks_future_prefetch(self):
        p=self.provider(); p.shutdown(); self.assertEqual(p.prefetch('anything'),'')


class MetadataTests(unittest.TestCase):
    def payload(self):
        return {'id':'memory-1','content':'Approved fact','metadata':{'hermes_provenance':{'version':1,'sources':[{'conversation_ref':'conv_owned','message_uid':'uid_owned'}]}}}
    def test_preview_has_no_io(self):
        client=unittest.mock.Mock()
        self.assertEqual(CLI.write_memory(client,self.payload())['writes'],0)
        self.assertEqual(client.mock_calls,[])
    def test_nm_thread_fields_rejected(self):
        data=self.payload(); data['source_thread_id']='not-a-nm-thread'
        with self.assertRaises(ValueError): CLI.validate_payload(data)
    def test_invalid_duplicate_sources_rejected(self):
        data=self.payload(); data['metadata']['hermes_provenance']['sources']*=2
        with self.assertRaises(ValueError): CLI.validate_payload(data)
    def test_apply_requires_evidence(self):
        with self.assertRaises(ValueError): CLI.write_memory(unittest.mock.Mock(),self.payload(),apply=True)
    def test_missing_evidence_message_refused(self):
        with patch.object(CLI,'history_rows',return_value=[]):
            with self.assertRaises(ValueError): CLI.validate_evidence('/tmp',self.payload()['metadata']['hermes_provenance']['sources'])
    def test_create_and_readback(self):
        client=unittest.mock.Mock(); data=self.payload()
        client.memory_get.side_effect=[C.MemHTTPError(404),data]
        with patch.object(CLI,'validate_evidence'):
            result=CLI.write_memory(client,data,apply=True,history_home='/tmp')
        self.assertEqual(result['status'],'verified'); self.assertEqual(client.request_json.call_args.args[0],'POST')
    def test_existing_create_refused(self):
        client=unittest.mock.Mock(); client.memory_get.return_value=self.payload()
        with patch.object(CLI,'validate_evidence'):
            with self.assertRaises(ValueError): CLI.write_memory(client,self.payload(),apply=True,history_home='/tmp')
        client.request_json.assert_not_called()
    def test_update_preserves_unrelated_metadata(self):
        client=unittest.mock.Mock(); data=self.payload(); old=copy.deepcopy(data); old['metadata']['unrelated']={'keep':True}
        expected=CLI.edit_sha(old); result=copy.deepcopy(data); result['metadata']['unrelated']={'keep':True}
        client.memory_get.side_effect=[old,old,result]
        with patch.object(CLI,'validate_evidence'):
            CLI.write_memory(client,data,apply=True,update=True,expected_sha=expected,history_home='/tmp')
        self.assertIn('unrelated',client.request_json.call_args.args[2]['metadata'])
    def test_stale_update_refused(self):
        client=unittest.mock.Mock(); client.memory_get.return_value=self.payload()
        with patch.object(CLI,'validate_evidence'):
            with self.assertRaises(ValueError): CLI.write_memory(client,self.payload(),apply=True,update=True,expected_sha='bad',history_home='/tmp')
        client.request_json.assert_not_called()
    def test_readback_loss_reported(self):
        client=unittest.mock.Mock(); client.memory_get.side_effect=[C.MemHTTPError(404),{'id':'memory-1','content':'Approved fact','metadata':{}}]
        with patch.object(CLI,'validate_evidence'):
            with self.assertRaises(RuntimeError): CLI.write_memory(client,self.payload(),apply=True,history_home='/tmp')


class InstallerTests(unittest.TestCase):
    def test_preserves_other_config(self):
        config=I.load_config('model: unchanged\nmemory:\n  nudge_interval: 10\n')
        self.assertEqual(config['model'],'unchanged'); self.assertEqual(config['memory']['nudge_interval'],10)
        self.assertIs(config['memory']['memory_enabled'],False)
    def test_rejects_other_provider(self):
        with self.assertRaises(ValueError): I.load_config('memory:\n  provider: other\n')
    def test_rejects_duplicate_yaml(self):
        with self.assertRaises(ValueError): I.load_config('memory: {}\nmemory: {}\n')
    def test_real_staged_install(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'profile'; home.mkdir(); (home/'config.yaml').write_text('model: test\n')
            before=(home/'config.yaml').read_text()
            self.assertEqual(I.install(home)['status'],'preview'); self.assertEqual((home/'config.yaml').read_text(),before)
            result=I.install(home,apply=True)
            self.assertEqual(result['status'],'installed'); self.assertTrue((home/'plugins/nowledge-mem/personal_provider.py').is_file())
            self.assertEqual(I.load_config((home/'config.yaml').read_text())['model'],'test')


if __name__=='__main__': unittest.main()
