#!/usr/bin/env python3
"""Closed native Kanidm worker provisioning. No reset and no secret output."""
import fcntl
import base64
import json
import os
from pathlib import Path
import resource
import runpy
import signal
import stat
import sys
import time

ROOT = Path(__file__).resolve().parent
P = runpy.run_path(str(ROOT/'probe.py'), run_name='provision_transport')
H = P['HELPERS']
Refused = H['Refused']
TOKEN = P['TOKEN']
UUID = P['UUID']
STATE = Path('/var/lib/mrjam-identite')
CREDENTIALS = Path('/run/credentials/mrjam-kanidm-worker-provision.service')
SERVICES = {'admission':'mrjam-admission', 'cycle':'mrjam-cycle', 'replay':'mrjam-replay'}
MANAGER = 'idm_service_account_admins'
ACCESS = 'idm_access_control_admins'
HIGH = 'idm_high_privilege'
MAIL = 'idm_account_mail_read'
LABEL = 'mrjam-worker-provision-v1'
PEOPLE = 'idm_people_admins'
NEW = ('cycle','replay')


def request_permitted(method,path,body):
    if method == 'GET':
        return body is None and path in {
            '/v1/self','/v1/logout','/v1/group/'+MAIL,'/v1/group/'+PEOPLE,
            *(f'/v1/service_account/{SERVICES[r]}' for r in NEW),
            *(f'/v1/service_account/{SERVICES[r]}/_api_token' for r in NEW),
        }
    if method != 'POST':
        return False
    if path == '/v1/service_account':
        return any(body == {'attrs':{'name':[SERVICES[role]],'displayname':['Mrjam '+role+' worker'],
                                    'entry_managed_by':[MANAGER]}} for role in NEW)
    if path == '/v1/group/'+MAIL+'/_attr/member':
        return body == [SERVICES['cycle']]
    if path == '/v1/group/'+PEOPLE+'/_attr/member':
        return body == [SERVICES['replay']]
    for role in NEW:
        if path == '/v1/service_account/'+SERVICES[role]+'/_api_token':
            return (isinstance(body,dict) and set(body) == {'label','expiry','read_write','compact'}
                    and body['label'] == LABEL and type(body['expiry']) is int
                    and int(time.time())+89*86400 < body['expiry'] <= int(time.time())+90*86400+60
                    and body['read_write'] is (role == 'replay') and body['compact'] is False)
    return False


def require(condition):
    if not condition:
        raise Refused()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def scalar(attrs, key):
    value = attrs.get(key)
    require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], str))
    return value[0]


def members(attrs, key):
    value = attrs.get(key, [])
    require(isinstance(value, list) and all(isinstance(v, str) for v in value) and len(value) == len(set(value)))
    return set(v.removesuffix('@log.mrj.am') for v in value)


def attrs(value):
    require(isinstance(value, dict) and set(value) == {'attrs'} and isinstance(value['attrs'], dict))
    result = value['attrs']
    require(all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v)
                for k, v in result.items()))
    return result


def self_attrs(value):
    require(isinstance(value, dict) and set(value) == {'youare'})
    return attrs(value['youare'])


class Api:
    """Transport accepts only operations used by this fixed provisioner."""
    def __init__(self, context, *, port=8443):
        self.context = context
        self.port = port
        self.count = 0
        self.last_failure = None

    def __call__(self, token, method, path, body=None):
        require(isinstance(token, str) and TOKEN.fullmatch(token))
        require(request_permitted(method,path,body) and self.count < 100)
        self.count += 1
        peer = P['Loopback']('log.mrj.am', port=self.port, timeout=5, context=self.context)
        try:
            data = None if body is None else encode(body)
            require(data is None or len(data) <= 8192)
            peer.request(method, path, body=data, headers={'Host':'log.mrj.am',
                         'Authorization':'Bearer '+token, 'Content-Type':'application/json',
                         'Accept':'application/json', 'Connection':'close'})
            response = peer.getresponse()
            raw = response.read(65537)
            require(len(raw) <= 65536 and response.getheader('Location') is None)
            if response.status != 200:
                self.last_failure = (method,path,response.status)
            require(response.status == 200)
            require(response.getheader('Content-Type','').split(';')[0].strip() == 'application/json')
            return P['parse_json'](raw)
        finally:
            peer.close()


def cache_token(raw):
    """Only a dedicated official-CLI cache with one instance and one session."""
    value = H['strict_json'](raw)
    require(set(value) == {'instances'} and isinstance(value['instances'], dict) and set(value['instances']) == {''})
    instance = value['instances']['']
    require(isinstance(instance, dict) and set(instance) == {'keys','tokens'}
            and isinstance(instance['keys'], dict) and isinstance(instance['tokens'], dict))
    require(len(instance['tokens']) == 1)
    name, token = next(iter(instance['tokens'].items()))
    require(isinstance(name,str) and name.endswith('@log.mrj.am') and isinstance(token,str) and TOKEN.fullmatch(token))
    return token


