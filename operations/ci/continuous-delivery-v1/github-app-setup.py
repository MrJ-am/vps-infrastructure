"""Local, single-use GitHub App manifest handshake. No production activation.

The user registers the app in GitHub. Credentials go to a private local spool,
never stdout, browser HTML, source control, or the candidate environment.
"""
import hmac,html,json,os,re,secrets,stat,time,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

PORT=18089
ORIGIN=f'http://127.0.0.1:{PORT}'
OWNER='MrJ-am'
OWNER_ID=12571490
PERMISSIONS={'contents':'write','pull_requests':'write','statuses':'write','workflows':'write','metadata':'read'}

class Refused(Exception):pass
def require(value,code):
    if not value:raise Refused(code)

def manifest():
    return {'name':'MRJam Forge Synchronisation','url':'https://forge.mrj.am',
            'description':'Reception des propositions Cloud et retour des livraisons verifiees. Aucun acces au VPS pour les candidats.',
            'public':False,'redirect_url':ORIGIN+'/callback',
            'hook_attributes':{'url':'https://forge.mrj.am/_mrjam-github-events','active':False},
            'default_permissions':PERMISSIONS,'default_events':[],
            'request_oauth_on_install':False}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def convert(code):
    require(re.fullmatch(r'[A-Za-z0-9_-]{16,160}',code) is not None,'CODE_REFUSED')
    request=urllib.request.Request('https://api.github.com/app-manifests/'+code+'/conversions',
        data=b'',method='POST',headers={'Accept':'application/vnd.github+json','User-Agent':'mrjam-app-bootstrap','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
        require(response.status==201,'CONVERSION_REFUSED')
        raw=response.read(131073);require(len(raw)<=131072,'RESPONSE_LIMIT')
    return checked_response(json.loads(raw))

def checked_response(value):
    require(type(value) is dict,'APP_REFUSED')
    owner=value.get('owner',{})
    require(owner.get('login')==OWNER and owner.get('id')==OWNER_ID,'OWNER_REFUSED')
    require(type(value.get('id')) is int and 0<value['id']<2**53,'APP_ID_REFUSED')
    slug=value.get('slug');require(type(slug) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,99}',slug),'SLUG_REFUSED')
    require(value.get('html_url')=='https://github.com/apps/'+slug,'APP_URL_REFUSED')
    require(value.get('permissions')==PERMISSIONS and value.get('events')==[],'APP_PERMISSIONS_REFUSED')
    key=value.get('pem')
    require(type(key) is str and 1000<len(key)<16384 and key.isascii()
            and re.fullmatch(r'-----BEGIN (RSA )?PRIVATE KEY-----\n[A-Za-z0-9+/=\n]+-----END (RSA )?PRIVATE KEY-----\n?',key),'PRIVATE_KEY_REFUSED')
    # Client/webhook secrets are unused and deliberately not retained.
    return {'app_id':value['id'],'owner_id':OWNER_ID,'slug':slug,'private_key':key,
            'permissions':PERMISSIONS}

def save_private(directory,value):
    info=directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
            and stat.S_IMODE(info.st_mode)==0o700,'SPOOL_REFUSED')
    target=directory/'app-credentials.json'
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
    fd=os.open(directory,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Setup:
    def __init__(self,directory,exchange=convert):
        self.directory=directory;self.exchange=exchange
        self.state=secrets.token_urlsafe(32);self.deadline=time.monotonic()+3600;self.consumed=False
    def authorize(self,state,cookie):
        require(not self.consumed and time.monotonic()<self.deadline,'SESSION_EXPIRED')
        require(type(state) is str and type(cookie) is str
                and hmac.compare_digest(state,self.state) and hmac.compare_digest(cookie,self.state),'SESSION_REFUSED')
    def complete(self,state,cookie,code):
        self.authorize(state,cookie);self.consumed=True
        value=self.exchange(code);save_private(self.directory,value)
        return 'https://github.com/apps/'+value['slug']+'/installations/new'

def handler(setup):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send_page(self,status,body,cookie=None):
            raw=('<!doctype html><meta charset="utf-8"><title>MRJ.am — GitHub</title>'+body).encode()
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; form-action https://github.com; frame-ancestors 'none'; base-uri 'none'")
            if cookie:self.send_header('Set-Cookie','mrjam_setup='+cookie+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600')
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            try:
                require(self.headers.get('Host')==f'127.0.0.1:{PORT}','HOST_REFUSED')
                url=urlsplit(self.path);query=parse_qs(url.query,strict_parsing=True)
                if url.path=='/start':
                    require(set(query)=={'state'} and len(query['state'])==1,'QUERY_REFUSED')
                    state=query['state'][0];setup.authorize(state,state)
                    content=html.escape(json.dumps(manifest()),quote=True)
                    body=('<h1>Relier GitHub à la forge</h1><p>Cette application privée pourra lire et synchroniser le code, les demandes de fusion et leurs statuts dans les dépôts que vous sélectionnerez sur GitHub.</p>'
                          '<p>Elle ne recevra aucun accès au VPS ni aux données applicatives. Sélectionnez uniquement les dépôts MRJ.am concernés lors de son installation.</p>'
                          '<form method="post" action="https://github.com/settings/apps/new?state='+html.escape(state)+'">'
                          '<input type="hidden" name="manifest" value="'+content+'"><button>Configurer sur GitHub</button></form>')
                    self.send_page(200,body,state);return
                require(url.path=='/callback' and set(query)=={'state','code'}
                        and all(len(v)==1 for v in query.values()),'CALLBACK_REFUSED')
                cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
                cookie=cookies['mrjam_setup'].value if 'mrjam_setup' in cookies else ''
                link=setup.complete(query['state'][0],cookie,query['code'][0])
                self.send_page(200,'<h1>Application créée</h1><p>Sa clé est conservée localement dans le dossier privé de transfert.</p><a href="'+html.escape(link)+'">Installer sur les dépôts choisis</a>')
            except Exception:
                self.send_page(400,'<h1>Configuration interrompue</h1><p>Le relais doit vérifier cette tentative avant de recommencer. Aucun secret ne doit être transmis dans la conversation.</p>')
    return Handler

def main():
    root=Path(__file__).resolve().parents[3]
    directory=root/'.local/deployment-20261101/github-app-bootstrap-001'
    directory.mkdir(mode=0o700)
    setup=Setup(directory)
    server=HTTPServer(('127.0.0.1',PORT),handler(setup))
    (directory/'start-url').write_text(ORIGIN+'/start?state='+setup.state+'\n')
    print('LOCAL_GITHUB_SETUP_READY',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
