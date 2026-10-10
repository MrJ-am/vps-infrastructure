"""Choisir une seule phase qualifiée depuis le main, sans commande paramétrable."""
import json
import os
from pathlib import Path


def verifier(plan):
    if not isinstance(plan, dict) or set(plan) != {'version', 'action'} or type(plan['version']) is not int or plan['version'] != 1 or plan['action'] not in ('amorcage', 'diagnostic', 'construction', 'proprietaire', 'proprietaire-observer', 'vision-preparer', 'vision-diagnostic', 'vision-telephone', 'vision-sauvegarder', 'vision-essai-preparer', 'vision-essai-diagnostic', 'vision-retour-qualifier', 'vision-reprise-qualifier'):
        raise ValueError('Plan de mise en service non qualifié')
    return plan['action']


if __name__ == '__main__':
    action = verifier(json.loads((Path(__file__).resolve().parents[1]/'operations/vision-mise-en-service.json').read_text()))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
        f.write('action=' + action + '\n')
