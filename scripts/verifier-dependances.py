"""Refuser les ajouts npm/ASDF non inventoriés avant toute installation/build."""
import json
from pathlib import Path
import re
import sys
import os
from assemblage import chemins_sources,manifeste,empreinte


def verifier_outils_mcp(racine, inventory):
    declaration=inventory['outillage_mcp_autorise']
    p=racine/declaration['fichier']
    if p.is_symlink() or not p.resolve().is_relative_to(racine/'assemblage/outils'):
        raise ValueError('Lock MCP extérieur')
    lock=json.loads(p.read_text())
    toolchain=manifeste(racine)['toolchain']['qualification_locale']
    for cle in ('sbcl','asdf','nixpkgs_revision'):
        if lock[cle]!=toolchain[cle]:raise ValueError('Toolchain MCP différente : '+cle)
    attendus={'cl-mcp':'cl-ai-project/cl-mcp','cl-tron-mcp':'Alba-Intelligence/cl-tron-mcp',
              'quicklisp-client':'quicklisp/quicklisp-client'}
    if {o['nom']:o['depot'] for o in lock['outils']}!=attendus:
        raise ValueError('Projet MCP hors autorisation')
    for outil in lock['outils']:
        if (not re.fullmatch('[a-f0-9]{40}',outil['revision'])
            or outil['url']!='https://api.github.com/repos/'+outil['depot']+'/tarball/'+outil['revision']
            or not re.fullmatch('[a-z0-9]{52}',outil['nix_sha256'])):
            raise ValueError('Source MCP non verrouillée')
    noms={b['name'] for b in lock['bibliotheques']}
    if len(noms)!=len(lock['bibliotheques']) or 'cl-harness' in noms:
        raise ValueError('Graphe MCP invalide')
    for b in lock['bibliotheques']:
        source_nix_patchee=(b['name']=='swank' and b['version']=='2.29.1'
                           and b['url'] is None and b['src'].endswith('-sbcl-swank-2.29.1-build-patched'))
        if (not b['version'] or not (source_nix_patchee or (b['url'] or '').startswith('https://'))
            or not re.fullmatch(r'/nix/store/[a-z0-9]{32}-[^/]+',b['src'])
            or not b['nar_sha256'].startswith('sha256:')
            or not b['licences_asd'] or not set(b['deps']).issubset(noms)):
            raise ValueError('Transitive MCP non inventoriée : '+b['name'])
    for patch in lock.get('adaptations',[]):
        fichier=racine/patch['fichier']
        if fichier.is_symlink() or empreinte(fichier.read_bytes())!=patch['sha256']:
            raise ValueError('Patch MCP différent de son audit')


def verifier():
    racine=Path(__file__).resolve().parents[1]
    inventory=json.loads((racine/'assemblage/dependances.json').read_text())
    verifier_outils_mcp(racine,inventory)
    sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    for profile in inventory.get('python_profils',{}).values():
        p=racine/profile['fichier']
        if not p.resolve().is_relative_to(racine/'assemblage/python') or p.is_symlink() or empreinte(p.read_bytes())!=profile['sha256']:
            raise ValueError('Lock Python central différent de son inventaire')
        for v in profile['paquets']:
            if 'url' in v and not (v['nom']=='torch' and re.fullmatch(r'https://download\.pytorch\.org/whl/cpu/torch-2\.6\.0(?:%2B|\+)cpu-cp312-cp312-linux_x86_64\.whl',v['url'])):
                raise ValueError('URL de dépendance hors du composant CPU déjà approuvé')
        attendu={(v['nom']+' @ '+v['url'] if 'url' in v else v['nom']+'=='+v['version'])+' --hash=sha256:'+v['sha256'] for v in profile['paquets']}
        reels={l for l in p.read_text().splitlines() if l and not l.startswith('#')}
        if reels!=attendu:raise ValueError('Paquets Python centraux différents de leur inventaire')
    for entre in inventory['npm_verrouille']:
        base=sources[entre['composant']]
        lock=base/entre['lock']
        if empreinte(lock.read_bytes())!=entre['sha256']:
            raise ValueError('Lock npm modifié sans autorisation inventoriée : '+entre['composant']+'/'+entre['lock'])
        package=json.loads(lock.with_name('package.json').read_text())
        for cle,inventaire in [('dependencies','bibliotheques'),('devDependencies','developpement_test')]:
            if package.get(cle,{})!=entre['directes'][inventaire]:
                raise ValueError('Dépendance directe npm différente : '+entre['composant']+'/'+cle)
    # Un nouveau manifeste ne doit pas échapper au contrôle parce qu'il n'a
    # simplement pas été ajouté à la liste. Les entrées sont exclusivement Git.
    import subprocess
    declares={(e['composant'],e['lock']) for e in inventory['npm_verrouille']}
    declarations_python={(e['composant'],e['fichier']):e for e in inventory.get('python_requirements',[])}
    declarations_elm={(e['composant'],e['fichier']):e for e in inventory.get('elm_verrouille',[])}
    for nom,base in sources.items():
        fichiers=subprocess.check_output(['git','ls-files'],cwd=base,text=True).splitlines()
        for relatif in fichiers:
            p=base/relatif
            if p.name=='package-lock.json' and (nom,relatif) not in declares:
                raise ValueError('Lock npm hors inventaire : '+nom+'/'+relatif)
            if p.name=='package.json' and not p.with_name('package-lock.json').is_file():
                raise ValueError('Manifeste npm sans lock : '+nom+'/'+relatif)
            declaration=(declarations_python.get((nom,relatif)) if p.name.startswith('requirements') and p.suffix=='.txt'
                         else declarations_elm.get((nom,relatif)) if p.name=='elm.json' else False)
            if declaration is None or declaration and empreinte(p.read_bytes())!=declaration['sha256']:
                raise ValueError('Dépendance Python/Elm hors inventaire : '+nom+'/'+relatif)
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
    print('Npm, requirements Python, profils transitifs, Elm et graphe interne ASDF conformes à l’inventaire verrouillé.')


if __name__=='__main__':
    try:verifier()
    except (ValueError,KeyError) as e:print(str(e),file=sys.stderr);sys.exit(1)
