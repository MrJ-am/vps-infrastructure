"""Vérifier le module préparatoire Kanidm localement, sans construire/démarrer."""
import json
from pathlib import Path
import subprocess

RACINE = Path(__file__).resolve().parents[1]


def main():
    revision = 'c5c4a43b0e8056328ec4529f735cabdb8f1942bb'
    base = RACINE / ('state/outils-sources/nixpkgs-' + revision)
    if not base.is_dir():
        raise ValueError('Source Nixpkgs déjà verrouillée requise ; aucune installation implicite')
    nix = '/home/agent/.nix-profile/bin/nix-instantiate'
    if not Path(nix).is_file():
        nix = 'nix-instantiate'
    positif = 'let pkgs=import ' + str(base) + ' {}; in import ./tests/kanidm-configuration.nix {inherit pkgs;}'
    resultat = subprocess.run([nix, '--eval', '--strict', '--json', '--expr', positif],
                              cwd=RACINE, capture_output=True, text=True, timeout=60, check=True)
    attendu = {'version': '1.11.2', 'user': 'kanidm', 'stateMode': '0700',
               'secretsDansStore': False, 'provisioning': False, 'unix': False, 'ldap': None,
               'cible': 'configuration évaluée ; aucun serveur installé/démarré'}
    if json.loads(resultat.stdout) != attendu:
        raise ValueError('Configuration Kanidm différente')
    for fichier in ('/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-secret', '/runtime/cle\n.pem', '/runtime/cle\r.pem'):
        expression = positif[:-1] + ' tlsKeyFile=' + json.dumps(fichier) + ';}'
        resultat = subprocess.run([nix, '--eval', '--strict', '--json', '--expr', expression],
                                  cwd=RACINE, capture_output=True, text=True, timeout=60)
        if not resultat.returncode or 'assertion' not in resultat.stderr.lower():
            raise ValueError('Une fixture TLS non conforme doit être refusée par une assertion')
    print('Kanidm Nix : configuration positive et trois fixtures TLS refusées ; aucun serveur ni déploiement.')


if __name__ == '__main__':
    main()
