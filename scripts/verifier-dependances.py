"""Refuser les ajouts npm/ASDF non inventoriés avant toute installation/build."""
import json
from pathlib import Path
import re
import sys
from assemblage import chemins_sources,manifeste,empreinte


def verifier():
    racine=Path(__file__).resolve().parents[1]
    inventory=json.loads((racine/'assemblage/dependances.json').read_text())
    sources=chemins_sources()
    for entre in inventory['npm_verrouille']:
        base=sources[entre['composant']]
        lock=base/entre['lock']
        if empreinte(lock.read_bytes())!=entre['sha256']:
            raise ValueError('Lock npm modifié sans autorisation inventoriée : '+entre['composant']+'/'+entre['lock'])
        package=json.loads(lock.with_name('package.json').read_text())
        for cle,inventaire in [('dependencies','bibliotheques'),('devDependencies','developpement_test')]:
            if package.get(cle,{})!=entre['directes'][inventaire]:
                raise ValueError('Dépendance directe npm différente : '+entre['composant']+'/'+cle)
    asds=[p for base in sources.values() for p in base.glob('*.asd')]
    declared=set()
    for p in asds:
        declared.update(re.findall(r'\(asdf:defsystem\s+"([^"]+)"',p.read_text(),re.I))
    for p in asds:
        texte=p.read_text()
        for contenu in re.findall(r':depends-on\s*\(([^)]*)\)',texte,re.I):
            dependencies=re.findall(r'"([^"]+)"',contenu)
            if re.sub(r'"[^"]+"','',contenu).strip():raise ValueError('Déclaration ASDF non analysable : '+p.name)
            if any(d not in declared for d in dependencies):raise ValueError('Bibliothèque tierce ASDF non autorisée : '+p.name)
    print('Dépendances directes npm et graphe interne ASDF conformes à l’inventaire verrouillé.')


if __name__=='__main__':
    try:verifier()
    except (ValueError,KeyError) as e:print(str(e),file=sys.stderr);sys.exit(1)
