"""Retain at least two verified pairs and thirty days; never touch unknown data.

The service calls this only after a new successful capture, under the same
exclusive lock. Incomplete work and legacy backups are outside this policy.
"""
import json
import os
from pathlib import Path
import re
import shutil
import time
import capture as C
import envelope as E


def inspect(path, *, owner=0, group=0):
    C.require(re.fullmatch('[0-9a-f]{32}', path.name), 'VISE_RETENTION_NAME_REFUSED')
    C.directory(path, owner, group)
    C.require({p.name for p in path.iterdir()} == {'manifest.json', 'components.tar.age', 'key.age'},
              'VISE_RETENTION_CONTENT_REFUSED')
    fd, _ = C.regular(path / 'manifest.json', owner, 16384, group)
    with os.fdopen(fd, 'rb') as source:
        value = json.load(source)
    C.require(type(value) is dict and set(value) == {
        'schema_version', 'kind', 'capture_id', 'created', 'components',
        'offline_pair', 'requires_current_erasure_journal', 'files'}, 'VISE_RETENTION_MANIFEST_REFUSED')
    C.require(type(value['schema_version']) is int and value['schema_version'] == 1
        and value['kind'] == 'vise-paired-backup' and value['capture_id'] == path.name
        and type(value['created']) is int and value['created'] > 0
        and value['components'] == list(E.FILES) and value['offline_pair'] is True
        and value['requires_current_erasure_journal'] is True
        and type(value['files']) is dict and set(value['files']) == {'components.tar.age', 'key.age'},
        'VISE_RETENTION_MANIFEST_REFUSED')
    for name, digest in value['files'].items():
        C.require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
            and C.hash_private(path / name, owner, 10 * 1024**3, group) == digest,
            'VISE_RETENTION_HASH_REFUSED')
    return value


def prune(root, latest, *, owner=0, group=0, now=None):
    root = Path(root)
    C.directory(root, owner, group)
    C.require(type(latest) is str and re.fullmatch('[0-9a-f]{32}', latest), 'VISE_RETENTION_LATEST_REFUSED')
    timestamp = int(time.time()) if now is None else now
    C.require(type(timestamp) is int and timestamp > 0, 'VISE_RETENTION_CLOCK_REFUSED')
    newest = inspect(root / latest, owner=owner, group=group)
    # Clock anomalies must not turn an old receipt into permission to prune.
    C.require(timestamp - 3600 <= newest['created'] <= timestamp, 'VISE_RETENTION_FRESH_BACKUP_REQUIRED')
    eligible = []
    for path in root.iterdir():
        if not re.fullmatch('[0-9a-f]{32}', path.name):
            continue
        try:
            value = inspect(path, owner=owner, group=group)
        except (OSError, ValueError, C.Refused):
            continue
        if value['created'] <= timestamp:
            eligible.append((value['created'], path.name))
    eligible.sort(reverse=True)
    protected = {latest} | {name for _, name in eligible[:2]}
    removed = 0
    for created, name in eligible:
        if name in protected or created >= timestamp - 30 * 86400:
            continue
        # Recheck the complete private format and ciphertext immediately before
        # deleting, even though the caller's lock excludes other writers.
        inspect(root / name, owner=owner, group=group)
        shutil.rmtree(root / name)
        C.sync(root)
        removed += 1
    return removed
