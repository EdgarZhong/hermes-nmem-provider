"""Completed-turn Thread continuation through real host DB and official CLI to loopback."""
from __future__ import annotations

import copy
import importlib.util
import json
import socket
import sqlite3
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('_thread_fixture', ROOT / 'personal_tests/test_r3_thread.py')
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)
P = FIXTURE.P


class ThreadHandler(FIXTURE.Handler):
    threads = {}
    serial = 0
    mode = None

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST', self.path, payload))
        identity = payload['thread_id']
        saved = self.threads.setdefault((payload.get('space_id'), identity), [])
        expected = payload.get('expected_message_count', 0)
        if len(saved) != expected:
            reply = {'success': False, 'thread_id': identity, 'error': 'checkpoint mismatch'}
        else:
            for row in payload['messages']:
                type(self).serial += 1
                saved.append({**row, 'id': f'native-message-{type(self).serial}',
                              'index': len(saved), 'order_index': len(saved)})
            reply = {'success': True, 'thread_id': identity}
        if self.mode == 'disconnect':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if self.mode == 'wrong-ack':
            reply = {'success': True, 'thread_id': 'wrong-thread'}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(reply).encode())

    def do_GET(self):
        self.calls.append(('GET', self.path, None))
        parsed = urlsplit(self.path)
        if parsed.path == '/capabilities':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
            return
        spaces = [{'id': identity, 'name': name, 'key': identity, 'aliases': aliases}
                  for identity, name, aliases in (
                      ('fixture-space', 'Fixture Space', ['Study alias']),
                      ('second-space', 'Second Space', []),
                      ('other-profile-space', 'Other Profile Space', []),
                      ('default', 'Default', []))]
        if parsed.path == '/spaces' or parsed.path.startswith('/spaces/'):
            reference = unquote(parsed.path.rsplit('/', 1)[-1])
            value = ({'enabled': True, 'spaces': spaces} if parsed.path == '/spaces'
                     else next((space for space in spaces if space['id'] == reference), {}))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())
            return
        identity = unquote(parsed.path.split('/threads/', 1)[-1])
        query = parse_qs(parsed.query)
        space = query.get('space_id', [None])[0]
        space = None if space == 'default' else space
        rows = self.threads.get((space, identity))
        if rows is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        offset, limit = int(query.get('offset', ['0'])[0]), int(query.get('limit', ['100'])[0])
        payload = {'thread': {'thread_id': identity, 'id': identity, 'space_id': space,
                             'title': 'Synthetic Thread', 'source': 'hermes'},
                   'messages': copy.deepcopy(rows[offset:offset + limit]), 'total_messages': len(rows)}
        if self.mode == 'missing-id':
            for row in payload['messages']:
                row.pop('id')
        if self.mode == 'wrong-time':
            for row in payload['messages']:
                row['timestamp'] = '2000-01-01T00:00:00Z'
        if self.mode == 'wrong-space':
            payload['thread']['space_id'] = 'another-space'
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


