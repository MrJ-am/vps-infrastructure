"""Contrats métier historiques sur le serveur commun, PostgreSQL jetable et
vecteurs de transport synthétiques. Le vrai modèle et OIDC ont leurs propres
qualifications : aucune authentification réelle n'est revendiquée ici.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemblage import compilation_entrees,chemins_sources
from http_fixture import entree
IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'


def qualifier(sources,executable,navigateur=False):
    sources=Path(sources).resolve();executable=Path(executable).resolve()
    r=json.loads(executable.with_suffix('.qualification.json').read_text())
    assert r['artefact_sha256']==hashlib.sha256(executable.read_bytes()).hexdigest()
    assert r['sources_lisp_sha256']==compilation_entrees(chemins_sources(atelier=os.environ.get('MRJAM_ATELIER')))
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','PLAYWRIGHT_BROWSERS_PATH','CI','SBCL_HOME')}
    nom='mrjam-vision-reference-'+uuid.uuid4().hex[:12]
    def docker(*args,input=None):
        return subprocess.run(['docker',*args],input=input,env=env,text=True,capture_output=True,check=True).stdout
    docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432','--env','POSTGRES_HOST_AUTH_METHOD=trust',
           '--env','POSTGRES_DB=vision_interface_test','--mount','type=bind,src='+str(sources)+',dst=/fixture,readonly',IMAGE)
    try:
        bind=json.loads(docker('inspect',nom))[0]['NetworkSettings']['Ports']['5432/tcp'][0]
        assert bind['HostIp']=='127.0.0.1'
        for _ in range(100):
            try:docker('exec',nom,'pg_isready','--host=127.0.0.1','-U','postgres');break
            except subprocess.CalledProcessError:time.sleep(.1)
        else:raise AssertionError('PostgreSQL Vision indisponible')
        with tempfile.TemporaryDirectory(prefix='vision-reference-') as tmp:
            tmp=Path(tmp);socket_path=tmp/'metier.sock'
            psql=tmp/'psql'
            psql.write_text('#!/usr/bin/env python3\nimport os,subprocess,sys\n'
                +'args=[a.replace('+repr(str(sources))+',"/fixture") for a in sys.argv[1:]]\n'
                +'c=["docker","exec","-i","--workdir","/fixture",'+repr(nom)+',"env","PGHOST=127.0.0.1","PGPORT=5432","PGDATABASE=vision_interface_test","PGUSER="+os.environ.get("PGUSER","postgres"),"psql",*args]\n'
                +'sys.exit(subprocess.run(c).returncode)\n');psql.chmod(0o700)
            env.update(PATH=str(tmp)+os.pathsep+env['PATH'],PGHOST='127.0.0.1',PGPORT=bind['HostPort'],
                       PGDATABASE='vision_interface_test',PGUSER='postgres',PGPASSWORD='',VISION_PSQL=str(psql))
            def run(command):subprocess.run(command,cwd=sources,env=env,check=True)
            run(['psql','-X','--set=ON_ERROR_STOP=1','--command','CREATE EXTENSION vector'])
            run(['sh','scripts/migrate.sh']);run(['sh','scripts/migrate.sh'])
            run(['psql','-X','--set=ON_ERROR_STOP=1','--file','scripts/roles.sql'])
            run(['psql','-X','--set=ON_ERROR_STOP=1','--command',"UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,responsable='Fixture',contact='operator@example.test',pays_hebergement='Test',notice_version='fixture',budget_octets=100000000000"])
            # Les anciennes campagnes inventent des sujets synthétiques. Leur
            # admission est une fixture explicite, jamais une capacité du serveur.
            import psycopg
            root=psycopg.connect(host='127.0.0.1',port=bind['HostPort'],dbname='vision_interface_test',user='postgres',autocommit=True)
            def inscrire(headers):
                user=headers.get('X-Mrj-User')
                if user and headers.get('X-Vision-Authenticated')=='1' and re.fullmatch('[A-Za-z0-9_-]{1,100}',user):
                    with root.cursor() as c:
                        c.execute('INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user,user))
            with socket.socket() as s:s.bind(('127.0.0.1',0));port_embedding=s.getsockname()[1]
            provider=subprocess.Popen([sys.executable,'-c',
                'import sys;sys.path[:0]=["tests","scripts"];from embeddings_fixture import Doublure;from embeddings import servir;servir(Doublure(),'+str(port_embedding)+')'],
                cwd=sources,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            runtime={k:v for k,v in env.items() if k in ('PATH','HOME','LANG','LC_ALL')}
            runtime.update(MRJAM_LIBCRYPTO=os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'),
                MRJAM_LIBPQ=os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'),
                VISION_DSN=f"host=127.0.0.1 port={bind['HostPort']} user=vision dbname=vision_interface_test",
                VISION_DOCUMENT_ROOT=str(sources/'docs'),VISION_EMBEDDINGS_URL=f'http://127.0.0.1:{port_embedding}/embedding',
                VISION_PUBLIC_MCP_URL='https://exemple.test/vision/mcp',MATHEVAL_BANK_VERSION='fixture',
                MATHEVAL_DSN=f"host=127.0.0.1 port={bind['HostPort']} user=vision dbname=vision_interface_test",MATHEVAL_ORIGIN='https://example.test',
                MRJAM_SOCKET=str(socket_path),MRJAM_INGRESS_UID=str(os.geteuid()))
            env['VISION_EMBEDDINGS_URL']=runtime['VISION_EMBEDDINGS_URL']
            with (tmp/'serveur.log').open('wb') as log:p=subprocess.Popen([executable],env=runtime,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    if socket_path.exists():break
                    if p.poll() is not None:raise AssertionError('Serveur commun Vision refusé')
                    time.sleep(.05)
                else:raise AssertionError('Socket Vision absent')
                # La campagne navigateur historique réserve 39000–39999 ;
                # garder son garde-fou, sans réutiliser un listener existant.
                with entree(socket_path,sources/'interface/dist',prefix='',service='vision',preparer=inscrire,port=39003 if navigateur else 0) as origin:
                    env['VISION_DATABASE_TEST_PORT']=origin.rsplit(':',1)[1]
                    if navigateur:run(['python3','interface/tests/refonte.py','--port-serveur',env['VISION_DATABASE_TEST_PORT']])
                    else:
                        for fichier in ['check_refonte.py','check_cloture.py','check_creation.py','check_autonomie.py']:
                            run(['python3','tests/'+fichier])
                        run(['psql','-X','--set=ON_ERROR_STOP=1','--file','tests/refonte.sql'])
                        run(['python3','tests/check_migration.py'])
                        run(['psql','-X','--set=ON_ERROR_STOP=1','--file','tests/coherence_cloture.sql'])
                        run(['python3','tests/comptes.py'])
                        run(['python3','tests/mesures.py'])
            finally:
                root.close();p.terminate();provider.terminate()
                for child in (p,provider):
                    try:child.wait(timeout=12)
                    except subprocess.TimeoutExpired:child.kill();child.wait();raise AssertionError('Arrêt fixture non borné')
        print('Vision : campagne historique sur le binaire commun ; rôles réels, données et sujets synthétiques.')
    finally:docker('rm','--force',nom)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sources',default=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))['vision']);p.add_argument('--executable',default=ROOT/'state/artefacts/mrjam-metier');p.add_argument('--navigateur',action='store_true')
    a=p.parse_args();source=Path(a.sources).resolve()
    parent=ROOT/'state/ateliers-vision';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='reference-',dir=parent) as tmp:
        atelier=Path(tmp)/'source'
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
        subprocess.run(['git','worktree','add','--quiet','--detach',atelier,revision],cwd=source,check=True)
        try:
            if a.navigateur:
                from frontends import reutiliser_candidat
                from assemblage import manifeste
                locaux=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'));locaux['vision']=atelier
                reutiliser_candidat('vision',locaux,manifeste())
            qualifier(atelier,a.executable,a.navigateur)
        except Exception:
            if (atelier/'interface/rapports').is_dir():
                cible=ROOT/'state/rapports-frontends'/('vision-reference-'+uuid.uuid4().hex[:12])
                shutil.copytree(atelier/'interface/rapports',cible)
                print('Diagnostics privés : '+str(cible.relative_to(ROOT)),flush=True)
            raise
        finally:subprocess.run(['git','worktree','remove','--force',atelier],cwd=source,check=True)
