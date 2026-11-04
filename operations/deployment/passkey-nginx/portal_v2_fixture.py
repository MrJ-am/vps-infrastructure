"""Independent inactive-unit upgrade and native rights through HTTPS/Unix/systemd."""
import ast
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def require(value,code):
    if not value:raise RuntimeError(code)


H=load('previous_fixture_utilities',Path('/etc/synthetic-nginx/previous-portal-fixture.py'))
manager=H.manager
fingerprint=H.fingerprint
wait_socket=H.wait_socket
RUNTIME=Path('/run/systemd/system')
PORTAL='mrjam-kanidm-passkey-portal.service'
PROVISION='mrjam-kanidm-worker-provision.service'
ROUTE='mrjam-passkey-nginx-route.service'


def seal(name,binding,label):
    source=Path('/etc/synthetic-nginx',name).read_bytes()
    replacements={'PREVIOUS':os.path.realpath('/run/current-system'),'BINDING':binding}
    tree=ast.parse(source);lines=source.splitlines(keepends=True);found=set()
    for node in reversed(tree.body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
            key=node.targets[0].id;found.add(key)
            lines[node.lineno-1:node.end_lineno]=[(key+' = '+repr(replacements[key])+'\n').encode()]
    require(found==set(replacements),'EXACT_CONSTANT_BINDINGS')
    raw=b''.join(lines)
    before=[ast.get_source_segment(source.decode(),n) for n in tree.body if isinstance(n,ast.FunctionDef)]
    after=[ast.get_source_segment(raw.decode(),n) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)]
    require(before==after,'HELPER_FUNCTION_CHANGED')
    path=Path('/run/synthetic-'+label+'.py');path.write_bytes(raw);path.chmod(0o600)
    return path


