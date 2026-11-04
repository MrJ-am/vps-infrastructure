"""Native disposable provider; passwords/passkeys/tokens are invented only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import socket
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

Q=load('software_signer',ROOT/'operations/deployment/passkey-portal/qualify.py')
M=load('authentication_helper',ROOT/'operations/deployment/passkey-nginx/capability_matrix_fixture.py')
B=load('local_bootstrap',Path(__file__).with_name('bootstrap.py'))
PROBE=load('builtin_probe',Path(__file__).with_name('builtin_probe.py'))
P=runpy.run_path(B.PROVISION+'/libexec/provision.py',run_name='immutable_v3')


def require(value,code):
    if not value:raise RuntimeError(code)


class Files(Q.F['MemoryFiles']):
    def close(self):pass


def setup(f):
    identity,access=f.login('idm_admin'),f.login('admin')
    owner='invented-fixed-owner';key=Q.enroll(f,identity,owner)
    f.ok(identity,'POST','/v1/group',{'attrs':{'name':[B.POLICY]}})
    f.ok(identity,'POST','/v1/group/'+B.POLICY+'/_attr/class',['account_policy'])
    f.ok(identity,'PUT','/v1/group/'+B.POLICY+'/_attr/credential_type_minimum',['mfa'])
    f.ok(identity,'POST','/v1/group/'+B.POLICY+'/_attr/member',[owner])
    f.ok(access,'POST','/v1/group/idm_high_privilege/_attr/member',[owner])
    token=M.authenticate(f,owner,key)
    status=f.ok(identity,'GET','/v1/person/'+owner+'/_credential/_status')
    f.ok(identity,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
    f.ok(identity,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
    f.ok(access,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
    admission=f.ok(identity,'POST','/v1/service_account/mrjam-admission/_api_token',{'label':'invented-existing','expiry':int(time.time())+86400,'read_write':True})
    return identity,access,owner,key,token,status,admission


def native_socket(f):
    return B.AdminSocket(f.root/'admin.sock',os.getuid(),os.getgid())


def disabled(f,admin):
    for name in B.NAMES:admin('DisableAccount',name)
    require(PROBE.observe(f.root/'kanidm.db')['both_eligible'],'DISABLED_PREFLIGHT')


def qualify():
    checks=[]
    with Q.F['Fixture']() as f:
        identity,access,owner,key,owner_session,status,admission=setup(f)
        admin=native_socket(f);files=Files(admission)
        disabled(f,admin)
        require(all(f.request(token,'GET','/v1/self')[0]==401 for token in (identity,access)),'DISABLE_RETAINS_SESSION')
        checks.append('native-disable-invalidates-builtin-sessions-and-readonly-probe-accepts-only-disabled-rescue-accounts')
        calls=[]
        def counted(action,name):calls.append((action,name));return admin(action,name)
        result=B.execute(P,f.context,counted,lambda:PROBE.observe(f.root/'kanidm.db'),lambda:files,port=f.port)
        require(result['code']=='KANIDM_LOCAL_BOOTSTRAP_COMPLETE' and result['owner_role_added'],'FIXED_HELPER_FAILED')
        require(calls==[('RecoverAccount','idm_admin'),('RecoverAccount','admin'),('DisableAccount','idm_admin'),('DisableAccount','admin')],'ADMIN_SOCKET_SCOPE')
        checks.append('exact-helper-recovers-only-two-builtin-service-accounts-and-finally-disables-both')
        require(f.request(owner_session,'GET','/v1/self')[0]==200,'OWNER_SESSION_REVOKED')
        fresh=M.authenticate(f,owner,key)
        require(f.ok(fresh,'GET','/v1/person/'+owner+'/_credential/_status')==status,'OWNER_CREDENTIAL_STATUS_CHANGED')
        capabilities=P['members'](P['self_attrs'](f.ok(fresh,'GET','/v1/self')),'memberof')
        require({'idm_admins','idm_service_account_admins','idm_group_admins','idm_high_privilege'}<=capabilities,'OWNER_ROLE_NOT_EFFECTIVE')
        checks.append('same-human-passkey-and-existing-session-survive-role-addition-with-identical-credential-status')
        require(files.read('admission')==admission and files.writes==['cycle','replay'],'FIXED_TOKEN_WRITES')
        for role in ('admission','cycle','replay'):require(P['token_identity'](P['Api'](f.context,port=f.port),files.read(role),role),'NATIVE_TOKEN_SCOPE')
        checks.append('unchanged-v3-functions-create-and-verify-two-fixed-worker-tokens-preserving-admission')
        before=files.values.copy()
        result=B.execute(P,f.context,admin,lambda:PROBE.observe(f.root/'kanidm.db'),lambda:files,port=f.port)
        require(not result['owner_role_added'] and files.values==before and files.writes==['cycle','replay'],'SECOND_CALL_NOT_IDEMPOTENT')
        checks.append('repeat-helper-is-idempotent-for-owner-role-and-existing-worker-capabilities')
        # Fail after recovery but before provision to exercise the real finally.
        changed=dict(P)
        def refused(*_):raise RuntimeError('INVENTED_PROVIDER_FAILURE')
        changed['provision_workers']=refused
        try:B.execute(changed,f.context,admin,lambda:PROBE.observe(f.root/'kanidm.db'),lambda:files,port=f.port)
        except RuntimeError:pass
        else:raise RuntimeError('INJECTED_FAILURE_IGNORED')
        require(PROBE.observe(f.root/'kanidm.db')['both_eligible'] and files.values==before,'FAILURE_LEFT_RESCUE_OPEN')
        checks.append('injected-provision-failure-still-revokes-and-disables-rescue-accounts')
        def partial(action,name):
            if action=='RecoverAccount' and name=='admin':raise RuntimeError('INVENTED_RECOVERY_TRANSPORT_FAILURE')
            return admin(action,name)
        try:B.execute(P,f.context,partial,lambda:PROBE.observe(f.root/'kanidm.db'),lambda:files,port=f.port)
        except RuntimeError:pass
        else:raise RuntimeError('PARTIAL_RECOVERY_FAILURE_IGNORED')
        require(PROBE.observe(f.root/'kanidm.db')['both_eligible'],'PARTIAL_RECOVERY_LEFT_RESCUE_OPEN')
        checks.append('failure-between-two-recoveries-still-disables-both-builtins')
        require(f.request(owner_session,'GET','/v1/self')[0]==200 and f.request(fresh,'GET','/v1/self')[0]==200,'OWNER_SESSION_LOST_AFTER_ERRORS')
        checks.append('human-sessions-survive-success-repeat-and-error-cleanup')
        for token in (owner_session,fresh):f.ok(token,'GET','/v1/logout')
    # A policy with two people is not silently treated as a sole owner.
    with Q.F['Fixture']() as f:
        identity,access,owner,key,token,status,admission=setup(f)
        Q.enroll(f,identity,'invented-second-person')
        f.ok(identity,'POST','/v1/group/'+B.POLICY+'/_attr/member',['invented-second-person'])
        admin=native_socket(f);disabled(f,admin);files=Files(admission)
        try:B.execute(P,f.context,admin,lambda:PROBE.observe(f.root/'kanidm.db'),lambda:files,port=f.port)
        except B.Refused:pass
        else:raise RuntimeError('AMBIGUOUS_OWNER_ACCEPTED')
        require(PROBE.observe(f.root/'kanidm.db')['both_eligible'] and not files.writes,'AMBIGUOUS_OWNER_MUTATED_WORKERS')
        observed=P['members'](P['self_attrs'](f.ok(token,'GET','/v1/self')),'memberof')
        require('idm_admins' not in observed,'AMBIGUOUS_OWNER_GRANTED_ROLE')
        checks.append('ambiguous-owner-policy-refused-without-role-or-worker-write-and-builtins-reclosed')
    return {'schema_version':1,'passed':True,'production_access':False,'real_kanidm':True,'real_software_p256_passkeys':True,
            'checks':checks,'bootstrap_source_sha256':hashlib.sha256(Path(__file__).with_name('bootstrap.py').read_bytes()).hexdigest(),
            'limits':['Invented provider state and persons only. TokenFiles is an in-memory sink here; its unchanged actual file implementation was separately qualified in the V3 systemd VM.',
                      'Socket path/UID/GID and API port are synthetic parameters of execute/AdminSocket; production main has fixed observed bindings and no runtime arguments.',
                      'Credential status and successful authentication with the original passkey are observed; no private key or credential contents leave the fixture.']}


if __name__=='__main__':
    try:print(json.dumps(qualify(),sort_keys=True))
    except Exception as error:
        print(json.dumps({'passed':False,'error':type(error).__name__,'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1)
