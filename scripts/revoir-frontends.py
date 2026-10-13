"""Contrôle Elm canonique, sur applications et sources partagées réellement consommées.

Une configuration centrale ; aucun filtre de règles, fix, suppression ou exclusion.
La préparation du cache des dépendances est explicite et séparée de la qualification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from assemblage import RACINE, chemins_sources, manifeste
from frontends import cache_style, sha


CONFIG=RACINE/'assemblage/elm-review'


def outils():
    lock=json.loads((CONFIG/'outils.lock.json').read_text())
    store=(RACINE/'state/outils-sources/elm-review-store.txt').read_text().strip()
    if store!=lock['cli']['store']:raise ValueError('elm-review différent du paquet Nix audité')
    exe=Path(store)/'bin/elm-review'
    if not str(exe).startswith('/nix/store/') or not exe.is_file():
        raise ValueError('elm-review Nix verrouillé non installé')
    compiler=chemins_sources()['matheval']/'docs/node_modules/.bin/elm'
    if not compiler.is_file():raise ValueError('Compilateur Elm existant indisponible')
    env=dict(os.environ,ELM_HOME=str(RACINE/'state/elm-home'))
    return [str(exe),'--config',str(CONFIG),'--compiler',str(compiler),'--offline','--unsuppress','--report=json'],env


def projet(composant,sources,m,destination,projet_elm=None):
    base=sources[composant]
    fichier=projet_elm or {'vision':'interface/elm.json','matheval':'docs/elm.json','logique':'elm.json','style':'elm.json'}[composant]
    elm=base/fichier;d=json.loads(elm.read_text());paths=[]
    if composant=='style':commun=base/'src'
    else:
        edge=m['frontends'][composant]
        raw=(base/edge['verrou_style']).read_bytes();lock=json.loads(raw)
        if sha(raw)!=edge['sha256'] or lock['revision']!=edge['revision_style']:
            raise ValueError('Style différent du manifeste central')
        commun=cache_style(sources['style'],edge['revision_style'])/'src'
    shutil.copytree(commun,destination/'commun')
    paths.append('commun')
    for i,rel in enumerate(d['source-directories']):
        # Remplacer seulement la dépendance style exacte, pas ignorer des
        # sources applicatives portant des noms similaires.
        if rel in ('.dependances/style-mrjam/src','.style-mrjam/src','.cache/style-mrjam/src') or (composant=='style' and (elm.parent/rel).resolve()==(base/'src').resolve()):
            continue
        src=elm.parent/rel
        if not src.is_dir():raise ValueError('Source Elm absente : '+str(src))
        dest='application/'+str(i)
        shutil.copytree(src,destination/dest);paths.append(dest)
    d['source-directories']=paths
    tests=elm.parent/'tests'
    if tests.is_dir():shutil.copytree(tests,destination/'tests')
    (destination/'elm.json').write_text(json.dumps(d,indent=2)+'\n')


def verifier(composant,sources=None,m=None,*,fixture=None,projet_elm=None):
    if composant=='style' and not fixture and not projet_elm:
        verifier(composant,sources,m,projet_elm='ateliers/logo/elm.json')
    cmd,env=outils()
    parent=RACINE/'state/review-frontends';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=composant+'-',dir=parent) as temp:
        stage=Path(temp)
        if fixture:
            if not fixture.resolve().is_relative_to(RACINE/'tests/fixtures'):
                raise ValueError('Fixture de qualification hors infrastructure')
            shutil.copytree(fixture,stage,dirs_exist_ok=True)
        else:
            projet(composant,sources or chemins_sources(),m or manifeste(),stage,projet_elm)
        r=subprocess.run(cmd,cwd=stage,env=env,capture_output=True,text=True)
        # Rapport complet local et borné ; pas de dump CI ou contenu métier.
        nom=fixture.name if fixture else composant+('-logo' if projet_elm=='ateliers/logo/elm.json' else '')
        report=parent/(nom+'.json');report.write_text(r.stdout)
        if r.returncode:
            try:
                data=json.loads(r.stdout)
                if data.get('type')=='review-errors':
                    errors=data.get('errors',[])
                    count=sum(len(f.get('errors',[])) for f in errors)
                    print(f'{composant} : elm-review refuse la qualification ({count} violations). Rapport : {report}')
                else:
                    print(f'{composant} : contrôle non exécuté avec succès ({data.get("type")}) ; rapport : {report}')
            except json.JSONDecodeError:
                print((r.stderr or r.stdout)[-3500:])
            raise ValueError('Contrôle Elm échoué : '+composant)
        if not fixture:
            spec=__import__('importlib.util',fromlist=['spec_from_file_location'])
            loader=spec.spec_from_file_location('revoir_ressources',RACINE/'scripts/revoir-ressources.py')
            resources=spec.module_from_spec(loader);loader.loader.exec_module(resources)
            resources.verifier(composant,sources or chemins_sources())
        print(composant+' : elm-review réussi sur toutes les sources assemblées.')


def verifier_interne(nom):
    """Consommateur interne, avec le même socle verrouillé et toutes les règles."""
    sources=chemins_sources();m=manifeste();edge=m['frontends_infrastructure'][nom]
    commun=cache_style(sources['style'],edge['revision_style'])/'src'
    cmd,env=outils();parent=RACINE/'state/review-frontends';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=nom+'-',dir=parent) as temp:
        stage=Path(temp)
        shutil.copytree(commun,stage/'commun')
        shutil.copytree(RACINE/('interface-'+nom)/'src',stage/'src')
        shutil.copytree(RACINE/('interface-'+nom)/'tests',stage/'tests')
        d=json.loads((RACINE/('interface-'+nom)/'elm.json').read_text());d['source-directories']=['src','commun']
        (stage/'elm.json').write_text(json.dumps(d)+'\n')
        r=subprocess.run(cmd,cwd=stage,env=env,capture_output=True,text=True)
        (parent/(nom+'.json')).write_text(r.stdout)
        if r.returncode:raise ValueError('elm-review '+nom+' refusé ; rapport state/review-frontends/'+nom+'.json')
    import importlib.util
    spec=importlib.util.spec_from_file_location('ressources_log',RACINE/'scripts/revoir-ressources.py')
    resources=importlib.util.module_from_spec(spec);spec.loader.exec_module(resources)
    resources.verifier(nom,dict(sources,**{nom:RACINE}))
    print(nom+' : toutes les sources communes et applicatives, amorçage et interopérabilité contrôlés.')


def verifier_log():
    """API historique conservée pour les qualifieurs Log déjà publiés."""
    return verifier_interne('log')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--composant',choices=['vision','matheval','logique','style','log','audition'],action='append')
    p.add_argument('--fixture',type=Path,help='Projet synthétique complet ; mêmes règles sans exclusions')
    args=p.parse_args()
    for cle in args.composant or ['style','vision','matheval','logique']:
        if cle in ('log','audition'):verifier_interne(cle)
        else:verifier(cle,fixture=args.fixture)


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError) as e:
        print(e);raise SystemExit(1)
