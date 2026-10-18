"""Cold mirror cycles use disposable real SQLite files and real process/open-file inspection."""
from contextlib import closing
import fcntl
import importlib.util
import json
import os
import shutil
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('deployment_mirror', ROOT / 'deployment/hermes-sqlite-snapshot.py')
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)


def seed(path, generation):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY, cwd TEXT);'
            'CREATE TABLE messages(message_uid TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id), content TEXT);'
            'CREATE TABLE bindings(session_id TEXT PRIMARY KEY, conversation_ref TEXT);')
        db.execute('INSERT INTO sessions VALUES(?,?)', ('pi-original-session', '/root/workspace'))
        db.execute('INSERT INTO messages VALUES(?,?,?)', ('opaque-original-message-uid', 'pi-original-session', generation))
        db.execute('INSERT INTO bindings VALUES(?,?)', ('pi-original-session', 'canonical-original-conversation-ref'))
        db.commit()


@pytest.fixture
def setup():
    temporary_root = ROOT.parent / 'temp-r3-personal'
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
        base = Path(temporary)
        cloud, mac, staging, known = (base / name for name in ('cloud', 'mac', 'staging', 'known'))
        for profile in ('Alex', 'study'):
            seed(cloud / profile / 'state.db', 'cloud-complete-original-text')
            seed(mac / profile / 'state.db', 'mac-original-pi-copy')
            for name in ('SOUL.md', 'config.yaml'):
                (mac / profile / name).write_bytes(b'local-user-static-unchanged\n')
        return_value = {'cloud': cloud, 'mac': mac, 'staging': staging, 'known': known,
                        'archive': cloud / '.snapshots/databases-current.zip'}
        yield return_value


def publish(data):
    return S.publish_cycle(data['cloud'], data['cloud'], data['staging'], data['archive'])


def receive(data):
    return S.receive_cycle(data['archive'], data['mac'], data['mac'], data['known'])


