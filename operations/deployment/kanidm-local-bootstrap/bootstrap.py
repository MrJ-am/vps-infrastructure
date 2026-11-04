"""Fixed local rescue accounts -> existing owner role -> unchanged V3 workers."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import runpy
import signal
import socket
import stat
import struct
import sys
import time

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
PROVISION='/nix/store/13qs6kk65vss4k3mcb86aiv8nww1qazl-mrjam-kanidm-worker-provision-3'
ADMIN_SOCKET=Path('/run/kanidmd/admin.sock')
DATABASE=Path('/var/lib/kanidm/kanidm.db')
SERVICE_UID=983
SERVICE_GID=983
POLICY='mrjam-proprietaire-policy'
ADMINS='idm_admins'
NAMES=('idm_admin','admin')
NAME=re.compile(r'[a-z0-9_.-]{1,64}')
UUID=re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
STAGE='INITIALIZE'


class Refused(Exception):
    pass


def require(value):
    if not value:raise Refused()


def decode(raw):
    require(type(raw) is bytes and 0<len(raw)<=65536)
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result);result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(Refused()))


def load_probe():
    path=Path(__file__).with_name('builtin_probe.py')
    require(hashlib.sha256(path.read_bytes()).hexdigest()=='ce1832ffc9e857af28a3082aaf08d0da76950026f878d3a26de38477ff35e02f')
    spec=importlib.util.spec_from_file_location('fixed_builtin_projection',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class AdminSocket:
    def __init__(self,path=ADMIN_SOCKET,uid=SERVICE_UID,gid=SERVICE_GID):
        self.path,self.uid,self.gid=path,uid,gid

    def __call__(self,action,name):
        require(action in ('RecoverAccount','DisableAccount') and name in NAMES)
        meta=self.path.lstat()
        require(stat.S_ISSOCK(meta.st_mode) and (meta.st_uid,meta.st_gid)==(self.uid,self.gid)
                and stat.S_IMODE(meta.st_mode)==0o750 and os.path.realpath(self.path)==str(self.path))
        deadline=time.monotonic()+15
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(10);peer.connect(str(self.path))
            _,uid,gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            require((uid,gid)==(self.uid,self.gid))
            peer.sendall(json.dumps({action:{'name':name}},separators=(',',':')).encode())
            raw=b''
            while len(raw)<8192:
                require(time.monotonic()<deadline)
                peer.settimeout(max(.001,deadline-time.monotonic()))
                chunk=peer.recv(8192-len(raw));require(chunk);raw+=chunk
                try:value=json.loads(raw)
                except json.JSONDecodeError:continue
                if action=='DisableAccount':require(value=='Success');return None
                require(type(value) is dict and set(value)=={'RecoverAccount'})
                value=value['RecoverAccount'];require(type(value) is dict and set(value)=={'password'})
                password=value['password']
                require(type(password) is str and 16<=len(password)<=512 and all(32<=ord(c)<127 for c in password))
                return password
        raise Refused()


class ControlApi:
    def __init__(self,provision,context,port=8443):
        self.P,self.context,self.port=provision,context,port
        self.target=None;self.uuid=None;self.count=0

    def select(self,identifier):
        require(self.target is None and type(identifier) is str)
        require(NAME.fullmatch(identifier) or UUID.fullmatch(identifier))
        self.target=identifier

    def __call__(self,token,method,path,body=None,session=None):
        self.count+=1;require(self.count<=64)
        if path=='/v1/auth':
            require(token is None and method=='POST' and type(body) is dict and set(body)=={'step'})
            step=body['step'];require(type(step) is dict and len(step)==1)
            if 'init2' in step:
                item=step['init2'];require(type(item) is dict and set(item)=={'username','issue','privileged'}
                    and item['username'] in NAMES and item['issue']=='token' and item['privileged'] is True and session is None)
            elif 'begin' in step:require(step['begin']=='password' and session is not None)
            else:
                require(set(step)=={'cred'} and type(step['cred']) is dict and set(step['cred'])=={'password'}
                        and type(step['cred']['password']) is str and 16<=len(step['cred']['password'])<=512 and session is not None)
        elif method=='GET':
            allowed={'/v1/self','/v1/logout','/v1/group/'+POLICY,'/v1/group/'+ADMINS}
            if self.target:
                allowed|={'/v1/person/'+self.target,'/v1/person/'+self.target+'/_credential/_status'}
            require(path in allowed and body is None and session is None)
        else:
            require(method=='POST' and path=='/v1/group/'+ADMINS+'/_attr/member' and self.uuid is not None
                    and body==[self.uuid] and session is None)
        headers={'Host':'log.mrj.am','Content-Type':'application/json','Accept':'application/json','Connection':'close'}
        if token is not None:
            require(type(token) is str and len(token)<=16384 and self.P['TOKEN'].fullmatch(token));headers['Authorization']='Bearer '+token
        if session is not None:
            require(type(session) is str and len(session)<=4096 and self.P['TOKEN'].fullmatch(session));headers['x-kanidm-auth-session-id']=session
        peer=self.P['P']['Loopback']('log.mrj.am',port=self.port,timeout=5,context=self.context)
        try:
            peer.request(method,path,body=None if body is None else self.P['encode'](body),headers=headers)
            response=peer.getresponse();raw=response.read(65537)
            if path=='/v1/logout' and response.status==401:return None,None
            require(response.status==200 and response.getheader('Location') is None
                    and response.getheader('Content-Type','').split(';')[0]=='application/json' and len(raw)<=65536)
            return decode(raw),response.getheader('x-kanidm-auth-session-id')
        finally:peer.close()


def login(api,name,password):
    value,session=api(None,'POST','/v1/auth',{'step':{'init2':{'username':name,'issue':'token','privileged':True}}})
    require('password' in value.get('state',{}).get('choose',[]))
    value,session=api(None,'POST','/v1/auth',{'step':{'begin':'password'}},session=session)
    require('password' in value.get('state',{}).get('continue',[]))
    value,_=api(None,'POST','/v1/auth',{'step':{'cred':{'password':password}}},session=session)
    token=value.get('state',{}).get('success')
    require(type(token) is str and api.P['TOKEN'].fullmatch(token))
    return token


def owner_role(api,identity):
    P=api.P
    def get(path):return api(identity,'GET',path)[0]
    policy=P['attrs'](get('/v1/group/'+POLICY))
    require(policy.get('name')==[POLICY] and {'group','account_policy'}<=set(policy.get('class',[])))
    members=P['members'](policy,'member');require(len(members)==1)
    api.select(next(iter(members)))
    path='/v1/person/'+api.target
    before=P['attrs'](get(path))
    require({'person','account'}<=set(before.get('class',[])) and 'service_account' not in before.get('class',[]))
    require(type(before.get('uuid')) is list and len(before['uuid'])==1 and UUID.fullmatch(before['uuid'][0]))
    require(before['uuid'][0] not in ('00000000-0000-0000-0000-000000000000','00000000-0000-0000-0000-000000000018'))
    require(type(before.get('name')) is list and len(before['name'])==1 and NAME.fullmatch(before['name'][0]))
    require(api.target in (before['uuid'][0],before['name'][0]) and before.get('spn')==[before['name'][0]+'@log.mrj.am'])
    require('idm_high_privilege' in P['members'](before,'memberof'))
    credential=get(path+'/_credential/_status')
    api.uuid=before['uuid'][0]
    previous=P['members'](P['attrs'](get('/v1/group/'+ADMINS)),'member')
    added=before['name'][0] not in previous
    if added:api(identity,'POST','/v1/group/'+ADMINS+'/_attr/member',[api.uuid])
    require(P['members'](P['attrs'](get('/v1/group/'+ADMINS)),'member')==previous|{before['name'][0]})
    after=P['attrs'](get(path))
    excluded={'memberof','directmemberof','last_modified_cid'}
    require({k:v for k,v in before.items() if k not in excluded}=={k:v for k,v in after.items() if k not in excluded})
    require({'idm_admins','idm_service_account_admins','idm_group_admins'}<=P['members'](after,'memberof'))
    require(get(path+'/_credential/_status')==credential and P['attrs'](get('/v1/group/'+POLICY))==policy)
    return added


def execute(provision,context,admin,observe,files_factory,*,port=8443):
    global STAGE
    STAGE='BUILTIN_PRECONDITION'
    require(observe()['both_eligible'])
    api=ControlApi(provision,context,port);sessions=[];files=None;result=None
    attempted=False;cleanup_ok=True
    try:
        STAGE='RECOVER_RESCUE_ACCOUNTS';attempted=True
        for name in NAMES:
            password=admin('RecoverAccount',name)
            try:sessions.append(login(api,name,password))
            finally:password=None
        STAGE='OWNER_ROLE'
        added=owner_role(api,sessions[0])
        STAGE='FIXED_WORKER_PROVISION'
        files=files_factory()
        value=provision['provision_workers'](provision['Api'](context,port=port),sessions[0],sessions[1],files,int(time.time()))
        require(value['prepared'] is True)
        result={'schema_version':1,'code':'KANIDM_LOCAL_BOOTSTRAP_COMPLETE','owner_role_added':added,
                'owner_credentials_preserved':True,'workers_prepared':True,'admission_preserved':True,
                'credential_material_exported':False,'application_generation_changed':False}
    finally:
        # The operation deadline must not interrupt its bounded rescue cleanup.
        signal.alarm(0)
        if files is not None:
            try:files.close()
            except Exception:cleanup_ok=False
        for token in sessions:
            try:api(token,'GET','/v1/logout')
            except Exception:cleanup_ok=False
        sessions.clear()
        if attempted:
            for name in NAMES:
                try:admin('DisableAccount',name)
                except Exception:cleanup_ok=False
            try:cleanup_ok=observe()['both_eligible'] and cleanup_ok
            except Exception:cleanup_ok=False
        if not cleanup_ok:
            STAGE='RESCUE_CLEANUP_REQUIRED'
            raise Refused()
    result['rescue_accounts_disabled']=True
    result['dedicated_sessions_revoked']=True
    return result


def main():
    global STAGE
    require(len(sys.argv)==1 and os.geteuid()==0 and os.path.realpath('/run/current-system')==PREVIOUS)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    def interrupted(*_):raise Refused()
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    signal.signal(signal.SIGALRM,interrupted);signal.alarm(180)
    probe=load_probe()
    info=DATABASE.lstat();require((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(SERVICE_UID,SERVICE_GID,0o600))
    descriptor=os.open('/run/systemd/system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        meta=os.fstat(descriptor);require(meta.st_uid==0 and not meta.st_mode&0o022)
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not Path('/run/mrjam-kanidm-passkey-portal').exists() and not Path('/run/mrjam-kanidm-worker-login').exists())
        provision=runpy.run_path(PROVISION+'/libexec/provision.py',run_name='fixed_native_v3')
        public=provision['H']['strict_json'](Path(PROVISION+'/libexec/probe-public.json').read_bytes())
        require(set(public)=={'ca_sha256'})
        context=provision['P']['tls_context'](Path(PROVISION+'/libexec/ca.pem').read_bytes(),public['ca_sha256'])
        return execute(provision,context,AdminSocket(),lambda:probe.observe(DATABASE),provision['TokenFiles'])
    finally:
        os.close(descriptor);signal.alarm(0)


if __name__=='__main__':
    try:print(json.dumps(main(),sort_keys=True,separators=(',',':')))
    except Exception:
        print(json.dumps({'schema_version':1,'code':'KANIDM_LOCAL_BOOTSTRAP_REFUSED','stage':STAGE},sort_keys=True,separators=(',',':')))
        raise SystemExit(1)
