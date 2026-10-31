#!/usr/bin/env python3
"""Verify and record the completed local, public-code staging qualification."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path('/workspace/vps-infrastructure')
VALIDATION = Path('/workspace/mrjam-validation')
OUTPUT = Path('/workspace/shared/mrjam-declarative-nix')
BUILD = Path('/workspace/shared/mrjam-declarative-build')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    assert os.getuid() == 0 and set(os.listdir('/sys/class/net')) == {'lo'}
    native = OUTPUT/'staging-native-20261031-04.log'
    assert 'Ran 17 tests' in native.read_text() and native.read_text().endswith('\nOK\n')
    module = read(OUTPUT/'staging-module-20261031-02.json')
    assert len(module) == 17 and all(value is True for value in module.values())
    builds = {}
    for name in ('staging-build-20261031-02', 'staging-systemd-20261031-03'):
        assert read(OUTPUT/(name+'-execution.json'))['exit_code'] == 0
        items = read(OUTPUT/(name+'.json'))
        assert len(items) == 1
        builds[name] = items[0]
    package = builds['staging-build-20261031-02']
    vm = builds['staging-systemd-20261031-03']
    package_current = subprocess.check_output(['nix','eval','--offline','--raw','--file',
        str(BUILD/'staging-package-20261031-01.nix'),'--apply','p: p.drvPath']).decode()
    vm_current = subprocess.check_output(['nix','eval','--offline','--raw','--file',
        str(VALIDATION/'operational-review/staging-sources-systemd.nix'),'--arg','nixpkgs',
        '/nix/store/ydk30pf7qngrw0ws113m9p005p681rxy-source','--apply','p: p.drvPath']).decode()
    assert package_current == package['drvPath'] and vm_current == vm['drvPath']
    result_path = Path(vm['outputs']['out'])/'staging-systemd-assertions.json'
    result = read(result_path)
    assert len(result['checks']) == 8 and result['source_files'] == 815
    assert result['package'] == package['outputs']['out'] and result['production_ready'] is False
    roots = [package['outputs']['out'], vm['outputs']['out'], result['source_bundle']]
    subprocess.run(['nix','store','verify','--offline','--recursive','--no-trust',*roots],check=True)
    info = json.loads(subprocess.check_output(['nix','path-info','--json',*roots]))
    for label, build in (('package', package), ('systemd', vm)):
        log = subprocess.check_output(['nix','log','--offline',build['drvPath']])
        with (OUTPUT/('staging-'+label+'-full-20261031-02.log')).open('xb') as out:
            out.write(log)
        if label == 'package':
            assert re.search(rb'Ran 17 tests in [0-9.]+s', log) and b'\nOK\n' in log
    for attempt, derivation in [
        ('01', '/nix/store/6qmpgidfbbkx32bbz32mfnr5bk6a8dz6-vm-test-run-mrjam-staging-sources-systemd-independent.drv'),
        ('02', '/nix/store/zhk0q4y0zvirl581fyk4y7gwavzbnysm-vm-test-run-mrjam-staging-sources-systemd-independent.drv')]:
        log = subprocess.check_output(['nix','log','--offline',derivation])
        with (OUTPUT/('staging-systemd-failed-20261031-'+attempt+'-full.log')).open('xb') as out:
            out.write(log)
    sources = [
        ROOT/'operations/forgejo/stage_sources.py', ROOT/'operations/forgejo/worker.py',
        ROOT/'operations/forgejo/staging-package.nix', ROOT/'operations/nixos/mrjam-validation-staging.nix',
        ROOT/'operations/nixos/mrjam-validation-worker.nix',
        ROOT/'operations/forgejo/tests/test_stage_sources.py', ROOT/'operations/forgejo/tests/staging-module-evaluation.nix',
        ROOT/'operations/forgejo/tests/qualify_staging_20261031.py', Path(__file__),
        ROOT/'operations/forgejo/tests/qualify_staging_20261031_02.py',
        ROOT/'operations/forgejo/tests/qualify_staging_vm_20261031.py',
        ROOT/'operations/forgejo/tests/staging-package-local.nix',
        VALIDATION/'operational-review/STAGING-SOURCES.org',
        VALIDATION/'operational-review/staging-source-fixture.py',
        VALIDATION/'operational-review/staging-sources-systemd.nix']
    for name, original in [('qualify_staging_20261031.py', 'qualify-staging-package-20261031-01.py'),
                           ('qualify_staging_vm_20261031.py', 'qualify-staging-vm-20261031-02.py'),
                           ('staging-package-local.nix', 'staging-package-20261031-01.nix'),
                           ('qualify_staging_20261031_02.py', 'qualify-staging-20261031-02.py')]:
        assert (ROOT/'operations/forgejo/tests'/name).read_bytes() == (BUILD/original).read_bytes()
    record = {'schema_version':1,'authority':'unverified-local-test-result','production_access':False,
        'production_ready':False,'source_revisions':{
            'infrastructure_candidate':'facbe4cf8bac29a9b098fccc9f8358cc83538807',
            'validation_suite':'ea9178ceea306f909d3d904ce0edab0f41c88f8e'},
        'control_source_binding':'Qualification/recording drivers are bound separately by source_sha256, not claimed to belong to the candidate revision.',
        'native_tests':17,'nix_package_tests':17,'module':module,'builds':builds,
        'current_derivations_match':True,'recursive_contents_verified':True,'path_info':info,
        'result':result,'result_sha256':sha(result_path),
        'execution':read(OUTPUT/'staging-systemd-20261031-03-execution.json'),
        'source_sha256':{str(p):sha(p) for p in sources},
        'logs_sha256':{p.name:sha(p) for p in OUTPUT.glob('staging-*.log')},
        'earlier_systemd_attempt':read(OUTPUT/'staging-systemd-20261031-01-execution.json'),
        'second_systemd_attempt':read(OUTPUT/'staging-systemd-20261031-02-execution.json'),
        'second_systemd_failure_reason':'Repeated publication unnecessarily copied and verified an already checked tree and reached the unchanged 120s unit timeout at 20% CPU. The new implementation rechecks both published and store bytes without copying an existing proposal. Unit limits are unchanged.',
        'earlier_systemd_failure_reason':'The first three groups passed; reset-failed on an unloaded successful oneshot unit was a harness error. It is now called only for an actually failed unit.',
        'earlier_failures_preserved':[
            {'attempt':'native-01','tests':16,'errors':8,'reason':'Cross-parent rename lacked owner-write permissions on the private parent and moved directory'},
            {'attempt':'native-02','tests':16,'errors':8,'reason':'Private parent fixed; moved directory still lacked owner-write for its parent update'}],
        'limits':['No production access, signing identity, protected rule adoption or host quotas established',
                  'Recovery uses constructed interrupted-copy/rename states and injected rename errors; physical power-loss durability is not established',
                  'The full compiler integration remains a distinct prior proof; this suite checks exact publication of its 815 public input files',
                  'No remote forge fetch, target VPS generation, deployment activation or data migration executed']}
    target = OUTPUT/'staging-qualification-20261031-02.json'
    with target.open('x') as stream:
        stream.write(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'decision':'verified-staging-qualification','native_tests':17,
        'nix_package_tests':17,'module_assertions':17,'systemd_groups':8,
        'result_path':str(target),'production_ready':False}))


if __name__ == '__main__':
    main()
