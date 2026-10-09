"""Refuser une opération VPS avant réussite de la CI du commit opérateur exact."""
import json
import os
import re
import urllib.request

revision = os.environ['GITHUB_SHA']
if not re.fullmatch('[0-9a-f]{40}', revision): raise SystemExit('Révision opérateur invalide')
url = 'https://api.github.com/repos/MrJ-am/vps-infrastructure/actions/workflows/check.yml/runs?head_sha=' + revision + '&per_page=20'
req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN']})
with urllib.request.urlopen(req, timeout=20) as r: runs = json.load(r)['workflow_runs']
if not any(r['head_sha'] == revision and r['event'] == 'push' and r['conclusion'] == 'success' for r in runs):
    raise SystemExit('CI exacte non réussie ; aucune opération VPS autorisée par ce programme')
print('CI du commit opérateur exact réussie.')
