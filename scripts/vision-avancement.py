"""Résumé technique lisible, construit uniquement depuis une preuve bornée."""
import argparse
import json
import os
from pathlib import Path
import re


def resume(rapport, termine=False):
    if not isinstance(rapport, dict): raise ValueError('Rapport absent')
    revision = rapport.get('infrastructure', '')
    if not re.fullmatch('[0-9a-f]{40}', revision) or revision != os.environ['GITHUB_SHA']:
        raise ValueError('Rapport de révision différente')
    if termine:
        if not all(rapport.get(cle) is True for cle in ('activation_reservee', 'generation_enregistree',
                'retour_autonome', 'retour_neutralise', 'copie_locale_chiffree', 'postgres_prive', 'services_conserves')):
            raise ValueError('Preuve finale incomplète')
        if any(rapport.get(cle) is not False for cle in ('identite_humaine', 'mode_vision_oidc', 'inscriptions')):
            raise ValueError('Périmètre d’amorçage différent')
        return ('Identité réservée activée et contrôlée sur https://log.mrj.am.\n\n'
            'Vision conserve son accès et ses données actuels. Les inscriptions sont fermées.\n\n'
            'L’agent prépare ensuite votre compte commun. Aucune nouvelle action dans GitHub Actions '
            'n’est demandée ; il vous préviendra pour votre mot de passe et votre second facteur.\n')
    if type(rapport.get('enregistre')) is not bool: raise ValueError('Avancement non établi')
    return ('Étape déjà enregistrée : seuls les contrôles seront répétés.\n' if rapport['enregistre'] else
        'Activation réservée : contrôles, sauvegarde chiffrée, retour autonome, essai, vérification des sites et enregistrement.\n')


def main():
    p = argparse.ArgumentParser(); p.add_argument('rapport', type=Path); p.add_argument('--termine', action='store_true')
    a = p.parse_args(); contenu = a.rapport.read_bytes()
    if len(contenu) > 16384: raise ValueError('Rapport trop volumineux')
    rapport = json.loads(contenu); texte = resume(rapport, a.termine)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f: f.write(texte)
    if not a.termine:
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            f.write('enregistre=' + str(rapport['enregistre']).lower() + '\n')


if __name__ == '__main__':
    main()
