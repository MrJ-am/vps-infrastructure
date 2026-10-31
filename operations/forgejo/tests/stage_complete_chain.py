#!/usr/bin/env python3
"""Seal a public integration fixture in the offline Cloud Nix container."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BUILD = Path('/workspace/shared/mrjam-declarative-build')
OUTPUT = Path('/workspace/shared/mrjam-declarative-nix')
CODE = Path(__file__).resolve().parents[1]
FILES = ('worker.py', 'submit.py', 'reconcile.py', 'register_runner.py',
         'independent-validation.yml', 'tests/complete_chain_services.py',
         'tests/qualify_complete_chain.py')


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def main():
    require(os.getuid() == 0 and set(os.listdir('/sys/class/net')) == {'lo'} and
            os.environ.get('MRJAM_SYNTHETIC_CONTAINER') == '1' and len(sys.argv) == 3 and
            re.fullmatch(r'complete-chain-[0-9-]+', sys.argv[1]) and
            re.fullmatch(r'complete-chain-fixture-[0-9-]+', sys.argv[2]), 'OFFLINE_FIXTURE_REQUIRED')
    source = BUILD/sys.argv[1]
    root = OUTPUT/sys.argv[2]
    require(not root.exists(), 'FIXTURE_COLLISION')
    prepared = json.loads((source/'preparation.json').read_bytes())
    build = json.loads((OUTPUT/'complete-chain-package-20261031-01.json').read_bytes())
    paths = [item['outputs']['out'] for item in build]
    validator = next(p for p in paths if p.endswith('-mrjam-validate'))
    closure = next(p for p in paths if p.endswith('-closure-info'))
    subprocess.run(['nix', 'store', 'verify', '--offline', '--recursive', '--no-trust', *paths], check=True)
    current = json.loads(subprocess.check_output(['nix', 'eval', '--offline', '--json',
        '--file', str(source/'package.nix'), '--apply', 'map (p: p.drvPath)']))
    require(set(current) == {item['drvPath'] for item in build}, 'CURRENT_DERIVATION_CHANGED')
    configuration = {'schema_version': 1, 'rules_revision': prepared['fixture_rules_revision'],
        'validator_store': validator, 'closure_file': closure+'/store-paths',
        'bubblewrap_store': '/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0'}
    root.mkdir(mode=0o755)
    manifest = json.loads((source/'input/manifest.json').read_bytes())
    proposal = prepared['proposal_sha256']
    require(hashlib.sha256((source/'input/manifest.json').read_bytes()).hexdigest() == proposal,
            'PROPOSAL_CHANGED')
    target = root/'input'/proposal
    target.mkdir(parents=True)
    for item in manifest['files']:
        name = item['path']
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'INPUT_PATH_REFUSED')
        original = source/'input'/name
        require(not original.is_symlink(), 'INPUT_SYMLINK_REFUSED')
        raw = original.read_bytes()
        require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'INPUT_CHANGED')
        (target/name).parent.mkdir(parents=True, exist_ok=True)
        with (target/name).open('xb') as out:
            out.write(raw)
    shutil.copyfile(source/'input/manifest.json', target/'manifest.json')
    code = {}
    for name in FILES:
        raw = (CODE/name).read_bytes()
        path = root/'code/forgejo'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:
            out.write(raw)
        code[name] = hashlib.sha256(raw).hexdigest()
    for p in (source/'rules.git').rglob('*'):
        require(not p.is_symlink() and (p.is_file() or p.is_dir()), 'GIT_FIXTURE_TYPE_REFUSED')
    shutil.copytree(source/'rules.git', root/'rules.git')
    runtime = {'rules_revision': prepared['fixture_rules_revision'], 'proposal_sha256': proposal,
        'workflow_sha256': prepared['added_workflow_sha256'], 'configuration': configuration,
        'builds': build, 'code_sha256': code, 'production_access': False, 'production_ready': False}
    (root/'runtime.json').write_text(json.dumps(runtime, sort_keys=True, indent=2)+'\n')
    shutil.copyfile(source/'preparation.json', root/'preparation.json')
    for base, _, files in os.walk(root, topdown=False):
        for name in files:
            (Path(base)/name).chmod(0o444)
        Path(base).chmod(0o555)
    spec = importlib.util.spec_from_file_location('worker', CODE/'worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.verify_input(root/'input', proposal, prepared['fixture_rules_revision'])
    print(json.dumps({'decision': 'sealed-offline-fixture', 'fixture': str(root),
        'runtime_sha256': hashlib.sha256((root/'runtime.json').read_bytes()).hexdigest(),
        'configuration': configuration, 'proposal_sha256': proposal, 'production_access': False}))


if __name__ == '__main__':
    main()
