#!/usr/bin/env python3
"""Explicit SQLite snapshots for an existing file-sync channel; no daemon, Hermes imports or live restore.

A stable ZIP_STORED filename permits file-sync block reuse without a growing timestamped archive tree.
The archive contains the manifest and every declared file: arrival of an independent manifest is never
proof of completeness. Each SQLite database is consistent independently, not a cross-database transaction.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import time
import zipfile

STATIC_NAMES = frozenset({'config.yaml', 'SOUL.md', '.env', 'nowledge-mem.json', 'profile.yaml'})


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or str(path) != value:
        raise ValueError('Expected a normalized relative profile path')
    if len(path.parts) < 2 or path.parts[0].startswith('.'):
        raise ValueError('Expected an explicit profile/file path')
    return value


def _input(root: Path, value: str) -> Path:
    path = root / _relative(value)
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ValueError('Snapshot inputs must be physical files, not symlinks')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing input file or profile-root escape')
    return path


def _digest_file(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _check_db(path: Path) -> None:
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite foreign-key check failed')


def _copy_database(source: Path, target: Path, timeout: float) -> None:
    started = time.monotonic()

    def progress(_status, _remaining, _total):
        if time.monotonic() - started > timeout:
            raise TimeoutError('SQLite online backup deadline exceeded')

    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=min(timeout, 1))) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst, pages=256, progress=progress, sleep=0.01)
            dst.execute('PRAGMA journal_mode=DELETE')
    _check_db(target)


def create_snapshot(profile_root: Path, databases: list[str], static_files: list[str],
                    sync_root: Path, staging_root: Path, publish_file: Path, timeout: float = 30) -> dict:
    root, sync, staging, publish = (p.expanduser().absolute() for p in
                                    (profile_root, sync_root, staging_root, publish_file))
    names = [_relative(name) for name in databases + static_files]
    if not databases or len(names) != len(set(names)) or not 0 < timeout <= 3600:
        raise ValueError('Supply a nonempty, unique DB list and a bounded positive timeout')
    if any(Path(name).suffix not in ('.db', '.sqlite', '.sqlite3') for name in databases):
        raise ValueError('Database list must not contain WAL/SHM, directories or other runtime files')
    if any(Path(name).name not in STATIC_NAMES or len(PurePosixPath(name).parts) != 2 for name in static_files):
        raise ValueError('Only explicit profile configuration/SOUL files may accompany databases')
    if staging.resolve().is_relative_to(sync.resolve()) or sync.resolve().is_relative_to(staging.resolve()):
        raise ValueError('Staging must be outside the synchronization tree')
    if not publish.resolve().is_relative_to(sync.resolve()) or publish.name != 'databases-current.zip':
        raise ValueError('Publish databases-current.zip inside the existing synchronization tree')
    if any(staging.resolve().is_relative_to((root / name).parent.resolve()) for name in names):
        raise ValueError('Staging must not overlap an input profile')
    sources = {name: _input(root, name) for name in names}
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    publish.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if staging.stat().st_dev != publish.parent.stat().st_dev:
        raise ValueError('Staging and publish directory must share a filesystem for atomic replacement')
    with tempfile.TemporaryDirectory(prefix='hermes-sqlite-', dir=staging) as temporary:
        work = Path(temporary)
        entries = {}
        for name, source in sources.items():
            target = work / 'files' / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if name in databases:
                _copy_database(source, target, timeout)
            else:
                with source.open('rb') as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
            target.chmod(0o600)
            entries[name] = {'kind': 'sqlite' if name in databases else 'static', 'size': target.stat().st_size,
                             'sha256': _digest_file(target)}
        manifest = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'consistency': 'per-database SQLite backup; not a multi-database transaction', 'files': entries}
        raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode()
        archive = work / 'completed.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr('manifest.json', raw)
            bundle.writestr('manifest.sha256', hashlib.sha256(raw).hexdigest())
            for name in sorted(entries):
                bundle.write(work / 'files' / name, 'files/' + name)
        archive.chmod(0o600)
        verify_snapshot(archive, databases)
        with archive.open('rb') as handle:
            os.fsync(handle.fileno())
        archive_sha = _digest_file(archive)
        os.replace(archive, publish)
        directory_fd = os.open(publish.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {'archive': str(publish), 'archive_sha256': archive_sha, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                'files': entries, 'stable_name': True, 'published_atomically': True}


def _extract_verified(archive: Path, work: Path, expected_databases: list[str], expected_sha: str | None) -> dict:
    if archive.is_symlink():
        raise ValueError('Archive symlink is not a snapshot')
    try:
        with archive.open('rb') as handle, zipfile.ZipFile(handle) as bundle:
            # Pin one inode while Mutagen may atomically replace the stable path.
            handle.seek(0)
            if expected_sha and hashlib.file_digest(handle, 'sha256').hexdigest() != expected_sha:
                raise ValueError('Source archive SHA mismatch')
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate archive entries')
            raw = bundle.read('manifest.json')
            if hashlib.sha256(raw).hexdigest() != bundle.read('manifest.sha256').decode('ascii').strip():
                raise ValueError('Manifest SHA mismatch')
            manifest = json.loads(raw)
            if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), dict):
                raise ValueError('Unsupported snapshot manifest')
            entries = manifest['files']
            databases = {name for name, row in entries.items() if row.get('kind') == 'sqlite'}
            if not expected_databases or databases != {_relative(name) for name in expected_databases}:
                raise ValueError('Snapshot does not contain the exact expected database set')
            if set(names) != {'manifest.json', 'manifest.sha256'} | {'files/' + _relative(name) for name in entries}:
                raise ValueError('Missing or unexpected archive files')
            for name, row in entries.items():
                if row.get('kind') not in ('sqlite', 'static'):
                    raise ValueError('Unknown snapshot file kind')
                if row['kind'] == 'static' and (Path(name).name not in STATIC_NAMES or len(PurePosixPath(name).parts) != 2):
                    raise ValueError('Unexpected static file')
                target = work / 'files' / _relative(name)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with bundle.open('files/' + name) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                target.chmod(0o600)
                if target.stat().st_size != row['size'] or _digest_file(target) != row['sha256']:
                    raise ValueError('Incomplete or changed snapshot payload')
                if row['kind'] == 'sqlite':
                    _check_db(target)
            return manifest
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError('Incomplete or invalid snapshot archive') from exc


def verify_snapshot(archive: Path, expected_databases: list[str], expected_sha: str | None = None) -> dict:
    # Default temporary directory is local staging, never an existing Profile Home.
    with tempfile.TemporaryDirectory(prefix='verify-hermes-sqlite-') as temporary:
        return _extract_verified(archive.expanduser().absolute(), Path(temporary), expected_databases, expected_sha)


def promote_known_good(incoming: Path, known_good_root: Path, sync_root: Path,
                       expected_databases: list[str], expected_sha: str | None = None) -> dict:
    """Copy to private staging, verify the pinned copy, then rotate two fixed verified slots."""
    incoming, known, sync = (p.expanduser().absolute() for p in (incoming, known_good_root, sync_root))
    if incoming.is_symlink() or known.is_symlink() or known.resolve().is_relative_to(sync.resolve()):
        raise ValueError('Known-good slots must be physical and outside the synchronization root')
    known.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = known / '.promote-lock'
    lock.mkdir(mode=0o700)  # Exclusive; an abandoned lock needs operator inspection, never automatic takeover.
    try:
        with tempfile.TemporaryDirectory(prefix='.promote-', dir=known) as temporary:
            candidate = Path(temporary) / 'candidate.zip'
            shutil.copyfile(incoming, candidate)
            candidate.chmod(0o600)
            manifest = verify_snapshot(candidate, expected_databases, expected_sha)
            current, previous = known / 'current.zip', known / 'previous.zip'
            if current.exists() or current.is_symlink():
                verify_snapshot(current, expected_databases)
                staged_previous = Path(temporary) / 'previous.zip'
                os.link(current, staged_previous)  # Keep the old immutable inode until new-current publish succeeds.
                os.replace(staged_previous, previous)
            with candidate.open('rb') as handle:
                os.fsync(handle.fileno())
            digest = _digest_file(candidate)
            os.replace(candidate, current)
            directory_fd = os.open(known, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return {'current': str(current), 'previous': str(previous) if previous.exists() else None,
                    'archive_sha256': digest, 'manifest': manifest, 'fully_verified_before_promotion': True}
    finally:
        lock.rmdir()


def restore_new_root(archive: Path, destination: Path, expected_databases: list[str], expected_sha: str) -> dict:
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError('Restore only to a nonexistent sibling root; never overwrite any live Profile Home')
    if not expected_sha:
        raise ValueError('Recovery requires an operator-selected source archive SHA')
    with tempfile.TemporaryDirectory(prefix='.restore-hermes-sqlite-', dir=destination.parent) as temporary:
        work = Path(temporary)
        manifest = _extract_verified(archive.expanduser().absolute(), work, expected_databases, expected_sha)
        destination.mkdir(mode=0o700)  # Exclusive reservation: never replace a preexisting recovery root.
        try:
            os.rename(work / 'files', destination)
        except OSError:
            if not any(destination.iterdir()):
                destination.rmdir()
            raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('snapshot')
    for name in ('profile-root', 'sync-root', 'staging-root', 'publish-file'):
        create.add_argument('--' + name, type=Path, required=True)
    create.add_argument('--database', action='append', required=True)
    create.add_argument('--static', action='append', default=[])
    create.add_argument('--timeout', type=float, default=30)
    for name in ('verify', 'promote', 'restore-new-root'):
        command = commands.add_parser(name)
        command.add_argument('--archive', type=Path, required=True)
        command.add_argument('--database', action='append', required=True)
        command.add_argument('--archive-sha256', required=name == 'restore-new-root')
        if name == 'restore-new-root':
            command.add_argument('--destination', type=Path, required=True)
        if name == 'promote':
            command.add_argument('--known-good-root', type=Path, required=True)
            command.add_argument('--sync-root', type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == 'snapshot':
            result = create_snapshot(args.profile_root, args.database, args.static, args.sync_root,
                                     args.staging_root, args.publish_file, args.timeout)
        elif args.command == 'verify':
            result = verify_snapshot(args.archive, args.database, args.archive_sha256)
        elif args.command == 'promote':
            result = promote_known_good(args.archive, args.known_good_root, args.sync_root,
                                        args.database, args.archive_sha256)
        else:
            result = restore_new_root(args.archive, args.destination, args.database, args.archive_sha256)
    except (OSError, ValueError, sqlite3.Error, TimeoutError) as exc:
        parser.exit(2, f'snapshot rejected: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
