"""Accepter une demande dédiée, jamais un push ordinaire ou une révision étrangère."""
import json
import os
import re
import subprocess
import urllib.request

DEPOT = 'MrJ-am/vps-infrastructure'
BRANCHE = 'operations/vision'


def verifier(env, evenement, main):
    revision = env.get('GITHUB_SHA', '')
    if env.get('GITHUB_REPOSITORY') != DEPOT or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Dépôt ou révision de demande invalide')
    if evenement.get('repository', {}).get('full_name') != DEPOT:
        raise ValueError('Provenance étrangère')
    nom = env.get('GITHUB_EVENT_NAME'); branche = env.get('GITHUB_REF')
    if nom == 'workflow_dispatch':
        if branche != 'refs/heads/main' or evenement.get('inputs'):
            raise ValueError('Le lancement manuel exige main sans paramètres libres')
    elif nom == 'workflow_run':
        signal = evenement.get('workflow_run', {})
        if branche != 'refs/heads/main' or signal.get('event') != 'push' or signal.get('head_branch') != BRANCHE or signal.get('status') != 'completed' or signal.get('conclusion') != 'success' or signal.get('path') != '.github/workflows/vision-demande.yml':
            raise ValueError('Signal dédié absent ou non réussi')
        if signal.get('head_sha') != revision or signal.get('head_repository', {}).get('full_name') != DEPOT or signal.get('repository', {}).get('full_name') != DEPOT:
            raise ValueError('Signal étranger ou révision incohérente')
    else:
        raise ValueError('Événement sans droit de lancer une opération')
    if main.get('ref') != 'refs/heads/main' or main.get('object', {}).get('type') != 'commit' or main['object']['sha'] != revision:
        raise ValueError('La demande doit désigner exactement le main actuel')
    return {'demande_validee': True, 'revision': revision, 'parametres_libres': False}


def main():
    # Ce contrôle précède toute lecture de credential VPS. Le token est utilisé
    # exclusivement pour l'API fixe du dépôt ; ni événement ni réponse affichés.
    with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as fichier:
        evenement = json.load(fichier)
    code = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, text=True, capture_output=True).stdout.strip()
    if code != os.environ['GITHUB_SHA']: raise ValueError('Code extrait différent de la révision opérateur')
    requete = urllib.request.Request('https://api.github.com/repos/' + DEPOT + '/git/ref/heads/main',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(requete, timeout=20) as reponse:
        contenu = reponse.read(65537)
    if len(contenu) > 65536: raise ValueError('Référence distante trop volumineuse')
    print(json.dumps(verifier(os.environ, evenement, json.loads(contenu))))


if __name__ == '__main__':
    main()
