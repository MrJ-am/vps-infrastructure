"""Copie chiffrée du seul paquet Kanidm audité, sans base ni configuration.

Le canal administratif central reste celui de monolithe-stage. Le destinataire
public éphémère est commité ; sa clé privée n'existe que dans l'atelier local.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_REF') != 'refs/heads/main'
            or os.environ.get('GITHUB_REPOSITORY') != 'MrJ-am/vps-infrastructure'):
        raise ValueError('Opération réservée à la CI centrale sur main.')
    lock = json.loads((ROOT/'assemblage/kanidm/installation-locale.json').read_text())
    public = json.loads((ROOT/'operations/reconnexion-outillage.json').read_text())['destinataire_age']
    if not re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}', public):
        raise ValueError('Destinataire age invalide.')
    if lock['paquet'] != '/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2':
        raise ValueError('Seul le paquet Kanidm déjà audité peut être reçu.')
    spec = importlib.util.spec_from_file_location('stage_outillage', ROOT/'scripts/monolithe-stage.py')
    stage = importlib.util.module_from_spec(spec); spec.loader.exec_module(stage)
    programme = '''import json,subprocess,sys
p=json.loads(sys.argv[1]);paquet=p['paquet']
h=subprocess.check_output(['nix-store','--query','--hash',paquet],text=True).strip()
h=subprocess.check_output(['nix','--extra-experimental-features','nix-command','hash','convert','--hash-algo','sha256','--to','sri',h],text=True).strip()
assert h==p['nar_sha256']
export=subprocess.Popen(['nix-store','--export',paquet],stdout=subprocess.PIPE)
try:
 chiffrement=subprocess.run(['age','-r',p['destinataire']],stdin=export.stdout,check=True)
finally:
 export.stdout.close()
assert export.wait()==0
'''
    params = {k: lock[k] for k in ('paquet', 'nar_sha256')}
    params['destinataire'] = public
    commande = 'python3 -B - '+shlex.quote(json.dumps(params))
    destination = Path(os.environ['RUNNER_TEMP'])/'kanidm-reconnexion.nar.age'
    with destination.open('xb') as sortie:
        stage.ssh('nix-shell -I nixpkgs='+stage.manifeste()['toolchain']['production']['nixpkgs']+
                  ' -p python3 age --run '+shlex.quote(commande),
                  input=programme.encode(), stdout=sortie)
    if not 0 < destination.stat().st_size < 256*1024*1024:
        raise ValueError('Export chiffré hors limite.')
    print('Paquet Kanidm verrouillé exporté et chiffré pour qualification locale.')
    if os.environ.get('MRJAM_TRANSPORT_OUTILLAGE') == 'git-chiffre':
        # Même transport Git chiffré que les candidats. Le token reste dans
        # l'environnement du helper GitHub, jamais dans une URL ou un argv.
        with tempfile.TemporaryDirectory(prefix='kanidm-transport-') as tmp:
            depot = Path(tmp)
            with destination.open('rb') as source:
                for i in range(8):
                    bloc = source.read(40*1024*1024)
                    if not bloc: break
                    (depot/('kanidm.nar.age.part-'+str(i).zfill(3))).write_bytes(bloc)
                else: raise ValueError('Export hors limite du transport.')
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=depot,text=True).strip()
            git('init','--quiet')
            git('config','user.name','github-actions[bot]')
            git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
            git('config','credential.https://github.com.helper','!gh auth git-credential')
            git('add','--','.')
            git('commit','--quiet','-m','Transport chiffré du Kanidm verrouillé pour reconnexion')
            branche='artefacts/kanidm-reconnexion-'+os.environ['GITHUB_RUN_ID']
            git('push','https://github.com/MrJ-am/vps-infrastructure.git','HEAD:refs/heads/'+branche)
            print(json.dumps({'transport_chiffre':git('rev-parse','HEAD'),'branche':branche}))


if __name__ == '__main__':
    main()
