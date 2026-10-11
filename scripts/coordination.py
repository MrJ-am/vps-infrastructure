#!/usr/bin/env python3
"""Références de l'assemblage central ; aucun message ou acquittement."""
import argparse
from pathlib import Path
import json
from assemblage import manifeste, catalogue, RACINE

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('operation', choices=['lire', 'verifier'])
p.add_argument('composant', nargs='?')
p.add_argument('--base', help='Compatibilité lecture : ne déclenche aucun protocole')
args = p.parse_args()
m = manifeste()
catalogue()
if args.operation == 'lire':
    nom = 'matheval' if args.composant == 'memoire' else args.composant
    if nom is not None and nom not in m['sources']:
        p.error('Composant hors périmètre')
    print(json.dumps(m['sources'].get(nom, m['sources']), ensure_ascii=False, indent=2))
    print((RACINE / 'assemblage/REPRISE.md').read_text())
else:
    ancien = RACINE / 'coordination/historique/REGISTRE-20261011.org'
    import hashlib
    if hashlib.sha256(ancien.read_bytes()).hexdigest() != 'e755167b9424288102e8089cc020de890edf3e7b1ee6f219c0a3182922fb3874':
        raise ValueError('Archive historique modifiée')
    print('Contrat central, manifeste et archive exacte valides ; aucun acquittement requis.')
