"""Fixture Docker/PG17 isolée, sources SQL réelles, un SBCL neuf de qualification."""
import json
import os
import shutil
from admission_idp_fixture import IdP
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import importlib.util
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

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
UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,responsable='Qualification',contact='operator@example.test',pays_hebergement='Test',notice_version='notice-test';
INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('alice','Alice synthétique'),('bob','Bob synthétique');
INSERT INTO vision_profils(utilisateur) VALUES('alice'),('bob');
INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('alice','Privé Alice','Texte Alice'),('bob','Privé Bob','Texte Bob');
INSERT INTO vision_items(utilisateur,titre,contenu,objectifs,sens) VALUES('alice','Item Alice','Texte Alice',ARRAY['definition'],ARRAY['rappel']),('bob','Item Bob','Texte Bob',ARRAY['definition'],ARRAY['rappel']);
INSERT INTO vision_liens(utilisateur,fiche_id,item_id) VALUES('alice',1,1),('bob',2,2);
UPDATE vision_gestion.comptes SET administrateur=true WHERE utilisateur='alice';
INSERT INTO vision_gestion.identites(emetteur,sujet,utilisateur) VALUES('https://log.mrj.am/realms/mrjam','sujet-alice','alice'),('https://log.mrj.am/realms/mrjam','sujet-bob','bob');
"""
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','vision_native_test','--set=ON_ERROR_STOP=1','--file=-',input=sql)
        docker('exec',nom,'createdb','-U','postgres','matheval')
        schema=''.join(p.read_text()+'\n' for p in sorted((atelier/'M-moire/server/migrations').glob('*.sql')))
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','matheval','--set=ON_ERROR_STOP=1','--file=-',input=schema)
        # Les noms seulement changent pour la fixture Vision ; même fichier ACL.
        acls=(ROOT/'assemblage/roles-metier.sql').read_text().replace('\\connect vision\n','\\connect vision_native_test\n').replace('ON DATABASE vision ', 'ON DATABASE vision_native_test ')
        docker('exec','-i',nom,'psql','-X','-U','postgres','--set=ON_ERROR_STOP=1','--file=-',input=acls)
        spec=importlib.util.spec_from_file_location('verifier_tables',ROOT/'scripts/verifier-tables.py')
        contrats=importlib.util.module_from_spec(spec);spec.loader.exec_module(contrats)
        for composant,base in [('vision','vision_native_test'),('matheval','matheval')]:
            contrats.verifier(composant,lambda sql,base=base:docker('exec',nom,'psql','-X','-At','-U','postgres','-d',base,
                              '--set=ON_ERROR_STOP=1','--command',sql).stdout)
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','matheval','--set=ON_ERROR_STOP=1','--file=-',input="""
INSERT INTO corpus(version,digest,bank,codebook) VALUES('fixture','synthetique','{}','{}');
SET ROLE matheval_app;
INSERT INTO participations(id,token_hash,bank_version,levels,seed,question_order,production_order)
 VALUES('00000000-0000-4000-8000-000000000001','synthetique','fixture',ARRAY['fixture'],0,ARRAY[]::text[],'{}');
INSERT INTO answers(participation_id,question_id,production_id,note,initial_note,x,y,z,evaluated_axes)
 VALUES('00000000-0000-4000-8000-000000000001','q','p',0,NULL,0,0,0,ARRAY[]::text[]);
DELETE FROM answers WHERE participation_id='00000000-0000-4000-8000-000000000001';
INSERT INTO interaction_events VALUES('00000000-0000-4000-8000-000000000001',0,'fixture',now(),0,'{}');
INSERT INTO administrators(username,password_hash) VALUES('synthetique','synthetique');
INSERT INTO administrator_sessions(token_hash,administrator_id,expires_at) SELECT 'synthetique',id,now()+interval '1 hour' FROM administrators;
DELETE FROM administrator_sessions;
""")
        try:docker('exec',nom,'psql','-X','-U','postgres','-d','matheval','--set=ON_ERROR_STOP=1','--command',"SET ROLE matheval_app; INSERT INTO corpus VALUES('interdit','interdit','{}','{}',now())")
        except subprocess.CalledProcessError:pass
        else:raise AssertionError('Le runtime peut modifier le corpus')
        def literal(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
        dsn=f"host=127.0.0.1 port={bind['HostPort']} user=vision dbname=vision_native_test"
        # Le même binaire qualifié que Matheval exerce le transport Vision/MCP.
        spec=importlib.util.spec_from_file_location('vision_http_commun',ROOT/'tests/vision-http-commun.py')
        transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
        transport.verifier(os.environ.get('MRJAM_TEST_EXECUTABLE',ROOT/'state/artefacts/mrjam-metier'),dsn,atelier/'vision/docs')
        with tempfile.TemporaryDirectory(prefix='vision-native-sbcl-') as d, IdP() as idp:
            runner=Path(d)/'verifier.lisp'
            runner.write_text(f"""(load {literal(ROOT/'assemblage/charger.lisp')})
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-postgresql {literal(os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'))})
(mrjam-native:initialiser-crypto {literal(os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'))})
(mrjam-native:initialiser-sqlite {literal(os.environ.get('MRJAM_LIBSQLITE','/lib/x86_64-linux-gnu/libsqlite3.so.0'))})
(load {literal(ROOT/'tests/vision-sql-native.lisp')})
(vision-sql-native:verifier {literal(dsn)})
(asdf:load-system "vision/cycle")
(load {literal(ROOT/'tests/vision-cycle.lisp')})
(vision-cycle-test:verifier {literal(dsn)} {literal(d)})
(load {literal(ROOT/'tests/admission-composant.lisp')})
(load {literal(ROOT/'tests/fermeture-composant.lisp')})
(multiple-value-bind (admission sujet)
    (admission-composant:verifier {literal(dsn)} {literal(d)} "http://127.0.0.1:{idp.server.server_port}" {literal(shutil.which('curl'))})
  (fermeture-composant:verifier {literal(dsn)} {literal(d)} "http://127.0.0.1:{idp.server.server_port}" {literal(shutil.which('curl'))} admission sujet))
""")
            subprocess.run([os.environ.get('SBCL','sbcl'),'--script',str(runner)],check=True)
            assert idp.creations==2 and len(idp.reset)==2
    finally:docker('rm','--force',nom)


if __name__=='__main__':verifier()
