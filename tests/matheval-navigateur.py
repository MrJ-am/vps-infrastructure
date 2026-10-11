"""Parcours historiques Firefox/Chromium sur l'artefact SBCL et le site qualifié.

PostgreSQL jetable, corpus officiel inchangé, rôle applicatif limité ; aucune
participation de production, aucun backend Node lancé pour cette campagne.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemblage import compilation_entrees,chemins_sources
from http_fixture import entree
IMAGE='mirror.gcr.io/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'


def qualifier(sources, executable):
    sources=Path(sources).resolve();executable=Path(executable).resolve()
    r=json.loads(executable.with_suffix('.qualification.json').read_text())
    assert r['artefact_sha256']==hashlib.sha256(executable.read_bytes()).hexdigest()
    assert r['sources_lisp_sha256']==compilation_entrees(chemins_sources(atelier=os.environ.get('MRJAM_ATELIER')))
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','PLAYWRIGHT_BROWSERS_PATH','PLAYWRIGHT_CHROMIUM_EXECUTABLE','CI')}
    nom='mrjam-matheval-browser-'+uuid.uuid4().hex[:12]
    def docker(*args,input=None):
        return subprocess.run(['docker',*args],input=input,env=env,text=True,capture_output=True,check=True).stdout
    docker('run','--detach','--name',nom,'--publish','127.0.0.1::5432','--env','POSTGRES_HOST_AUTH_METHOD=trust',
           '--env','POSTGRES_DB=matheval','--label','mrjam.qualification=monolithe-20261011',IMAGE)
    try:
        bind=json.loads(docker('inspect',nom))[0]['NetworkSettings']['Ports']['5432/tcp'][0]
        assert bind['HostIp']=='127.0.0.1'
        for _ in range(100):
            try:docker('exec',nom,'pg_isready','--host=127.0.0.1','-U','postgres','-d','matheval');break
            except subprocess.CalledProcessError:time.sleep(.1)
        else:raise AssertionError('PostgreSQL navigateur indisponible')
        schema=''.join(p.read_text()+'\n' for p in sorted((sources/'server/migrations').glob('*.sql')))
        acls=(ROOT/'assemblage/roles-metier.sql').read_text().split('\\connect matheval\n',1)[1]
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','matheval','--set=ON_ERROR_STOP=1','--file=-',input=schema+acls)
        # La même référence JSON.stringify est utilisée pour l'empreinte du corpus.
        bank=json.loads((sources/'research/bank.json').read_text());codes=json.loads((sources/'research/codebook.json').read_text())
        digest=subprocess.check_output(['node','--input-type=module','-e',
            "import{createHash}from'node:crypto';import{readFileSync}from'node:fs';let{bank,codebook}=JSON.parse(readFileSync(0));process.stdout.write(createHash('sha256').update(JSON.stringify({bank,codebook})).digest('hex'));"],
            input=json.dumps({'bank':bank,'codebook':codes}).encode(),env=env).decode()
        def sql(s):return "'"+s.replace("'","''")+"'"
        insertion='INSERT INTO corpus(version,digest,bank,codebook) VALUES('+','.join(map(sql,[bank['version'],digest,json.dumps(bank,ensure_ascii=False),json.dumps(codes,ensure_ascii=False)]))+');'
        docker('exec','-i',nom,'psql','-X','-U','postgres','-d','matheval','--set=ON_ERROR_STOP=1','--file=-',input=insertion)
        with tempfile.TemporaryDirectory(prefix='matheval-browser-') as tmp:
            tmp=Path(tmp);socket=tmp/'metier.sock'
            activation=tmp/'activation';activation.write_text(hashlib.sha256(('a'*64).encode()).hexdigest());activation.chmod(0o600)
            config=sources/'docs/.central-playwright.cjs'
            # Un contexte navigateur représente un client synthétique distinct.
            # L'adresse est imposée par cette entrée de fixture, jamais utilisable
            # sur Nginx de production. Aucun mode test ne désactive les quotas Lisp.
            config.write_text("const c=require('./playwright.config.cjs');delete c.webServer;module.exports=c;\n")
            for test in (sources/'docs/tests/e2e').glob('*.spec.js'):
                test.write_text("const centralQuotaTest=require('@playwright/test').test;\ncentralQuotaTest.beforeEach(async({page})=>{const h=require('node:crypto').randomBytes(6).toString('hex');await page.setExtraHTTPHeaders({'X-Fixture-IP':'fd00:'+h.match(/.{4}/g).join(':')+'::1'});});\n"+test.read_text())
            diagnostic=bool(os.environ.get('MRJAM_TEST_FILTER') or os.environ.get('MRJAM_TEST_DIAGNOSTIC'))
            if diagnostic:
                # Instrumentation de fixture bornée : événements d'entrée et
                # état du dialogue, sans corps réseau, cookie ou contenu.
                test=sources/'docs/tests/e2e/survey.spec.js'
                instrumentation='''const centralTest=require('@playwright/test').test;
centralTest.beforeEach(async({page})=>{await page.addInitScript(()=>{
window.__MRJAM_EVENEMENTS=[];for(const type of ['pointerdown','pointerup','click','read'])document.addEventListener(type,e=>{
const out=window.__MRJAM_EVENEMENTS;if(out.length>=200)out.shift();const b=document.querySelector('#validate-reading'),r=b?.getBoundingClientRect();out.push({type,temps:performance.now(),cible:e.target.id||e.target.closest('button')?.id||e.target.tagName,x:e.clientX,y:e.clientY,detail:typeof e.detail==='number'?e.detail:undefined,lecteur:!!document.querySelector('reading-card'),fermetureDesactivee:b?.disabled,fermetureRect:r?{x:r.x,y:r.y,width:r.width,height:r.height}:null,actif:document.activeElement?.id});},true);});});
centralTest.afterEach(async({page},info)=>{await info.attach('evenements-dialogue',{body:JSON.stringify(await page.evaluate(()=>window.__MRJAM_EVENEMENTS||[])),contentType:'application/json'});});
'''
                test.write_text(instrumentation+test.read_text())
            with entree(socket,sources/'docs/site') as origin:
                dsn=f"host=127.0.0.1 port={bind['HostPort']} user=matheval_app dbname=matheval"
                runtime={k:v for k,v in env.items() if k in ('PATH','HOME','LANG','LC_ALL')}
                runtime.update(MRJAM_LIBCRYPTO=os.environ.get('MRJAM_LIBCRYPTO','/lib/x86_64-linux-gnu/libcrypto.so.3'),
                    MRJAM_LIBPQ=os.environ.get('MRJAM_LIBPQ','/lib/x86_64-linux-gnu/libpq.so.5'),
                    MATHEVAL_DSN=dsn,MATHEVAL_BANK_VERSION=bank['version'],MATHEVAL_ORIGIN=origin,
                    MATHEVAL_SETUP_HASH_FILE=str(activation),VISION_DSN=dsn,VISION_DOCUMENT_ROOT=str(tmp),
                    MRJAM_SOCKET=str(socket),MRJAM_INGRESS_UID=str(os.geteuid()))
                with (tmp/'serveur.log').open('wb') as log:p=subprocess.Popen([executable],env=runtime,stdout=log,stderr=log)
                try:
                    for _ in range(100):
                        if socket.exists():break
                        if p.poll() is not None:raise AssertionError('Serveur SBCL navigateur refusé')
                        time.sleep(.05)
                    else:raise AssertionError('Socket navigateur absent')
                    commande=['node_modules/.bin/playwright','test','--config=.central-playwright.cjs']
                    if diagnostic:commande+=['--trace=on']
                    if os.environ.get('MRJAM_TEST_FILTER'):commande+=['--grep',os.environ['MRJAM_TEST_FILTER']]
                    if os.environ.get('MRJAM_TEST_PROJECT'):commande+=['--project',os.environ['MRJAM_TEST_PROJECT']]
                    if os.environ.get('MRJAM_TEST_REPEAT'):
                        nombre=int(os.environ['MRJAM_TEST_REPEAT'])
                        if not 2<=nombre<=20:raise ValueError('Campagne de reproduction bornée à 2–20 scénarios')
                        commande+=['--repeat-each',str(nombre)]
                    subprocess.run(commande,
                                   cwd=sources/'docs',env=dict(env,TEST_ORIGIN=origin),check=True)
                finally:
                    p.terminate()
                    try:p.wait(timeout=12)
                    except subprocess.TimeoutExpired:p.kill();p.wait();raise AssertionError('Arrêt navigateur non borné')
                    config.unlink(missing_ok=True)
        print('Matheval : campagne navigateur sur le binaire SBCL commun, base et participations synthétiques uniquement.')
    finally:docker('rm','--force',nom)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sources',required=True);p.add_argument('--executable',default=ROOT/'state/artefacts/mrjam-metier')
    a=p.parse_args();qualifier(a.sources,a.executable)
