"""Root VM execution of unchanged helper main with invented fixed bindings."""
import ast
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def require(value,code):
    if not value:raise RuntimeError(code)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def authenticate(f,name,key):
    code,value,session=f.request(None,'POST','/v1/auth',{'step':{'init2':{'username':name,'issue':'token','privileged':True}}})
    require(code==200,'AUTH_INIT')
    code,value,session=f.request(None,'POST','/v1/auth',{'step':{'begin':'passkey'}},session=session)
    require(code==200,'AUTH_BEGIN')
    challenge=value['state']['continue'][0]['passkey']
    code,value,_=f.request(None,'POST','/v1/auth',{'step':{'cred':{'passkey':key.assertion(challenge)}}},session=session)
    require(code==200 and 'success' in value['state'],'AUTH_SIGNATURE')
    return value['state']['success']


def sealed(source,target,bindings):
    text=source.read_text();lines=text.splitlines(keepends=True);tree=ast.parse(text);found=set()
    for node in reversed(tree.body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in bindings:
            key=node.targets[0].id;found.add(key)
            value=bindings[key]
            replacement='Path('+repr(str(value))+')' if isinstance(value,Path) else repr(value)
            lines[node.lineno-1:node.end_lineno]=[key+'='+replacement+'\n']
    require(found==set(bindings),'BINDING_ASSIGNMENTS')
    raw=''.join(lines)
    require([ast.get_source_segment(text,node) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))]
            ==[ast.get_source_segment(raw,node) for node in ast.parse(raw).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))],'HELPER_FUNCTION_OR_CLASS_CHANGED')
    target.write_text(raw);target.chmod(0o600)