class ThreadForkSyncTests(unittest.TestCase):
    setUp = FIXTURE.ArchiveIntegrationTests.setUp
    provider = FIXTURE.ArchiveIntegrationTests.provider
    add_turn = FIXTURE.ArchiveIntegrationTests.add_turn
    writes = FIXTURE.ArchiveIntegrationTests.writes
    receipts = FIXTURE.ArchiveIntegrationTests.receipts
    feedback_agent = FIXTURE.ArchiveIntegrationTests.feedback_agent
    completed_feedback = FIXTURE.ArchiveIntegrationTests.completed_feedback

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), ThreadHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def run(self, result=None):
        ThreadHandler.threads, ThreadHandler.serial, ThreadHandler.mode = {}, 0, None
        return super().run(result)

    def edit(self, uid, content):
        self.db._execute_write(lambda conn: conn.execute(
            'UPDATE messages SET content=? WHERE message_uid=?', (content, uid)))

    def state(self):
        with closing(sqlite3.connect(self.home / 'nowledge-mem-personal/receipts.sqlite3')) as db:
            row = db.execute('SELECT state,pending FROM thread_sync').fetchone()
            return json.loads(row[0]), json.loads(row[1]) if row[1] else None

    def test_edit_new_thread_native_anchor_header_suffix_then_incremental(self):
        p, notices = self.provider(), []
        rows = self.add_turn() + self.add_turn(number=2, user='second question')
        agent = self.feedback_agent(p, notices=notices)
        self.completed_feedback(agent, rows)
        old_id = p._scope().thread_id
        old_rows = copy.deepcopy(ThreadHandler.threads[('fixture-space', old_id)])
        self.edit('s1-2-user', 'edited second question')
        self.completed_feedback(agent, rows)
        state, pending = self.state()
        new_id = state['thread_id']
        self.assertNotEqual(new_id, old_id)
        self.assertIsNone(pending)
        self.assertEqual(notices, [])
        payload = self.writes()[-1][2]
        header, *suffix = payload['messages']
        self.assertEqual(header['role'], 'system')
        self.assertIn(old_id, header['content'])
        self.assertIn(old_rows[1]['id'], header['content'])
        self.assertNotIn('s1-1-assistant', header['content'])
        self.assertEqual([row['content'] for row in suffix], ['edited second question', 'answer'])
        self.assertEqual(ThreadHandler.threads[('fixture-space', old_id)], old_rows)
        third = self.add_turn(number=3)
        self.assertEqual(p.sync_turn('q', 'a', messages=rows + third)['status'], 'acknowledged')
        self.assertEqual(self.writes()[-1][2]['thread_id'], new_id)
        self.assertEqual(self.writes()[-1][2]['expected_message_count'], 3)
        self.assertEqual(len(self.writes()[-1][2]['messages']), 2)

    def test_second_fork_with_anchor_in_prior_fork_or_ancestor(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        original = p._scope().thread_id
        self.edit('s1-2-user', 'branch one')
        first = p.sync_turn('q', 'a', messages=rows)['thread_id']
        third = self.add_turn(number=3)
        p.sync_turn('q', 'a', messages=rows + third)
        self.edit('s1-3-user', 'branch two')
        second = p.sync_turn('q', 'a', messages=rows + third)['thread_id']
        header = self.writes()[-1][2]['messages'][0]['content']
        self.assertIn(first, header)
        self.assertIn(ThreadHandler.threads[('fixture-space', first)][2]['id'], header)
        self.edit('s1-1-assistant', 'earlier branch')
        third_id = p.sync_turn('q', 'a', messages=rows + third)['thread_id']
        header = self.writes()[-1][2]['messages'][0]['content']
        self.assertIn(second, header)
        self.assertIn(original, header)
        self.assertIn(ThreadHandler.threads[('fixture-space', original)][0]['id'], header)
        self.assertEqual(len({original, first, second, third_id}), 4)

    def test_zero_common_prefix_rewind_waits_for_real_new_message(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        self.db.rewind_user_turn('s1', 0)
        self.assertEqual(p.sync_turn('q', 'a', messages=rows)['status'], 'reconciliation-required')
        self.assertEqual(len(self.writes()), 1)
        replacement = self.add_turn(number=2, user='replacement')
        result = p.sync_turn('q', 'a', messages=replacement)
        self.assertEqual(result['status'], 'acknowledged')
        header, *suffix = self.writes()[-1][2]['messages']
        self.assertIn('没有共同前缀', header['content'])
        self.assertNotIn('native-message-', header['content'])
        self.assertEqual([row['content'] for row in suffix], ['replacement', 'answer'])
        self.assertNotIn('暂停', str(result))

    def test_identical_body_and_time_with_replaced_local_identity_is_new_branch(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        self.db.rewind_user_turn('s1', 0)
        replacement = self.add_turn(number=2)
        for old, new in zip(rows, replacement):
            self.db._execute_write(lambda conn, old=old, new=new: conn.execute(
                'UPDATE messages SET timestamp=? WHERE message_uid=?', (old['timestamp'], new['message_uid'])))
        result = p.sync_turn('q', 'a', messages=replacement)
        self.assertTrue(result['forked'])
        self.assertIn('没有共同前缀', self.writes()[-1][2]['messages'][0]['content'])
        self.assertEqual(len(self.writes()[-1][2]['messages']), 3)

    def test_isolated_official_install_loads_sync_module_and_completed_hook(self):
        home = self.home / 'installed-profile'
        home.mkdir()
        result = FIXTURE.INSTALLER.install(home, apply=True)
        installed = Path(result['plugin_dir'])
        spec = importlib.util.spec_from_file_location('_installed_thread_fork', installed / '__init__.py',
                                                     submodule_search_locations=[str(installed)])
        module = importlib.util.module_from_spec(spec)
        FIXTURE.sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        manager = FIXTURE.MemoryManager()
        self.addCleanup(manager.shutdown_all)
        class Context:
            register_memory_provider = staticmethod(manager.add_provider)
        module.register(Context())
        manager.initialize_all('native-installed', hermes_home=str(home), platform='cli')
        manager.sync_all('question', 'answer', session_id='native-installed', messages=[
            {'role': 'user', 'content': 'installed question'}, {'role': 'assistant', 'content': 'installed answer'}])
        self.assertTrue(manager.flush_pending(timeout=5))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual([row['content'] for row in self.writes()[0][2]['messages']],
                         ['installed question', 'installed answer'])
        self.assertTrue((home / 'nowledge-mem-personal/receipts.sqlite3').exists())

    def test_cold_instance_compaction_keeps_active_fork(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        self.edit('s1-2-user', 'edited')
        branch = p.sync_turn('q', 'a', messages=rows)['thread_id']
        self.db.end_session('s1', 'compression')
        self.db.create_session('s2', 'cli', parent_session_id='s1')
        cold = self.provider(sid='s2')
        second = self.add_turn(sid='s2', number=3)
        self.assertEqual(cold.sync_turn('q', 'a', messages=second)['thread_id'], branch)
        self.assertEqual(self.writes()[-1][2]['expected_message_count'], 3)
        self.assertEqual(len(self.writes()[-1][2]['messages']), 2)

    def test_unknown_after_server_commit_readback_never_replays_or_forks_again(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        self.edit('s1-2-user', 'edited')
        before = self.receipts()
        ThreadHandler.mode = 'disconnect'
        self.assertEqual(p.sync_turn('q', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), before)
        pending_id = self.state()[1]['state']['thread_id']
        ThreadHandler.mode = None
        cold = self.provider()
        result = cold.sync_turn('q', 'a', messages=rows)
        self.assertEqual(result['thread_id'], pending_id)
        self.assertEqual(len(self.writes()), 2)
        self.assertIsNone(self.state()[1])

    def test_cold_prefetch_reports_pending_without_remote_io(self):
        p = self.provider()
        rows = self.add_turn()
        ThreadHandler.mode = 'wrong-ack'
        p.sync_turn('q', 'a', messages=rows)
        count = len(FIXTURE.Handler.calls)
        cold = self.provider()
        cold._check_cold_archive_observation(cold._scope())
        observation = cold._archive_observations[cold._observation_key(cold._scope())]
        self.assertEqual(observation['state'], 'paused')
        self.assertIn('NM Thread同步', observation['text'])
        self.assertEqual(len(FIXTURE.Handler.calls), count)

    def test_prefix_only_snapshot_does_not_create_header_without_real_suffix(self):
        p = self.provider(source='cron')
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        previous = self.receipts()
        self.assertEqual(p.sync_turn('q', 'a', messages=rows[:2])['status'], 'awaiting-branch-message')
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.receipts(), previous)

    def test_wrong_ack_and_unconfirmed_readback_keep_receipt_and_intent(self):
        p = self.provider()
        rows = self.add_turn()
        ThreadHandler.mode = 'wrong-ack'
        self.assertEqual(p.sync_turn('q', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(self.receipts(), [])
        ThreadHandler.mode = 'missing-id'
        cold = self.provider()
        self.assertEqual(cold.sync_turn('q', 'a', messages=rows)['status'], 'unacknowledged')
        self.assertEqual(len(self.writes()), 1)
        self.assertIsNotNone(self.state()[1])
        self.assertEqual(self.receipts(), [])

    def test_unknown_readback_changed_timestamp_cannot_confirm_write(self):
        p = self.provider()
        rows = self.add_turn()
        ThreadHandler.mode = 'disconnect'
        p.sync_turn('q', 'a', messages=rows)
        ThreadHandler.mode = 'wrong-time'
        result = p.sync_turn('q', 'a', messages=rows)
        self.assertEqual(result['category'], 'pending_write_unknown')
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.receipts(), [])

    def test_missing_native_anchor_never_substitutes_hash_uid_or_ordinal(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        previous = self.receipts()
        self.edit('s1-2-user', 'edited')
        ThreadHandler.mode = 'missing-id'
        result = p.sync_turn('q', 'a', messages=rows)
        self.assertEqual(result['category'], 'native_message_anchor_unconfirmed')
        self.assertIn('暂停', result['feedback'].text)
        self.assertNotIn('归档', result['feedback'].text)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.receipts(), previous)

    def test_concurrent_provider_instances_create_only_one_fork(self):
        p, q = self.provider(), self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        self.edit('s1-2-user', 'edited')
        barrier, results = threading.Barrier(2), []
        def sync(provider):
            barrier.wait()
            results.append(provider.sync_turn('q', 'a', messages=rows))
        workers = [threading.Thread(target=sync, args=(provider,)) for provider in (p, q)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(len({result['thread_id'] for result in results}), 1)
        self.assertEqual({result['status'] for result in results}, {'acknowledged', 'unchanged'})

    def test_profile_and_space_ledger_isolation(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        self.edit('s1-2-user', 'edited')
        branch = p.sync_turn('q', 'a', messages=rows)['thread_id']
        q = self.provider(space='second-space')
        result = q.sync_turn('q', 'a', messages=rows)
        self.assertEqual(result['thread_id'], q._scope().thread_id)
        self.assertNotEqual(result['thread_id'], branch)
        self.assertEqual(len(self.receipts()), 2)
        before = self.receipts()
        other_home = self.home / 'other-profile'
        other_home.mkdir()
        (other_home / 'nowledge-mem.json').write_text(json.dumps({'space': 'other-profile-space'}))
        other_db = FIXTURE.SessionDB(db_path=other_home / 'state.db')
        self.addCleanup(other_db.close)
        other_db.create_session('s1', 'cli')
        other = P.PersonalNowledgeMemProvider()
        self.addCleanup(other.shutdown)
        other.initialize('s1', hermes_home=str(other_home), platform='cli')
        own = []
        for role in ('user', 'assistant'):
            row = {'role': role, 'content': f'other profile {role}', 'message_uid': f'other-{role}'}
            other_db.append_message('s1', **row)
            own.append(row)
        self.assertEqual(other.sync_turn('q', 'a', messages=own)['status'], 'acknowledged')
        self.assertEqual(self.writes()[-1][2]['space_id'], 'other-profile-space')
        self.assertEqual([row['content'] for row in self.writes()[-1][2]['messages']],
                         ['other profile user', 'other profile assistant'])
        self.assertNotEqual(other._observation_key(other._scope()), p._observation_key(p._scope()))
        self.assertTrue((other_home / 'nowledge-mem-personal/receipts.sqlite3').exists())
        self.assertEqual(self.receipts(), before)

    def test_legacy_ack_ledger_adopted_without_clearing_or_reuploading_prefix(self):
        p = self.provider()
        rows = self.add_turn() + self.add_turn(number=2)
        p.sync_turn('q', 'a', messages=rows)
        path = self.home / 'nowledge-mem-personal/receipts.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('DROP TABLE thread_sync')
        self.edit('s1-2-user', 'edited')
        self.assertEqual(p.sync_turn('q', 'a', messages=rows)['status'], 'acknowledged')
        self.assertEqual(len(self.writes()[-1][2]['messages']), 3)
        self.assertEqual(len(self.writes()), 2)

    def test_cli_resolves_space_alias_to_id_and_still_rejects_wrong_space(self):
        p = self.provider()
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        alias = self.provider(space='Study alias')
        messages = alias._client.thread_messages(p._scope().thread_id)
        self.assertEqual([row['content'] for row in messages], ['question', 'answer'])
        reads = [call[1] for call in FIXTURE.Handler.calls if call[0] == 'GET']
        self.assertTrue(any(urlsplit(path).path == '/spaces' for path in reads))
        self.assertTrue(any(urlsplit(path).path == '/spaces/fixture-space' for path in reads))
        self.assertEqual(parse_qs(urlsplit(reads[-1]).query)['space_id'], ['fixture-space'])
        ThreadHandler.mode = 'wrong-space'
        with self.assertRaisesRegex(RuntimeError, 'Space unconfirmed'):
            alias._client.thread_messages(p._scope().thread_id)

    def test_cli_default_blank_clears_ambient_and_named_default_resolves_none(self):
        p = self.provider(source='cron', space='')
        rows = self.add_turn()
        p.sync_turn('q', 'a', messages=rows)
        with FIXTURE.patch.dict(FIXTURE.os.environ, {'NMEM_SPACE': 'foreign', 'NMEM_SPACE_ID': 'foreign'}):
            self.assertEqual(len(p._client.thread_messages(p._scope().thread_id)), 2)
        reads = [call[1] for call in FIXTURE.Handler.calls if call[0] == 'GET']
        self.assertFalse(any('/spaces/' in path for path in reads))
        self.assertNotIn('space_id', parse_qs(urlsplit(reads[-1]).query))
        named = self.provider(source='cron', space='Default')
        self.assertEqual(len(named._client.thread_messages(p._scope().thread_id)), 2)
        self.assertTrue(any(urlsplit(path).path == '/spaces/default'
                            for method, path, _ in FIXTURE.Handler.calls if method == 'GET'))

    def test_cli_pagination_total_not_page_count_and_reject_wrong_space(self):
        p = self.provider(source='cron')
        rows = [{'role': 'user', 'content': f'synthetic {index}'} for index in range(103)]
        p.sync_turn('q', 'a', messages=rows)
        messages = p._client.thread_messages(p._scope().thread_id)
        self.assertEqual(len(messages), 103)
        self.assertEqual(messages[-1]['index'], 102)
        reads = [call[1] for call in FIXTURE.Handler.calls if call[0] == 'GET' and '/threads/' in call[1]]
        self.assertEqual(len(reads), 2)
        ThreadHandler.mode = 'wrong-space'
        with self.assertRaises(RuntimeError):
            p._client.thread_messages(p._scope().thread_id)


if __name__ == '__main__':
    unittest.main()