def rows(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        return {table: db.execute('SELECT * FROM ' + table).fetchall()
                for table in ('sessions', 'messages', 'bindings')}


def target_hashes(data):
    return {name: S._digest_file(data['mac'] / name) for name in S.REQUIRED_DATABASES}


def test_publish_is_local_only_bounded_and_discovers_only_known_optional_databases(setup, monkeypatch):
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError('Publisher must not depend on the Mac or any network')
    monkeypatch.setattr(socket, 'create_connection', no_network)
    first = publish(setup)
    assert first['status'] == 'published' and first['databases'] == list(S.REQUIRED_DATABASES)
    seed(setup['cloud'] / 'Alex/nowledge-mem-personal/receipts.sqlite3', 'later real receipt')
    seed(setup['cloud'] / 'study/projects.db', 'later project')
    seed(setup['cloud'] / 'study/unknown.db', 'not approved')
    for _ in range(3):
        result = publish(setup)
        assert result['status'] == 'published'
        assert set(result['databases']) == {*S.REQUIRED_DATABASES, 'Alex/nowledge-mem-personal/receipts.sqlite3', 'study/projects.db'}
    assert sorted(path.name for path in setup['archive'].parent.iterdir()) == ['databases-current.zip']
    assert sorted(path.name for path in setup['staging'].iterdir()) == ['.cycle.lock', 'status.json']
    assert receive(setup)['status'] == 'applied'
    assert rows(setup['mac'] / 'study/projects.db')['messages'][0][2] == 'later project'
    assert not (setup['mac'] / 'study/unknown.db').exists()


def test_receive_preserves_complete_identity_rows_static_files_and_initial_pi_copy(setup):
    old = target_hashes(setup)
    static = {str(path): path.read_bytes() for path in setup['mac'].glob('*/*') if path.name in ('SOUL.md', 'config.yaml')}
    # Legacy archives may contain static files; even these must never overwrite local edits.
    (setup['cloud'] / 'Alex/SOUL.md').write_bytes(b'fixture cloud static must not be applied')
    S.create_snapshot(setup['cloud'], list(S.REQUIRED_DATABASES), ['Alex/SOUL.md'],
                      setup['cloud'], setup['staging'], setup['archive'])
    assert receive(setup)['status'] == 'applied'
    for name in S.REQUIRED_DATABASES:
        actual = rows(setup['mac'] / name)
        assert actual['sessions'] == [('pi-original-session', '/root/workspace')]
        assert actual['messages'] == [('opaque-original-message-uid', 'pi-original-session', 'cloud-complete-original-text')]
        assert actual['bindings'] == [('pi-original-session', 'canonical-original-conversation-ref')]
        assert S._digest_file(setup['known'] / 'initial' / name) == old[name]
    assert {name: Path(name).read_bytes() for name in static} == static


def test_duplicate_package_skips_target_replace_and_keeps_only_two_verified_slots(setup):
    publish(setup)
    assert receive(setup)['status'] == 'applied'
    before = {name: (setup['mac'] / name).stat().st_ino for name in S.REQUIRED_DATABASES}
    assert receive(setup)['status'] == 'unchanged'
    assert {name: (setup['mac'] / name).stat().st_ino for name in S.REQUIRED_DATABASES} == before
    for number in range(3):
        with closing(sqlite3.connect(setup['cloud'] / 'Alex/state.db')) as db:
            db.execute('UPDATE messages SET content=?', (f'updated-{number}',)); db.commit()
        publish(setup)
        assert receive(setup)['status'] == 'applied'
    assert sorted(path.name for path in setup['known'].glob('*.zip')) == ['current.zip', 'previous.zip']
    assert sorted(path.name for path in setup['known'].iterdir()) == ['.cycle.lock', 'current.zip', 'initial', 'previous.zip', 'status.json']


def test_live_open_database_refuses_all_targets_then_recovers_after_process_closes(setup):
    publish(setup); before = target_hashes(setup)
    process = subprocess.Popen([sys.executable, '-c',
        'import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); d.execute("SELECT * FROM messages").fetchall(); print("ready",flush=True); sys.stdin.read(); d.close()',
        str(setup['mac'] / 'study/state.db')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'ready'
        result = receive(setup)
        assert result['status'] == 'paused' and 'open by a local process' in result['error']
        assert target_hashes(setup) == before
    finally:
        process.communicate(input='', timeout=5)
    assert receive(setup)['status'] == 'applied'


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_sidecar_refuses_entire_batch_without_deleting_sidecar_and_next_cycle_recovers(setup, suffix):
    publish(setup); before = target_hashes(setup)
    sidecar = Path(str(setup['mac'] / 'study/state.db') + suffix)
    sidecar.write_bytes(b'')
    result = receive(setup)
    assert result['status'] == 'paused' and 'sidecar' in result['error']
    assert sidecar.exists() and target_hashes(setup) == before
    sidecar.unlink()  # Fixture owner simulates the local writer's own shutdown cleanup.
    assert receive(setup)['status'] == 'applied'


def test_missing_partial_and_corrupt_transfer_keep_verified_slots_and_targets_then_recover(setup):
    assert receive(setup)['status'] == 'waiting'
    for content in ('first', 'second'):
        with closing(sqlite3.connect(setup['cloud'] / 'Alex/state.db')) as db:
            db.execute('UPDATE messages SET content=?', (content,)); db.commit()
        publish(setup); assert receive(setup)['status'] == 'applied'
    slots = {name: S._digest_file(setup['known'] / name) for name in ('current.zip', 'previous.zip')}
    before = target_hashes(setup)
    publish(setup); good = setup['archive'].read_bytes()
    corrupted = setup['cloud'] / 'corrupted.zip'
    with zipfile.ZipFile(setup['archive']) as source, zipfile.ZipFile(corrupted, 'w') as destination:
        for name in source.namelist():
            value = source.read(name)
            destination.writestr(name, value + b'bad' if name == 'files/Alex/state.db' else value)
    for bad in (good[:100], good[:len(good)//2], b'not a zip', corrupted.read_bytes()):
        setup['archive'].write_bytes(bad)
        assert receive(setup)['status'] == 'rejected'
        assert target_hashes(setup) == before
        assert {name: S._digest_file(setup['known'] / name) for name in slots} == slots
    setup['archive'].write_bytes(good)
    assert receive(setup)['status'] == 'unchanged'


def test_mid_apply_failure_records_partial_and_next_cycle_finishes_without_losing_originals(setup, monkeypatch):
    publish(setup); before = target_hashes(setup)
    original = os.replace
    def fail_study(source, destination):
        if destination == setup['mac'] / 'study/state.db':
            raise OSError('fixture destination unavailable')
        return original(source, destination)
    monkeypatch.setattr(S.os, 'replace', fail_study)
    result = receive(setup)
    assert result['status'] == 'partial' and result['applied'] == ['Alex/state.db']
    assert rows(setup['mac'] / 'Alex/state.db')['messages'][0][2] == 'cloud-complete-original-text'
    assert S._digest_file(setup['mac'] / 'study/state.db') == before['study/state.db']
    assert all(S._digest_file(setup['known'] / 'initial' / name) == before[name] for name in before)
    assert (setup['known'] / 'current.zip').exists()
    monkeypatch.setattr(S.os, 'replace', original)
    result = receive(setup)
    assert result['status'] == 'applied' and result['applied'] == ['study/state.db']


def test_cannot_prove_closed_or_destination_symlink_fails_closed(setup, monkeypatch):
    publish(setup); before = target_hashes(setup)
    monkeypatch.setattr(S.shutil, 'which', lambda name: None)
    result = receive(setup)
    assert result['status'] == 'paused' and 'lsof unavailable' in result['error']
    assert target_hashes(setup) == before
    monkeypatch.undo()
    original = setup['mac'] / 'study/state.db'
    moved = original.with_name('original-safe.db'); original.rename(moved); original.symlink_to(moved)
    assert receive(setup)['status'] == 'rejected'
    assert S._digest_file(moved) == before['study/state.db']


def test_unknown_database_cannot_enter_known_good_or_mirror_targets(setup):
    seed(setup['cloud'] / 'Alex/unapproved.db', 'unknown')
    S.create_snapshot(setup['cloud'], [*S.REQUIRED_DATABASES, 'Alex/unapproved.db'], [],
                      setup['cloud'], setup['staging'], setup['archive'])
    before = target_hashes(setup)
    assert receive(setup)['status'] == 'rejected'
    assert target_hashes(setup) == before and not (setup['known'] / 'current.zip').exists()


def test_single_receiver_lock_and_abandoned_stage_recovery_with_bounded_status(setup):
    publish(setup); known = setup['known']; known.mkdir()
    abandoned = known / '.receive-abandoned'; abandoned.mkdir(); (abandoned / 'half.zip').write_bytes(b'partial')
    with (known / '.cycle.lock').open('a+b') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert receive(setup)['status'] == 'busy'
        assert not (known / 'status.json').exists()
    assert receive(setup)['status'] == 'applied' and not abandoned.exists()
    assert json.loads((known / 'status.json').read_text(encoding='utf-8'))['status'] == 'applied'
    assert (known / 'status.json').stat().st_size < 4096


def test_cold_wal_header_without_sidecars_is_mirrored_without_creating_sidecars(setup):
    for name in S.REQUIRED_DATABASES:
        with closing(sqlite3.connect(setup['mac'] / name)) as db:
            assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        assert not Path(str(setup['mac'] / name) + '-wal').exists()
    publish(setup)
    assert receive(setup)['status'] == 'applied'
    assert not list(setup['mac'].rglob('*-wal')) and not list(setup['mac'].rglob('*-shm'))


def test_late_open_handle_before_first_replace_pauses_without_touching_targets(setup, monkeypatch):
    publish(setup); before = target_hashes(setup)
    original = S._stage_mirrors
    processes = []
    def reader_after_staging(*args):
        result = original(*args)
        process = subprocess.Popen([sys.executable, '-c',
            'import os,sys; f=os.open(sys.argv[1],os.O_RDONLY); print("ready",flush=True); sys.stdin.read(); os.close(f)',
            str(setup['mac'] / 'study/state.db')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        processes.append(process)
        assert process.stdout.readline().strip() == 'ready'
        return result
    monkeypatch.setattr(S, '_stage_mirrors', reader_after_staging)
    try:
        result = receive(setup)
        assert result['status'] == 'paused'
        assert target_hashes(setup) == before
    finally:
        for process in processes:
            process.communicate(input='', timeout=5)


def test_low_disk_space_stops_local_publisher_and_preserves_last_complete_package(setup, monkeypatch):
    publish(setup); before = setup['archive'].read_bytes()
    monkeypatch.setattr(S.shutil, 'disk_usage', lambda path: types.SimpleNamespace(free=1))
    result = publish(setup)
    assert result['status'] == 'rejected' and 'disk reserve' in result['error']
    assert setup['archive'].read_bytes() == before
    assert sorted(path.name for path in setup['staging'].iterdir()) == ['.cycle.lock', 'status.json']


def test_standalone_periodic_cli_publish_transfer_and_cold_receive_are_wired(setup):
    source = ROOT / 'deployment/hermes-sqlite-snapshot.py'
    publish_command = [sys.executable, str(source), 'publish-cycle', '--profile-root', str(setup['cloud']),
        '--sync-root', str(setup['cloud']), '--staging-root', str(setup['staging']), '--publish-file', str(setup['archive'])]
    result = subprocess.run(publish_command, check=True, capture_output=True, text=True, timeout=20)
    assert json.loads(result.stdout)['status'] == 'published'
    incoming = setup['mac'] / '.snapshots/databases-current.zip'
    incoming.parent.mkdir()
    shutil.copyfile(setup['archive'], incoming)  # Controlled completed-file transport arrival.
    command = [sys.executable, str(source), 'receive-cycle', '--archive', str(incoming),
        '--profile-root', str(setup['mac']), '--sync-root', str(setup['mac']), '--known-good-root', str(setup['known'])]
    for expected in ('applied', 'unchanged'):
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        assert json.loads(result.stdout)['status'] == expected
    assert rows(setup['mac'] / 'Alex/state.db')['messages'][0][2] == 'cloud-complete-original-text'


def test_malformed_manifest_and_cli_failure_report_rejection_without_touching_cold_databases(setup):
    publish(setup); before = target_hashes(setup)
    import hashlib
    for manifest in ([], {'schema_version': 1, 'files': {'Alex/state.db': 'invalid-row'}}):
        raw = json.dumps(manifest).encode()
        with zipfile.ZipFile(setup['archive'], 'w') as archive:
            archive.writestr('manifest.json', raw)
            archive.writestr('manifest.sha256', hashlib.sha256(raw).hexdigest())
        command = [sys.executable, str(ROOT / 'deployment/hermes-sqlite-snapshot.py'), 'receive-cycle',
            '--archive', str(setup['archive']), '--profile-root', str(setup['mac']),
            '--sync-root', str(setup['mac']), '--known-good-root', str(setup['known'])]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        assert result.returncode == 2 and json.loads(result.stdout)['status'] == 'rejected'
        assert not result.stderr and target_hashes(setup) == before
        assert not (setup['known'] / 'current.zip').exists()


def test_cycle_error_status_is_bounded_and_overwritten_instead_of_appended(setup, monkeypatch):
    def huge_failure(*args):
        raise OSError('fixture failure ' + 'x' * 10000)
    monkeypatch.setattr(S, '_receive_verified', huge_failure)
    for _ in range(3):
        result = receive(setup)
        assert result['status'] == 'rejected' and len(result['error']) <= 240
        assert (setup['known'] / 'status.json').stat().st_size < 512
    assert sorted(path.name for path in setup['known'].iterdir()) == ['.cycle.lock', 'status.json']


def test_invalid_private_roots_are_rejected_before_cleanup_or_status_writes(setup):
    protected = setup['cloud'] / 'hermes-sqlite-user-original'
    protected.mkdir(); (protected / 'original.txt').write_bytes(b'never remove user-owned directory')
    with pytest.raises(ValueError, match='outside'):
        S.publish_cycle(setup['cloud'], setup['cloud'], setup['cloud'], setup['archive'])
    assert (protected / 'original.txt').read_bytes() == b'never remove user-owned directory'
    assert not (setup['cloud'] / '.cycle.lock').exists()
    invalid_known = setup['mac'] / 'bad-known-root'
    with pytest.raises(ValueError, match='outside'):
        S.receive_cycle(setup['archive'], setup['mac'], setup['mac'], invalid_known)
    assert not invalid_known.exists()