def needs_reauth(raw):
    # UX hint from a new cache verified by the official CLI. This is never an
    # authorization decision: Kanidm verifies the original bearer on every API
    # call, and an edited/unverified purpose cannot grant any server privilege.
    token = cache_token(raw)
    parts = token.split('.')
    require(len(parts) == 3)
    claims = H['strict_json'](base64.urlsafe_b64decode(parts[1]+'='*(-len(parts[1])%4)))
    purpose = claims.get('purpose')
    require(isinstance(purpose,dict) and set(purpose) == {'readwrite'})
    access = purpose['readwrite']
    require(isinstance(access,dict) and set(access) == {'expiry'})
    expiry = access['expiry']
    require(expiry is None or type(expiry) is int)
    return expiry is None or expiry <= int(time.time())+140


def service(api, admin, role):
    value = api(admin, 'GET', '/v1/service_account/'+SERVICES[role])
    if value is None:
        return None
    entry = attrs(value)
    require(scalar(entry,'name') == SERVICES[role])
    require(members(entry,'class') == {'object','account','service_account','memberof'})
    require(UUID.fullmatch(scalar(entry,'uuid')))
    if role in NEW:
        require(members(entry,'entry_managed_by') == {MANAGER})
        require(not any(entry.get(k) for k in ('account_expire','account_valid_from','mail','primary_credential','passkeys')))
        allowed = {'idm_all_accounts',MAIL} if role == 'cycle' else {'idm_all_accounts',PEOPLE,HIGH}
        require(members(entry,'memberof') <= allowed)
    return entry


def token_identity(api, token, role):
    found = self_attrs(api(token,'GET','/v1/self'))
    require(scalar(found,'name') == SERVICES[role] and 'service_account' in members(found,'class'))
    require(UUID.fullmatch(scalar(found,'uuid')))
    expected = {'admission':{'idm_people_on_boarding',MAIL,HIGH,'idm_all_accounts'},
                'cycle':{MAIL,'idm_all_accounts'},'replay':{PEOPLE,HIGH,'idm_all_accounts'}}[role]
    actual = members(found,'memberof')
    require(actual == expected)
    return scalar(found,'uuid')


def token_records(api, admin, role):
    records = api(admin,'GET','/v1/service_account/'+SERVICES[role]+'/_api_token')
    require(isinstance(records,list) and len(records) <= 32)
    for item in records:
        require(isinstance(item,dict) and item.get('label') == LABEL
                and item.get('purpose') == ('readonly' if role == 'cycle' else 'readwrite'))
        expiry = item.get('expiry')
        require(type(expiry) is int and int(time.time()) < expiry <= int(time.time())+90*86400+60)
    return records


def provision_workers(api, identity, access, files, now):
    """Create the two missing fixed services; retain the admission credential."""
    require(type(now) is int)
    capabilities = members(self_attrs(api(identity,'GET','/v1/self')),'memberof')
    require({MANAGER,'idm_admins'} <= capabilities)
    require(ACCESS in members(self_attrs(api(access,'GET','/v1/self')),'memberof'))
    original = files.read('admission')
    require(original is not None)
    token_identity(api,original,'admission')
    existing = {role:service(api,identity,role) for role in NEW}
    present = {role:files.read(role) for role in NEW}
    groups = {'cycle':(access,MAIL),'replay':(identity,PEOPLE)}
    before = {role:members(attrs(api(admin,'GET','/v1/group/'+group)),'member')
              for role,(admin,group) in groups.items()}
    for role in NEW:
        require(present[role] is None or existing[role] is not None)
        if present[role] is not None:
            token_identity(api,present[role],role)
        if existing[role] is not None:
            records = token_records(api,identity,role)
            require(all(item['label'] == LABEL for item in records) and len(records) <= 1)
            require(not records or present[role] is not None)
    for role in NEW:
        if existing[role] is None:
            api(identity,'POST','/v1/service_account',{'attrs':{'name':[SERVICES[role]],
                'displayname':['Mrjam '+role+' worker'],'entry_managed_by':[MANAGER]}})
            require(service(api,identity,role) is not None)
        admin,group = groups[role]
        if SERVICES[role] not in before[role]:
            api(admin,'POST','/v1/group/'+group+'/_attr/member',[SERVICES[role]])
        after = members(attrs(api(admin,'GET','/v1/group/'+group)),'member')
        require(after == before[role]|{SERVICES[role]})
        if present[role] is None:
            value = api(identity,'POST','/v1/service_account/'+SERVICES[role]+'/_api_token',
                        {'label':LABEL,'expiry':now+90*86400,'read_write':role == 'replay','compact':False})
            require(isinstance(value,str) and TOKEN.fullmatch(value) and len(value.encode())+1 <= 4096)
            files.write(role,value)
            present[role] = value
        token_identity(api,present[role],role)
    require(files.read('admission') == original and len({original,*present.values()}) == 3)
    return {'schema_version':1,'prepared':True,'admission_preserved':True,'tokens_distinct':True,
            'replay_upstream_people_admins':True,'replay_credential_requires_isolated_adapter':True}


