#!/usr/bin/env python3
"""Verify the fixed public Cloud fixture, without building or activating it."""
from pathlib import Path
import json
import os
import subprocess
import sys

BASE = Path('/workspace/shared/mrjam-declarative-nix')
BUILD = Path('/workspace/shared/mrjam-declarative-build')


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def main():
    require(len(sys.argv) == 1 and os.getuid() == 0 and
            os.environ.get('MRJAM_SYNTHETIC_CONTAINER') == '1' and
            set(os.listdir('/sys/class/net')) == {'lo'}, 'OFFLINE_CLOUD_FIXTURE_REQUIRED')
    built = json.loads((BASE/'complete-chain-package-20261031-01.json').read_bytes())
    expected = {e['drvPath'] for e in built}
    for attempt in ('01', '02'):
        actual = json.loads(subprocess.check_output(['nix', 'eval', '--offline', '--json',
            '--file', str(BUILD/('complete-chain-20261031-'+attempt)/'package.nix'),
            '--apply', 'map (p: p.drvPath)']))
        require(set(actual) == expected, 'DERIVATION_REPRODUCTION_CHANGED')
    roots = [e['outputs']['out'] for e in built] + [
        '/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1',
        '/nix/store/cdj7b2dnn83kbwwhrpia79zbfllxbzsb-mrjam-forgejo-runner-13.2.0']
    subprocess.run(['nix', 'store', 'verify', '--offline', '--recursive', '--no-trust', *roots], check=True)
    info = json.loads(subprocess.check_output(['nix', 'path-info', '--json', *roots]))
    result = {'current_derivations_match': True, 'repeated_preparation_derivations_match': True,
        'recursive_contents_verified': True, 'path_info': info, 'production_access': False}
    with (BASE/'complete-chain-nix-metadata-20261031-01.json').open('x') as out:
        out.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'decision': 'verified-public-complete-chain-store', 'roots': len(roots)}))


if __name__ == '__main__':
    main()
