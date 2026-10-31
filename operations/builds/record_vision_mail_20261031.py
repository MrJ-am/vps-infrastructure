from pathlib import Path
import hashlib
import json
import re

BASE = Path('/workspace/shared/mrjam-declarative-nix')
INFRA = Path('/workspace/vps-infrastructure')
VALIDATION = Path('/workspace/mrjam-validation')
VISION = Path('/workspace/shared/vision-workers-operationnels')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(name):
    return json.loads((BASE/name).read_bytes())


def write(p, value):
    with p.open('x') as out:
        out.write(json.dumps(value, indent=2)+'\n')


execution = read('vision-mail-build-20261031-02-execution.json')
assert execution['exit_code'] == 0
build = read('vision-mail-build-metadata-20261031-02.json')
assert build['current_derivation_matches'] and build['recursive_content_verification']
log = (BASE/'vision-mail-build-20261031-02.log').read_text()
count = sum(int(n) for n in re.findall(r'test result: ok\. (\d+) passed;', log))
assert count == 40
native = json.loads((VISION/'docs/qualification-folded-envelope-20261031.json').read_bytes())
assert native['native_all_features_tests'] == 43 and native['fmt'] == native['clippy'] == 'passed'
for name, expected in native['logs_sha256'].items():
    assert sha(BASE/name) == expected
assert 'No space left on device' in (BASE/'vision-mail-build-20261031-01.log').read_text()
build.update(schema_version=1, authority='unverified-local-test-result',
    tests_without_postgresql=count, native_checks=native,
    compatibility=read('vision-mail-compatibility-20261031-02.json'), execution=execution,
    prior_attempt={'exit_code':1, 'reason':'Cloud disk exhausted; unchanged recipe rerun after byte-preserving cache deduplication',
        'log_sha256':sha(BASE/'vision-mail-build-20261031-01.log'),
        'cache_deduplication':read('vendor-cache-deduplication-20261031-01.json')},
    sources_sha256={n:sha(INFRA/n) for n in ['operations/builds/vision-mail-workers-20261031.nix',
        'operations/builds/prepare_vision_workers.py','operations/builds/prepare.py']},
    logs_sha256={n:sha(BASE/n) for n in ['vision-mail-build-20261031-02.log',
        'vision-mail-build-20261031-02.json', 'vision-mail-build-20261031-02-execution.json']},
    limits=['Only admission, archive and cycle are selected from this new build',
        'Closure and replay retain their separately qualified revisions',
        'Public synthetic qualification is not protected approval, native IdP/MFA, snapshot coherence or deployment readiness'])

receipts = []
for suffix, test, extras, modules, destination in [
    ('admission-folded', 'admission-resume-folded-systemd.nix', ['fixtures/admission-resume-folded-synthetic.py'],
     ['mrjam-admission-adoption.nix', 'mrjam-vision-admission.nix', 'mrjam-postgresql-access.nix'],
     'operations/migrations/admission/qualification-resume-folded-systemd-20261031.json'),
    ('admission', 'admission-systemd.nix', ['fixtures/admission-state-synthetic.py', 'fixtures/admission-private-synthetic.py'],
     ['mrjam-vision-admission.nix', 'mrjam-postgresql-access.nix'],
     'operations/runtime/qualification-vision-admission-mail-systemd-20261031.json'),
    ('archive', 'archive-mail-systemd.nix', [],
     ['mrjam-vision-archive.nix', 'mrjam-postgresql-access.nix'],
     'operations/runtime/qualification-vision-archive-mail-systemd-20261031.json'),
    ('cycle', 'cycle-systemd.nix', [],
     ['mrjam-vision-cycle.nix', 'mrjam-postgresql-access.nix'],
     'operations/runtime/qualification-vision-cycle-mail-systemd-20261031.json'),
]:
    name = 'vision-mail-'+suffix+'-systemd-20261031-01'
    metadata = read(name+'-metadata.json')
    executed = read(name+'-execution.json')
    assert executed['exit_code'] == 0 and metadata['current_derivation_matches']
    assert metadata['recursive_content_verification'] and len(metadata['result']['checks']) == 8
    duration = re.findall(r'test script finished in ([0-9.]+)s', (BASE/(name+'.log')).read_text())
    assert len(duration) == 1
    sources = {'mrjam-validation/operational-review/'+n:sha(VALIDATION/'operational-review'/n)
               for n in [test,*extras]}
    sources.update({'vps-infrastructure/operations/nixos/'+n:sha(INFRA/'operations/nixos'/n) for n in modules})
    metadata.update(schema_version=1, authority='unverified-local-test-result',
        validation_test_commit='d468bb90c87043b182ca20d7998f092b1c15ab6c',
        duration_seconds=float(duration[0]), execution=executed, sources_sha256=sources,
        qualification_helper_sha256=sha(Path('/workspace/shared/mrjam-declarative-build/qualify-vision-mail-20261031-02.py')),
        logs_sha256={name+ext:sha(BASE/(name+ext)) for ext in ['.log','.json','-execution.json']})
    receipts.append((destination, 'operational-review/'+name+'-pass.json', metadata))

write(INFRA/'operations/builds/qualification-vision-mail-build-20261031.json', build)
for infrastructure_path, validation_path, record in receipts:
    write(INFRA/infrastructure_path, record)
    write(VALIDATION/validation_path, record)
print(json.dumps({'build_tests':count,'native_tests':43,'systemd_suites':4,
    'systemd_groups':32,'production_ready':False}))