def qualify(source,tls,provision):
    Q=load('software_signer',source/'passkey-portal/qualify.py')
    B=load('local_bootstrap',source/'kanidm-local-bootstrap/bootstrap.py')
    Probe=load('readonly_builtin_probe',source/'kanidm-local-bootstrap/builtin_probe.py')
    checks=[];outputs=[]
    with Q.F['Fixture'](port=8443,ca_directory=tls,openssl='/run/current-system/sw/bin/openssl') as f:
        # The production database was independently observed at0600; the
        # disposable daemon inherits the test driver's different umask.
        (f.root/'kanidm.db').chmod(0o600)
        identity,access=f.login('idm_admin'),f.login('admin')
        owner='invented-owner';key=Q.enroll(f,identity,owner)
        f.ok(identity,'POST','/v1/group',{'attrs':{'name':[B.POLICY]}})
        f.ok(identity,'POST','/v1/group/'+B.POLICY+'/_attr/class',['account_policy'])
        f.ok(identity,'PUT','/v1/group/'+B.POLICY+'/_attr/credential_type_minimum',['mfa'])
        f.ok(identity,'POST','/v1/group/'+B.POLICY+'/_attr/member',[owner])
        f.ok(access,'POST','/v1/group/idm_high_privilege/_attr/member',[owner])
        owner_session=authenticate(f,owner,key)
        credential=f.ok(identity,'GET','/v1/person/'+owner+'/_credential/_status')
        members=f.ok(identity,'GET','/v1/group/idm_admins')['attrs']['member']
        f.ok(identity,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
        f.ok(identity,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
        f.ok(access,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
        admission=f.ok(identity,'POST','/v1/service_account/mrjam-admission/_api_token',{'label':'invented-existing','expiry':int(time.time())+86400,'read_write':True})
        state=Path('/var/lib/mrjam-identite');state.mkdir(mode=0o700)
        file=state/'kanidm-admission.token';file.write_text(admission+'\n');file.chmod(0o600)
        original=(file.stat().st_ino,file.stat().st_mtime_ns,file.read_bytes())
        admin=B.AdminSocket(f.root/'admin.sock',0,0)
        for name in B.NAMES:admin('DisableAccount',name)
        require(Probe.observe(f.root/'kanidm.db')['both_eligible'],'NATIVE_PREFLIGHT')
        work=Path('/run/synthetic-bootstrap');work.mkdir(mode=0o700)
        (work/'builtin_probe.py').write_bytes((source/'kanidm-local-bootstrap/builtin_probe.py').read_bytes())
        bindings={'PREVIOUS':os.path.realpath('/run/current-system'),'PROVISION':str(provision),'ADMIN_SOCKET':f.root/'admin.sock',
                  'DATABASE':f.root/'kanidm.db','SERVICE_UID':0,'SERVICE_GID':0}
        executable=work/'bootstrap.py';sealed(source/'kanidm-local-bootstrap/bootstrap.py',executable,bindings)
        wrong=work/'wrong.py';sealed(source/'kanidm-local-bootstrap/bootstrap.py',wrong,{**bindings,'PREVIOUS':'/nix/store/INVENTED_WRONG_GENERATION'})
        def invoke(path=executable,success=True):
            result=subprocess.run([sys.executable,'-I','-S',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=200)
            require(not result.stderr,'HELPER_STDERR_NOT_CLOSED');outputs.append(result.stdout)
            value=json.loads(result.stdout)
            stage=value.get('stage','NONE')
            require(stage in ('NONE','INITIALIZE','BUILTIN_PRECONDITION','RECOVER_RESCUE_ACCOUNTS','OWNER_ROLE','FIXED_WORKER_PROVISION','RESCUE_CLEANUP_REQUIRED'),'UNKNOWN_STAGE')
            require((result.returncode==0)==success and value['code']==('KANIDM_LOCAL_BOOTSTRAP_COMPLETE' if success else 'KANIDM_LOCAL_BOOTSTRAP_REFUSED'),'HELPER_EXIT_'+stage)
            return value
        invoke(wrong,False);require(Probe.observe(f.root/'kanidm.db')['both_eligible'],'GENERATION_REFUSAL_MUTATED_RESCUE')
        checks.append('fixed-main-wrong-generation-refuses-before-recovery')
        descriptor=os.open('/run/systemd/system',os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB);invoke(success=False)
        finally:os.close(descriptor)
        require(Probe.observe(f.root/'kanidm.db')['both_eligible'],'LOCK_REFUSAL_MUTATED_RESCUE')
        checks.append('fixed-main-concurrent-opener-lock-refuses-before-recovery')
        marker=Path('/run/mrjam-kanidm-passkey-portal');marker.mkdir(mode=0o700)
        invoke(success=False);require(marker.is_dir() and Probe.observe(f.root/'kanidm.db')['both_eligible'],'PORTAL_REFUSAL_MUTATED_STATE');marker.rmdir()
        checks.append('fixed-main-existing-portal-runtime-is-preserved-and-refused')
        result=invoke();require(result['workers_prepared'] and result['owner_role_added'],'FIXED_MAIN_DID_NOT_COMPLETE')
        require(Probe.observe(f.root/'kanidm.db')['both_eligible'],'MAIN_LEFT_RESCUE_OPEN')
        checks.append('fixed-main-real-unix-recovery-and-v3-tokenfiles-complete-with-rescue-accounts-disabled')
        require((file.stat().st_ino,file.stat().st_mtime_ns,file.read_bytes())==original,'ADMISSION_REPLACED')
        def fingerprints():
            values={}
            for role in ('admission','cycle','replay'):
                path=state/('kanidm-'+role+'.token');meta=path.stat()
                require((meta.st_uid,meta.st_gid,meta.st_nlink,meta.st_mode&0o777)==(0,0,1,0o600),'CREDENTIAL_METADATA')
                values[role]=(meta.st_ino,meta.st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest())
            require(len({item[2] for item in values.values()})==3,'TOKEN_DISTINCTNESS');return values
        before=fingerprints();require(state.stat().st_mode&0o777==0o700,'STATE_MODE')
        checks.append('actual-three-root-private-token-files-have-exact-modes-and-admission-is-preserved')
        fresh=authenticate(f,owner,key)
        require(f.ok(fresh,'GET','/v1/person/'+owner+'/_credential/_status')==credential and f.request(owner_session,'GET','/v1/self')[0]==200,'OWNER_CREDENTIAL_OR_SESSION_CHANGED')
        after=f.ok(fresh,'GET','/v1/group/idm_admins')['attrs']['member']
        require(set(after)==set(members)|{owner+'@log.mrj.am'},'OTHER_MEMBERS_CHANGED')
        checks.append('sole-owner-role-added-with-other-members-same-passkey-and-existing-session-preserved')
        again=invoke();require(not again['owner_role_added'] and fingerprints()==before and Probe.observe(f.root/'kanidm.db')['both_eligible'],'MAIN_REPEAT_CHANGED_STATE')
        checks.append('fixed-main-repeat-preserves-token-inodes-and-role-idempotence')
        require(not Path('/run/mrjam-kanidm-worker-login').exists(),'HUMAN_CACHE_CREATED')
        sensitive=[admission,identity,access,owner_session,fresh,*f.passwords.values(),*(path.read_text().strip() for path in state.glob('kanidm-*.token'))]
        require(not any(value.encode() in b''.join(outputs) for value in sensitive),'PRIVATE_VALUE_EXPORTED')
        checks.append('no-human-cache-created-and-closed-outputs-exclude-invented-secrets')
    return {'passed':True,'checks':checks,'real_token_files':True,'functions_and_classes_unchanged':True,
            'invented_binding_constants':sorted(bindings),'actual_proton_pass_browser':False}


if __name__=='__main__':
    try:print(json.dumps(qualify(*(Path(value) for value in sys.argv[1:])),sort_keys=True))
    except Exception as error:
        print(json.dumps({'passed':False,'error':type(error).__name__,'closed_failure':str(error) if isinstance(error,RuntimeError) else None,
                          'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1)
