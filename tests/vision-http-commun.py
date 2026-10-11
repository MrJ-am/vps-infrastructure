"""Exercer API/MCP de l'artefact commun sur la fixture PostgreSQL Alice/Bob.

L'UID Unix et les identités synthétiques représentent ici l'entrée déjà vérifiée.
Ce test ne remplace pas la qualification réelle de Nginx et du fournisseur OIDC.
"""
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemblage import compilation_entrees,chemins_sources
spec=importlib.util.spec_from_file_location('artefact_http',ROOT/'tests/serveur-artefact.py')
http=importlib.util.module_from_spec(spec);spec.loader.exec_module(http)


def verifier(executable,dsn,docs):
    executable=Path(executable).resolve()
    r=json.loads(executable.with_suffix('.qualification.json').read_text())
    assert r['artefact_sha256']==hashlib.sha256(executable.read_bytes()).hexdigest()
    assert r['sources_lisp_sha256']==compilation_entrees(chemins_sources(atelier=os.environ.get('MRJAM_ATELIER')))
    assert 'host=127.0.0.1 ' in dsn and 'dbname=vision_native_test' in dsn
    with tempfile.TemporaryDirectory(prefix='vision-http-commun-') as tmp:
        sock=Path(tmp)/'metier.sock'
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL')}
        env.update(MRJAM_LIBCRYPTO=os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'),
                   MRJAM_LIBPQ=os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'),
                   MATHEVAL_DSN=dsn.replace('user=vision ','user=matheval_app ').replace('dbname=vision_native_test','dbname=matheval'),
                   MATHEVAL_BANK_VERSION='fixture',MATHEVAL_ORIGIN='http://127.0.0.1:4173',
                   VISION_DSN=dsn,VISION_DOCUMENT_ROOT=str(docs),MRJAM_SOCKET=str(sock),MRJAM_INGRESS_UID=str(os.geteuid()))
        with (Path(tmp)/'log-prive').open('wb') as log:
            p=subprocess.Popen([executable],env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if sock.exists():break
                if p.poll() is not None:raise AssertionError('Démarrage commun refusé')
                time.sleep(.05)
            else:raise AssertionError('Socket commun absent')
            def call(path,body,user='alice',browser=False):
                entetes=b''
                if user is not None:
                    entetes=('X-Vision-Authenticated: 1\r\nX-Mrj-User: '+user+'\r\n').encode()
                if browser:entetes+=b'X-Vision-Browser: 1\r\n'
                status,_,raw=http.requete(sock,http.http('POST',path,service='vision',
                    corps=json.dumps(body,ensure_ascii=False).encode(),extra=entetes))
                return status,json.loads(raw)
            def rpc(method,params,user='alice'):
                code,result=call('/mcp',{'jsonrpc':'2.0','id':1,'method':method,'params':params},user)
                assert code==200 and 'error' not in result
                return result['result']
            assert call('/api/v1/lire',{'type':'item','ids':[1]},None)[0]==401
            assert call('/mcp',{'jsonrpc':'2.0','id':1,'method':'ping'},None)[0]==401
            assert rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}})['serverInfo']['name']=='vision'
            assert 'lire' in [v['name'] for v in rpc('tools/list',{})['tools']]
            def lecture(user):
                own=1 if user=='alice' else 2
                code,val=call('/api/v1/lire',{'type':'item','ids':[1,2]},user)
                assert code==200 and [o['id'] for o in val['objets']]==[own]
                result=rpc('tools/call',{'name':'lire','arguments':{'type':'item','ids':[1,2]}},user)
                assert not result['isError'] and [o['id'] for o in result['structuredContent']['objets']]==[own]
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                list(pool.map(lecture,['alice','bob']*20))
            assert call('/api/web/lire',{'type':'item','ids':[1]})[0]==401
            assert call('/api/web/lire',{'type':'item','ids':[1]},browser=True)[0]==200
            assert call('/api/v1/lire',{'type':'item','ids':[1],'utilisateur':'bob'})[0]==400
            now=datetime.datetime.now(datetime.timezone.utc).isoformat()
            arguments={'cle':uuid.uuid4().hex,'emise_a':now,'objet':'item','objet_id':1,'texte':'Observation synthétique conservée.'}
            result=rpc('tools/call',{'name':'ajouter_observation','arguments':arguments})
            assert not result['isError']
            code,own=call('/api/v1/lire',{'type':'item','ids':[1]})
            assert code==200 and own['objets'][0]['observations'][-1]['texte']==arguments['texte']
            arguments['cle']=uuid.uuid4().hex
            assert call('/api/v1/ajouter_observation',arguments,'bob')[0]==404
            # Une identité ne doit pas contaminer la requête suivante, même après
            # un conflit/refus. Les tâches cycle utilisent ensuite cette même base.
            lecture('bob');lecture('alice')
            print('Artefact commun Vision : API/MCP lecture et écriture, 40 parcours Alice/Bob concurrents, identité injectée et écriture étrangère refusées.')
        finally:
            p.terminate()
            try:p.wait(timeout=12)
            except subprocess.TimeoutExpired:p.kill();p.wait();raise AssertionError('Arrêt commun non borné')
