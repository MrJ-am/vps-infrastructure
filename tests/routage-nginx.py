"""Locations métier Nix réelles, Nginx verrouillé et même artefact SBCL.

Fixture documentaire loopback sans PostgreSQL, SMTP, IdP ni données personnelles.
Les auth_request/TLS des modules existants restent qualifiés séparément.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def simplifier(v):
    if isinstance(v,dict) and v.get('_type') in ('override','order'):return simplifier(v['content'])
    return v


def verifier():
    audit=json.loads((ROOT/'assemblage/nginx-qualification.json').read_text())
    nginx=Path(audit['paquet'])/'bin/nginx'
    assert hashlib.sha256(nginx.read_bytes()).hexdigest()==audit['binaire_sha256']
    exe=Path(os.environ['MRJAM_TEST_EXECUTABLE']).resolve()
    q=json.loads(exe.with_suffix('.qualification.json').read_text())
    assert hashlib.sha256(exe.read_bytes()).hexdigest()==q['artefact_sha256']
    r=json.loads((ROOT/'state/frontends-candidats/dernier-vision.json').read_text())
    documents=(ROOT/r['candidat']).resolve()
    source=ROOT/'state/outils-sources'/('nixpkgs-'+audit['revision'])
    expression='let p=import '+json.dumps(str(source))+' { system="x86_64-linux"; }; in (import '+str(ROOT/'modules/metier.nix')+' { lib=p.lib; pkgs=p; config.infrastructure.metier={ enable=true; documentVision='+json.dumps(str(documents))+'; ressourcesMatheval="/sans-matheval"; }; }).config.content.services.nginx.virtualHosts."vision.mrj.am".locations'
    locations=json.loads(subprocess.check_output(['nix-instantiate','--eval','--strict','--json','--expr',expression],text=True))
    with tempfile.TemporaryDirectory(prefix='mrjam-routage-') as tmp:
        d=Path(tmp);sock=d/'metier.sock'
        env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','MRJAM_LIBCRYPTO','MRJAM_LIBPQ','MRJAM_LIBSQLITE')}
        env.update(MRJAM_SOCKET=str(sock),MRJAM_INGRESS_UID=str(os.geteuid()),
            VISION_DSN='host=/sans-postgresql dbname=fixture_test',MATHEVAL_DSN='host=/sans-postgresql dbname=fixture_test',
            MATHEVAL_BANK_VERSION='fixture',MATHEVAL_ORIGIN='https://fixture.test',
            VISION_DOCUMENT_ROOT=str(documents),VISION_PUBLIC_MCP_URL='https://fixture.test/mcp')
        log=(d/'metier.log').open('wb')
        app=subprocess.Popen([str(exe)],env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if sock.exists():break
                assert app.poll() is None,'Artefact documentaire arrêté'
                time.sleep(.05)
            else:raise AssertionError('Socket documentaire absent')
            def campagne(ancien):
                with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
                lignes=[]
                selection=dict(locations)
                # Ancienne location exacte qualifiée à tort : son index
                # interne /index.html arrivait au routeur métier.
                if ancien:selection['= /']={'root':str(documents)}
                for chemin,opts in selection.items():
                    directives=[]
                    for k in ('root','alias','proxyPass','extraConfig'):
                        if k not in opts:continue
                        value=simplifier(opts[k]).replace('/run/mrjam-metier/http.sock',str(sock))
                        directives.append(value if k=='extraConfig' else ('proxy_pass' if k=='proxyPass' else k)+' '+value+';')
                    lignes.append('location '+chemin+' {\n'+'\n'.join(directives)+'\n}')
                conf=d/('ancien.conf' if ancien else 'actuel.conf')
                user='user root;\n' if os.geteuid()==0 else ''
                conf.write_text(user+'daemon off;\npid '+str(d/'nginx.pid')+';\nerror_log '+str(d/'nginx.log')+';\nevents {}\nhttp { access_log off; types { text/html html; application/javascript js; text/css css; application/json json; } server { listen 127.0.0.1:'+str(port)+'; server_name vision.mrj.am;\n'+'\n'.join(lignes)+'\n} }\n')
                command=[str(nginx),'-p',str(d),'-c',str(conf)]
                subprocess.run(command+['-t'],capture_output=True,check=True)
                process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    for _ in range(100):
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                        except OSError:
                            assert process.poll() is None,'Nginx documentaire arrêté'
                            time.sleep(.02)
                    else:raise AssertionError('Nginx documentaire absent')
                    def get(path):
                        try:response=urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=5)
                        except urllib.error.HTTPError as e:response=e
                        with response:return response.status,response.read(),response.headers
                    if ancien:
                        assert get('/')[0]==404,'La fixture doit reproduire la redirection interne perdue'
                    else:
                        for path,filename in [('/','index.html'),('/app.js','app.js'),('/app.css','app.css')]:
                            status,body,headers=get(path);assert status==200 and hashlib.sha256(body).hexdigest()==r['fichiers'][filename],path
                            if path=='/':
                                assert headers['Cache-Control']=='no-store'
                                assert "base-uri 'none'" in headers['Content-Security-Policy']
                                assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
                        status,body,headers=get('/interface-manifest.json')
                        assert status==200 and hashlib.sha256(body).hexdigest()==r['fichiers']['manifest.json']
                        assert json.loads(body)['revisionApplication']==r['revision']
                        for path in ('/docs','/docs/','/privacy','/connexion','/invitation','/admission'):
                            status,body,headers=get(path);assert status==200 and body==(documents/'app.html').read_bytes(),path
                            assert headers['Cache-Control']=='no-store'
                            assert "base-uri 'none'" in headers['Content-Security-Policy']
                        assert get('/mcp')[0]==401
                        assert get('/ressource-inexistante')[0]==404
                finally:process.terminate();process.wait(timeout=5)
            campagne(True);campagne(False)
        finally:app.terminate();app.wait(timeout=10);log.close()
    print('Nginx/SBCL réels : ancien accueil404 reproduit, accueil Vision/mêmes octets et CSP/no-store conservés, six chemins publics et refus MCP/anonyme vérifiés sans connexion SQL.')


if __name__=='__main__':verifier()
