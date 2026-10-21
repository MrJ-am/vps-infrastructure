"""Transport du correctif fermé, uniquement par la clé/CI centrales existantes."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'assemblage/nextcloud-php-security/'
FILES = [PREFIX+n for n in ('guard.nix', 'containment.nix', 'module.nix', 'filter-test-cgi.sh', 'evaluation.nix', 'target.json', 'promote.py')]
FILES += ['scripts/monolithe-sauvegarde.py']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') == 'refs/heads/main'
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert re.fullmatch('[a-f0-9]{40}', rev)
    proof = json.loads((ROOT/PREFIX/'qualification-locale.json').read_text())
    assert proof['passed'] and proof['realNixEvaluation'] and proof['unsafeChangesRejected']
    assert set(FILES+['scripts/nextcloud-php-security-operation.py']) <= set(proof['sha256'])
    for name, expected in proof['sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, 'Source différente de la qualification'
    remote = '/root/mrjam-corrections/nextcloud-php-security/'+rev
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as archive:
        for name in FILES:
            data = (ROOT/name).read_bytes()
            member = tarfile.TarInfo('payload/'+Path(name).name)
            member.size = len(data)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(data))
    def ssh(command, **kwargs):
        return subprocess.run(['sh', str(ROOT/'scripts/connect.sh'), command], check=True, **kwargs)
    ssh('set -eu; umask 077; test ! -e '+remote+'; mkdir -p '+remote+'; tar -xzf - -C '+remote, input=payload.getvalue())
    target = json.loads((ROOT/PREFIX/'target.json').read_text())
    command = 'python3 -B '+remote+'/payload/promote.py correct '+rev
    ssh('nix-shell -I nixpkgs='+target['nixpkgs']+' -p python3 --run '+shlex.quote(command))


if __name__ == '__main__':
    main()
