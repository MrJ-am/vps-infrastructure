"""Real disposable Nextcloud 34.0.4 / user_oidc 8.10.1 / Kanidm 1.11.2.
Native IdP login is mediated by its MFA API; no personal login or production data.
Containers and their TLS CA must have been prepared locally before this command.
"""
import importlib.util,json,pathlib,secrets,socket,subprocess,sys,urllib.parse
import requests
ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=pathlib.Path('/workspace/nextcloud-sso-work')
sys.path.insert(0,str(ROOT/'tests'))
from kanidm_reel import KanidmLocal
from kanidm_politiques import creer_neuf_mfa
spec=importlib.util.spec_from_file_location('client',ROOT/'assemblage/nextcloud-sso/client.py')
client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
orig=socket.getaddrinfo
socket.getaddrinfo=lambda host,*args,**kw:orig('127.0.0.1' if host=='kanidm.test' else host,*args,**kw)
CA=str(WORK/'native/chain.pem')

def command(*args):
    p=subprocess.run(list(args),capture_output=True,text=True)
    if p.returncode:
        (WORK/'test-command-error.log').write_text(p.stderr+'\n'+p.stdout)
        raise RuntimeError('Local command failed; private log recorded')
    return p.stdout.strip()
def occ(*args):return command('docker','exec','nextcloud-sso-test','runuser','-u','www-data','--','php','occ',*args)
def session():
    s=requests.Session();s.trust_env=False;s.verify=CA;return s
class Native(KanidmLocal):
    def __init__(self):
        self.root=WORK/'native';self.nom='owner-'+secrets.token_hex(4);self.mail=self.nom+'@example.test'
        self.password=secrets.token_urlsafe(40);self.sessions={}
    def commande(self,*args):return command('docker','exec','nextcloud-sso-native','/sbin/kanidmd','-c','/data/server.toml',*args)
    def http(self,path,document=None,*,token=None,cookies=None,method=None,headers=False):
        s=self.sessions.setdefault(str(cookies),session()) if cookies else session()
        r=s.request(method or ('POST' if document is not None else 'GET'),'https://kanidm.test:8443'+path,
           json=document,headers={'Authorization':'Bearer '+token} if token else {},allow_redirects=False,timeout=20)
        try:value=r.json()
        except ValueError:value=r.text
        return (r.status_code,value,dict(r.headers)) if headers else (r.status_code,value)
class Api:
    def http(self,path,body=None,*,token=None,method=None):
        status,v=n.http(path,body,token=token,method=method)
        assert status==200,(path,status)
        return v
n=Native();uat=creer_neuf_mfa(n);op=n.login('idm_admin',n.recuperer('idm_admin'),privilegie=True);api=Api()
groups=api.http('/v1/group',token=op)
if not any(g['attrs'].get('name')==['mrjam-proprietaire-policy'] for g in groups):
    api.http('/v1/group',{'attrs':{'name':['mrjam-proprietaire-policy']}},token=op)
api.http('/v1/group/mrjam-proprietaire-policy/_attr/member',[n.uuid],token=op,method='PUT')
uid='existing-owner';base='https://localhost:18443';callback=base+'/apps/user_oidc/code'
data=client.configure(api,op,uid,n.uuid,callback)
secret=WORK/'test-client-secret';secret.write_text(data['clientSecret']);secret.chmod(0o600)
command('docker','cp',str(secret),'nextcloud-sso-test:/tmp/sso-client-secret')
command('docker','exec','nextcloud-sso-test','chown','www-data:www-data','/tmp/sso-client-secret')
occ('user_oidc:provider','Log','--clientid',client.CLIENT,'--clientsecret-file','/tmp/sso-client-secret','--discoveryuri',
    'https://kanidm.test:8443/oauth2/openid/'+client.CLIENT+'/.well-known/openid-configuration',
    '--mapping-uid','nextcloud_uid','--unique-uid','0','--check-bearer','0','--bearer-provisioning','0','--scope','openid profile email')
secret.unlink()
for k,v in {'auto_provision':False,'enable_default_claims':False,'use_pkce':True,'single_logout':False}.items():
    occ('config:system:set','user_oidc',k,'--type','boolean','--value',str(v).lower())
for k,v in {'token_auth_enforced':True,'hide_login_form':True,'auth.webauthn.enabled':False}.items():
    occ('config:system:set',k,'--type','boolean','--value',str(v).lower())
occ('config:app:set','user_oidc','allow_multiple_user_backends','--value','0','--type','string')
device=occ('user:auth-tokens:add','existing-owner','--name','sso-fixture','--no-interaction').splitlines()[-1]
before=json.loads(occ('user:list','--output=json'))
s=session()
r=s.get(base+'/index.php/login',allow_redirects=False);assert r.status_code==302,r.status_code
r=s.get(urllib.parse.urljoin(base,r.headers['Location']),allow_redirects=False)
assert r.status_code in (302,303),(r.status_code,r.text[:100])
q=urllib.parse.urlsplit(r.headers['Location']);qs=urllib.parse.parse_qs(q.query)
assert qs['code_challenge_method']==['S256'] and qs['redirect_uri']==[callback]
status,v,headers=n.http('/oauth2/authorise?'+q.query,token=uat,headers=True)
if status==200 and isinstance(v,dict) and 'ConsentRequested' in v:
    status,v,headers=n.http('/oauth2/authorise/permit',v['ConsentRequested']['consent_token'],token=uat,headers=True)
assert status in (200,302) and 'location' in {k.lower():v for k,v in headers.items()},('native consent',status)
location=next(v for k,v in headers.items() if k.lower()=='location')
r=s.get(location,allow_redirects=False)
if r.status_code!=303 and r.status_code!=302:
    (WORK/'callback-error.html').write_text(r.text)
assert r.status_code in (302,303),('callback',r.status_code)
r=s.get(base+'/ocs/v2.php/cloud/user?format=json',headers={'OCS-APIRequest':'true'})
assert r.status_code==200,(r.status_code,r.text[:100])
assert r.json()['ocs']['data']['id']==uid
assert json.loads(occ('user:list','--output=json'))==before
# Password POST must be refused even through the native direct escape hatch.
for path in ['/login','/index.php/login','/index.php/login?direct=1']:
    assert session().post(base+path,data={'user':uid,'password':'Local-test-only-long-password-43'}).status_code==403
r=session().request('PROPFIND',base+'/remote.php/dav/files/'+uid+'/',auth=(uid,'Local-test-only-long-password-43'),headers={'Depth':'0'})
assert r.status_code==401,r.status_code
r=session().request('PROPFIND',base+'/remote.php/dav/files/'+uid+'/',auth=(uid,device),headers={'Depth':'0'})
assert r.status_code==207,r.status_code
# An unbound real identity cannot obtain access to this client's scope.
n.nom='unbound-'+secrets.token_hex(4);n.mail=n.nom+'@example.test';n.password=secrets.token_urlsafe(40)
other=creer_neuf_mfa(n)
status,_,_=n.http('/oauth2/authorise?'+q.query,token=other,headers=True)
assert status in (400,403),status
proof={'nextcloud':'34.0.4','user_oidc':'8.10.1','kanidm':'1.11.2','realMfaPkceEs256':True,
 'existingAccountPreserved':True,'automaticAccountCreationDisabled':True,'unboundIdentityDenied':True,
 'localPasswordPostDenied':True,'davPasswordDenied':True,'existingAppTokenWorks':True,'production':False,'idpUiMediatedByNativeApi':True}
(ROOT/'assemblage/nextcloud-sso/qualification-locale.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
