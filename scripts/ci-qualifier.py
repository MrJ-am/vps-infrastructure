"""Exécuter les suites centrales affectées, une construction par candidat.

Les reçus Codex restent locaux : le runner rejoue les seules suites sélectionnées.
Ni ce script ni un reçu ne déclenchent une publication ou n'attestent la production.
"""
import json
import os
from pathlib import Path
import subprocess
from assemblage import RACINE, catalogue, chemins_sources, changements_assemblage,selection,manifeste,verifier_sources

sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
verifier_sources(sources,manifeste(),exact=True)
suites=catalogue()
choisis=selection(changements_assemblage(os.environ.get('MRJAM_COMMIT_AVANT'),sources),suites)
print(json.dumps({'suites':choisis,'evitees':len(suites)-len(choisis),'recus_locaux_reutilises':False},ensure_ascii=False),flush=True)
fronts={cle for cle,nom in [('vision','vision-interface'),('matheval','matheval-interface'),('logique','logique-interface'),('style','style')] if nom in choisis}
if 'vision-postgresql' in choisis:fronts.add('vision')
if any(suites[n].get('python_profils') for n in choisis):
    profils={p for n in choisis for p in suites[n].get('python_profils',[])}
    for profil in sorted(profils):subprocess.run(['python3','scripts/outiller.py','python','--profil',profil],check=True)
    browser=RACINE/'state/outils-python/navigateur/bin'
    if browser.exists():
        os.environ['PATH']=str(browser)+os.pathsep+os.environ['PATH']
        subprocess.run(['python3','-m','playwright','install','chromium'],check=True)
for cle in sorted(fronts):
    subprocess.run(['python3','scripts/outiller.py','npm','--composant',cle],check=True)
    subprocess.run(['python3','scripts/frontends.py','construire','--composant',cle],check=True)
if 'matheval' not in fronts and set(choisis)&{'matheval-pures','matheval-postgresql','vision-postgresql','vision-sql-native','navigateur-mcp'}:
    subprocess.run(['npm','--prefix',sources['matheval']/'server','ci','--ignore-scripts','--no-audit','--no-fund'],check=True)
if 'matheval-navigateur' in choisis:
    subprocess.run([sources['matheval']/'docs/node_modules/.bin/playwright','install','chromium','firefox'],check=True)
if 'style-logo' in choisis:
    subprocess.run([sources['style']/'ateliers/logo/node_modules/.bin/playwright','install','chromium','firefox'],check=True)
# Les suites HTTP Vision exercent ce même artefact ; sa construction qualifie
# Matheval une fois. La fermeture transitive ordonne les suites, sans les doubler.
if set(choisis)&{'vision-postgresql','vision-sql-native','navigateur-mcp','matheval-navigateur'}:
    choisis=sorted(set(choisis)|{'matheval-postgresql'})
ordonnes=[]
def ajouter(n):
    if n in ordonnes:return
    for parent in suites[n].get('dependances',[]):
        if parent in choisis:ajouter(parent)
    ordonnes.append(n)
for n in choisis:ajouter(n)
for nom in ordonnes:
    subprocess.run(['python3','scripts/assemblage.py','tester','--atelier',os.environ['MRJAM_ATELIER'],
                    '--exact','--ci','--suite',nom],check=True)
