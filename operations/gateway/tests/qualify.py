"""Exercise the Nix-generated proxy with synthetic TLS and loopback echo services."""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import traceback


def require(value):
    if not value:
        raise RuntimeError('GATEWAY_QUALIFICATION_FAILED')


class Echo(BaseHTTPRequestHandler):
    server_version = 'Synthetic'
    def log_message(self, *_args):
        pass
    def do_GET(self):
        data=json.dumps({'service':self.server.label,'headers':dict(self.headers)}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_POST=do_GET


def request(path, host='vision.synthetic.invalid', headers=None, tls=True):
    connection=(http.client.HTTPSConnection('127.0.0.1',18443,timeout=3,context=TLS)
                if tls else http.client.HTTPConnection('127.0.0.1',18081,timeout=3))
    try:
        connection.request('GET',path,headers={'Host':host,**(headers or {})})
        response=connection.getresponse()
        return response.status, dict(response.getheaders()), response.read(65537)
    finally:
        connection.close()


def main():
    global TLS
    require(len(sys.argv)==1 and os.getuid()==0 and os.environ.get('MRJAM_GATEWAY_SYNTHETIC')=='1')
    require(set(p.name for p in Path('/sys/class/net').iterdir())=={'lo'})
    root=Path(__file__).absolute().parent
    runtime=json.loads((root/'runtime.json').read_text())
    cert=Path('/var/lib/acme/synthetic.invalid')
    cert.mkdir(parents=True,mode=0o700,exist_ok=False)
    subprocess.run([runtime['openssl'],'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                    '-subj','/CN=synthetic.invalid','-addext',
                    'subjectAltName=DNS:vision.synthetic.invalid,DNS:mateval.synthetic.invalid,IP:127.0.0.1',
                    '-keyout',str(cert/'key.pem'),'-out',str(cert/'fullchain.pem')],
                   stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20)
    (cert/'key.pem').chmod(0o600)
    TLS=ssl.create_default_context(cafile=str(cert/'fullchain.pem'))
    for value in ('/var/log/nginx','/var/spool/nginx','/var/cache/nginx','/run/nginx'):
        Path(value).mkdir(parents=True,exist_ok=True)
    services=[]
    process=None
    checks=[]
    try:
        for port,label in ((38101,'rust-synthetic'),(3002,'identity-synthetic')):
            service=ThreadingHTTPServer(('127.0.0.1',port),Echo)
            service.label=label
            threading.Thread(target=service.serve_forever,daemon=True).start()
            services.append(service)
        checked=subprocess.run([runtime['nginx'],'-t','-c',runtime['config']],stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=False,timeout=5)
        if checked.returncode:
            # Nginx sees only this test's generated configuration and invented
            # TLS material, never a production file or application response.
            sys.stderr.write(checked.stderr[:4096].decode('utf-8',errors='replace'))
            raise RuntimeError('SYNTHETIC_NGINX_CONFIG_REJECTED')
        checks.append('generated_nginx_configuration_valid')
        process=subprocess.Popen([runtime['nginx'],'-c',runtime['config']],
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        start=time.monotonic()
        while True:
            require(process.poll() is None and time.monotonic()-start<5)
            try:
                with socket.create_connection(('127.0.0.1',18443),timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        status,_,data=request('/api/web/synthetic',headers={
            'Cookie':'synthetic_session=fixture','Origin':'https://vision.synthetic.invalid',
            'X-CSRF-Token':'synthetic-csrf','Authorization':'Bearer synthetic-token',
            'X-Mrj-User':'forged','X-User-Id':'forged','X-Authenticated-User':'forged',
            'X-Forwarded-User':'forged','X-Vision-Authenticated':'forged','X-Vision-Browser':'forged',
            'X-Forwarded-Host':'forged.invalid','X-Forwarded-Proto':'http','X-Forwarded-For':'198.51.100.23'})
        require(status==200)
        value=json.loads(data); headers={key.lower():value for key,value in value['headers'].items()}
        require(value['service']=='rust-synthetic')
        require(headers['host']=='vision.synthetic.invalid' and headers['x-forwarded-host']=='vision.synthetic.invalid')
        checks.append('canonical_host_forwarded')
        require(headers['cookie']=='synthetic_session=fixture' and headers['origin']=='https://vision.synthetic.invalid')
        require(headers['x-csrf-token']=='synthetic-csrf' and headers['authorization']=='Bearer synthetic-token')
        checks.append('authentication_inputs_preserved')
        require(not any(key in headers for key in ('x-mrj-user','x-user-id','x-authenticated-user','x-forwarded-user','x-vision-authenticated','x-vision-browser')))
        checks.append('forged_identity_headers_removed')
        require(headers['x-forwarded-proto']=='https' and headers['x-forwarded-for']=='127.0.0.1')
        checks.append('forwarded_network_headers_replaced')
        require(request('/healthz')[0]==404 and request('/readyz')[0]==404)
        checks.append('private_health_not_published')
        status,_,data=request('/auth/session',headers={'Cookie':'synthetic_session=fixture'})
        require(status==200 and json.loads(data)['service']=='identity-synthetic')
        checks.append('auth_bridge_to_separate_service')
        for path in ('/.well-known/oauth-authorization-server','/.well-known/oauth-protected-resource',
                     '/.well-known/oauth-protected-resource/mcp','/oauth/authorize','/oauth/token','/oauth/register'):
            status,_,data=request(path)
            require(status==200 and json.loads(data)['service']=='identity-synthetic')
        checks.append('six_exact_oauth_discovery_endpoints_preserved')
        status,_,data=request('/oauth/unexpected')
        require(status==200 and json.loads(data)['service']=='rust-synthetic')
        checks.append('other_oauth_paths_not_delegated')
        status,_,data=request('/auth/session',host='mateval.synthetic.invalid')
        require(status==200 and json.loads(data)['service']=='rust-synthetic')
        checks.append('mateval_not_sent_to_identity_bridge')
        require(request('/api/web/synthetic',host='unknown.synthetic.invalid')[0]==421)
        checks.append('unrecognized_host_refused')
        status,headers,_=request('/matheval/',host='mateval.synthetic.invalid',tls=False)
        require(status in (301,308) and headers.get('Location','').startswith('https://mateval.synthetic.invalid'))
        checks.append('http_redirects_to_https')
        subprocess.run([runtime['nginx'],'-c',runtime['config'],'-s','reload'],
                       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=5)
        require(request('/api/web/synthetic')[0]==200)
        checks.append('graceful_reload_accepts_new_connection')
        print(json.dumps({'schema_version':1,'scope':'synthetic-container-only','checks':{x:'PASS' for x in checks},
                          'configuration_sha256':hashlib.sha256(Path(runtime['config']).read_bytes()).hexdigest(),
                          'runtime':runtime,'adaptations':['root worker in disposable network-none container','synthetic certificate','loopback echo services, not application/auth validation','HTTP18081/HTTPS18443'],
                          'limitations':['No production TLS/certificate checked','No long-lived request or application migration continuity proof']},sort_keys=True))
    finally:
        if process is not None:
            process.send_signal(signal.SIGQUIT)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=1)
        for service in services:
            service.shutdown(); service.server_close()


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        sys.stderr.write('GATEWAY_QUALIFICATION_FAILED\n')
        # This driver accepts only an isolated synthetic fixture. Report the
        # failing code location without dumping HTTP bodies or credentials.
        frames=traceback.extract_tb(error.__traceback__)
        sys.stderr.write(json.dumps({'exception':type(error).__name__,
            'locations':[{'function':f.name,'line':f.lineno} for f in frames]})+'\n')
        raise SystemExit(65)
