"""Construction centrale des interfaces avec leurs sources communes exactes.

Les caches sont des entrées de construction vérifiées, jamais des sources éditées.
Aucune installation, publication ou écriture de données depuis cette commande.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import uuid

from assemblage import RACINE, chemins_sources, manifeste, verifier_sources


def sha(data): return hashlib.sha256(data).hexdigest()


def contenus(root,provenance_cache=False):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('Lien interdit dans un cache de sources')
        if p.is_file() and not (provenance_cache and p==root/'.provenance-centrale.json'):
            result[str(p.relative_to(root))] = sha(p.read_bytes())
    return result


def sortie_frontend(cle):
    return {'vision':'interface/dist','matheval':'docs/site','logique':'.cache/site-complet','style':'.pages'}[cle]


def enregistrer_candidat(cle, sources, m):
    parent = RACINE / 'state/frontends-candidats'
    parent.mkdir(parents=True, exist_ok=True)
    candidat = parent / (cle+'-'+m['sources'][cle]['revision'][:12]+'-'+uuid.uuid4().hex[:8])
    sorties={'galerie':'public','atelier':'ateliers/logo/dist','publication':'.pages'} if cle=='style' else {'publication':sortie_frontend(cle)}
    if cle=='style':
        candidat.mkdir()
        for nom,path in sorties.items():shutil.copytree(sources[cle]/path,candidat/nom)
    else:shutil.copytree(sources[cle] / sortie_frontend(cle), candidat)
    h = contenus(candidat)
    rapport = {'composant':cle,'revision':m['sources'][cle]['revision'],'construction':'reussie',
               'publication':False,'candidat':str(candidat.relative_to(RACINE)),'fichiers':h,
               'ensemble_sha256':sha(json.dumps(h,sort_keys=True).encode()),'sorties':sorties}
    candidat.with_suffix('.construction.json').write_text(json.dumps(rapport,indent=2)+'\n')
    (parent/('dernier-'+cle+'.json')).write_text(json.dumps(rapport,indent=2)+'\n')
    print(json.dumps({k:v for k,v in rapport.items() if k!='fichiers'},ensure_ascii=False))
    return rapport


def reutiliser_candidat(cle, sources, m):
    rapport=json.loads((RACINE/'state/frontends-candidats'/('dernier-'+cle+'.json')).read_text())
    if rapport['composant']!=cle or rapport['revision']!=m['sources'][cle]['revision']:
        raise ValueError('Candidat différent des sources verrouillées')
    candidat=RACINE/rapport['candidat']
    if not candidat.resolve().is_relative_to(RACINE/'state/frontends-candidats') or candidat.is_symlink():
        raise ValueError('Candidat hors espace central')
    if contenus(candidat)!=rapport['fichiers']:raise ValueError('Candidat modifié après construction')
    if cle=='style':
        if rapport.get('sorties')!={'galerie':'public','atelier':'ateliers/logo/dist','publication':'.pages'}:
            raise ValueError('Candidat style incomplet ; galerie et atelier doivent aussi être conservés')
        for nom,path in rapport['sorties'].items():
            sortie=sources[cle]/path
            if sortie.exists():shutil.rmtree(sortie)
            shutil.copytree(candidat/nom,sortie)
    else:
        sortie=sources[cle]/sortie_frontend(cle)
        if sortie.exists():shutil.rmtree(sortie) # seulement dans le worktree neuf créé par cet appel
        shutil.copytree(candidat,sortie)
    if cle=='logique':shutil.copytree(candidat,sources[cle]/'dist')
    return rapport


def tester_frontend(cle,sources,caches,campagne='base'):
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','ELM_HOME',
        'PLAYWRIGHT_BROWSERS_PATH','CHROMIUM','PLAYWRIGHT_CHROMIUM_EXECUTABLE','CI',
        'MRJAM_TEST_FILTER','MRJAM_TEST_PROJECT','MRJAM_TEST_REPEAT','MRJAM_TEST_DIAGNOSTIC')}
    env['STYLE_MRJAM_SOURCE']=str(caches.get(cle,sources['style']))
    commandes={
        'vision':[['npm','--prefix','interface','run','verifier'],['npm','--prefix','interface','test'],
                  ['python3','interface/tests/graphisme.py'],['python3','interface/tests/vitrine.py'],
                  ['python3','interface/tests/multiutilisateur.py']],
        'matheval':[['npm','--prefix','docs','run','check:data'],['npm','--prefix','docs','run','test:data'],
                    ['python3','-m','unittest','discover','-s','docs/tests','-p','test_published_site.py'],
                    ['node','docs/scripts/test-survey.cjs'],['npm','--prefix','docs','run','test:construction'],
                    ['npm','--prefix','docs','run','test:logic']],
        'logique':[['npm','run','test:interface'],['npm','run','test:atelier:interface'],['npm','run','test:typographie']],
        'style':[['node_modules/.bin/elm-format','src','exemples','--validate'],['python3','scripts/verifier-identite.py'],
                 ['python3','-m','unittest','discover','-s','tests','-p','test_architecture.py'],
                 ['python3','tests/navigation.py'],['python3','tests/documentaire.py'],['python3','tests/blocs.py']]
    }
    if campagne=='unitaire':
        if cle!='logique':raise ValueError('Campagne unitaire définie uniquement pour Logique')
        commandes[cle]=[['npm','test'],['node_modules/.bin/elm-format','src','tests/Check.elm','tests/AtelierCheck.elm','tests/AtelierRegles.elm','--validate']]
    if campagne=='complement':
        commandes={
            'matheval':[['python3',str(RACINE/'tests/matheval-navigateur.py'),'--sources',str(sources['matheval'])]],
            'style':[['npm','--prefix','ateliers/logo','run','format:check'],
                *[['python3','ateliers/logo/scripts/'+p+'.py'] for p in ('analyser-y','analyser-z','construire-z','generate-data')],
                ['ateliers/logo/node_modules/.bin/elm-format','ateliers/logo/src/Echo/ReferenceData.elm','--yes'],
                ['git','diff','--exit-code','--','ateliers/logo/donnees','ateliers/logo/dessins','ateliers/logo/references/Z-reference.svg','ateliers/logo/src/Echo/ReferenceData.elm'],
                ['npm','--prefix','ateliers/logo','test','--','--seed','20261007'],
                ['npm','--prefix','ateliers/logo','run','test:reference'],
                ['npm','--prefix','ateliers/logo','run','test:geometry'],
                ['npm','--prefix','ateliers/logo','run','test:browser'],
                ['npm','--prefix','ateliers/logo','run','test:raster']]
        }
        if cle not in commandes:raise ValueError('Aucune campagne complémentaire pour ce composant')
        if cle=='style':
            env['PATH']=str(RACINE/'state/outils-python/logo/bin')+os.pathsep+env['PATH']
            # Les analyseurs d'origine attendent le dossier de l'atelier.
            for commande in commandes[cle]:
                if commande[0]=='python3' and commande[1].startswith('ateliers/logo/scripts/'):
                    commande[1]=commande[1].removeprefix('ateliers/logo/')
                    subprocess.run(commande,cwd=sources[cle]/'ateliers/logo',env=env,check=True)
                else:subprocess.run(commande,cwd=sources[cle],env=env,check=True)
            return
    for commande in commandes[cle]:subprocess.run(commande,cwd=sources[cle],env=env,check=True)


def cache_style(source, revision):
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Révision de style non verrouillée')
    # Aucun fetch implicite : le checkout central lit les révisions nécessaires.
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', revision,
                                       'src', 'public', 'identite.json', 'elm.json'])
    parent = RACINE / 'state/sources-style'
    parent.mkdir(parents=True, exist_ok=True)
    cible = parent / revision
    with tempfile.TemporaryDirectory(prefix='style-', dir=parent) as tmp:
        stage = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            membres = tar.getmembers()
            if len(membres) > 2000 or sum(m.size for m in membres) > 64*1024*1024:
                raise ValueError('Archive de style hors limites')
            for m in membres:
                path = Path(m.name)
                if path.is_absolute() or '..' in path.parts or not (m.isdir() or m.isfile()):
                    raise ValueError('Archive de style refusée')
            tar.extractall(stage, filter='data')
        attendu = contenus(stage)
        if cible.exists():
            if cible.is_symlink() or contenus(cible,provenance_cache=True) != attendu:
                raise ValueError('Cache de style modifié ; préserver et examiner le travail concurrent')
        else:
            shutil.copytree(stage, cible)
        (cible / '.provenance-centrale.json').write_text(json.dumps(
            {'depot': 'MrJ-am/style-mrjam', 'revision': revision, 'archive_sha256': sha(archive),
             'fichiers': attendu}, sort_keys=True) + '\n')
    return cible


def copier_cache(source, cible):
    if cible.exists():
        if cible.is_symlink() or contenus(cible,provenance_cache=True) != contenus(source,provenance_cache=True):
            raise ValueError('Cache consommateur différent ; aucun nettoyage automatique')
    else:
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, cible)


def preparer(sources, m):
    verifier_sources(sources, m, exact=True)
    caches = {}
    for cle, edge in m['frontends'].items():
        raw = (sources[cle] / edge['verrou_style']).read_bytes()
        lock = json.loads(raw)
        if sha(raw) != edge['sha256'] or lock['revision'] != edge['revision_style'] or edge['origine_style'] != 'MrJ-am/style-mrjam':
            raise ValueError('Contrat de style différent du manifeste central')
        caches[cle] = cache_style(sources['style'], edge['revision_style'])
    # Le cache Logique est déjà prévu par le composant. Aucun miroir externe.
    copier_cache(caches['logique'], sources['logique'] / '.cache/style-mrjam')
    police = sources['logique'] / '.cache/signature/web'
    identite = json.loads((caches['logique'] / 'identite.json').read_text())
    for nom, attendu in identite['ressources_externes'].items():
        if nom not in ('web/EchoPoint.woff2', 'web/MrJamSignature.woff2'):
            raise ValueError('Nouvelle ressource d’identité non déclarée')
        data = (sources['signature'] / nom).read_bytes()
        if hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest() != attendu:
            raise ValueError('Police Signature différente du contrat existant')
        police.mkdir(parents=True, exist_ok=True)
        cible = police / Path(nom).name
        if cible.exists():
            if cible.is_symlink() or cible.read_bytes() != data: raise ValueError('Cache typographique modifié')
        else: cible.write_bytes(data)
    dependance = sources['vision'] / 'interface/.dependances/style-mrjam'
    copier_cache(caches['vision'], dependance)
    return caches


def construire_dans_atelier(cle, sources, m, caches):
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','ELM_HOME','CI')}
    env['GITHUB_SHA'] = m['sources'][cle]['revision']
    env['STYLE_MRJAM_SOURCE'] = str(caches.get(cle, sources['style']))
    commandes = {
        'vision': [['python3', 'interface/compiler.py', '--style', str(caches['vision'])]],
        'matheval': [['npm', '--prefix', 'docs', 'run', 'build:main']],
        'logique': [['npm', 'run', 'build'], ['npm', 'run', 'preparer:identite']],
        'style': [['npm', 'run', 'compiler'], ['npm', '--prefix', 'ateliers/logo', 'run', 'build'],
                  ['node', 'scripts/construire-pages.mjs']]
    }
    for commande in commandes[cle]: subprocess.run(commande, cwd=sources[cle], env=env, check=True)
    return enregistrer_candidat(cle,sources,m)


def construire(cle, sources, m,qualification=False,campagne='base'):
    # Les générateurs écrivent parfois dans des fichiers suivis. Ils travaillent
    # sur un checkout temporaire propre, pas dans la bibliothèque partagée.
    parent = RACINE / 'state/ateliers-frontends'
    parent.mkdir(parents=True, exist_ok=True)
    verifier_sources(sources, m, exact=True)
    with tempfile.TemporaryDirectory(prefix=cle+'-', dir=parent) as tmp:
        atelier = Path(tmp) / 'source'
        subprocess.run(['git', '-C', str(sources[cle]), 'worktree', 'add', '--quiet',
                        '--detach', str(atelier), m['sources'][cle]['revision']], check=True)
        try:
            locaux = dict(sources); locaux[cle] = atelier
            caches = {} if cle=='signature' else preparer(locaux, m)
            for dossier in ['node_modules', 'docs/node_modules', 'interface/node_modules', 'ateliers/logo/node_modules']:
                outils = sources[cle] / dossier
                if outils.is_dir():
                    dest = atelier / dossier
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.symlink_to(outils.resolve(), target_is_directory=True)
            if qualification:
                if cle=='signature':
                    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','PLAYWRIGHT_BROWSERS_PATH')}
                    geometrie=json.loads((atelier/'web/geometry.json').read_text())
                    subprocess.run([RACINE/'state/outils-python/signature/bin/python','tools/build-web.py'],cwd=atelier,env=env,check=True)
                    # Certaines roues fontTools rendent des coordonnées entières
                    # en float. L'objet JSON doit rester identique ; tous les
                    # glyphes, fontes, CSS et HTML restent vérifiés octet par octet.
                    if json.loads((atelier/'web/geometry.json').read_text())!=geometrie:
                        raise ValueError('Géométrie Signature modifiée par la génération')
                    subprocess.run(['git','diff','--exit-code','--','.',':(exclude)web/geometry.json'],cwd=atelier,check=True)
                    subprocess.run([RACINE/'state/outils-python/navigateur/bin/python','tests/browser-copy.py'],cwd=atelier,env=env,check=True)
                    print(json.dumps({'composant':cle,'revision':m['sources'][cle]['revision'],'tests':'reussis','publication':False}))
                    return
                rapport=reutiliser_candidat(cle,locaux,m)
                tester_frontend(cle,locaux,caches,campagne)
                print(json.dumps({'composant':cle,'candidat_sha256':rapport['ensemble_sha256'],
                    'tests':'reussis','campagne':campagne,
                    'diagnostic_specifique':any(os.environ.get(k) for k in ('MRJAM_TEST_FILTER','MRJAM_TEST_PROJECT','MRJAM_TEST_REPEAT','MRJAM_TEST_DIAGNOSTIC')),
                    'construction_reutilisee':True,'publication':False},ensure_ascii=False))
            else:construire_dans_atelier(cle, locaux, m, caches)
        except Exception:
            # Captures et traces de fixtures restent privées et disponibles
            # après la suppression du worktree temporaire de cet appel.
            rapports=RACINE/'state/rapports-frontends'/(cle+'-'+uuid.uuid4().hex[:12])
            for relatif in ('docs/test-results','interface/rapports','ateliers/logo/test-results','ateliers/logo/verification'):
                dossier=atelier/relatif
                if dossier.is_dir():
                    rapports.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(dossier,rapports/relatif)
            if rapports.exists():print('Diagnostics privés conservés : '+str(rapports.relative_to(RACINE)),flush=True)
            raise
        finally:
            if (os.environ.get('MRJAM_TEST_FILTER') or os.environ.get('MRJAM_TEST_DIAGNOSTIC')) and (atelier/'docs/test-results').is_dir():
                rapports=RACINE/'state/rapports-frontends'/(cle+'-diagnostic-'+uuid.uuid4().hex[:12])
                shutil.copytree(atelier/'docs/test-results',rapports)
                print('Trace ciblée conservée : '+str(rapports.relative_to(RACINE)),flush=True)
            # Uniquement le worktree créé dans ce TemporaryDirectory, jamais
            # un checkout de l'utilisateur ou une source concurrente.
            subprocess.run(['git', '-C', str(sources[cle]), 'worktree', 'remove', '--force', str(atelier)], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['preparer', 'construire','qualifier'])
    p.add_argument('--composant', choices=['vision', 'matheval', 'logique', 'style','signature'])
    p.add_argument('--campagne',choices=['base','complement','unitaire'],default='base')
    args = p.parse_args()
    if args.operation != 'preparer' and not args.composant: p.error('--composant requis')
    if args.composant=='signature' and args.operation!='qualifier':p.error('Signature est qualifiée sans nouvelle construction de site')
    sources = chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    m = manifeste()
    if args.operation != 'preparer': construire(args.composant,sources,m,args.operation=='qualifier',args.campagne)
    else:
        preparer(sources, m)
        print('Trois révisions de style et les ressources Signature contrôlées, sans fetch ni publication.')


if __name__ == '__main__': main()
