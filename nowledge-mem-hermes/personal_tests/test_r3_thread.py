"""R3 archive integration: real Hermes DB/MemoryManager, local HTTP only.

Run with the sibling Hermes PM interpreter and PYTHONPATH. Every database is
under this repository's ignored temp-r3-personal tree, never a user's profile.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent.memory_manager import MemoryManager
from hermes_state import SessionDB

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = types.ModuleType('_nm_r3_thread')
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE.__name__] = PACKAGE
P = importlib.import_module(PACKAGE.__name__ + '.personal_provider')
INSTALLER = importlib.import_module(PACKAGE.__name__ + '.install_personal')


class Handler(BaseHTTPRequestHandler):
    calls = []
    replies = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.calls.append(('GET', self.path, None))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"rendered_markdown":"Fixture stable context"}')

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST', self.path, payload))
        reply = self.replies.pop(0) if self.replies else {'success': True}
        if reply == 'disconnect':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if reply == 'timeout':
            time.sleep(0.15)
            reply = {'success': True}
        self.send_response(200)
        self.end_headers()
        try:
            self.wfile.write(json.dumps(reply).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass


class ArchiveIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        temp_root = ROOT.parent / 'temp-r3-personal'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        env = patch.dict(os.environ, {'HERMES_HOME': str(self.home),
            'NMEM_API_URL': self.url, 'NMEM_API_KEY': 'fixture-only-not-a-real-key'})
        env.start()
        self.addCleanup(env.stop)
        Handler.calls, Handler.replies = [], []
        self.db = SessionDB(db_path=self.home / 'state.db')
        self.addCleanup(self.db.close)
        self.providers = []

    def provider(self, sid='s1', source='cli', space='fixture-space'):
        if self.db.get_session(sid) is None:
            self.db.create_session(sid, source)
        (self.home / 'nowledge-mem.json').write_text(json.dumps({'space': space}))
        p = P.PersonalNowledgeMemProvider()
        p.initialize(sid, hermes_home=str(self.home), platform=source, agent_context='primary')
        self.providers.append(p)
        self.addCleanup(p.shutdown)
        return p

    def add_turn(self, sid='s1', number=1, *, user='question', answer='answer'):
        result = []
        for index, (role, content) in enumerate((('user', user), ('assistant', answer))):
            row = {'role': role, 'content': content,
                   'timestamp': 1792100000 + number * 10 + index,
                   'message_uid': f'{sid}-{number}-{role}'}
            self.db.append_message(sid, **row)
            result.append(row)
        return result

    def writes(self):
        return [call for call in Handler.calls if call[0] == 'POST']

    def receipts(self):
        path = self.home / 'nowledge-mem-personal' / 'receipts.sqlite3'
        if not path.exists():
            return []
        with closing(sqlite3.connect(path)) as db:
            return list(db.execute('SELECT scope,fingerprints FROM receipts'))

    def test_real_manager_archive_suffix_restart_and_pending_tail_boundary(self):
        p = self.provider()
        first = self.add_turn()
        # Worker must archive canonical DB content, not injected api_content or
        # a lossy live summary, and must not absorb later durable input.
        first[-1]['api_content'] = 'MODEL INJECTION'
        self.db.append_message('s1', 'user', 'UNCOMPLETED NEXT TURN', message_uid='next-user')
        manager = MemoryManager()
        manager.add_provider(p)
        self.addCleanup(manager.shutdown_all)
        manager.sync_all('question', 'answer', session_id='s1', messages=first)
        self.assertTrue(manager.flush_pending(timeout=5))
        self.assertEqual([r['content'] for r in self.writes()[0][2]['messages']], ['question', 'answer'])
        self.assertEqual(len(self.receipts()), 1)
        # A new Provider instance consumes the durable ACK cursor.
        q = self.provider()
        second = self.add_turn(number=2)
        q.sync_turn('question', 'answer', messages=first + second)
        path, payload = self.writes()[-1][1:]
        self.assertTrue(path.endswith('/append'))
        self.assertTrue(payload['deduplicate'])
        self.assertEqual(len(payload['messages']), 3)  # previous unmatched user is real History
        self.assertNotIn('api_content', payload['messages'][0])

    def test_batch_egress_sees_tool_secret_before_prose_filter(self):
        p = self.provider()
        secret = 'OpaqueFixtureValue' + 'a1B2c3D4' * 5
        self.db.append_message('s1', 'user', 'question', message_uid='u')
        self.db.append_message('s1', 'tool', f'Authorization: Bearer {secret}', message_uid='t')
        self.db.append_message('s1', 'assistant', f'The value was {secret}', message_uid='a')
        rows = [{'role': 'assistant', 'content': 'done', 'message_uid': 'a'}]
        self.assertEqual(p.sync_turn('q', 'a', messages=rows)['status'], 'acknowledged')
        output = json.dumps(self.writes()[0][2])
        self.assertNotIn(secret, output)
        self.assertIn('[redacted]', output)
        self.assertEqual([m['role'] for m in self.writes()[0][2]['messages']], ['user', 'assistant'])

    def test_noncompleted_interrupted_failed_and_unadmitted_end_make_no_writes(self):
        p = self.provider()
        rows = self.add_turn()
        p.on_session_end(rows)
        for verdict in ({'completed': False}, {'interrupted': True}, {'failed': True}):
            p.sync_turn('u', 'a', messages=rows, **verdict)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.receipts(), [])

    def test_session_end_retries_only_accepted_completed_snapshot(self):
        p = self.provider()
        rows = self.add_turn()
        Handler.replies = ['disconnect']
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), [])
        self.db.append_message('s1', 'user', 'interrupted tail', message_uid='tail')
        p.on_session_end(rows + [{'role': 'user', 'content': 'interrupted tail'}])
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(len(self.writes()[-1][2]['messages']), 2)
        self.assertEqual(len(self.receipts()), 1)

    def test_only_explicit_matching_ack_advances_receipts(self):
        p = self.provider()
        rows = self.add_turn()
        for reply in ({}, {'error': 'failed'}, {'success': False}, [], 'ok',
                      {'success': True, 'thread_id': 'another'},
                      {'success': True, 'results': [{'success': False}]}):
            Handler.replies = [reply]
            self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
            self.assertEqual(self.receipts(), [])
        Handler.replies = [{'success': True, 'thread_id': p._scope().thread_id}]
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'acknowledged')
        self.assertEqual(len(self.receipts()), 1)
        count = len(self.writes())
        p.sync_turn('u', 'a', messages=rows)
        self.assertEqual(len(self.writes()), count)

    def test_timeout_does_not_acknowledge_and_retry_remains_at_least_once(self):
        p = self.provider()
        rows = self.add_turn()
        p._client._timeout = 0.03
        Handler.replies = ['timeout']
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), [])
        p._client._timeout = 2
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'acknowledged')
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(self.writes()[0][2]['messages'], self.writes()[1][2]['messages'])

    def test_edit_rewind_or_empty_path_requires_reconciliation(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('u', 'a', messages=rows)
        before = self.receipts()
        self.db._execute_write(lambda conn: conn.execute("UPDATE messages SET content='edited' WHERE message_uid='s1-1-user'"))
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'reconciliation-required')
        self.db._execute_write(lambda conn: conn.execute('UPDATE messages SET active=0,compacted=0'))
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'reconciliation-required')
        self.assertEqual(self.receipts(), before)
        self.assertEqual(len(self.writes()), 1)

    def test_native_empty_rewind_checks_acknowledged_prefix(self):
        p = self.provider(source='cron')
        rows = self.add_turn()
        p.sync_turn('u', 'a', messages=rows)
        self.assertEqual(p.sync_turn('u', 'a', messages=[])['status'], 'reconciliation-required')
        self.assertEqual(len(self.writes()), 1)

    def test_continuation_fork_and_new_session_thread_identity(self):
        p = self.provider()
        first = self.add_turn()
        p.sync_turn('u', 'a', messages=first)
        thread = p._scope().thread_id
        self.db.end_session('s1', 'compression')
        self.db.create_session('s2', 'cli', parent_session_id='s1')
        p.on_session_switch('s2', parent_session_id='s1')
        second = self.add_turn(sid='s2', number=2)
        p.sync_turn('u', 'a', messages=second)
        self.assertEqual(p._scope().thread_id, thread)
        self.assertTrue(self.writes()[-1][1].endswith('/append'))
        self.db.create_session('fork', 'cli', parent_session_id='s2', model_config={'_branched_from': 's2'})
        p.on_session_switch('fork', parent_session_id='s2', reset=True)
        fork_turn = self.add_turn(sid='fork', number=3)
        p.sync_turn('u', 'a', messages=fork_turn)
        self.assertNotEqual(p._scope().thread_id, thread)
        p.on_session_switch('new', reset=True)
        self.db.create_session('new', 'cli')
        new_turn = self.add_turn(sid='new', number=4)
        p.sync_turn('u', 'a', messages=new_turn)
        self.assertEqual(len(self.receipts()), 3)

    def test_native_reset_has_independent_conversation_and_thread(self):
        p = self.provider()
        first = self.add_turn()
        p.sync_turn('u', 'a', messages=first)
        previous = p._scope().thread_id
        self.db.end_session('s1', 'reset')
        self.db.create_session('reset', 'cli', parent_session_id='s1', model_config={'_reset_from': 's1'})
        p.on_session_switch('reset', parent_session_id='s1', reset=True)
        rows = self.add_turn(sid='reset', number=2)
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'acknowledged')
        self.assertNotEqual(p._scope().thread_id, previous)
        self.assertEqual(len(self.receipts()), 2)
        self.assertEqual(len(self.writes()[-1][2]['messages']), 2)

    def test_endpoint_space_scopes_have_separate_ack_cursors(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('u', 'a', messages=rows)
        q = self.provider(space='other-space')
        q.sync_turn('u', 'a', messages=rows)
        # Same fixture server via another hostname, distinct endpoint scope.
        with patch.dict(os.environ, {'NMEM_API_URL': self.url.replace('127.0.0.1', 'localhost')}):
            q.sync_turn('u', 'a', messages=rows)
        self.assertEqual(len(self.receipts()), 3)
        self.assertEqual(len(self.writes()), 3)

    def test_cron_body_and_auxiliary_matrix_no_extra_network_or_distillation(self):
        cron = self.provider(source='cron')
        rows = self.add_turn()
        rows.extend([{'role': 'tool', 'content': 'TOOL PAYLOAD'},
                     {'role': 'assistant', 'content': 'HIDDEN', 'display_metadata': {'human_only': True}},
                     {'role': 'user', 'content': 'INJECTED', 'display_metadata': {'model_only': True}},
                     {'role': 'assistant', 'content': 'INTERRUPTED', 'display_metadata': {'interrupted': True}}])
        cron.sync_turn('u', 'a', messages=rows)
        self.assertEqual(self.writes()[0][2]['thread_id'], 'hermes-personal-s1')
        self.assertEqual(len(self.writes()[0][2]['messages']), 2)
        for source in ('noting', 'subagent', 'review', 'unknown'):
            p = self.provider(sid=source, source=source)
            p.sync_turn('u', 'a', messages=rows)
            p.on_session_end(rows)
            self.assertEqual(p.system_prompt_block(), '')
            self.assertEqual(p.prefetch('之前'), '')
        self.assertEqual(len(Handler.calls), 1)

    def test_missing_uid_or_retired_boundary_never_falls_back_to_live_body(self):
        p = self.provider()
        rows = self.add_turn()
        snapshot = copy.deepcopy(rows)
        snapshot[-1].pop('message_uid')
        self.assertEqual(p.sync_turn('u', 'a', messages=snapshot)['status'], 'unacknowledged')
        snapshot[-1]['message_uid'] = 'not-on-this-path'
        self.assertEqual(p.sync_turn('u', 'a', messages=snapshot)['status'], 'reconciliation-required')
        self.assertEqual(self.writes(), [])

    def test_installer_preserves_native_yaml11_booleans_and_rejects_duplicate_keys(self):
        config = INSTALLER.load_config("scheduler:\n  enabled: on\ncustom:\n  literal: 'off'\n")
        self.assertIs(config['scheduler']['enabled'], True)
        self.assertEqual(config['custom']['literal'], 'off')
        with self.assertRaises(ValueError):
            INSTALLER.load_config("memory: {}\nmemory: {}\n")
        with self.assertRaises(ValueError):
            INSTALLER.load_config("memory:\n  provider: other-provider\n")

    def test_installed_plugin_native_registration_bundle_and_completed_sync(self):
        home = self.home / 'installed-profile'
        home.mkdir()
        (home / 'MEMORY.md').write_text('original memory')
        (home / 'USER.md').write_text('original user')
        result = INSTALLER.install(home, apply=True)
        installed = Path(result['plugin_dir'])
        self.assertTrue((installed / 'personal_cli.py').is_file())
        self.assertIn('create --content-file', (installed / 'skills/nm-cli/SKILL.md').read_text())
        self.assertEqual((home / 'MEMORY.md').read_text(), 'original memory')
        spec = importlib.util.spec_from_file_location('_nm_r3_installed', installed / '__init__.py', submodule_search_locations=[str(installed)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        manager = MemoryManager()
        self.addCleanup(manager.shutdown_all)
        class Context:
            register_memory_provider = staticmethod(manager.add_provider)
            skills = []
            def register_skill(self, *args):
                self.skills.append(args)
        ctx = Context()
        module.register(ctx)
        self.assertEqual(len(manager.providers), 1)
        self.assertEqual(len(ctx.skills), 1)
        manager.initialize_all('native', hermes_home=str(home), platform='cli')
        self.assertIn('Fixture stable context', manager.build_system_prompt())
        manager.sync_all('question', 'answer', session_id='native', messages=[
            {'role': 'user', 'content': 'question'}, {'role': 'assistant', 'content': 'answer'}])
        self.assertTrue(manager.flush_pending(timeout=5))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][2]['thread_id'], 'hermes-personal-native')


if __name__ == '__main__':
    unittest.main()
