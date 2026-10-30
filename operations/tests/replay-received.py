"""Container-only replay of the exact received tests on a synthetic Nix profile.

The caller selects a built Nix profile. Never run this on a host or VPS. Root is
used only to construct an ephemeral container path; tests then run as UID1000.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2 or not Path('/.dockerenv').is_file() or os.getuid() != 0:
    raise SystemExit('DISPOSABLE_LOCAL_CONTAINER_REQUIRED')
profile = Path(sys.argv[1])
if not str(profile).startswith('/nix/store/') or not (profile / 'bin/python3').is_file():
    raise SystemExit('BUILT_TEST_PROFILE_REQUIRED')
target = Path('/run/current-system')
target.mkdir(parents=True, exist_ok=False)
(target / 'sw').symlink_to(profile)
os.setgroups([])
os.setgid(1000)
os.setuid(1000)
base = Path(__file__).resolve().parents[1] / 'received/20261030'
env = {'PATH': str(profile / 'bin'), 'LANG': 'C', 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': '/tmp'}
results = []
for folder, files, count in [('paquet-verifie', ['test_inventory.py', 'test_validate_report.py'], 22),
                             ('', ['test_remise.py'], 16),
                             ('acces-borne', ['test_acces.py'], 10)]:
    result = subprocess.run([str(profile / 'bin/python3'), '-B', '-m', 'unittest', '-v', *files],
                            cwd=base / folder, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60)
    # Only local synthetic tests produce these diagnostics.
    sys.stderr.buffer.write(result.stderr)
    results.append({'suite': folder or 'remise', 'test_methods': count, 'exit_code': result.returncode})
print(json.dumps({'scope': 'received-unmodified-local-synthetic', 'nix_profile': str(profile),
                  'test_uid': os.getuid(), 'results': results, 'production_access': False}))
raise SystemExit(int(any(r['exit_code'] for r in results)))
