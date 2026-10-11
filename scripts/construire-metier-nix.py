"""Construction centrale avec le Nixpkgs exact du VPS, sans données/secrets.

Nix doit déjà être fourni par l'environnement d'ingénierie approuvé.
Le téléchargement officiel est vérifié avant extraction dans un répertoire privé.
La production n'est ni contactée ni activée ; le candidat reste local au runner.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
from assemblage import RACINE,manifeste,chemins_sources,verifier_sources,compilation_entrees

def construire(outils_seulement=False):
    m=manifeste();sources=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))
    verifier_sources(sources,m,exact=True)
    if not shutil.which('nix-build'):raise ValueError('Nix approuvé requis ; aucune installation implicite')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RACINE,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=RACINE):
        raise ValueError('Le build Nix exige les sources infrastructure commitées')
    inputs=compilation_entrees(sources);cible=m['toolchain']['production']
    if cible['source_url']!='https://api.github.com/repos/NixOS/nixpkgs/tarball/'+cible['nixpkgs_revision']:
        raise ValueError('Source officielle Nixpkgs requise')
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','NIX_REMOTE','NIX_SSL_CERT_FILE','SSL_CERT_FILE')}
    # Pas de token GitHub, credentials Actions, proxy personnalisé ou .netrc.
    with tempfile.TemporaryDirectory(prefix='mrjam-nix-verrouille-') as d:
        d=Path(d);archive=d/'nixpkgs.tar.gz'
        subprocess.run(['curl','--disable','--fail','--location','--silent','--show-error','--max-time','180',
                        cible['source_url'],'--output',str(archive)],env=env,check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=cible['source_archive_sha256']:
            raise ValueError('Archive Nixpkgs différente du verrou ; ne pas poursuivre')
        with tarfile.open(archive) as t:t.extractall(d,filter='data')
        racines=[p for p in d.iterdir() if p.is_dir()]
        if len(racines)!=1:raise ValueError('Archive Nixpkgs ambiguë')
        def nix_chemin(p):return 'builtins.toPath '+json.dumps(str(p))
        expression=d/'assemblage.nix'
        expression.write_text('let pkgs=import ('+nix_chemin(racines[0])+') {}; in {\n'
            +'metier=import '+str(RACINE/'assemblage/metier.nix')+' { inherit pkgs; '
            +'vision='+nix_chemin(sources['vision'])+'; matheval='+nix_chemin(sources['matheval'])+'; '
            +'revisionInfrastructure='+json.dumps(revision)+'; };\n'
            +'outils=import '+str(RACINE/'assemblage/outils.nix')+' { inherit pkgs; };\n}\n')
        debut=time.monotonic();sorties={}
        for nom in (('outils',) if outils_seulement else ('metier','outils')):
            prefixe=['sudo','env','NIX_REMOTE=local'] if os.environ.get('GITHUB_ACTIONS')=='true' else []
            sorties[nom]=subprocess.check_output([*prefixe,'nix-build',str(expression),'--attr',nom,'--no-out-link',
              '--max-jobs','1','--cores','2'],env=env,text=True).strip()
            if not sorties[nom].startswith('/nix/store/') or '\n' in sorties[nom]:raise ValueError('Sortie Nix ambiguë')
        if compilation_entrees(sources)!=inputs:raise ValueError('Sources modifiées pendant le build Nix')
        p={'format':1,'source_revision':revision,'nixpkgs_revision':cible['nixpkgs_revision'],
           'sorties_nix':sorties,'publication_autorisee':False}
        if not outils_seulement:
            destination=RACINE/'state/artefacts/mrjam-metier';destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(Path(sorties['metier'])/'bin/mrjam-metier',destination);destination.chmod(0o700)
            p.update(artefact_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
              taille_octets=destination.stat().st_size,construction_secondes=round(time.monotonic()-debut,4),
              compilation=json.loads((Path(sorties['metier'])/'share/mrjam/compilation.json').read_text()),
              sources_lisp_sha256=inputs)
            preparation=destination.with_suffix('.construction-nix.json');preparation.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
        outils=Path(sorties['outils'])
        configuration={'PATH':str(outils/'sbcl/bin')+os.pathsep+os.environ['PATH'],
          'SBCL':str(outils/'sbcl/bin/sbcl'),
          'SBCL_HOME':str(outils/'sbcl/lib/sbcl'),
          'MRJAM_LIBCRYPTO':str(outils/'openssl/lib/libcrypto.so.3'),
          'MRJAM_LIBPQ':str(outils/'postgresql/lib/libpq.so.5'),
          'MRJAM_LIBSQLITE':str(outils/'sqlite/lib/libsqlite3.so.0'),
          'MRJAM_CURL':str(outils/'curl/bin/curl')}
        if not outils_seulement:configuration['MRJAM_CONSTRUCTION_NIX']=str(preparation)
        if any('\n' in valeur for valeur in configuration.values()):raise ValueError('Environnement ambigu')
        (RACINE/'state').mkdir(exist_ok=True)
        (RACINE/'state/outils-nix.json').write_text(json.dumps(configuration,ensure_ascii=False,indent=2)+'\n')
        if os.environ.get('GITHUB_ENV'):
            with open(os.environ['GITHUB_ENV'],'a') as f:
                for cle,valeur in configuration.items():f.write(cle+'='+valeur+'\n')
        print(json.dumps({k:v for k,v in p.items() if k!='sources_lisp_sha256'},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outils-seulement',action='store_true');a=p.parse_args()
    construire(a.outils_seulement)