def invoke(path,success,code):
    result=subprocess.run([sys.executable,'-I','-S',str(path)],stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    value=json.loads(result.stdout)
    require((result.returncode==0)==success and value.get('code')==code,'CLOSED_HELPER_RESULT_'+path.name)
    if success:
        require(value['credential_creation'] is False and value['application_generation_changed'] is False,'HELPER_SCOPE')
    return value


def fragment(unit):
    return os.path.realpath(manager('show',unit,'--value','--property=FragmentPath').stdout.decode().strip())


def descriptor(path):
    return {'path':path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def inactive(unit):
    return manager('show',unit,'--value','--property=ActiveState').stdout.strip() in (b'inactive',b'failed')


def upgrade_fixture(checks):
    next_paths=json.loads(Path('/etc/synthetic-nginx/next-units.json').read_bytes())
    binding={unit:{version:descriptor(path) for version,path in next_paths[unit].items()} for unit in (PORTAL,PROVISION)}
    for unit in binding:(RUNTIME/unit).symlink_to(binding[unit]['previous']['path'])
    manager('daemon-reload')
    good=seal('upgrade_passkey_units.py',binding,'upgrade')
    wrong=json.loads(json.dumps(binding));wrong[PROVISION]['next']['sha256']='0'*64
    bad=seal('upgrade_passkey_units.py',wrong,'upgrade-bad-hash')
    original={unit:os.readlink(RUNTIME/unit) for unit in binding}
    def unchanged():
        require(all(os.readlink(RUNTIME/unit)==target for unit,target in original.items()),'UPGRADE_REFUSAL_REPLACED_LINK')
    invoke(bad,False,'PASSKEY_UNIT_UPGRADE_REFUSED');unchanged()
    checks.append('upgrade-bad-hash-refused-before-either-link-change')
    foreign=RUNTIME/PROVISION;foreign.unlink();foreign.write_bytes(b'[Unit]\nDescription=INVENTED FOREIGN\n[Service]\nExecStart=/bin/false\n')
    preserved=foreign.read_bytes();manager('daemon-reload')
    invoke(good,False,'PASSKEY_UNIT_UPGRADE_REFUSED')
    require(foreign.read_bytes()==preserved and os.readlink(RUNTIME/PORTAL)==original[PORTAL],'FOREIGN_UNIT_CHANGED')
    foreign.unlink();foreign.symlink_to(original[PROVISION]);manager('daemon-reload')
    checks.append('upgrade-foreign-unit-preserved-with-other-link-unchanged')
    fd=os.open(RUNTIME,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        invoke(good,False,'PASSKEY_UNIT_UPGRADE_REFUSED');unchanged()
    finally:os.close(fd)
    checks.append('upgrade-refuses-concurrent-directory-lock')
    manager('start',PORTAL);wait_socket()
    pid=manager('show',PORTAL,'--value','--property=MainPID').stdout
    invoke(good,False,'PASSKEY_UNIT_UPGRADE_REFUSED');unchanged()
    require(manager('show',PORTAL,'--value','--property=MainPID').stdout==pid,'UPGRADE_STOPPED_ACTIVE_PORTAL')
    manager('stop',PORTAL)
    checks.append('upgrade-active-old-unit-refused-without-stop-or-link-change')
    value=invoke(good,True,'PASSKEY_INACTIVE_UNITS_UPDATED')
    require(value['services_started'] is False and all(inactive(unit) for unit in binding),'UPGRADE_STARTED_UNIT')
    require(all(fragment(unit)==versions['next']['path'] for unit,versions in binding.items()),'UPGRADE_WRONG_FRAGMENT')
    require(not Path('/run/mrjam-kanidm-passkey-portal').exists(),'UPGRADE_LEFT_RUNTIME')
    checks.append('real-upgrade-replaces-both-exact-units-with-no-activation')
    # Simulate interruption after the first exact replacement, before reload.
    for unit in binding:
        (RUNTIME/unit).unlink();(RUNTIME/unit).symlink_to(binding[unit]['previous']['path'])
    manager('daemon-reload')
    (RUNTIME/PORTAL).unlink();(RUNTIME/PORTAL).symlink_to(binding[PORTAL]['next']['path'])
    invoke(good,True,'PASSKEY_INACTIVE_UNITS_UPDATED')
    before={unit:(RUNTIME/unit).lstat().st_ino for unit in binding}
    invoke(good,True,'PASSKEY_INACTIVE_UNITS_UPDATED')
    require(all((RUNTIME/unit).lstat().st_ino==inode and inactive(unit) for unit,inode in before.items()),'UPGRADE_REPEAT_CHANGED_LINK_OR_STATE')
    checks.append('partial-upgrade-retry-completes-and-repeat-preserves-inodes')
    return good,binding


def native_expiration(Q,f,portal_package,name,key):
    C=load('independent_clock_portal',portal_package/'libexec/portal.py')
    ca=(f.root/'ca.pem').read_bytes()
    api=C.Api(ca,hashlib.sha256(ca).hexdigest(),f.port)
    actual=time.monotonic();clock=[actual]
    C.time=SimpleNamespace(monotonic=lambda:clock[0],time=time.time)
    deliveries=[]
    p=C.Portal(api,lambda *_:deliveries.append(True))
    first=p.act('begin',{'identity':name,'access':None});nonce=first['transaction']
    clock[0]=actual+250
    result=p.act('assert',{'transaction':nonce,'assertion':key.assertion(first['challenge'])})
    require(result['status']=='READY' and result['expires_in']==300,'AUTHENTICATION_DID_NOT_RENEW')
    token=p.transactions[nonce]['tokens'][0]
    require(p.transactions[nonce]['deadline']==actual+550,'AUTHENTICATION_RENEWAL_BOUND')
    clock[0]=actual+551
    require(p.act('commit',{'transaction':nonce})=={'status':'EXPIRED'} and not deliveries,'EXPIRED_DELIVERY')
    require(f.request(token,'GET','/v1/self')[0]==401,'EXPIRED_SESSION_REMAINS')
    clock[0]=actual
    p=C.Portal(api,lambda *_:deliveries.append(True));clock[0]=actual+700
    first=p.act('begin',{'identity':name,'access':None});nonce=first['transaction']
    clock[0]=actual+701
    result=p.act('assert',{'transaction':nonce,'assertion':key.assertion(first['challenge'])})
    require(result['status']=='READY' and result['expires_in']==49,'GLOBAL_MARGIN_NOT_RESERVED')
    token=p.transactions[nonce]['tokens'][0];clock[0]=actual+750
    require(p.act('commit',{'transaction':nonce})=={'status':'EXPIRED'} and not deliveries,'GLOBAL_EXPIRED_DELIVERY')
    require(f.request(token,'GET','/v1/self')[0]==401,'GLOBAL_EXPIRED_SESSION_REMAINS')


def qualify(source,tls,portal_package,provision_package,result_probe):
    require(os.geteuid()==0,'SYNTHETIC_VM_ROOT_ONLY')
    Q=load('software_signing_fixture',source/'passkey-portal/qualify.py')
    N=load('nginx_fixture',Path('/etc/synthetic-nginx/fixture.py'))
    checks=[];responses=[]
    hashes=json.loads(Path('/etc/synthetic-nginx/production-source-hashes.json').read_bytes())
    for kind,package in (('portal',portal_package),('provision',provision_package)):
        for name,digest in hashes[kind].items():require(hashlib.sha256((package/'libexec'/name).read_bytes()).hexdigest()==digest,'PRODUCTION_SOURCE_CHANGED')
    require(hashlib.sha256((result_probe/'libexec/result_probe.py').read_bytes()).hexdigest()==hashes['result_probe'],'PROBE_SOURCE_CHANGED')
    checks.append('new-portal-provisioner-and-probe-sources-match-frozen-production-packages')
    with Q.F['Fixture'](port=8443,ca_directory=tls,openssl='/run/current-system/sw/bin/openssl') as f:
        identity_admin,access_admin=f.login('idm_admin'),f.login('admin')
        names=('independent-identity','independent-access','independent-single','independent-ordinary','independent-service','independent-group')
        identity,access,single,ordinary,service,group=names
        keys={name:Q.enroll(f,identity_admin,name) for name in names}
        f.ok(identity_admin,'POST','/v1/group/idm_admins/_attr/member',[identity,single])
        f.ok(access_admin,'POST','/v1/group/idm_access_control_admins/_attr/member',[access])
        f.ok(identity_admin,'POST','/v1/group/idm_service_account_admins/_attr/member',[service])
        f.ok(identity_admin,'POST','/v1/group/idm_group_admins/_attr/member',[group])
        f.ok(identity_admin,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
        f.ok(identity_admin,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
        f.ok(access_admin,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
        admission=f.ok(identity_admin,'POST','/v1/service_account/mrjam-admission/_api_token',{'label':'invented-existing-admission','expiry':int(time.time())+86400,'read_write':True})
        state=Path('/var/lib/mrjam-identite');state.mkdir(mode=0o700)
        admitted=state/'kanidm-admission.token';admitted.write_text(admission+'\n');admitted.chmod(0o600)
        admission_original=(admitted.stat().st_ino,admitted.stat().st_mtime_ns,admitted.read_bytes())
        N.bind()
        upgrader,upgrade_binding=upgrade_fixture(checks)
        opener_binding={unit:descriptor(fragment(unit)) for unit in (PORTAL,ROUTE)}
        opener=seal('start_passkey_portal.py',opener_binding,'open-v2')
        def reopen():
            invoke(opener,True,'PASSKEY_PORTAL_OPEN');wait_socket();N.ready()
        def restart():
            manager('stop',ROUTE);manager('stop',PORTAL);reopen()
        reopen();checks.append('real-opener-starts-upgraded-portal-and-unchanged-route')
        pids={unit:manager('show',unit,'--value','--property=MainPID').stdout for unit in (PORTAL,ROUTE)}
        invoke(opener,False,'PASSKEY_PORTAL_OPEN_REFUSED');invoke(upgrader,False,'PASSKEY_UNIT_UPGRADE_REFUSED')
        require(all(manager('show',unit,'--value','--property=MainPID').stdout==pid for unit,pid in pids.items()),'DUPLICATE_HELPER_DISTURBED_SESSION')
        checks.append('active-opener-and-upgrader-refusals-preserve-running-pids')

        def request(action=None,body=None,origin='https://log.mrj.am',path=None):
            peer=Q.P['P']['Loopback']('log.mrj.am',port=443,timeout=160,context=f.context)
            try:
                peer.request('POST' if action else 'GET',path or Q.C.PREFIX+'api/'+action,
                             body=None if body is None else json.dumps(body).encode(),
                             headers={'Host':'log.mrj.am','Origin':origin,'Content-Type':'application/json','Sec-Fetch-Site':'same-origin'})
                response=peer.getresponse();raw=response.read(65537)
                require(len(raw)<=65536 and response.getheader('Set-Cookie') is None,'RESPONSE_BOUND_OR_COOKIE')
                require("default-src 'none'" in response.getheader('Content-Security-Policy','') and response.getheader('Cache-Control')=='no-store','RESPONSE_POLICY')
                responses.append(raw);return response.status,raw
            finally:peer.close()
        def act(action,body):
            status,raw=request(action,body);require(status==200,'HTTP_ACTION_'+action.upper());return json.loads(raw)
        def begin(name,other=None):
            first=act('begin',{'identity':name,'access':other})
            require(set(first)=={'status','account','challenge','transaction','expires_in'} and first['account']==1,'FIRST_CHALLENGE_SHAPE')
            require(0<first['expires_in']<=300,'CHALLENGE_COUNTDOWN')
            answer=act('assert',{'transaction':first['transaction'],'assertion':keys[name].assertion(first['challenge'])})
            return first['transaction'],answer
        def second(nonce,challenge,name):
            require(challenge['status']=='PASSKEY_REQUIRED' and challenge['account']==2,'SECOND_CHALLENGE')
            return act('assert',{'transaction':nonce,'assertion':keys[name].assertion(challenge['challenge'])})
        def ready(value):
            require(set(value)=={'status','permissions','expires_in'} and value['status']=='READY' and all(value['permissions'].values())
                    and set(value['permissions'])=={'identity_admins','identity_services','mail_group_management'} and 0<value['expires_in']<=300,'READY_WITHOUT_PROVED_RIGHTS')
        def not_started():
            require(manager('show',PROVISION,'--value','--property=ExecMainStartTimestampMonotonic').stdout.strip()==b'0','REFUSAL_STARTED_PROVISION')
            require(not Path('/run/mrjam-kanidm-worker-login').exists() and not (state/'kanidm-cycle.token').exists() and not (state/'kanidm-replay.token').exists(),'REFUSAL_CREATED_CREDENTIAL')
        for path,name in ((Q.C.PREFIX,'index.html'),(Q.C.PREFIX+'portal.js','portal.js'),(Q.C.PREFIX+'style.css','style.css')):
            code,raw=request(path=path);require(code==200 and raw==(portal_package/'libexec'/name).read_bytes(),'TLS_ASSET_CHANGED')
        checks.append('exact-v2-assets-over-real-https-with-csp-and-no-cookie')
        require(request('begin',{'identity':identity,'access':None},origin='https://wrong.invalid')[0]==400,'CROSS_ORIGIN')
        require(request('commit',{'transaction':'A'*43})[0]==400,'UNKNOWN_CSRF');not_started()
        checks.append('origin-and-csrf-refusals-precede-private-unit')
        nonce,value=begin(ordinary);require(value['status']=='IDENTITY_RIGHTS_REQUIRED' and not any(value['permissions'].values()),'ORDINARY_READY');not_started()
        checks.append('real-ordinary-person-explicitly-refused-before-ready-and-no-unit-start')
        nonce,value=begin(service);require(value['status']=='IDENTITY_RIGHTS_REQUIRED' and value['permissions']['identity_services'] and not value['permissions']['identity_admins'],'SERVICE_ONLY_READY');not_started()
        checks.append('real-service-admin-without-idm-admin-refused-before-ready')
        nonce,value=begin(identity,ordinary);value=second(nonce,value,ordinary)
        require(value['status']=='ACCESS_RIGHTS_REQUIRED' and not value['permissions']['mail_group_management'],'WRONG_SECOND_READY');not_started()
        checks.append('real-insufficient-second-person-explicitly-refused-before-ready')
        nonce,value=begin(identity,access);ready(second(nonce,value,access))
        f.ok(access_admin,'DELETE','/v1/group/idm_access_control_admins/_attr/member',[access])
        value=act('commit',{'transaction':nonce});require(value['status']=='ACCESS_RIGHTS_REQUIRED','REMOVED_ACCESS_NOT_RECHECKED');not_started()
        checks.append('native-access-right-removed-after-ready-refuses-before-unit-start')
        restart()
        actual=f.ok(identity_admin,'GET','/v1/person/'+single)['attrs']['memberof']
        groups={item.removesuffix('@log.mrj.am') for item in actual}
        require('idm_admins' in groups and 'idm_group_admins' in groups and 'idm_access_control_admins' not in groups,'SINGLE_PERSON_ROLES')
        nonce,value=begin(single);ready(value)

        def commit(transaction,count):
            sessions=set();stop=threading.Event()
            def watch():
                while not stop.wait(.002):
                    for name in ('identity.json','access.json'):
                        try:sessions.add(Q.P['cache_token'](Path('/run/mrjam-kanidm-worker-login',name).read_bytes()))
                        except (OSError,ValueError,KeyError):pass
            observer=threading.Thread(target=watch);observer.start()
            try:require(act('commit',{'transaction':transaction})=={'status':'COMPLETE'},'COMMIT_FAILED')
            finally:stop.set();observer.join()
            require(len(sessions)==count and not Path('/run/mrjam-kanidm-worker-login').exists(),'SESSION_COUNT_OR_CACHE')
            require(all(f.request(token,'GET','/v1/self')[0]==401 for token in sessions),'DEDICATED_SESSION_REMAINS')
        commit(nonce,1)
        require(manager('show',PROVISION,'--value','--property=ExecMainStatus').stdout.strip()==b'0','REAL_V3_EXIT')
        checks.append('idm-admins-without-access-control-admins-completes-real-loadcredential-v3')
        checks.append('one-fresh-administrative-session-revoked-and-private-cache-removed')
        require((admitted.stat().st_ino,admitted.stat().st_mtime_ns,admitted.read_bytes())==admission_original,'ADMISSION_REPLACED')
        before=fingerprint()
        result=subprocess.run([str(result_probe/'bin/mrjam-kanidm-worker-result-probe')],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
        observed=json.loads(result.stdout)
        require(result.returncode==0 and observed['write_authorization_proved'] is False and observed['all_tokens_present'] and observed['tokens_distinct'] and observed['all_expected_memberships'],'RESULT_PROBE')
        checks.append('closed-result-probe-validates-three-distinct-tokens-and-admission-preserved')
        require(request('commit',{'transaction':nonce})[0]==400 and fingerprint()==before,'COMMIT_REPLAY')
        checks.append('completed-transaction-replay-refused-with-token-inodes-unchanged')
        restart()
        nonce,value=begin(identity,group);ready(second(nonce,value,group));commit(nonce,2)
        require(fingerprint()==before,'IDEMPOTENCE_ROTATED_TOKEN')
        checks.append('separate-group-admin-only-second-person-completes-idempotently')
        restart()
        nonce,value=begin(identity);ready(value)
        f.ok(identity_admin,'DELETE','/v1/group/idm_admins/_attr/member',[identity])
        started=manager('show',PROVISION,'--value','--property=ExecMainStartTimestampMonotonic').stdout
        require(act('commit',{'transaction':nonce})['status']=='IDENTITY_RIGHTS_REQUIRED','REMOVED_IDENTITY_NOT_RECHECKED')
        require(manager('show',PROVISION,'--value','--property=ExecMainStartTimestampMonotonic').stdout==started and fingerprint()==before,'RIGHT_REFUSAL_STARTED_UNIT_OR_WROTE')
        checks.append('native-identity-right-removed-after-ready-refuses-with-existing-tokens-preserved')
        native_expiration(Q,f,portal_package,single,keys[single])
        checks.append('real-passkey-session-with-invented-clock-renews-then-expires-and-reserves-global-margin')
        require(f.request(identity_admin,'GET','/v1/self')[0]==200 and f.request(access_admin,'GET','/v1/self')[0]==200,'UNRELATED_ADMIN_SESSION_REVOKED')
        private=[admission,identity_admin,access_admin,*f.passwords.values(),*(p.read_text().strip() for p in state.glob('kanidm-*.token'))]
        journal=subprocess.check_output(['journalctl','-u',PORTAL,'-u',PROVISION,'--no-pager'],stderr=subprocess.DEVNULL)
        require(not any(secret.encode() in b''.join(responses)+journal for secret in private),'PRIVATE_VALUE_LEAK')
        checks.append('no-private-values-in-browser-or-journal-and-unrelated-sessions-retained')
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            if not N.DROPIN.exists() and not N.WORK.joinpath('state.json').exists() and not Path('/run/mrjam-kanidm-passkey-portal').exists():break
            time.sleep(.2)
        require(not N.DROPIN.exists() and not N.WORK.joinpath('state.json').exists() and not Path('/run/mrjam-kanidm-passkey-portal').exists()
                and not Path('/run/mrjam-kanidm-worker-login').exists(),'NATURAL_EXPIRATION_NOT_CLEAN')
        checks.append('natural-unit-expiration-restores-nginx-and-cleans-new-portal')
    return {'passed':True,'checks':checks,'actual_proton_pass_browser':False,'real_https_unix_portal':True,
            'real_loadcredential_provisioner':True,'real_kanidm':True,'upgrader_functions_unchanged':True,
            'opener_functions_unchanged':True,'upgrade_invented_bindings':upgrade_binding,'opener_invented_bindings':opener_binding,
            'access_required_branch':'Not claimed native: idm_admins normally inherits group administration; separately exercised by author state-machine tests.'}


if __name__=='__main__':
    try:print(json.dumps(qualify(*(Path(value) for value in sys.argv[1:])),sort_keys=True))
    except Exception as error:
        locations=[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'passed':False,'code':str(error) if isinstance(error,RuntimeError) else type(error).__name__,'synthetic_failure_locations':locations}))
        raise SystemExit(1)
