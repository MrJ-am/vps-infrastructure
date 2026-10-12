"""Exécuter la qualification native locale avec les seuls outils déjà installés."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE/'tests'))
from kanidm_reel import EchecQualification, qualifier_import, constater_limite_import


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--paquet', default=os.environ.get('MRJAM_KANIDM'))
    args = parser.parse_args()
    if not args.paquet:
        raise EchecQualification('MRJAM_KANIDM ou --paquet installé requis ; aucune installation implicite')
    paquet = Path(args.paquet).resolve()
    if not str(paquet).startswith('/nix/store/') or not (paquet/'bin/kanidmd').is_file():
        raise EchecQualification('paquet Nix natif absent')
    nix = shutil.which('nix-store') or '/home/agent/.nix-profile/bin/nix-store'
    controle = subprocess.run([nix, '--verify-path', str(paquet)], capture_output=True, timeout=45)
    if controle.returncode:
        raise EchecQualification('intégrité du paquet Nix refusée')
    version = subprocess.run([str(paquet/'bin/kanidmd'), 'version'],
                             capture_output=True, text=True, timeout=10)
    attendue = json.loads((RACINE/'assemblage/kanidm/dependances.json').read_text())['version']
    if version.returncode or not re.search(r'(?<![0-9.])' + re.escape(attendue) + r'(?![0-9.])', version.stdout):
        raise EchecQualification('version native différente du verrou')
    curl = os.environ.get('MRJAM_CURL')
    if not curl:
        raise EchecQualification('MRJAM_CURL verrouillé requis')
    resultat = qualifier_import(paquet, curl)
    explicite = qualifier_import(paquet, curl, 656000)
    if resultat != explicite:
        raise EchecQualification('résultats divergents avec rounds explicites')
    resultat['sha512_crypt_rounds_qualifies'] = [5000, 656000]
    resultat.update(constater_limite_import(paquet, curl))
    print(json.dumps(resultat, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except EchecQualification as err:
        print('Qualification Kanidm : ' + str(err), file=sys.stderr)
        sys.exit(1)
