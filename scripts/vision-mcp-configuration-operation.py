"""Transport fermé du correctif qualifié, par la CI/clé SSH existantes."""
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
PREFIX = 'assemblage/vision-mcp-configuration/'
FILES = [PREFIX+n for n in ('promote.py', 'evaluation.nix', 'module.nix', 'target.json')]
FILES += ['scripts/monolithe-sauvegarde.py']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') == 'refs/heads/main'
    phase = os.environ['MRJAM_OPERATION'].removeprefix('vision-mcp-')
    assert phase in ('preparer', 'deployer', 'retour', 'diagnostic')
    rev = json.loads((ROOT/'operations/vision-mcp-configuration-candidat.json').read_text())['revision_sources']
    assert re.fullmatch('[a-f0-9]{40}', rev)
    remote = '/root/mrjam-corrections/vision-mcp-configuration/'+rev
    def ssh(command, **kwargs):
        return subprocess.run(['sh', str(ROOT/'scripts/connect.sh'), command], check=True, **kwargs)
    if phase == 'preparer':
        subprocess.run(['git', 'fetch', '--depth=1', 'origin', rev], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        def source(name):
            return subprocess.check_output(['git', 'show', rev+':'+name], cwd=ROOT)
        proof = json.loads(source(PREFIX+'qualification-locale.json'))
        assert proof['passed'] and proof['regressionBeforeRejected'] and proof['realNixAndSbcl']
        for name, digest in proof['sha256'].items():
            assert hashlib.sha256(source(name)).hexdigest() == digest, 'Source non qualifiée : '+name
        assert set(FILES) <= set(proof['sha256'])
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            for name in FILES:
                content = source(name)
                entry = tarfile.TarInfo('payload/'+Path(name).name); entry.size = len(content); entry.mode = 0o600
                archive.addfile(entry, io.BytesIO(content))
        ssh('set -eu; umask 077; test ! -e '+remote+'; mkdir -p '+remote+'; tar -xzf - -C '+remote,
            input=data.getvalue())
    command = 'python3 -B '+remote+'/payload/promote.py '+('launch' if phase == 'deployer' else phase)+' '+rev
    nixpkgs = json.loads((ROOT/'assemblage/manifest.json').read_text())['toolchain']['production']['nixpkgs']
    ssh('nix-shell -I nixpkgs='+nixpkgs+' -p python3 --run '+shlex.quote(command))


if __name__ == '__main__':
    main()
