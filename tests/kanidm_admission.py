"""Capacités natives d'admission : pas d'administrateur général produit."""
import json
import time
from pathlib import Path
import importlib.util
import subprocess
import os
import uuid
from kanidm_reel import KanidmLocal, EchecQualification

def qualifier(paquet,curl,*,persistante=False):
    with KanidmLocal(paquet,curl) as n:
        op=n.login('idm_admin',n.recuperer('idm_admin'),privilegie=True)
        sys=n.login('admin',n.recuperer('admin'),privilegie=True)
        def r(path,body=None,*,token=op,method=None):
            code,d=n.http(path,body,token=token,method=method)
            if code!=200: raise EchecQualification('Capacité admission refusée HTTP'+str(code))
            return d
        r('/v1/person',{'attrs':{'name':['fixture-protegee'],'displayname':['Fixture protégée'],'mail':['protegee@example.test']}})
        uid=r('/v1/person/fixture-protegee')['attrs']['uuid'][0]
        r('/v1/group/idm_high_privilege/_attr/member',[uid],token=sys)
        r('/v1/service_account',{'attrs':{'name':['fixture-admission'],'displayname':['Fixture admission'],'entry_managed_by':['idm_admin']}})
        r('/v1/group/idm_people_on_boarding/_attr/member',['fixture-admission'])
        r('/v1/group/idm_account_mail_read/_attr/member',['fixture-admission'],token=sys)
        svc=r('/v1/service_account/fixture-admission/_api_token',{'label':'fixture','expiry':int(time.time())+3600,'read_write':True})
        root=Path(__file__).resolve().parents[1]
        fixture=n.root/'client-lisp.json';fixture.write_text(json.dumps({'token':svc,'curl':str(n.curl),
            'ca':str(n.ca),'port':n.port}));fixture.chmod(0o600)
        spec=importlib.util.spec_from_file_location('pont_admission',root/'scripts/mcp-appel.py')
        pont=importlib.util.module_from_spec(spec);spec.loader.exec_module(pont)
        code='''(progn (asdf:load-system "mrjam-metier")
          (let* ((d (vision:parse-json (uiop:read-file-string PATH)))
                 (c (mrjam-identite:faire-client-kanidm (vision:json-object-get d "token")
                    (vision:json-object-get d "curl") (vision:json-object-get d "ca") :port (vision:json-object-get d "port")))
                 (p (mrjam-identite:creer-personne c "fixture-lisp" "lisp@example.test" "Élodie 東京"))
                 (id (vision:json-object-get p "id")))
            (assert (eq :false (vision:json-object-get p "enabled")))
            (assert (= 1 (length (mrjam-identite:chercher-personnes c "email" "lisp@example.test"))))
            (mrjam-identite:activer-personne c id)
            (assert (eq :true (vision:json-object-get (mrjam-identite:personne c id) "enabled")))
            (assert (search "https://log.mrj.am/ui/reset?token=" (mrjam-identite:inviter-personne c id)))
            (mrjam-identite:expirer-personne c id)
            (assert (eq :false (vision:json-object-get (mrjam-identite:personne c id) "enabled"))))
          (format t "ADMISSION-NATIVE-TERMINEE"))'''.replace('PATH',json.dumps(str(fixture)))
        code_initial=code
        def evaluer(code,marqueur):
            res=pont.requete('cl-mcp','tools/call',{'name':'repl-eval','arguments':{'code':code}})
            if res.get('error_context') or res.get('isError') or marqueur not in res.get('stdout',''):
                fd=os.open(root/'state/admission-native-diagnostic.json',os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
                with os.fdopen(fd,'w') as f:json.dump(res,f)
                raise EchecQualification('Admission Lisp : diagnostic privé, pas de réussite')
        if persistante:evaluer(code_initial,'ADMISSION-NATIVE-TERMINEE')
        image='mirror.gcr.io/pgvector/pgvector@sha256:40b404964359299eefdd5f8518facf1886c562848cf4de13b6eaf91cb70c2b87'
        nom='mrjam-admission-native-'+uuid.uuid4().hex[:10]
        env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
        def docker(*args,input=None):
            return subprocess.run(['docker',*args],input=input,text=True,capture_output=True,env=env,check=True)
        docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432','--env','POSTGRES_HOST_AUTH_METHOD=trust',
               '--env','POSTGRES_DB=vision_native_test',image)
        try:
            bind=json.loads(docker('inspect',nom).stdout)[0]['NetworkSettings']['Ports']['5432/tcp'][0]
            for _ in range(100):
                if subprocess.run(['docker','exec',nom,'pg_isready','-h','127.0.0.1','-U','postgres','-d','vision_native_test'],env=env,
                                  capture_output=True).returncode==0:break
                time.sleep(.1)
            else:raise EchecQualification('PostgreSQL isolé hors délai')
            vision=root.parent/'vision'
            ddl='CREATE EXTENSION vector;\n'+''.join(p.read_text()+'\n' for p in sorted((vision/'migrations').glob('*.sql')))
            ddl+=(vision/'scripts/roles.sql').read_text()+"""
UPDATE vision_gestion.configuration SET inscriptions_ouvertes=true,responsable='Qualification',contact='operator@example.test',
 pays_hebergement='Test',notice_version='notice-test';
INSERT INTO vision_gestion.comptes(utilisateur,affichage,administrateur) VALUES('alice','Qualification',true);
"""
            docker('exec','-i',nom,'psql','-X','-U','postgres','-d','vision_native_test','--set=ON_ERROR_STOP=1','--file=-',input=ddl)
            doc=json.loads(fixture.read_text());doc.update(dsn='host=127.0.0.1 port='+bind['HostPort']+' dbname=vision_native_test',
                                                         root=str(n.root/'admissions'))
            fixture.write_text(json.dumps(doc))
            code='(progn (mrjam-native:initialiser-postgresql '+json.dumps(os.environ['MRJAM_LIBPQ'])+') (load '+json.dumps(str(root/'tests/admission-kanidm.lisp'))+') (uiop:symbol-call :admission-kanidm :verifier '+json.dumps(str(fixture))+'))'
            if persistante:evaluer(code,'ADMISSION-PG-NATIVE-TERMINEE')
            else:
                formes=n.root/'qualification.lisp';formes.touch(mode=0o600)
                formes.write_text(code_initial+'\n'+code+'\n')
                diagnostic=root/'state/admission-kanidm-froid-prive.log'
                fd=os.open(diagnostic,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
                with os.fdopen(fd,'w') as journal:
                    p=subprocess.run(['sbcl','--script','tests/admission-kanidm-froid.lisp'],
                        env=dict(os.environ,MRJAM_ADMISSION_FORMES=str(formes)),stdout=journal,stderr=subprocess.STDOUT,timeout=90)
                resultat=diagnostic.read_text()
                if p.returncode or any(m not in resultat for m in ('ADMISSION-NATIVE-TERMINEE','ADMISSION-PG-NATIVE-TERMINEE')):
                    raise EchecQualification('Admission en image propre refusée ; diagnostic privé')
        finally:docker('rm','--force',nom)
        r('/v1/person',{'attrs':{'name':['fixture-nouvelle'],'displayname':['Élodie 東京'],'mail':['nouvelle@example.test'],
                                'account_expire':['1970-01-01T00:00:00Z']}},token=svc)
        profil=r('/v1/person/fixture-nouvelle',token=svc)['attrs']
        if profil['mail']!=['nouvelle@example.test']:raise EchecQualification('Mail d’admission non lisible')
        r('/v1/person/fixture-nouvelle/_attr/account_expire',token=svc,method='DELETE')
        r('/v1/person/fixture-nouvelle/_credential/_update_intent/600',token=svc)
        for path,body,method in [('/v1/person/'+uid+'/_credential/_update_intent/600',None,None),
          ('/v1/person/'+uid+'/_attr/account_expire',['1970-01-01T00:00:00Z'],'PUT'),
          ('/v1/group/idm_all_persons/_attr/authsession_expiry',['7776000'],'PUT'),
          ('/v1/group/idm_admins/_attr/member',['fixture-admission'],None)]:
            code,d=n.http(path,body,token=svc,method=method)
            # Cette version retourne500/NotAuthorised pour un intent refusé.
            # Un500 quelconque ne démontre aucun refus d'autorisation.
            denied=code in (403,404) or (code==500 and isinstance(d,str) and d.lower()=='notauthorised')
            if not denied:raise EchecQualification('Capacité admission indûment privilégiée HTTP'+str(code)+' type='+str(type(d).__name__))
        return {'creation_admission':True,'mail_metadata_seul':True,'activation_et_invitation':True,
                'reset_proprietaire_protege_refuse':True,'politique_globale_refusee':True,
                'elevation_administrateur_refusee':True,'image_propre':not persistante,'production':False}
