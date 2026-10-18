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
import subprocess
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
U = importlib.import_module(PACKAGE.__name__ + '.client')
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
        if callable(reply):
            reply = reply(payload)
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

    def provider(self, sid='s1', source='cli', space='fixture-space', **config):
        if self.db.get_session(sid) is None:
            self.db.create_session(sid, source)
        (self.home / 'nowledge-mem.json').write_text(json.dumps({'space': space, **config}))
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

    def test_cli_file_import_preserves_large_payload_config_and_cleans_file(self):
        p = self.provider()
        messages = [{'role': 'user', 'content': '合成资料' * 100000,
                     'timestamp': '2026-10-18T00:00:00Z'}]
        files = []
        acknowledgement = {'success': True, 'thread_id': 'fixture-thread'}

        def run(argv, *, timeout, env):
            self.assertEqual(argv[:4], ['/fixture/nmem', '--json', 'threads', 'import'])
            path = Path(argv[argv.index('--file') + 1])
            files.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), messages)
            self.assertLess(sum(map(len, argv)), 2000)
            self.assertEqual(argv[argv.index('--id') + 1], 'fixture-thread')
            self.assertEqual(argv[argv.index('--space-id') + 1], 'fixture-space')
            self.assertEqual(argv[argv.index('--expected-message-count') + 1], '7')
            self.assertEqual(argv[argv.index('--idempotency-key') + 1], 'checkpoint-key')
            self.assertEqual(env['NMEM_SPACE_ID'], 'fixture-space')
            self.assertEqual(env['NMEM_API_URL'], self.url)
            self.assertEqual(timeout, p._client._timeout)
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(acknowledgement), stderr='')

        with patch.object(U, '_resolve_nmem', return_value='/fixture/nmem'), \
             patch.object(U, '_run_nmem', side_effect=run):
            result = p._client.import_thread('fixture-thread', messages,
                expected_message_count=7, idempotency_key='checkpoint-key')
        self.assertEqual(result, acknowledgement)
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0].exists())
        self.assertEqual(Handler.calls, [])

    def test_cli_file_import_cleans_file_on_timeout(self):
        p = self.provider()
        files = []

        def fail(argv, **kwargs):
            files.append(Path(argv[argv.index('--file') + 1]))
            raise subprocess.TimeoutExpired('/fixture/nmem', kwargs['timeout'])

        with patch.object(U, '_resolve_nmem', return_value='/fixture/nmem'), \
             patch.object(U, '_run_nmem', side_effect=fail):
            with self.assertRaises(subprocess.TimeoutExpired):
                p._client.import_thread('fixture-thread', [{'role': 'user', 'content': 'fixture'}])
        self.assertFalse(files[0].exists())
        self.assertEqual(Handler.calls, [])

    def test_first_import_creates_without_checkpoint_then_uploads_suffix(self):
        p = self.provider()
        first = self.add_turn()

        def create_reply(payload):
            if 'expected_message_count' in payload or 'idempotency_key' in payload:
                return {'success': False, 'imported_count': 0, 'failed_count': 1,
                        'results': [{'success': False, 'thread_id': payload['thread_id'],
                                     'error_code': 'thread_not_found', 'error': 'Thread not found'}]}
            return {'success': True, 'imported_count': 1, 'failed_count': 0,
                    'results': [{'success': True, 'thread_id': payload['thread_id']}]}

        Handler.replies = [create_reply]
        self.assertEqual(p.sync_turn('u', 'a', messages=first)['status'], 'acknowledged')
        second = self.add_turn(number=2)
        self.assertEqual(p.sync_turn('u', 'a', messages=first + second)['status'], 'acknowledged')
        initial, suffix = [write[2] for write in self.writes()]
        self.assertNotIn('expected_message_count', initial)
        self.assertNotIn('idempotency_key', initial)
        self.assertEqual(initial['thread_id'], suffix['thread_id'])
        self.assertEqual(initial['space_id'], suffix['space_id'])
        self.assertEqual(suffix['expected_message_count'], 2)
        self.assertEqual(len(suffix['idempotency_key']), 64)
        self.assertEqual(len(suffix['messages']), 2)

    def test_batch_wrong_thread_ack_does_not_advance_receipts(self):
        p = self.provider()
        rows = self.add_turn()
        Handler.replies = [{'success': True, 'results': [
            {'success': True, 'thread_id': 'another-thread'}]}]
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), [])

    def test_checkpoint_not_found_keeps_cursor_and_logs_only_safe_category(self):
        p = self.provider()
        first = self.add_turn()
        self.assertEqual(p.sync_turn('u', 'a', messages=first)['status'], 'acknowledged')
        previous = self.receipts()
        second = self.add_turn(number=2)
        Handler.replies = [{'success': False, 'failed_count': 1, 'results': [
            {'success': False, 'thread_id': p._scope().thread_id,
             'error_code': 'thread_not_found', 'error': 'PRIVATE BODY MUST NOT BE LOGGED'}]}]
        with self.assertLogs(P.log, level='WARNING') as logs:
            self.assertEqual(p.sync_turn('u', 'a', messages=first + second)['status'], 'unacknowledged')
        self.assertIn('thread_not_found', '\n'.join(logs.output))
        self.assertNotIn('PRIVATE BODY', '\n'.join(logs.output))
        self.assertEqual(self.receipts(), previous)

    def test_archive_disabled_preserves_bundle_recall_and_skips_manager_sync(self):
        p = self.provider(space='default', archive_enabled=False)
        rows = self.add_turn()
        with patch.object(p._client, '_cli', return_value={'rendered_markdown': 'Fixture stable context'}) as bundle:
            self.assertIn('Fixture stable context', p.system_prompt_block())
            self.assertEqual(bundle.call_args.args[0], [
                'context', 'read', '--source-app', 'hermes', '--no-working-memory', '--space-id', 'default'])
        with patch.object(P.PersonalMemClient, '_cli', return_value={
                'memories': [{'id': 'read-only-pointer', 'title': 'Readable'}]}) as search:
            self.assertIn('read-only-pointer', p.prefetch('之前'))
            search.assert_called_once()
        manager = MemoryManager()
        manager.add_provider(p)
        self.addCleanup(manager.shutdown_all)
        manager.sync_all('question', 'answer', session_id='s1', messages=rows)
        self.assertTrue(manager.flush_pending(timeout=5))
        manager.on_session_end(rows)
        self.assertEqual(p.sync_turn('question', 'answer', messages=rows), {'status': 'skipped'})
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.receipts(), [])
        self.assertFalse((self.home / 'nowledge-mem-personal').exists())
        self.assertEqual(Handler.calls, [])

    def test_archive_disabled_blocks_final_write_outlet(self):
        p = self.provider(archive_enabled=False)
        rows = self.add_turn()
        self.assertEqual(p._archive_cleaned(p._scope(), rows), {'status': 'skipped'})
        self.assertEqual(self.writes(), [])
        self.assertFalse((self.home / 'nowledge-mem-personal').exists())

    def test_reinitialize_disabled_drops_previous_unacknowledged_retry(self):
        p = self.provider()
        rows = self.add_turn()
        Handler.replies = [{'success': False}]
        self.assertEqual(p.sync_turn('question', 'answer', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(len(self.writes()), 1)
        (self.home / 'nowledge-mem.json').write_text(json.dumps({'archive_enabled': False}))
        p.initialize('s1', hermes_home=str(self.home), platform='cli', agent_context='primary')
        p.on_session_end(rows)
        self.assertEqual(p.sync_turn('question', 'answer', messages=rows), {'status': 'skipped'})
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.receipts(), [])

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
        self.assertEqual(path, '/threads/import')
        self.assertEqual(payload['expected_message_count'], 2)
        self.assertEqual(len(payload['idempotency_key']), 64)
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

    def test_session_end_checks_unknown_accepted_snapshot_without_blind_replay(self):
        p = self.provider()
        rows = self.add_turn()
        Handler.replies = ['disconnect']
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), [])
        self.db.append_message('s1', 'user', 'interrupted tail', message_uid='tail')
        p.on_session_end(rows + [{'role': 'user', 'content': 'interrupted tail'}])
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.receipts(), [])

    def test_only_explicit_matching_ack_advances_receipts(self):
        replies = ({}, {'error': 'failed'}, {'success': False}, [], 'ok',
                   {'success': True, 'thread_id': 'another'},
                   {'success': True, 'results': [{'success': False}]},
                   {'success': True, 'results': []}, {'success': True, 'failed_count': 1})
        for index, reply in enumerate(replies):
            sid = f'ack-{index}'
            p = self.provider(sid=sid)
            rows = self.add_turn(sid=sid)
            Handler.replies = [reply]
            self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
            self.assertEqual(self.receipts(), [])
        p = self.provider(sid='success')
        rows = self.add_turn(sid='success')
        Handler.replies = [{'success': True, 'thread_id': p._scope().thread_id}]
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'acknowledged')
        self.assertEqual(len(self.receipts()), 1)
        count = len(self.writes())
        p.sync_turn('u', 'a', messages=rows)
        self.assertEqual(len(self.writes()), count)

    def test_timeout_does_not_acknowledge_or_blindly_retry_unknown_write(self):
        p = self.provider()
        first = self.add_turn()
        self.assertEqual(p.sync_turn('u', 'a', messages=first)['status'], 'acknowledged')
        previous = self.receipts()
        rows = first + self.add_turn(number=2)
        p._client._timeout = 0.1
        Handler.replies = ['timeout']
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), previous)
        p._client._timeout = 2
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(self.receipts(), previous)

    def test_unconfirmed_anchor_and_retired_boundary_do_not_write(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('u', 'a', messages=rows)
        before = self.receipts()
        self.db._execute_write(lambda conn: conn.execute("UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        result = p.sync_turn('u', 'a', messages=rows)
        self.assertEqual(result['status'], 'unacknowledged')
        self.assertEqual(result['category'], 'native_message_anchor_unconfirmed')
        self.db._execute_write(lambda conn: conn.execute('UPDATE messages SET active=0,compacted=0'))
        self.assertEqual(p.sync_turn('u', 'a', messages=rows)['status'], 'reconciliation-required')
        self.assertEqual(self.receipts(), before)
        self.assertEqual(len(self.writes()), 1)

    def feedback_agent(self, provider, *, sid='s1', notices=None):
        from run_agent import AIAgent
        manager = MemoryManager()
        manager.add_provider(provider)
        self.addCleanup(manager.shutdown_all)
        agent = AIAgent.__new__(AIAgent)
        agent.session_id = sid
        agent._memory_manager = manager
        agent.notice_callback = (notices if notices is not None else []).append
        agent.status_callback = None
        return agent

    def completed_feedback(self, agent, rows):
        from agent.context_compaction_request import enter_native_turn, leave_native_turn
        token, _ = enter_native_turn(agent, None, rows)
        try:
            agent._sync_external_memory_for_turn(original_user_message='current question',
                final_response='completed answer', interrupted=False, messages=rows)
            self.assertTrue(agent._memory_manager.flush_pending(timeout=5))
        finally:
            leave_native_turn(agent, token)

    def test_q03_formal_sync_edit_refusal_notice_dedup_and_current_input_fact(self):
        p = self.provider()
        rows, notices = self.add_turn(), []
        agent = self.feedback_agent(p, notices=notices)
        self.completed_feedback(agent, rows)
        before = self.receipts()
        self.assertEqual(notices, [])
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited legal question' WHERE message_uid='s1-1-assistant'"))
        for _ in range(3):
            self.completed_feedback(agent, rows)
        self.assertEqual(len(notices), 1)
        self.assertEqual((notices[0].level, notices[0].ttl_ms), ('warn', 5000))
        for fact in ('当前 Profile', '本 Conversation', '暂停', '本地合法 History 仍可用', '旧副本未被撤回'):
            self.assertIn(fact, notices[0].text)
        self.assertEqual(self.receipts(), before)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(P.history_rows(str(self.home), p._scope().conversation_ref)[1]['content'],
                         'edited legal question')
        with patch.object(p._recall_client, 'search', return_value={'memories': []}):
            facts = p.prefetch('what happened?')
        self.assertIn(notices[0].text, facts)
        for private in (str(self.home), self.url, p._scope().thread_id, p._scope().conversation_ref):
            self.assertNotIn(private, notices[0].text)
        self.assertNotIn('请', notices[0].text)
        # Reading cannot repair or clear a refused archive.
        self.assertIn('暂停', p.sync_turn('q', 'a', messages=rows)['feedback'].text)

    def test_q03_late_result_does_not_use_next_callback_and_retries_same_scope(self):
        from agent.context_compaction_request import enter_native_turn, leave_native_turn
        p = self.provider()
        rows, old, new = self.add_turn(), [], []
        agent = self.feedback_agent(p, notices=old)
        self.completed_feedback(agent, rows)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        entered, release = threading.Event(), threading.Event()

        def barrier():
            entered.set()
            self.assertTrue(release.wait(5))

        manager = agent._memory_manager
        manager._submit_background(barrier)
        self.assertTrue(entered.wait(5))
        token, _ = enter_native_turn(agent, None, rows)
        agent._sync_external_memory_for_turn(original_user_message='question', final_response='answer',
                                            interrupted=False, messages=rows)
        leave_native_turn(agent, token)
        agent.notice_callback = new.append
        next_token, _ = enter_native_turn(agent, None, rows)
        release.set()
        try:
            self.assertTrue(manager.flush_pending(timeout=5))
            self.assertEqual((old, new), ([], []))
            self.assertEqual(manager._sync_feedback_attempted, {})
            agent._sync_external_memory_for_turn(original_user_message='next question', final_response='answer',
                                                interrupted=False, messages=rows)
            self.assertEqual(len(new), 1)  # replay at this completed boundary, before another worker result
            self.assertTrue(manager.flush_pending(timeout=5))
            self.assertEqual(len(new), 1)
        finally:
            release.set()
            leave_native_turn(agent, next_token)

    def test_q03_cold_prefetch_rechecks_existing_receipt_without_remote_write(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        before = self.receipts()
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET active=0,compacted=0 WHERE message_uid='s1-1-assistant'"))
        cold = self.provider()
        self.assertEqual(cold._archive_observations, {})
        with patch.object(cold._recall_client, 'search', return_value={'memories': []}):
            text = cold.prefetch('meaningful question')
        self.assertIn('NM Thread sync observation:', text)
        self.assertIn('暂停', text)
        self.assertEqual(self.receipts(), before)
        self.assertEqual(len(self.writes()), 1)
        # Disabled profile gains no archive fact or observation, even with old receipts.
        disabled = self.provider(archive_enabled=False)
        with patch.object(disabled._recall_client, 'search', return_value={'memories': []}):
            self.assertNotIn('sync observation', disabled.prefetch('meaningful question'))
        self.assertEqual(disabled._archive_observations, {})

    def test_q03_unacknowledged_skipped_recall_cannot_clear_only_formal_compatibility_can(self):
        p = self.provider()
        rows, notices = self.add_turn(), []
        agent = self.feedback_agent(p, notices=notices)
        self.completed_feedback(agent, rows)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)
        paused = p.sync_turn('q', 'a', messages=rows)['feedback']
        with patch.object(p, '_archive', side_effect=OSError('offline')):
            self.assertEqual(p.sync_turn('q', 'a', messages=rows)['feedback'], paused)
        p._archive_enabled = False
        self.assertEqual(p.sync_turn('q', 'a', messages=rows), {'status': 'skipped'})
        p._archive_enabled = True
        with patch.object(p._recall_client, 'search', return_value={'memories': []}):
            self.assertIn('暂停', p.prefetch('meaningful input'))
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='answer' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)
        self.assertEqual(len(notices), 2)
        self.assertIn('该时点的正式检查', notices[-1].text)
        self.assertIn('不表示已重新核验', notices[-1].text)
        self.assertEqual(len(self.writes()), 1)  # unchanged verifies prefix, not a new remote ACK
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited again' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)
        self.assertEqual(len(notices), 3)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='answer' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows + self.add_turn(number=2))
        self.assertEqual(len(notices), 4)
        self.assertEqual(len(self.writes()), 2)  # affirmative ACK + committed suffix receipt

    def test_q03_official_rewind_retired_boundary_pauses_then_real_branch_recovers(self):
        p = self.provider()
        rows, notices = self.add_turn(), []
        agent = self.feedback_agent(p, notices=notices)
        self.completed_feedback(agent, rows)
        before = self.receipts()
        self.db.rewind_user_turn('s1', 0)
        self.assertEqual(P.history_rows(str(self.home), p._scope().conversation_ref), [])
        self.completed_feedback(agent, rows)
        self.assertEqual(self.receipts(), before)
        self.completed_feedback(agent, self.add_turn(number=2, user='replacement question'))
        self.assertEqual(len(notices), 2)
        self.assertEqual([notice.level for notice in notices], ['warn', 'info'])
        self.assertIn('当前分支', notices[-1].text)
        self.assertEqual(len(self.writes()), 2)
        self.assertNotEqual(self.writes()[0][2]['thread_id'], self.writes()[1][2]['thread_id'])

    def test_q03_repause_is_a_new_transition_even_when_recovery_callback_failed(self):
        p = self.provider()
        rows, notices = self.add_turn(), []
        agent = self.feedback_agent(p, notices=notices)
        self.completed_feedback(agent, rows)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)

        def unavailable(notice):
            raise RuntimeError('driver unavailable during recovery')

        agent.notice_callback = unavailable
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='answer' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)
        agent.notice_callback = notices.append
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited again' WHERE message_uid='s1-1-assistant'"))
        self.completed_feedback(agent, rows)
        self.assertEqual(len(notices), 3)
        self.assertEqual([notice.level for notice in notices], ['warn', 'info', 'warn'])
        self.assertIn('暂停', notices[-1].text)

    def test_q03_compaction_scope_keeps_pause_new_conversation_does_not_inherit(self):
        p = self.provider()
        first = self.add_turn()
        p.sync_turn('q', 'a', messages=first)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        paused = p.sync_turn('q', 'a', messages=first)['feedback']
        self.db.end_session('s1', 'compression')
        self.db.create_session('s2', 'cli', parent_session_id='s1')
        p.on_session_switch('s2', parent_session_id='s1')
        second = self.add_turn(sid='s2', number=2)
        self.assertEqual(p.sync_turn('q', 'a', messages=second)['feedback'], paused)
        self.db.create_session('fresh', 'cli')
        p.on_session_switch('fresh', reset=True)
        fresh = self.add_turn(sid='fresh')
        self.assertNotIn('feedback', p.sync_turn('q', 'a', messages=fresh))
        p.on_session_switch('s2', parent_session_id='s1')
        self.assertEqual(p.sync_turn('q', 'a', messages=second)['feedback'], paused)

    def test_q03_timeout_cannot_mark_model_fact_delivered_or_hide_next_fact(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        p.sync_turn('q', 'a', messages=rows)
        manager = MemoryManager(external_prefetch_timeout=0.05)
        manager.add_provider(p)
        self.addCleanup(manager.shutdown_all)
        entered, release = threading.Event(), threading.Event()

        def search(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return {'memories': []}

        try:
            with patch.object(p._recall_client, 'search', side_effect=search):
                self.assertEqual(manager.prefetch_all('meaningful input', session_id='s1'), '')
                self.assertTrue(entered.is_set())
                release.set()
                manager._external_prefetch_threads[p.name].join(5)
            with patch.object(p._recall_client, 'search', return_value={'memories': []}):
                self.assertIn('暂停', manager.prefetch_all('next meaningful input', session_id='s1'))
        finally:
            release.set()

    def test_q03_same_stored_id_other_profile_has_distinct_feedback_scope(self):
        p = self.provider()
        first = self.add_turn()
        p.sync_turn('q', 'a', messages=first)
        self.db._execute_write(lambda conn: conn.execute(
            "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
        paused = p.sync_turn('q', 'a', messages=first)['feedback']
        other_home = self.home / 'other-profile'
        other_home.mkdir()
        other = P.PersonalNowledgeMemProvider()
        other_db = SessionDB(db_path=other_home / 'state.db')
        self.addCleanup(other_db.close)
        self.addCleanup(other.shutdown)
        other_db.create_session('s1', 'cli')
        other.initialize('s1', hermes_home=str(other_home), platform='cli', agent_context='primary')
        self.assertNotEqual(p._observation_key(p._scope()), other._observation_key(other._scope()))
        with patch.object(other._recall_client, 'search', return_value={'memories': []}):
            self.assertNotIn('sync observation', other.prefetch('same stored ID question'))
        self.assertEqual(other._archive_observations, {})
        self.assertEqual(p.sync_turn('q', 'a', messages=first)['feedback'], paused)

    def test_q03_cold_compatible_prefix_with_unfinished_tail_does_not_claim_normal(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        self.db.append_message('s1', 'user', 'unfinished next input', message_uid='unfinished')
        cold = self.provider()
        with patch.object(cold._recall_client, 'search', return_value={'memories': []}):
            self.assertNotIn('sync observation', cold.prefetch('meaningful input'))
        self.assertEqual(cold._archive_observations, {})
        self.assertEqual(len(self.writes()), 1)

    def test_q03_actual_native_wire_contains_only_current_fact_keeps_root_history_and_archive_clean(self):
        from run_agent import AIAgent
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        notices, wire = [], []
        manager = MemoryManager()
        manager.add_provider(p)
        self.addCleanup(manager.shutdown_all)

        def response(request):
            wire.append(copy.deepcopy(request))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
                content='Fixture completed response.', tool_calls=None, reasoning_content=None, reasoning=None),
                finish_reason='stop')], model='test/model', usage=None)

        with patch('model_tools.get_tool_definitions', return_value=[]), \
             patch('model_tools.check_toolset_requirements', return_value={}), \
             patch('agent.process_bootstrap.OpenAI'), \
             patch('hermes_logging.setup_logging'), \
             patch('agent.model_metadata.fetch_model_metadata', return_value={}), \
             patch('agent.context_compressor.get_model_context_length', return_value=130000), \
             patch('agent.title_generator.maybe_auto_title'), \
             patch('run_agent._hermes_home', self.home):
            agent = AIAgent(api_key='fixture-only', base_url='https://example.invalid/v1', model='test/model',
                quiet_mode=True, skip_context_files=True, skip_memory=True, session_db=self.db, session_id='s1')
        self.addCleanup(agent.close)
        agent._memory_manager = manager
        agent._compression_feasibility_checked = True
        agent.context_compressor.threshold_tokens = 1000000
        agent.save_trajectories = False
        agent.notice_callback = notices.append
        with patch.object(p._recall_client, 'search', return_value={'memories': []}), \
             patch('agent.title_generator.maybe_auto_title'), \
             patch.object(agent, '_interruptible_api_call', side_effect=response), \
             patch.object(agent, '_interruptible_streaming_api_call', side_effect=response):
            first_result = agent.run_conversation('A meaningful first native question',
                conversation_history=self.db.get_messages_as_conversation('s1', include_row_ids=True))
            self.assertTrue(manager.flush_pending(timeout=5))
            self.assertTrue(first_result['completed'])
            original_root = wire[0]['messages'][0]['content']
            self.db._execute_write(lambda conn: conn.execute(
                "UPDATE messages SET content='edited' WHERE message_uid='s1-1-assistant'"))
            p.sync_turn('q', 'a', messages=rows)
            result = agent.run_conversation('What is the current sync observation?',
                conversation_history=self.db.get_messages_as_conversation('s1', include_row_ids=True))
        self.assertTrue(manager.flush_pending(timeout=5))
        self.assertTrue(result['completed'])
        messages = wire[-1]['messages']
        self.assertEqual(messages[0]['content'], original_root)
        current_input = messages[-1]['content']
        fact = current_input.split('NM Thread sync observation:\n', 1)[1].split('</memory-context>', 1)[0]
        self.assertIn('暂停', fact)
        self.assertIn('截至 ', fact)
        for instruction in ('must ', 'should ', 'please ', '请', '修复', self.url, str(self.home), p._scope().thread_id):
            self.assertNotIn(instruction, fact)
        self.assertEqual(agent._cached_system_prompt, original_root)
        self.assertNotIn('sync observation', json.dumps(messages[1:-1]))
        for row in self.db.get_messages('s1'):
            self.assertNotIn('NM Thread sync observation:', str(row.get('content')))
        self.assertEqual(len(self.writes()), 2)

    def test_native_empty_rewind_checks_acknowledged_prefix(self):
        p = self.provider(source='cron')
        rows = self.add_turn()
        p.sync_turn('u', 'a', messages=rows)
        self.assertEqual(p.sync_turn('u', 'a', messages=[])['status'], 'awaiting-branch-message')
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
        self.assertEqual(self.writes()[-1][1], '/threads/import')
        self.assertEqual(self.writes()[-1][2]['expected_message_count'], 2)
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
        installed_skill = (installed / 'skills/nm-cli/SKILL.md').read_text()
        self.assertIn('python3 personal_cli.py create ', installed_skill)
        create_example = installed_skill.split('python3 personal_cli.py create ', 1)[1].split('```', 1)[0]
        self.assertIn('--content-file', create_example)
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
        with patch.object(manager.providers[0]._client, '_cli', return_value={
                'rendered_markdown': 'Fixture stable context'}):
            self.assertIn('Fixture stable context', manager.build_system_prompt())
        manager.sync_all('question', 'answer', session_id='native', messages=[
            {'role': 'user', 'content': 'question'}, {'role': 'assistant', 'content': 'answer'}])
        self.assertTrue(manager.flush_pending(timeout=5))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][2]['thread_id'], 'hermes-personal-native')


if __name__ == '__main__':
    unittest.main()
