"""Read exact candidate Git objects without checkout, hooks or network.

Repository paths, selectors and executable belong to the installed intake
service. Only exact commit IDs come from an observed proposal. This module
establishes source content, not review, policy adoption or deployment authority.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import time

OID = re.compile(r'[0-9a-f]{40}\Z')
COMPONENT = re.compile(rb'[A-Za-z0-9._+~-]{1,255}\Z')
MAX_TREE_BYTES = 4 * 1024 * 1024
MAX_BLOB_BYTES = 32 * 1024 * 1024
MAX_SELECTED_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 16384
MAX_DEPTH = 64
MAX_COMMITS = 4096
MODES = {b'40000': ('040000', 'tree'), b'100644': ('100644', 'blob'),
         b'100755': ('100755', 'blob'), b'120000': ('120000', 'blob'),
         b'160000': ('160000', 'commit')}


class Refused(Exception):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def object_id(kind, raw):
    return hashlib.sha1(kind.encode('ascii') + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class NativeObjects:
    """Only a service-owned local object database; absent objects stay absent."""
    def __init__(self, repository, git):
        self.repository = Path(repository)
        info = self.repository.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o022, 'REPOSITORY_OWNER_REFUSED')
        require(Path(git).is_absolute(), 'GIT_EXECUTABLE_REFUSED')
        self.git = str(git)
        self.end = time.monotonic() + 120
        self.environment = {'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/nonexistent',
                            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                            'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
                            'GIT_NO_LAZY_FETCH': '1', 'GIT_ALLOW_PROTOCOL': ''}

    def command(self, *args):
        remaining = self.end - time.monotonic()
        require(remaining > 0, 'OBJECT_READ_DEADLINE')
        try:
            p = subprocess.run([self.git, '--no-replace-objects',
                                '-c', 'core.hooksPath=/dev/null',
                                '--git-dir=' + str(self.repository), *args],
                               env=self.environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=min(15, remaining))
        except (OSError, subprocess.TimeoutExpired):
            raise Refused('GIT_OBJECT_UNAVAILABLE') from None
        require(p.returncode == 0, 'GIT_OBJECT_UNAVAILABLE')
        return p.stdout

    def read(self, kind, oid, limit):
        require(kind in ('commit', 'tree', 'blob') and type(oid) is str
                and OID.fullmatch(oid), 'OBJECT_REQUEST_REFUSED')
        require(self.command('cat-file', '-t', oid).strip() == kind.encode(), 'OBJECT_TYPE_REFUSED')
        size = self.command('cat-file', '-s', oid).strip()
        require(re.fullmatch(rb'[0-9]{1,10}', size) and int(size) <= limit, 'OBJECT_SIZE_REFUSED')
        raw = self.command('cat-file', kind, oid)
        require(len(raw) == int(size) and object_id(kind, raw) == oid, 'OBJECT_HASH_REFUSED')
        return raw


def commit(reader, oid):
    raw = reader.read('commit', oid, 65536)
    require(object_id('commit', raw) == oid, 'COMMIT_HASH_REFUSED')
    header, separator, _ = raw.partition(b'\n\n')
    lines = header.split(b'\n')
    require(separator and lines and re.fullmatch(rb'tree [0-9a-f]{40}', lines[0]), 'COMMIT_TREE_REFUSED')
    parents = []
    for line in lines[1:]:
        require(not line.startswith(b'tree '), 'COMMIT_TREE_REFUSED')
        if line.startswith(b'parent '):
            require(re.fullmatch(rb'parent [0-9a-f]{40}', line), 'COMMIT_PARENT_REFUSED')
            parents.append(line[7:].decode('ascii'))
    require(len(parents) <= 16 and len(set(parents)) == len(parents), 'COMMIT_PARENTS_REFUSED')
    return lines[0][5:].decode('ascii'), parents


def ancestry(reader, base, head):
    require(type(base) is str and type(head) is str and OID.fullmatch(base)
            and OID.fullmatch(head) and base != head, 'PROPOSAL_COMMITS_REFUSED')
    commit(reader, base)
    pending, seen = [head], set()
    while pending:
        oid = pending.pop()
        if oid == base:
            return
        if oid in seen:
            continue
        seen.add(oid)
        require(len(seen) <= MAX_COMMITS, 'ANCESTRY_LIMIT')
        _, parents = commit(reader, oid)
        pending.extend(parents)
    raise Refused('BASE_NOT_ANCESTOR')


def complete_tree(reader, revision):
    root, _ = commit(reader, revision)
    entries = []

    def visit(oid, prefix, depth):
        require(depth <= MAX_DEPTH, 'TREE_DEPTH_LIMIT')
        raw = reader.read('tree', oid, MAX_TREE_BYTES)
        require(object_id('tree', raw) == oid, 'TREE_HASH_REFUSED')
        offset, seen, previous = 0, set(), None
        while offset < len(raw):
            end = raw.find(b'\0', offset)
            require(end >= 0 and end + 21 <= len(raw), 'TREE_RECORD_REFUSED')
            mode, space, name = raw[offset:end].partition(b' ')
            require(space and mode in MODES and 0 < len(name) <= 255
                    and b'/' not in name and b'\\' not in name
                    and name not in (b'.', b'..', b'.git') and name not in seen, 'TREE_PATH_REFUSED')
            try:
                decoded = name.decode('utf-8')
            except UnicodeDecodeError:
                raise Refused('TREE_ENCODING_REFUSED') from None
            seen.add(name)
            normalized, kind = MODES[mode]
            key = name + (b'/' if kind == 'tree' else b'')
            require(previous is None or previous < key, 'TREE_ORDER_REFUSED')
            previous = key
            child = raw[end + 1:end + 21].hex()
            path = prefix + decoded
            require(len(path) <= 300, 'TREE_PATH_LIMIT')
            entries.append({'path': path, 'mode': normalized, 'type': kind, 'sha': child})
            require(len(entries) <= MAX_ENTRIES, 'TREE_ENTRY_LIMIT')
            if kind == 'tree':
                visit(child, path + '/', depth + 1)
            offset = end + 21
    visit(root, '', 0)
    return {'sha': root, 'truncated': False, 'tree': entries}


def select_blobs(reader, tree, selector):
    """Selector is protected control code, never a candidate manifest or glob."""
    result, total = {}, 0
    for entry in tree['tree']:
        if entry['type'] != 'blob' or not selector(entry['path']):
            continue
        require(entry['mode'] in ('100644', '100755'), 'SOURCE_LINK_REFUSED')
        require(all(COMPONENT.fullmatch(p.encode('utf-8')) for p in entry['path'].split('/')), 'SELECTED_PATH_REFUSED')
        raw = reader.read('blob', entry['sha'], min(MAX_BLOB_BYTES, MAX_SELECTED_BYTES - total))
        require(object_id('blob', raw) == entry['sha'], 'BLOB_HASH_REFUSED')
        require(not raw.startswith(b'version https://git-lfs.github.com/spec/v1\n'), 'LFS_CONTENT_NOT_RESOLVED')
        total += len(raw)
        require(total <= MAX_SELECTED_BYTES, 'SOURCE_BYTES_LIMIT')
        result[entry['path']] = raw
    require(result, 'EMPTY_SOURCE_SELECTION')
    return result


def snapshot(reader, base, head, selector):
    ancestry(reader, base, head)
    tree = complete_tree(reader, head)
    blobs = select_blobs(reader, tree, selector)
    return tree, blobs
