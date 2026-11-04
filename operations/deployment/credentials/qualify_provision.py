#!/usr/bin/env python3
"""Author qualification against a fresh disposable Kanidm. No real credentials."""
import hashlib
import json
import os
import pty
from pathlib import Path
import resource
import select
import runpy
import socket
import subprocess
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parent
P = runpy.run_path(str(ROOT/'provision.py'),run_name='candidate')
KANIDMD = '/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2/bin/kanidmd'
KANIDM = '/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2/bin/kanidm'
OPENSSL = '/etc/profiles/per-user/jam/bin/openssl'


class FixtureError(Exception):
    pass


def check(value, label):
    if not value:
        raise FixtureError(label)


class Fixture:
    def __init__(self,port=None,ca_directory=None,openssl=OPENSSL):
        self.requested_port = port
        self.ca_directory = None if ca_directory is None else Path(ca_directory)
        self.openssl = openssl

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mrjam-provision-synthetic-')
        self.root = Path(self.tmp.name)
        self.passwords = {}
        self.cli_reauths = 0
        os.chmod(self.root,0o700)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        with socket.socket() as port:
            port.bind(('127.0.0.1',self.requested_port or 0))
            self.port = port.getsockname()[1]
        if self.ca_directory is not None:
            for name in ('ca.pem','leaf.pem','key.pem'):
                (self.root/name).write_bytes((self.ca_directory/name).read_bytes())
        else:
            self.certificates()
        os.chmod(self.root/'key.pem',0o600)
        config = {'version':'2','domain':'log.mrj.am','origin':'https://log.mrj.am',
                  'bindaddress':'127.0.0.1:'+str(self.port),'db_path':str(self.root/'kanidm.db'),
                  'tls_chain':str(self.root/'leaf.pem'),'tls_key':str(self.root/'key.pem'),
                  'adminbindpath':str(self.root/'admin.sock'),'log_level':'info'}
        (self.root/'server.toml').write_text('\n'.join(k+' = '+json.dumps(v) for k,v in config.items())+'\n')
        self.log = open(self.root/'provider.log','wb')
        os.chmod(self.root/'provider.log',0o600)
        self.process = subprocess.Popen([KANIDMD,'server','--config-path',str(self.root/'server.toml')],
                                        stdout=self.log,stderr=self.log,env={'PATH':'/nix/var/nix/profiles/default/bin'})
        ca = (self.root/'ca.pem').read_bytes()
        self.context = P['P']['tls_context'](ca,hashlib.sha256(ca).hexdigest())
        for _ in range(300):
            if self.process.poll() is not None:
                self.__exit__()
                raise FixtureError('PROVIDER_START_FAILED')
            if (self.root/'admin.sock').exists():
                try:
                    if self.request(None,'GET','/status')[0] == 200:
                        return self
                except Exception:
                    pass
            time.sleep(0.1)
        self.__exit__()
        raise FixtureError('PROVIDER_START_TIMEOUT')

    def certificates(self):
        subprocess.run([self.openssl,'req','-x509','-newkey','rsa:2048','-nodes',
                        '-keyout',str(self.root/'ca-key.pem'),'-out',str(self.root/'ca.pem'),
                        '-days','1','-subj','/CN=Invented qualification CA',
                        '-addext','basicConstraints=critical,CA:true'],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run([self.openssl,'req','-new','-newkey','rsa:2048','-nodes',
                        '-keyout',str(self.root/'key.pem'),'-out',str(self.root/'leaf.csr'),
                        '-subj','/CN=log.mrj.am'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (self.root/'leaf.ext').write_text('basicConstraints=critical,CA:false\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:log.mrj.am,DNS:localhost\n')
        subprocess.run([self.openssl,'x509','-req','-in',str(self.root/'leaf.csr'),
                        '-CA',str(self.root/'ca.pem'),'-CAkey',str(self.root/'ca-key.pem'),
                        '-CAcreateserial','-out',str(self.root/'leaf.pem'),'-days','1',
                        '-extfile',str(self.root/'leaf.ext')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def __exit__(self,*_):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=15)
        self.log.close()
        self.tmp.cleanup()

    def request(self,token,method,path,body=None,session=None):
        peer = P['P']['Loopback']('log.mrj.am',port=self.port,timeout=5,context=self.context)
        headers = {'Host':'log.mrj.am','Content-Type':'application/json','Accept':'application/json','Connection':'close'}
        if token is not None:
            headers['Authorization'] = 'Bearer '+token
        if session is not None:
            headers['x-kanidm-auth-session-id'] = session
        try:
            peer.request(method,path,body=None if body is None else P['encode'](body),headers=headers)
            response = peer.getresponse()
            raw = response.read(65537)
            check(len(raw) <= 65536,'FIXTURE_RESPONSE_BOUND')
            value = json.loads(raw) if raw else None
            return response.status,value,response.getheader('x-kanidm-auth-session-id')
        finally:
            peer.close()

    def ok(self,token,method,path,body=None):
        status,value,_ = self.request(token,method,path,body)
        check(status == 200,'FIXTURE_API_'+str(status)+'_'+method+'_'+path.split('/')[2])
        return value

    def login(self,name):
        check(name in ('admin','idm_admin'),'FIXTURE_NAME')
        # Fixture-only recovery: this socket exists inside a new temp directory.
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as admin:
            admin.settimeout(10)
            admin.connect(str(self.root/'admin.sock'))
            admin.sendall(P['encode']({'RecoverAccount':{'name':name}}))
            raw = b''
            for _ in range(20):
                raw += admin.recv(4096)
                check(len(raw) < 8192,'FIXTURE_RECOVERY_BOUND')
                try:
                    password = json.loads(raw)['RecoverAccount']['password']
                    break
                except json.JSONDecodeError:
                    continue
            else:
                raise FixtureError('FIXTURE_RECOVERY_FAILED')
        status,value,session = self.request(None,'POST','/v1/auth',{'step':{'init2':{'username':name,'issue':'token','privileged':True}}})
        check(status == 200 and 'choose' in value['state'],'FIXTURE_AUTH_INIT')
        status,value,session = self.request(None,'POST','/v1/auth',{'step':{'begin':'password'}},session=session)
        check(status == 200 and 'continue' in value['state'],'FIXTURE_AUTH_BEGIN')
        status,value,_ = self.request(None,'POST','/v1/auth',{'step':{'cred':{'password':password}}},session=session)
        self.passwords[name] = password
        password = None
        check(status == 200 and 'success' in value['state'],'FIXTURE_AUTH_FINISH')
        return value['state']['success']

    def cli_session(self,name):
        cache = self.root/(name+'-official-cache.json')
        for verb in ('login','reauth'):
            if verb == 'reauth' and not P['needs_reauth'](cache.read_bytes()):
                continue
            if verb == 'reauth':
                self.cli_reauths += 1
            master,slave = pty.openpty()
            process = subprocess.Popen([KANIDM,verb,'-H','https://localhost:'+str(self.port),
                '-C',str(self.root/'ca.pem'),'--token-cache-path',str(cache),'-D',name],
                stdin=slave,stdout=slave,stderr=slave,env={'PATH':str(Path(KANIDM).parent),'TERM':'dumb','LANG':'C.UTF-8'})
            os.close(slave)
            output = b''
            supplied = False
            deadline = time.monotonic()+45
            try:
                while process.poll() is None and time.monotonic() < deadline:
                    readable,_,_ = select.select([master],[],[],0.1)
                    if readable:
                        try:
                            chunk = os.read(master,4096)
                        except OSError:
                            break
                        output = (output+chunk)[-8192:]
                        if not supplied and b'password' in output.lower():
                            os.write(master,(self.passwords[name]+'\n').encode())
                            supplied = True
                if process.poll() is None:
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        raise FixtureError('OFFICIAL_CLI_'+verb.upper()+'_TIMEOUT_PASSWORD_SUPPLIED_'+str(supplied)) from None
                if process.returncode != 0 or not supplied:
                    flags = [term for term in ('certificate','connect','dns','terminal','auth','config','permission','error','unknownissuer','notvalidforname','causedasendentity','connection refused','self-signed','certificate verify failed','invalidsessionstate','sessionexpired','invalidrequeststate','notauthenticated','accessdenied','authenticationfailed','invalidstate','no valid authentication','http(400','http(401','http(403','notauthorised','sessionmaynotreauth','au0006credentialmaynotreauthenticate') if term.encode() in output.lower()]
                    raise FixtureError('OFFICIAL_CLI_'+verb.upper()+'_'+str(process.returncode)+'_'+str(supplied)+'_'+','.join(flags))
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
                os.close(master)
                output = b''
        check(cache.stat().st_mode & 0o777 == 0o600,'OFFICIAL_CLI_CACHE_MODE')
        token = P['cache_token'](cache.read_bytes())
        check(self.request(token,'GET','/v1/self')[0] == 200,'OFFICIAL_CLI_SESSION_VALID')
        return token


class MemoryFiles:
    def __init__(self,admission):
        self.values = {'admission':admission}
        self.writes = []
    def read(self,role):
        return self.values.get(role)
    def write(self,role,value):
        check(role not in self.values,'FIXTURE_OVERWRITE')
        self.values[role] = value
        self.writes.append(role)


def qualify():
    with Fixture() as f:
        identity,access = f.login('idm_admin'),f.login('admin')
        # The same pinned official CLI used by the human entry, password typed
        # only through its PTY, never an argument or environment variable.
        identity,access = f.cli_session('idm_admin'),f.cli_session('admin')
        f.ok(identity,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],
             'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
        f.ok(identity,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
        f.ok(access,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
        admission = f.ok(identity,'POST','/v1/service_account/mrjam-admission/_api_token',
                          {'label':'invented-existing-admission','expiry':int(time.time())+86400,'read_write':True})
        files = MemoryFiles(admission)
        protected_before = {group:f.ok(access,'GET','/v1/group/'+group)
                            for group in ('idm_high_privilege','idm_access_control_admins','idm_service_account_admins')}
        admission_before = f.ok(identity,'GET','/v1/service_account/mrjam-admission/_api_token')
        api = P['Api'](f.context,port=f.port)
        try:
            result = P['provision_workers'](api,identity,access,files,int(time.time()))
        except P['Refused']:
            if api.last_failure:
                raise FixtureError('CANDIDATE_HTTP_'+str(api.last_failure)) from None
            raise
        check(result['prepared'] and files.read('admission') == admission,'INITIAL_PROVISION')
        again = P['provision_workers'](P['Api'](f.context,port=f.port),identity,access,files,int(time.time()))
        check(again == result and files.writes == ['cycle','replay'],'IDEMPOTENT_WORKERS')
        check(protected_before == {group:f.ok(access,'GET','/v1/group/'+group) for group in protected_before},'OTHER_ROLES_UNCHANGED')
        check(admission_before == f.ok(identity,'GET','/v1/service_account/mrjam-admission/_api_token'),'ADMISSION_TOKEN_RECORD_UNCHANGED')
        f.ok(identity,'POST','/v1/person',{'attrs':{'name':['invented-deletion-person'],
            'displayname':['Invented person'],'mail':['invented@example.invalid']}})
        person = f.ok(identity,'GET','/v1/person/invented-deletion-person')
        subject = person['attrs']['uuid'][0]
        check(f.ok(files.read('cycle'),'GET','/v1/person/'+subject)['attrs']['mail'] == ['invented@example.invalid'],'CYCLE_MAIL_READ')
        for method,path,body in [('POST','/v1/person',{'attrs':{'name':['cycle-must-not-create'],'displayname':['Denied']}}),
                                 ('DELETE','/v1/person/'+subject,None),
                                 ('POST','/v1/group',{'attrs':{'name':['cycle-must-not-grant']}})]:
            check(f.request(files.read('cycle'),method,path,body)[0] == 403,'CYCLE_WRITE_DENIED')
        for method,path,body in [('POST','/v1/group',{'attrs':{'name':['admission-must-not-grant']}}),
                                 ('POST','/v1/service_account',{'attrs':{'name':['admission-must-not-provision'],'displayname':['Denied'],'entry_managed_by':['idm_admin']}})]:
            check(f.request(admission,method,path,body)[0] == 403,'ADMISSION_ADMINISTRATION_DENIED')
        # Acknowledge the native role is wider; the Unix adapter is the
        # application boundary. Never pretend this upstream token is DELETE-only.
        check(f.request(files.read('replay'),'GET','/v1/person/'+subject+'/_credential/_update_intent/600')[0] == 200,'REPLAY_UPSTREAM_ROLE_DOCUMENTED')
        check(f.request(files.read('replay'),'DELETE','/v1/person/'+subject)[0] == 200,'REPLAY_NATIVE_DELETE')
        absent_status = f.request(files.read('replay'),'DELETE','/v1/person/'+subject)[0]
        check(absent_status in (200,404),'REPLAY_NATIVE_IDEMPOTENCE_'+str(absent_status))
        for session in (identity,access):
            f.ok(session,'GET','/v1/logout')
            check(f.request(session,'GET','/v1/self')[0] in (401,403),'TEMPORARY_SESSION_REVOKED')
        return {'schema_version':1,'provider':'Kanidm 1.11.2','initial_provision':True,'idempotence':True,
                'official_cli_login':True,'official_cli_private_cache':True,
                'official_cli_existing_privilege_detected':f.cli_reauths == 0,
                'other_roles_unchanged':True,'admission_token_record_unchanged':True,
                'cycle_mail_read':True,'cycle_writes_denied':True,'admission_administration_denied':True,
                'replay_upstream_credential_reset_is_broader':True,'replay_delete_idempotent':True,
                'temporary_sessions_revoked':True}


if __name__ == '__main__':
    try:
        result = qualify()
    except FixtureError as error:
        print(json.dumps({'error':str(error)}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({'error':'QUALIFICATION_FAILED','type':type(error).__name__,
                          'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1)
    print(json.dumps(result,sort_keys=True))
