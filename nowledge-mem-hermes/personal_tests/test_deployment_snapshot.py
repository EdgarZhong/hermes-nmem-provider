"""Real SQLite/WAL snapshots, complete-transfer checks and offline recovery; no real Profile Home."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import zipfile

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'deployment' / 'hermes-sqlite-snapshot.py'
spec = importlib.util.spec_from_file_location('deployment_snapshot', SOURCE)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def seed(path, *, wal=False, large=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        if wal:
            db.execute('PRAGMA journal_mode=WAL')
        db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY, message_uid TEXT, payload TEXT);'
                         'CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));')
        count = 4096 if large else 3
        db.executemany('INSERT INTO parent VALUES(?,?,?)',
                       ((index, f'uid-{index}', 'x' * 1024 if large else f'body-{index}') for index in range(count)))
        db.executemany('INSERT INTO child VALUES(?,?)', ((index, index) for index in range(count)))
        db.commit()


@pytest.fixture
def layout(tmp_path):
    root, staging = tmp_path / 'sync', tmp_path / 'staging'
    seed(root / 'Alex/state.db')
    seed(root / 'study/projects.db')
    (root / 'Alex/SOUL.md').write_bytes(b'fixture-only soul\n')
    return root, staging, root / '.snapshots/databases-current.zip'


def publish(layout):
    root, staging, archive = layout
    return snapshot.create_snapshot(root, ['Alex/state.db', 'study/projects.db'], ['Alex/SOUL.md'],
                                    root, staging, archive)


def test_complete_set_hash_and_offline_restore_preserve_rows_and_exact_static(layout, tmp_path):
    root, _, archive = layout
    original = snapshot._digest_file(root / 'Alex/state.db')
    result = publish(layout)
    assert snapshot._digest_file(root / 'Alex/state.db') == original
    manifest = snapshot.verify_snapshot(archive, ['Alex/state.db', 'study/projects.db'], result['archive_sha256'])
    assert set(manifest['files']) == {'Alex/state.db', 'study/projects.db', 'Alex/SOUL.md'}
    restored = tmp_path / 'offline-recovery'
    snapshot.restore_new_root(archive, restored, ['Alex/state.db', 'study/projects.db'], result['archive_sha256'])
    assert (restored / 'Alex/SOUL.md').read_bytes() == (root / 'Alex/SOUL.md').read_bytes()
    for rel in ('Alex/state.db', 'study/projects.db'):
        with closing(sqlite3.connect(root / rel)) as a, closing(sqlite3.connect(restored / rel)) as b:
            for table in ('parent', 'child'):
                assert a.execute('SELECT * FROM ' + table).fetchall() == b.execute('SELECT * FROM ' + table).fetchall()
            assert b.execute('PRAGMA foreign_key_check').fetchall() == []
    assert not list(restored.rglob('*-wal')) and not list(restored.rglob('*-shm'))


def test_real_wal_writer_commits_between_online_backup_steps(layout, monkeypatch):
    root, staging, archive = layout
    source = root / 'Alex/wal.db'
    seed(source, wal=True, large=True)
    began, committed = threading.Event(), threading.Event()
    original_connect = sqlite3.connect
    errors = []

    def writer():
        try:
            assert began.wait(5)
            with closing(original_connect(source)) as db:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute("INSERT INTO parent VALUES(5000,'concurrent-uid','real WAL transaction')")
                db.execute('INSERT INTO child VALUES(5000,5000)')
                db.commit()
                committed.set()
        except BaseException as exc:
            errors.append(exc)
            committed.set()

    class SourceConnection:
        def __init__(self, db):
            self.db = db

        def backup(self, target, **options):
            callback = options['progress']

            def progress(status, remaining, total):
                if not began.is_set():
                    assert remaining > 0
                    began.set()
                    assert committed.wait(5)
                callback(status, remaining, total)

            self.db.backup(target, **{**options, 'progress': progress})

        def close(self):
            self.db.close()

    def connect(path, *args, **kwargs):
        db = original_connect(path, *args, **kwargs)
        return SourceConnection(db) if path == source.as_uri() + '?mode=ro' else db

    thread = threading.Thread(target=writer)
    thread.start()
    monkeypatch.setattr(snapshot.sqlite3, 'connect', connect)
    try:
        result = snapshot.create_snapshot(root, ['Alex/wal.db'], [], root, staging, archive)
    finally:
        thread.join(6)
    assert not thread.is_alive() and not errors and began.is_set() and committed.is_set()
    restored = root.parent / 'restored-wal'
    snapshot.restore_new_root(archive, restored, ['Alex/wal.db'], result['archive_sha256'])
    with closing(original_connect(restored / 'Alex/wal.db')) as db:
        assert db.execute('SELECT count(*) FROM parent').fetchone()[0] == db.execute('SELECT count(*) FROM child').fetchone()[0]
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT count(*) FROM parent WHERE id=5000').fetchone()[0] == 1


def test_manifest_only_missing_payload_and_truncated_transfer_are_rejected(layout, tmp_path):
    publish(layout)
    archive = layout[2]
    incomplete = tmp_path / 'incoming.zip'
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(incomplete, 'w') as dst:
        for name in ('manifest.json', 'manifest.sha256'):
            dst.writestr(name, src.read(name))
    with pytest.raises(ValueError, match='Missing'):
        snapshot.verify_snapshot(incomplete, ['Alex/state.db', 'study/projects.db'])
    incomplete.write_bytes(archive.read_bytes()[:len(archive.read_bytes()) // 2])
    with pytest.raises(ValueError, match='Incomplete'):
        snapshot.verify_snapshot(incomplete, ['Alex/state.db', 'study/projects.db'])
    shutil.copyfile(archive, incomplete)
    assert snapshot.verify_snapshot(incomplete, ['Alex/state.db', 'study/projects.db'])


def test_valid_sqlite_payload_with_wrong_hash_is_not_restorable(layout, tmp_path):
    result = publish(layout)
    broken = tmp_path / 'bad.zip'
    with zipfile.ZipFile(layout[2]) as src, zipfile.ZipFile(broken, 'w') as dst:
        for name in src.namelist():
            value = src.read(name)
            if name == 'files/Alex/state.db':
                changed = tmp_path / 'changed-but-valid.db'
                changed.write_bytes(value)
                with closing(sqlite3.connect(changed)) as db:
                    db.execute("UPDATE parent SET message_uid='different-valid-uid' WHERE id=1")
                    db.commit()
                value = changed.read_bytes()
            dst.writestr(name, value)
    with pytest.raises(ValueError, match='changed'):
        snapshot.verify_snapshot(broken, ['Alex/state.db', 'study/projects.db'])
    target = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError):
        snapshot.restore_new_root(broken, target, ['Alex/state.db', 'study/projects.db'], result['archive_sha256'])
    assert not target.exists()


def test_no_live_restore_and_no_profile_traversal_or_in_tree_staging(layout):
    root, _, archive = layout
    result = publish(layout)
    with pytest.raises(ValueError, match='never overwrite'):
        snapshot.restore_new_root(archive, root, ['Alex/state.db', 'study/projects.db'], result['archive_sha256'])
    for name in ('../Alex/state.db', '/Alex/state.db', 'Alex/state.db-wal'):
        with pytest.raises(ValueError):
            snapshot.create_snapshot(root, [name], [], root, root.parent / 'safe-staging', archive)
    with pytest.raises(ValueError, match='outside'):
        snapshot.create_snapshot(root, ['Alex/state.db'], [], root, root / 'bad-staging', archive)


def test_foreign_key_failure_keeps_last_completed_archive_and_no_growth(layout):
    root, staging, archive = layout
    first = publish(layout)
    second = publish(layout)
    assert first['archive'] == second['archive']
    assert len(list(archive.parent.iterdir())) == 1
    with closing(sqlite3.connect(root / 'Alex/state.db')) as db:
        db.execute('INSERT INTO child VALUES(9000,9000)')
        db.commit()
    before = archive.read_bytes()
    with pytest.raises(ValueError, match='foreign-key'):
        publish(layout)
    assert archive.read_bytes() == before and not list(staging.iterdir())


def test_manifest_path_escape_or_undeclared_extra_file_is_rejected(layout, tmp_path):
    publish(layout)
    extra = tmp_path / 'extra.zip'
    shutil.copyfile(layout[2], extra)
    with zipfile.ZipFile(extra, 'a') as dst:
        dst.writestr('../outside', b'bad')
    with pytest.raises(ValueError, match='unexpected'):
        snapshot.verify_snapshot(extra, ['Alex/state.db', 'study/projects.db'])


def test_recovery_pins_one_archive_during_atomic_transport_replacement(layout, monkeypatch):
    root, _, archive = layout
    first = publish(layout)
    old_bytes = archive.read_bytes()
    with closing(sqlite3.connect(root / 'Alex/state.db')) as db:
        db.execute("UPDATE parent SET message_uid='later-generation' WHERE id=1")
        db.commit()
    second = publish(layout)
    new_bytes = archive.read_bytes()
    archive.write_bytes(old_bytes)
    original_zip = zipfile.ZipFile
    replaced = False

    def replace_between_open_and_read(file, *args, **kwargs):
        nonlocal replaced
        if not replaced:
            replacement = archive.with_name('next.zip')
            replacement.write_bytes(new_bytes)
            os.replace(replacement, archive)
            replaced = True
        return original_zip(file, *args, **kwargs)

    monkeypatch.setattr(snapshot.zipfile, 'ZipFile', replace_between_open_and_read)
    manifest = snapshot.verify_snapshot(archive, ['Alex/state.db', 'study/projects.db'], first['archive_sha256'])
    assert manifest['files']['Alex/state.db']['sha256'] == first['files']['Alex/state.db']['sha256']
    assert snapshot._digest_file(archive) == second['archive_sha256']


def test_receiver_bad_incoming_never_replaces_two_verified_offline_slots(layout, tmp_path):
    root, _, archive = layout
    known = tmp_path / 'outside-sync-known-good'
    dbs = ['Alex/state.db', 'study/projects.db']
    first = publish(layout)
    result = snapshot.promote_known_good(archive, known, root, dbs, first['archive_sha256'])
    assert result['previous'] is None
    with closing(sqlite3.connect(root / 'Alex/state.db')) as db:
        db.execute("UPDATE parent SET message_uid='second-checkpoint' WHERE id=1")
        db.commit()
    second = publish(layout)
    snapshot.promote_known_good(archive, known, root, dbs, second['archive_sha256'])
    before = {p.name: snapshot._digest_file(p) for p in known.iterdir()}
    assert before == {'current.zip': second['archive_sha256'], 'previous.zip': first['archive_sha256']}
    archive.write_bytes(archive.read_bytes()[:100])
    with pytest.raises(ValueError):
        snapshot.promote_known_good(archive, known, root, dbs)
    assert {p.name: snapshot._digest_file(p) for p in known.iterdir()} == before
    with pytest.raises(ValueError, match='outside'):
        snapshot.promote_known_good(archive, root / 'bad-known-good', root, dbs)
