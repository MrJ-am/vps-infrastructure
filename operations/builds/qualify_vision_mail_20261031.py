from pathlib import Path
import hashlib
import json
import subprocess
import time

BASE = Path('/workspace/shared/mrjam-declarative-nix')
INPUT = '/workspace/shared/mrjam-declarative-build/inputs-vision-mail-20261031-01'
PKGS = '/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source'
REV = '7d87768bd141ec6a2a41b4ec9f3277639fcba67f'


def write(name, value):
    with (BASE/name).open('x') as output:
        output.write(json.dumps(value, indent=2)+'\n')


def run(*args):
    return subprocess.check_output(args, text=True).strip()


builds = json.loads((BASE/'vision-mail-build-20261031-02.json').read_text())
assert builds
paths = {}
derivations = set()
for item in builds:
    derivations.add(item['drvPath'])
    for key, path in item['outputs'].items():
        assert key not in paths or paths[key] == path
        paths[key] = path
assert len(derivations) == 1 and set(paths) == {'out', 'admission', 'archive', 'cycle'}
derivation = next(iter(derivations))
assert run('nix', 'eval', '--offline', '--raw', '--file', '/workspace/shared/mrjam-declarative-build/vision-mail-package-20261031-01.nix', 'drvPath') == derivation
subprocess.run(['nix', 'store', 'verify', '--offline', '--recursive', '--no-trust', *paths.values()], check=True)
catalog = json.loads((Path(paths['out'])/'artifacts.json').read_text())
assert set(catalog) == {'admission', 'archive', 'cycle'}
artifacts = {}
for name in catalog:
    path = Path(paths[name])
    record = json.loads((path/'artifact.json').read_text())
    binary = 'bin/vision-'+name
    sha = hashlib.sha256((path/binary).read_bytes()).hexdigest()
    assert record['source_commit'] == REV and record['artifact'] == 'vision-'+name
    assert record['payload_sha256'] == {binary: sha}
    assert catalog[name] == {'output': str(path), 'artifact': record}
    artifacts[name] = {'path': str(path), 'sha256': sha, 'manifest': record}
write('vision-mail-build-metadata-20261031-02.json', {
    'decision': 'verified-public-build', 'derivation': derivation, 'artifacts': artifacts,
    'catalog_output': paths['out'], 'path_info': json.loads(run('nix', 'path-info', '--json', *paths.values())),
    'recursive_content_verification': True, 'current_derivation_matches': True,
    'production_access': False, 'production_ready': False})

for suffix, test, result, selected in [
    ('admission-folded', 'admission-resume-folded-systemd.nix', 'admission-resume-folded-systemd-result.json', 'admission'),
    ('admission', 'admission-systemd.nix', 'admission-systemd-result.json', 'admission'),
    ('archive', 'archive-mail-systemd.nix', 'archive-mail-systemd-result.json', 'archive'),
    ('cycle', 'cycle-systemd.nix', 'cycle-systemd-result.json', 'cycle'),
]:
    name = 'vision-mail-'+suffix+'-systemd-20261031-01'
    artifact = artifacts[selected]
    args = f'  nixpkgs = {PKGS};\n  materialized = {INPUT};\n'
    if suffix == 'admission-folded':
        args += ('  artifactStorePath = "/nix/store/sc6zj2w7gpkqr08yhdyfdisyqlg64ax1-mrjam-admission-adoption-1";\n'
                 '  artifactSha256 = "01e60019d18e349e284aeb6a15a97cd543e9e536d6979816d634bd5677d3cad5";\n'
                 '  admissionStorePath = '+json.dumps(artifact['path'])+';\n  admissionSha256 = '+json.dumps(artifact['sha256'])+';\n')
    else:
        args += '  artifactStorePath = '+json.dumps(artifact['path'])+';\n  artifactSha256 = '+json.dumps(artifact['sha256'])+';\n'
    expression = BASE/(name+'.nix')
    with expression.open('x') as output:
        output.write(f'import /workspace/mrjam-validation/operational-review/{test} {{\n'+args+'}\n')
    started = time.monotonic()
    with (BASE/(name+'.json')).open('x') as output, (BASE/(name+'.log')).open('x') as log:
        status = subprocess.run(['nix', 'build', '--offline', '--no-link', '--json', '--print-build-logs', '--file', str(expression)], stdout=output, stderr=log).returncode
    write(name+'-execution.json', {'exit_code': status, 'wall_seconds': round(time.monotonic()-started, 3)})
    if status != 0:
        raise SystemExit(status)
    built = json.loads((BASE/(name+'.json')).read_text())[0]
    current = run('nix', 'eval', '--offline', '--raw', '--file', str(expression), 'drvPath')
    assert current == built['drvPath']
    path = Path(built['outputs']['out'])
    subprocess.run(['nix', 'store', 'verify', '--offline', '--recursive', '--no-trust', str(path)], check=True)
    raw = (path/result).read_bytes()
    write(name+'-metadata.json', {'derivation': current, 'current_derivation_matches': True,
        'path_info': json.loads(run('nix', 'path-info', '--json', str(path))),
        'result': json.loads(raw), 'result_sha256': hashlib.sha256(raw).hexdigest(),
        'recursive_content_verification': True, 'production_access': False, 'production_ready': False})
    print(json.dumps({'test': name, 'status': 'passed-and-verified'}), flush=True)
