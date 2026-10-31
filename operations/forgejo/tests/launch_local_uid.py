#!/usr/bin/env python3
"""Reproducible Cloud-only namespace qualification, no production endpoint."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path('/workspace/shared/mrjam-declarative-nix')
SOURCE = Path(__file__).resolve().parents[1]
IMAGE = 'nixos/nix@sha256:c03c1081ba8fb98528dee2a677dee6f42bdddb6b90e1c14c67aba8c1e31ed4bb'
VOLUME = 'mrjam-declarative-nix-store-20261030'
PYTHON = '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17/bin/python3'


def main():
    if os.getuid() == 0 or len(sys.argv) != 4 or sys.argv[1] not in {'qualify', 'diagnose', 'diagnose-http'} \
            or not re.fullmatch(r'qualifier-code-[0-9-]+', sys.argv[2]) \
            or not re.fullmatch(r'worker-[A-Za-z0-9_-]+', sys.argv[3]):
        raise RuntimeError('LOCAL_FIXTURE_ARGUMENTS_REQUIRED')
    mode, code, exported = sys.argv[1], ROOT / sys.argv[2], ROOT / sys.argv[3]
    for path in (code, exported):
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o222:
            raise RuntimeError('IMMUTABLE_LOCAL_FIXTURE_REQUIRED')
    record = json.loads((code / 'sources.json').read_bytes())
    if set(record) != {'worker.py', 'tests/qualify_nix_worker.py', 'tests/run_isolated_uid.py'}:
        raise RuntimeError('CODE_MANIFEST_CHANGED')
    for name, expected in record.items():
        for path in (SOURCE / name, code / 'forgejo' / name):
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError('CODE_CHANGED_PREPARE_NEW_FIXTURE')
    environment = {key: value for key, value in os.environ.items() if not key.startswith('DOCKER_')}
    docker = ['docker', '--host=unix:///var/run/docker.sock']
    label = subprocess.check_output([*docker, 'volume', 'inspect', '--format', '{{index .Labels "mrjam.scope"}}', VOLUME], env=environment, text=True).strip()
    if label != 'local-declarative-synthetic':
        raise RuntimeError('LOCAL_VOLUME_REFUSED')
    arguments = [*docker, 'run', '--rm', '--init', '--network=none', '--user=59990:59990',
        '--label=mrjam.scope=local-declarative-synthetic', '--cpus=1', '--memory=2g', '--pids-limit=256',
        '--cap-drop=ALL', '--security-opt=no-new-privileges', '--security-opt=seccomp=unconfined',
        '--security-opt=apparmor=unconfined', '--security-opt=systempaths=unconfined',
        '--mount', f'type=volume,src={VOLUME},dst=/nix,readonly',
        '--mount', f'type=bind,src={code},dst=/qualification,readonly',
        '--mount', f'type=bind,src={exported},dst={exported},readonly',
        '--mount', f'type=bind,src={ROOT}/qualifier-uid-59990,dst={ROOT}/qualifier-uid-59990']
    if mode == 'diagnose-http':
        arguments += ['--mount', f'type=bind,src={code}/diagnostic-server,dst={ROOT}/runtime-export-20261031-02/mrjam-server,readonly']
    arguments += ['--entrypoint', PYTHON, IMAGE, '-I', '-S', '/qualification/forgejo/tests/run_isolated_uid.py', mode, str(exported)]
    return subprocess.run(arguments, env=environment, stdin=subprocess.DEVNULL).returncode


if __name__ == '__main__':
    raise SystemExit(main())
