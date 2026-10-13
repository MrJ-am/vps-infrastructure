"""Qualification locale du codec Elm Log, pas du parcours de connexion complet.

Même elm-review/configuration/compilateur que les autres consommateurs.
Outils déjà verrouillés, aucune installation ni publication.
"""
import importlib.util
import json
from pathlib import Path
import subprocess

from assemblage import RACINE, chemins_sources


def main():
    spec = importlib.util.spec_from_file_location('revoir_frontends', RACINE/'scripts/revoir-frontends.py')
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    commande, env = review.outils()
    projet = RACINE/'interface-log'
    r = subprocess.run(commande, cwd=projet, env=env, capture_output=True, text=True)
    dossier = RACINE/'state/review-frontends'
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier/'log-protocole.json').write_text(r.stdout)
    if r.returncode:
        raise ValueError('elm-review Log refusé ; voir state/review-frontends/log-protocole.json')
    # Pas de recours silencieux à un outil global ou à une autre version.
    outils = chemins_sources()['matheval']/'docs/node_modules/.bin'
    subprocess.run([str(outils/'elm-format'), 'src', 'tests', '--validate'], cwd=projet, env=env, check=True)
    r = subprocess.run([str(outils/'elm-test'), '--compiler', str(outils/'elm'),
                        '--seed', '20261013', '--report', 'json'],
                       cwd=projet, env=env, capture_output=True, text=True)
    if r.returncode:
        raise ValueError('Tests du protocole Log refusés')
    events = [json.loads(line) for line in r.stdout.splitlines() if line.startswith('{')]
    resultats = [e for e in events if e.get('event') == 'runComplete']
    if len(resultats) != 1 or int(resultats[0]['passed']) < 9 or int(resultats[0]['failed']) != 0:
        raise ValueError('Résultat effectif des assertions Elm absent ou incomplet')
    print(json.dumps({'elm_review': 'succes', 'assertions': int(resultats[0]['passed']),
                      'portee': 'codec JSON ; connexion réelle et présentation non qualifiées'}))


if __name__ == '__main__':
    main()