class TokenFiles:
    def __init__(self, path=STATE):
        self.fd = H['open_directory'](path)
        meta = os.fstat(self.fd)
        require(meta.st_uid == 0 and meta.st_gid == 0 and stat.S_IMODE(meta.st_mode) == 0o700)
        self.lock = os.open('.worker-provision.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.fd)
        lock = os.fstat(self.lock)
        require(stat.S_ISREG(lock.st_mode) and lock.st_uid == 0 and lock.st_nlink == 1 and stat.S_IMODE(lock.st_mode) == 0o600)
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)


    def read(self, role):
        require(role in SERVICES)
        try:
            raw = H['read_file'](self.fd,'kanidm-'+role+'.token',4096)
        except FileNotFoundError:
            return None
        value = raw.decode('ascii').removesuffix('\n')
        require(TOKEN.fullmatch(value))
        return value

    def write(self, role, value):
        require(role in NEW and TOKEN.fullmatch(value))
        raw = (value+'\n').encode()
        require(len(raw) <= 4096)
        name = 'kanidm-'+role+'.token'
        temporary = '.'+name+'.pending'
        try:
            os.stat(name,dir_fd=self.fd,follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError()
        # Exclusive files never overwrite an existing or interrupted credential.
        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.fd)
        try:
            remaining = memoryview(raw)
            while remaining:
                count = os.write(fd,remaining)
                require(count > 0)
                remaining = remaining[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(temporary,name,src_dir_fd=self.fd,dst_dir_fd=self.fd,follow_symlinks=False)
        os.unlink(temporary,dir_fd=self.fd)
        os.fsync(self.fd)

    def close(self):
        os.close(self.lock)
        os.close(self.fd)


def administrative_cache(directory, name):
    # systemd gives a root service 0400 files. The 0440 staging reader in
    # adapt.py is deliberately not reused: that mode describes an ACL granted
    # to a different service UID, not these root-only temporary sessions.
    require(name in ('identity-session','access-session'))
    descriptor = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0
                and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o400
                and 0 < before.st_size <= 65536 and bool(os.fstatvfs(descriptor).f_flag & os.ST_RDONLY))
        chunks = []
        remaining = before.st_size+1
        while remaining:
            chunk = os.read(descriptor,remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)
                == (after.st_size,after.st_mtime_ns,after.st_ctime_ns))
        raw = b''.join(chunks)
        require(len(raw) == before.st_size)
        return raw
    finally:
        os.close(descriptor)


def administrative_credentials():
    fd = H['open_directory'](CREDENTIALS)
    try:
        meta = os.fstat(fd)
        require(meta.st_uid == 0 and meta.st_gid == 0 and stat.S_IMODE(meta.st_mode) == 0o500)
        require(bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY))
        require(H['entries'](fd) == {'identity-session','access-session'})
        for name in ('identity-session','access-session'):
            yield cache_token(administrative_cache(fd,name))
    finally:
        os.close(fd)


def main():
    files = None
    api = None
    sessions = []
    ok = False
    try:
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        os.umask(0o077)
        def timeout(*_):
            raise Refused()
        signal.signal(signal.SIGALRM,timeout)
        signal.alarm(120)
        require(len(sys.argv) == 1 and os.geteuid() == 0)
        public = H['strict_json']((ROOT/'probe-public.json').read_bytes())
        require(set(public) == {'ca_sha256'})
        api = Api(P['tls_context']((ROOT/'ca.pem').read_bytes(),public['ca_sha256']))
        for session in administrative_credentials():
            sessions.append(session)
        files = TokenFiles()
        result = provision_workers(api,*sessions,files,int(time.time()))
        ok = True
    except Exception:
        result = {'error':'KANIDM_WORKER_PROVISION_REFUSED'}
    finally:
        if files is not None:
            files.close()
        # Revoke exactly the dedicated supplied sessions, never all user sessions.
        for session in set(sessions):
            try:
                api(session,'GET','/v1/logout')
            except Exception:
                ok = False
                result = {'error':'KANIDM_WORKER_PROVISION_SESSION_CLEANUP_REQUIRED'}
    print(json.dumps(result,sort_keys=True,separators=(',',':')),file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
