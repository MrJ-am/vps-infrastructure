"""Rejouer HTTP puis Chromium, Firefox et WebKit, sans moteur de remplacement.

--candidat consomme l'artefact Vision contrôlé par l'assemblage central.
--interface permet une reproduction locale explicite, sans reçu de promotion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def candidat():
    from assemblage import manifeste
    from frontends import contenus
    recu = json.loads((ROOT/'state/frontends-candidats/dernier-vision.json').read_text())
    dossier = ROOT/recu['candidat']
    if (recu['revision'] != manifeste()['sources']['vision']['revision']
            or dossier.is_symlink()
            or not dossier.resolve().is_relative_to(ROOT/'state/frontends-candidats')
            or contenus(dossier) != recu['fichiers']):
        raise ValueError('Candidat Vision absent, modifié ou différent du manifeste.')
    return dossier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--candidat', action='store_true')
    source.add_argument('--interface', type=Path)
    args = parser.parse_args()
    env = os.environ.copy()
    python = sys.executable
    if args.candidat:
        # Ces adaptations sont utiles en reproduction, mais elles ne sont pas
        # les outils dont l'assemblage central calcule la provenance.
        if any(env.get(k) for k in ('MRJAM_CHARGEUR_TESTS', 'WEBKIT_EXECUTABLE', 'SBCL')):
            raise ValueError('Retirer les adaptations locales pour qualifier le candidat central.')
        dossier = candidat()
        python = str(ROOT/'state/outils-python/navigateur/bin/python')
    else:
        dossier = args.interface.resolve()
    if not all((dossier/f).is_file() for f in ('app.js', 'app.html', 'app.css', 'manifest.json')):
        raise ValueError('Interface Vision compilée complète requise.')
    env['VISION_TEST_DIST'] = str(dossier)
    for fichier, moteur in [('test_mcp_reconnexion.py', None),
                            *[('mcp_reconnexion_navigateurs.py', n)
                              for n in ('chromium', 'firefox', 'webkit')]]:
        if moteur:
            env['MRJAM_NAVIGATEUR'] = moteur
        print('Reconnexion MCP : '+(moteur or 'HTTP / OIDC / MCP'), flush=True)
        # Aucun retry automatique : un échec ou un moteur manquant arrête tout.
        subprocess.run([python, str(ROOT/'tests'/fichier)], cwd=ROOT, env=env,
                       check=True, timeout=300)
    print(json.dumps({'resultat': 'succes', 'production': False,
                      'navigateurs': ['chromium', 'firefox', 'webkit'],
                      'interface': str(dossier),
                      'app_sha256': hashlib.sha256((dossier/'app.js').read_bytes()).hexdigest()},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
