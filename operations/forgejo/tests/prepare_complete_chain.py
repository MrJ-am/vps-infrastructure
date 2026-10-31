#!/usr/bin/env python3
"""Prepare public code for an offline, disposable Forgejo/compiler integration.

The fixture commit is an orphan containing the exact reviewed validation tree
plus the already pinned manual workflow. It is not published or adopted as a
production rule. Candidate sources and their content hashes remain unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VALIDATION = Path('/workspace/mrjam-validation')
INFRA = Path(__file__).resolve().parents[3]
BUILD = Path('/workspace/shared/mrjam-declarative-build')
RESULTS = Path('/workspace/shared/mrjam-declarative-nix')
BASE_RULES = 'eb71ffe5944943474c5ee483e66c270b5976ab90'
BASE_PROPOSAL = '8bf05fb9065a4c91e565ec0d37f24f2c556f315109823ccdef95c6354b423d6a'
SOURCE = RESULTS/'worker-complete-20261031-10/input'/BASE_PROPOSAL


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    require(os.getuid() != 0 and len(sys.argv) == 2 and
            re.fullmatch(r'complete-chain-[0-9-]+', sys.argv[1]), 'LOCAL_FIXTURE_REQUIRED')
    root = BUILD/sys.argv[1]
    root.mkdir()  # Preserve all earlier attempts.
    environment = {'PATH': os.environ['PATH'], 'LANG': 'C', 'LC_ALL': 'C',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
        'GIT_AUTHOR_NAME': 'Synthetic qualification', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
        'GIT_COMMITTER_NAME': 'Synthetic qualification', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid',
        'GIT_AUTHOR_DATE': '2026-10-31T00:00:00Z', 'GIT_COMMITTER_DATE': '2026-10-31T00:00:00Z'}
    def git(*args, data=None):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *args],
            input=data, env=environment, stderr=subprocess.DEVNULL, timeout=30)
    source = root/'rules-source'
    records = []
    expected_tree = {}
    for entry in git('-C', str(VALIDATION), 'ls-tree', '-r', '-z', BASE_RULES).split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = name.decode()
        require(kind == 'blob' and mode in ('100644', '100755') and
                not Path(name).is_absolute() and '..' not in Path(name).parts, 'RULES_TREE_REFUSED')
        size = int(git('-C', str(VALIDATION), 'cat-file', '-s', blob))
        require(size <= 2*1024**2, 'RULE_FILE_LIMIT')
        raw = git('-C', str(VALIDATION), 'cat-file', 'blob', blob)
        require(len(raw) == size and hashlib.sha1(b'blob '+str(size).encode()+b'\0'+raw).hexdigest() == blob,
                'RULE_BLOB_CHANGED')
        put(source/name, raw)
        (source/name).chmod(0o755 if mode == '100755' else 0o644)
        records.append({'path': name, 'blob': blob, 'sha256': sha(raw)})
        expected_tree[name] = (mode, 'blob', blob)
    workflow = 'operations/forgejo/independent-validation.yml'
    raw = (INFRA/workflow).read_bytes()
    put(source/'.forgejo/workflows/independent-validation.yml', raw)
    expected_tree['.forgejo/workflows/independent-validation.yml'] = (
        '100644', 'blob', hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())
    git('init', '--bare', str(root/'rules.git'))
    args = ('--git-dir', str(root/'rules.git'), '--work-tree', str(source))
    git(*args, 'add', '--all')
    tree = git(*args, 'write-tree').decode().strip()
    revision = git(*args, 'commit-tree', tree, data=(
        'Offline synthetic workflow integration; validation bytes from '+BASE_RULES+'\n').encode()).decode().strip()
    git(*args, 'update-ref', 'refs/heads/main', revision)
    git(*args, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    actual_tree = {}
    for entry in git(*args, 'ls-tree', '-r', '-z', revision).split(b'\0'):
        if entry:
            metadata, name = entry.split(b'\t', 1)
            actual_tree[name.decode()] = tuple(metadata.decode().split())
    require(actual_tree == expected_tree, 'FIXTURE_GIT_TREE_CHANGED')
    original = (SOURCE/'manifest.json').read_bytes()
    require(sha(original) == BASE_PROPOSAL, 'BASE_PROPOSAL_CHANGED')
    manifest = json.loads(original)
    require(manifest['rules_revision'] == BASE_RULES, 'BASE_RULES_CHANGED')
    input_root = root/'input'
    for entry in manifest['files']:
        name = entry['path']
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'INPUT_PATH_REFUSED')
        raw = (SOURCE/name).read_bytes()
        require(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'INPUT_CHANGED')
        put(input_root/name, raw)
    manifest['rules_revision'] = revision
    raw = (json.dumps(manifest, sort_keys=True, separators=(',', ':'))+'\n').encode()
    put(input_root/'manifest.json', raw)
    proposal = sha(raw)
    policy = json.loads((RESULTS/'workflow-complete-policy-20261031-11.json').read_bytes())
    require(policy['rules_revision'] == BASE_RULES, 'BASE_POLICY_CHANGED')
    policy['rules_revision'] = revision
    put(root/'policy.json', (json.dumps(policy, sort_keys=True, indent=2)+'\n').encode())
    expression = (BUILD/'workflow-complete-package-20261031-10.nix').read_text()
    expression = expression.replace('/workspace/mrjam-validation/workflow-runner/qualification-package.nix',
                                    str(source/'workflow-runner/qualification-package.nix'))
    expression = expression.replace('/workspace/shared/mrjam-declarative-nix/workflow-complete-policy-20261031-11.json',
                                    str(root/'policy.json'))
    put(root/'package.nix', expression.encode())
    record = {'schema_version': 1, 'scope': 'offline-synthetic-complete-chain',
        'base_rules_revision': BASE_RULES, 'fixture_rules_revision': revision, 'fixture_rules_tree': tree,
        'rules_files': records, 'added_workflow_sha256': sha((INFRA/workflow).read_bytes()),
        'base_proposal_sha256': BASE_PROPOSAL, 'proposal_sha256': proposal,
        'candidate_input_files_unchanged': len(manifest['files']),
        'production_access': False, 'production_ready': False,
        'limit': 'The orphan workflow commit is a local integration fixture; no protected production authority is inferred.'}
    put(root/'preparation.json', (json.dumps(record, sort_keys=True, indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in record.items() if k != 'rules_files'}))


if __name__ == '__main__':
    main()
