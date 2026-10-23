"""Transport borné par la CI centrale ; aucune commande fournie par l'utilisateur."""
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
PREFIX = 'assemblage/php-upload-progress/'
FILES = [PREFIX+n for n in ('module.nix', 'evaluation.nix', 'promote.py', 'target.json')]
FILES += ['assemblage/nextcloud-php-security/evaluation.nix',
          'assemblage/nextcloud-php-security/promote.py', 'scripts/monolithe-sauvegarde.py']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') == 'refs/heads/main'
    operation = os.environ['UPLOAD_PROGRESS_OPERATION']
    assert operation in ('audit', 'apply')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert re.fullmatch('[a-f0-9]{40}', revision)
    proof = json.loads((ROOT/PREFIX/'qualification-locale.json').read_text())
    assert proof['passed'] and proof['realNixEvaluation'] and proof['unsafeChangesRejected']
    assert set(FILES+['scripts/php-upload-progress-operation.py']) <= set(proof['sha256'])
    for name, expected in proof['sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, 'Unqualified source'
    run_id = os.environ['GITHUB_RUN_ID']
    assert re.fullmatch('[0-9]+', run_id)
    remote = '/root/mrjam-corrections/php-upload-progress/'+revision+'/'+run_id+'-'+operation
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as archive:
        for name in FILES:
            data = (ROOT/name).read_bytes()
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o600
            archive.addfile(member, io.BytesIO(data))
    def ssh(command, **kwargs):
        subprocess.run(['sh', str(ROOT/'scripts/connect.sh'), command], check=True, **kwargs)
    ssh('set -eu; umask 077; test ! -e '+remote+'; mkdir -p '+remote+'; tar -xzf - -C '+remote,
        input=payload.getvalue())
    target = json.loads((ROOT/PREFIX/'target.json').read_text())
    command = 'python3 -B '+remote+'/'+PREFIX+'promote.py '+operation+' '+revision
    ssh('nix-shell -I nixpkgs='+target['nixpkgs']+' -p python3 --run '+shlex.quote(command))


if __name__ == '__main__':
    main()
