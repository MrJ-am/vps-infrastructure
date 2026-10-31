#!/usr/bin/env python3
"""Launch two disposable offline Cloud containers; no production capabilities."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path('/workspace/shared/mrjam-declarative-nix')
IMAGE = 'nixos/nix@sha256:c03c1081ba8fb98528dee2a677dee6f42bdddb6b90e1c14c67aba8c1e31ed4bb'
VOLUME = 'mrjam-declarative-nix-store-20261030'
PYTHON = '/nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17/bin/python3'


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def main():
    require(os.getuid() != 0 and len(sys.argv) == 3 and
        re.fullmatch(r'complete-chain-fixture-[0-9-]+', sys.argv[1]) and
        re.fullmatch(r'complete-chain-run-[0-9-]+', sys.argv[2]), 'LOCAL_FIXTURE_REQUIRED')
    fixture, output = ROOT/sys.argv[1], ROOT/sys.argv[2]
    meta = fixture.lstat()
    require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and not meta.st_mode & 0o222,
            'SEALED_FIXTURE_REQUIRED')
    output.mkdir(mode=0o700)
    ipc = output/'ipc'
    ipc.mkdir(mode=0o755)
    ipc.chmod(0o755)  # The Cloud account's 0077 umask must not hide the socket from its dedicated GID.
    artifacts = output/'public-results'
    artifacts.mkdir(mode=0o700)
    environment = {k:v for k,v in os.environ.items() if not k.startswith('DOCKER_')}
    docker = ['docker', '--host=unix:///var/run/docker.sock']
    label = subprocess.check_output([*docker, 'volume', 'inspect', '--format',
        '{{index .Labels "mrjam.scope"}}', VOLUME], env=environment, text=True).strip()
    require(label == 'local-declarative-synthetic', 'LOCAL_VOLUME_REFUSED')
    common = ['--rm', '--init', '--network=none', '--label=mrjam.scope=local-declarative-synthetic',
        '--security-opt=no-new-privileges', '--mount', f'type=volume,src={VOLUME},dst=/nix,readonly',
        '--mount', f'type=bind,src={fixture},dst=/fixture,readonly']
    name = 'mrjam-'+sys.argv[2]
    worker_args = [*docker, 'run', '--detach', '--name', name, *common,
        '--cpus=1', '--memory=2g', '--pids-limit=256',
        '--security-opt=seccomp=unconfined', '--security-opt=apparmor=unconfined',
        '--security-opt=systempaths=unconfined',
        '--mount', f'type=bind,src={fixture}/input,dst=/var/lib/mrjam-validation-input,readonly',
        '--mount', f'type=bind,src={ipc},dst=/run/mrjam-validation',
        '--entrypoint', PYTHON, IMAGE, '-I', '-S',
        '/fixture/code/forgejo/tests/complete_chain_services.py', 'worker']
    started = time.monotonic()
    launched = False
    try:
        subprocess.run(worker_args, env=environment, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, check=True, timeout=120)
        launched = True
        deadline = time.monotonic()+30
        while not (ipc/'ready.json').exists():
            require(time.monotonic() < deadline, 'WORKER_START_TIMEOUT')
            time.sleep(0.2)
        server_args = [*docker, 'run', *common, '--cpus=1', '--memory=1g', '--pids-limit=256',
            '--env=MRJAM_SYNTHETIC_CONTAINER=1',
            '--mount', f'type=bind,src={ipc},dst=/run/mrjam-validation,readonly',
            '--mount', f'type=bind,src={artifacts},dst=/results',
            '--entrypoint', PYTHON, IMAGE, '-I', '-S', '/fixture/code/forgejo/tests/qualify_complete_chain.py']
        with (output/'result.jsonl').open('x') as result, (output/'execution.log').open('x') as log:
            status = subprocess.run(server_args, env=environment, stdin=subprocess.DEVNULL,
                                    stdout=result, stderr=log, timeout=2100).returncode
        record = {'exit_code': status, 'wall_seconds': round(time.monotonic()-started, 3),
            'fixture': str(fixture), 'production_access': False, 'production_ready': False}
        with (output/'execution.json').open('x') as out:
            out.write(json.dumps(record, indent=2)+'\n')
        print(json.dumps(record))
        return status
    finally:
        if launched:
            subprocess.run([*docker, 'stop', '--time=3', name], env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


if __name__ == '__main__':
    raise SystemExit(main())
