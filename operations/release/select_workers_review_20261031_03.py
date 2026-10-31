from pathlib import Path
import hashlib
import json

ROOT = Path('/workspace/vps-infrastructure')
BASE = Path('/workspace/shared/mrjam-declarative-nix')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


previous = json.loads((ROOT/'operations/release/review-workers-20261031-02.json').read_bytes())
build = json.loads((ROOT/'operations/builds/qualification-vision-mail-build-20261031.json').read_bytes())
assert build['tests_without_postgresql'] == 40 and build['native_checks']['native_all_features_tests'] == 43
roots = {p:h for p,h in previous['roots'].items() if p.endswith('-mrjam-admission-adoption-1') or p.endswith('-mrjam-vision-closure-0.1.0-e067f8c74195')}
assert len(roots) == 2
for artifact in build['artifacts'].values():
    roots[artifact['path']] = build['path_info'][artifact['path']]['narHash']
evidence = [
    'operations/builds/qualification-vision-mail-build-20261031.json',
    'operations/builds/qualification-vision-closure-build-20261031.json',
    'operations/migrations/admission/qualification-build-20261031-02.json',
    'operations/migrations/admission/qualification-systemd-20261031.json',
    'operations/migrations/admission/qualification-resume-folded-systemd-20261031.json',
    'operations/migrations/admission/schema-provenance.json',
    'operations/runtime/qualification-vision-admission-mail-systemd-20261031.json',
    'operations/runtime/qualification-vision-admission-module-20261031.json',
    'operations/runtime/qualification-vision-archive-mail-systemd-20261031.json',
    'operations/runtime/qualification-vision-cycle-mail-systemd-20261031.json',
    'operations/runtime/qualification-vision-cycle-module-20261031.json',
    'operations/runtime/qualification-vision-closure-module-20261031.json',
    'operations/runtime/qualification-vision-closure-systemd-20261031.json',
]
selection = {'schema_version':1, 'scope':'public-review-only','production_authorized':False,
    'roots':dict(sorted(roots.items())),
    'evidence_sha256':{'vps-infrastructure/'+n:sha(ROOT/n) for n in sorted(evidence)},
    'limits':previous['limits'],
    'not_included':['The unchanged platform, replay and SQL004 artifacts remain in the separate platform bundle',
        'Whole VPS generation, service dependency closure and protected deployment authority',
        'Secrets, persistent state, snapshots and backups'],
    'notes':['Admission, archive and cycle are selected from Vision 7d87768bd141ec6a2a41b4ec9f3277639fcba67f; closure e067f8c7 and the offline adopter sc6zj2w7 retain their distinct evidence',
        'These three new mail consumers supersede admission 0d33bd70, cycle 47286a8a and archive 9b6cbe74 for folded historical envelopes; original archives and receipts remain unchanged',
        'New build: 40 Nix tests, 43 separate native tests and fmt/clippy; four independent systemd scenarios each bind the actual new executable',
        'The original platform review archive includes the older archive worker; only its platform, replay and SQL004 artifacts remain selected alongside this bundle',
        'No historical MIME bytes, content hashes, schema bytes or dependency pins are reassigned',
        'Fresh-store content verification is not protected trust, production installation or data rollback qualification']}
path = ROOT/'operations/release/review-workers-20261031-03.json'
with path.open('x') as out:
    out.write(json.dumps(selection, indent=2)+'\n')
print(json.dumps({'selection_sha256':sha(path),'roots':len(roots),'evidence':len(evidence)}))
