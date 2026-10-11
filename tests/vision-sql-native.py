"""Fixture Docker/PG17 isolée, sources SQL réelles, un SBCL neuf de qualification."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'


def verifier():
    env=dict(os.environ)
    for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'): env.pop(k,None)
    nom='mrjam-vision-native-'+uuid.uuid4().hex[:12]
    atelier=Path(os.environ.get('MRJAM_ATELIER',ROOT.parent))
    def docker(*args,input=None):
        return subprocess.run(['docker',*args],input=input,env=env,text=True,capture_output=True,check=True)
    docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432','--env','POSTGRES_HOST_AUTH_METHOD=trust',
           '--env','POSTGRES_DB=vision_native_test','--label','mrjam.qualification=monolithe-20261011',IMAGE)
    try:
        config=json.loads(docker('inspect',nom).stdout)[0]
        bind=config['NetworkSettings']['Ports']['5432/tcp'][0];assert bind['HostIp']=='127.0.0.1'
        for _ in range(100):
            # Le serveur temporaire d'initdb accepte le socket Unix puis redémarre.
            # Attendre son listener TCP final évite de migrer pendant cet arrêt.
            try:docker('exec',nom,'pg_isready','--host=127.0.0.1','-U','postgres','-d','vision_native_test');break
            except subprocess.CalledProcessError:time.sleep(.1)
        else:raise AssertionError('Fixture PostgreSQL non disponible')
        sql='CREATE EXTENSION vector;\n'+''.join(p.read_text()+'\n' for p in sorted((atelier/'vision/migrations').glob('*.sql')))
        sql+=(atelier/'vision/scripts/roles.sql').read_text()
        sql+="""
INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('alice','Alice synthétique'),('bob','Bob synthétique');
INSERT INTO vision_profils(utilisateur) VALUES('alice'),('bob');
INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('alice','Privé Alice','Texte Alice'),('bob','Privé Bob','Texte Bob');
INSERT INTO vision_items(utilisateur,titre,contenu,objectifs,sens) VALUES('alice','Item Alice','Texte Alice',ARRAY['definition'],ARRAY['rappel']),('bob','Item Bob','Texte Bob',ARRAY['definition'],ARRAY['rappel']);
INSERT INTO vision_liens(utilisateur,fiche_id,item_id) VALUES('alice',1,1),('bob',2,2);
"""
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','vision_native_test','--set=ON_ERROR_STOP=1','--file=-',input=sql)
        def literal(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
        dsn=f"host=127.0.0.1 port={bind['HostPort']} user=vision dbname=vision_native_test"
        with tempfile.TemporaryDirectory(prefix='vision-native-sbcl-') as d:
            runner=Path(d)/'verifier.lisp'
            runner.write_text(f"""(load {literal(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-postgresql {literal(os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'))})
(load {literal(ROOT/'tests/vision-sql-native.lisp')})
(vision-sql-native:verifier {literal(dsn)})
""")
            subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)
    finally:docker('rm','--force',nom)


if __name__=='__main__':verifier()
