"""Independent HTTPS + Unix portal + LoadCredential v2 execution in a VM."""
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


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def require(value,code):
    if not value:raise RuntimeError(code)


def manager(*args,check=True):
    result=subprocess.run(["systemctl",*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=160)
    if check:require(result.returncode==0,"FIXTURE_SYSTEMD_FAILED")
    return result


def wait_socket():
    until=time.monotonic()+10
    while time.monotonic()<until:
        if Path("/run/mrjam-kanidm-passkey-portal/http.sock").is_socket():return
        time.sleep(.05)
    raise RuntimeError("PORTAL_SOCKET_NOT_READY")


def fingerprint():
    result={}
    for role in ("admission","cycle","replay"):
        path=Path("/var/lib/mrjam-identite/kanidm-"+role+".token")
        meta=path.stat()
        require((meta.st_uid,meta.st_gid,meta.st_nlink,meta.st_mode&0o777)==(0,0,1,0o600),"TOKEN_METADATA_CHANGED")
        result[role]=(meta.st_ino,meta.st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def opener_fixture():
    source=Path('/etc/synthetic-nginx/start_passkey_portal.py').read_bytes()
    bindings={}
    for unit in ('mrjam-kanidm-passkey-portal.service','mrjam-passkey-nginx-route.service'):
        raw=manager('show',unit,'--value','--property=FragmentPath').stdout.decode().strip()
        path=os.path.realpath(raw)
        bindings[unit]={'path':path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    generation=os.path.realpath('/run/current-system')
    def sealed(path,binding):
        replacements={'PREVIOUS':generation,'BINDING':binding}
        tree=ast.parse(source);lines=source.splitlines(keepends=True);found=set()
        for node in reversed(tree.body):
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
                name=node.targets[0].id;found.add(name)
                lines[node.lineno-1:node.end_lineno]=[(name+' = '+repr(replacements[name])+'\n').encode()]
        require(found==set(replacements),'OPENER_CONSTANT_BINDINGS')
        raw=b''.join(lines)
        # Every function stays byte-for-byte identical; only the two constants
        # differ between the reviewed template and this invented sealed copy.
        before=[ast.get_source_segment(source.decode(),n) for n in tree.body if isinstance(n,ast.FunctionDef)]
        after=[ast.get_source_segment(raw.decode(),n) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)]
        require(before==after,'OPENER_FUNCTION_CHANGED')
        path.write_bytes(raw);path.chmod(0o600)
        return path
    executable=sealed(Path('/run/synthetic-start-portal.py'),bindings)
    wrong=json.loads(json.dumps(bindings));wrong['mrjam-kanidm-passkey-portal.service']['sha256']='0'*64
    bad=sealed(Path('/run/synthetic-start-portal-bad-hash.py'),wrong)
    def invoke(path=executable,success=True):
        result=subprocess.run([sys.executable,'-I','-S',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,timeout=180)
        value=json.loads(result.stdout)
        require((result.returncode==0)==success,'OPENER_STATUS')
        require(value.get('code')==('PASSKEY_PORTAL_OPEN' if success else 'PASSKEY_PORTAL_OPEN_REFUSED'),'OPENER_CLOSED_RESULT')
        if success:require(value['credential_creation'] is False and value['application_generation_changed'] is False,'OPENER_SCOPE')
        return value
    invoke(bad,False)
    require(not Path('/run/mrjam-kanidm-passkey-portal/http.sock').exists(),'BAD_HASH_STARTED_PORTAL')
    foreign=Path('/run/systemd/system/mrjam-kanidm-passkey-portal.service')
    foreign.write_bytes(b'[Unit]\nDescription=INVENTED-FOREIGN-UNIT\n[Service]\nExecStart=/bin/false\n')
    preserved=foreign.read_bytes();manager('daemon-reload')
    invoke(success=False)
    require(foreign.read_bytes()==preserved,'OPENER_REPLACED_FOREIGN_UNIT')
    foreign.unlink();manager('daemon-reload')
    require(not Path('/run/mrjam-kanidm-passkey-portal/http.sock').exists(),'FOREIGN_UNIT_STARTED_PORTAL')
    descriptor=os.open('/run/systemd/system',os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        invoke(success=False)
    finally:os.close(descriptor)
    require(not Path('/run/mrjam-kanidm-passkey-portal/http.sock').exists(),'CONCURRENT_OPENER_STARTED_PORTAL')
    invoke()
    pids={unit:manager('show',unit,'--value','--property=MainPID').stdout for unit in bindings}
    invoke(success=False)
    require(all(manager('show',unit,'--value','--property=MainPID').stdout==pid for unit,pid in pids.items()),'DUPLICATE_OPENER_STOPPED_ACTIVE_SESSION')
    return invoke,bindings


def qualify(source,tls,portal_package,provision_package,result_probe):
    require(os.geteuid()==0,"INVENTED_VM_ROOT_ONLY")
    Q=load("software_webauthn_fixture",source/"passkey-portal/qualify.py")
    N=load("nginx_fixture",Path("/etc/synthetic-nginx/fixture.py"))
    checks=[];responses=[]
    # Actual package source bytes are checked independently of wrappers/CA.
    production_hashes=json.loads(Path("/etc/synthetic-nginx/production-source-hashes.json").read_bytes())
    for filename in ("portal.py","index.html","portal.js","style.css"):
        require(hashlib.sha256((portal_package/"libexec"/filename).read_bytes()).hexdigest()==production_hashes['portal'][filename],"PORTAL_SOURCE_DIFFERS_FROM_PRODUCTION")
    require(hashlib.sha256((result_probe/"libexec/result_probe.py").read_bytes()).hexdigest()==production_hashes['result_probe'],"RESULT_PROBE_SOURCE_DIFFERS_FROM_PRODUCTION")
    with Q.F['Fixture'](port=8443,ca_directory=tls,openssl="/run/current-system/sw/bin/openssl") as f:
        identity_admin,access_admin=f.login("idm_admin"),f.login("admin")
        names=("independent-identity","independent-access","independent-single")
        keys={name:Q.enroll(f,identity_admin,name) for name in names}
        f.ok(identity_admin,"POST","/v1/group/idm_admins/_attr/member",[names[0],names[2]])
        f.ok(access_admin,"POST","/v1/group/idm_access_control_admins/_attr/member",[names[1],names[2]])
        f.ok(identity_admin,"POST","/v1/service_account",{"attrs":{"name":["mrjam-admission"],"displayname":["Invented admission"],"entry_managed_by":["idm_admin"]}})
        f.ok(identity_admin,"POST","/v1/group/idm_people_on_boarding/_attr/member",["mrjam-admission"])
        f.ok(access_admin,"POST","/v1/group/idm_account_mail_read/_attr/member",["mrjam-admission"])
        admission=f.ok(identity_admin,"POST","/v1/service_account/mrjam-admission/_api_token",{"label":"invented-existing-admission","expiry":int(time.time())+86400,"read_write":True})
        state=Path("/var/lib/mrjam-identite");state.mkdir(mode=0o700)
        admitted=state/"kanidm-admission.token";admitted.write_text(admission+"\n");admitted.chmod(0o600)
        admission_original=(admitted.stat().st_ino,admitted.stat().st_mtime_ns,admitted.read_bytes())
        N.bind()
        reopen,opener_bindings=opener_fixture();wait_socket();N.ready()
        checks.extend(['opener-wrong-hash-refused-before-start','opener-foreign-runtime-unit-preserved-before-start',
                       'opener-directory-lock-refuses-concurrent-run','real-opener-installs-starts-and-active-second-call-never-stops-session'])

        def request(action=None,body=None,origin="https://log.mrj.am",path=None):
            target=path or (Q.C.PREFIX+"api/"+action)
            peer=Q.P['P']['Loopback']("log.mrj.am",port=443,timeout=160,context=f.context)
            headers={"Host":"log.mrj.am","Origin":origin,"Content-Type":"application/json","Sec-Fetch-Site":"same-origin"}
            try:
                peer.request("POST" if action else "GET",target,body=None if body is None else json.dumps(body).encode(),headers=headers)
                response=peer.getresponse();raw=response.read(65537)
                require(len(raw)<=65536,"BROWSER_RESPONSE_BOUND")
                require(response.getheader("Set-Cookie") is None,"PORTAL_SESSION_COOKIE")
                require("default-src 'none'" in response.getheader("Content-Security-Policy",""),"PORTAL_CSP_LOST")
                require(response.getheader("Cache-Control")=="no-store","PORTAL_CACHEABLE")
                responses.append(raw)
                return response.status,raw
            finally:peer.close()

        def act(action,body):
            status,raw=request(action,body)
            require(status==200,"PORTAL_ACTION_REFUSED_"+action.upper())
            return json.loads(raw)

        for path,filename in ((Q.C.PREFIX,"index.html"),(Q.C.PREFIX+"portal.js","portal.js"),(Q.C.PREFIX+"style.css","style.css")):
            code,raw=request(path=path)
            require(code==200 and raw==(portal_package/"libexec"/filename).read_bytes(),"HTTPS_STATIC_SOURCE_CHANGED")
        checks.append("exact-real-portal-assets-over-tls-with-strict-csp-no-cookie")
        code,_=request("begin",{"identity":names[0],"access":names[1]},origin="https://wrong.invalid")
        require(code==400,"CROSS_ORIGIN_ACCEPTED")
        code,_=request("commit",{"transaction":"A"*43})
        require(code==400,"UNKNOWN_TRANSACTION_ACCEPTED")
        require(not Path("/run/mrjam-kanidm-worker-login").exists(),"REFUSAL_CREATED_CACHE")
        checks.append("cross-origin-and-unknown-csrf-refused-before-private-unit")

        first=act("begin",{"identity":names[0],"access":names[1]});nonce=first["transaction"]
        require(set(first)=={"status","account","challenge","transaction"} and first["account"]==1,"FIRST_CHALLENGE_SHAPE")
        second=act("assert",{"transaction":nonce,"assertion":keys[names[0]].assertion(first["challenge"])})
        require(second["status"]=="PASSKEY_REQUIRED" and second["account"]==2,"SECOND_ACCOUNT_NOT_REQUIRED")
        require(act("assert",{"transaction":nonce,"assertion":keys[names[1]].assertion(second["challenge"])})=={"status":"READY"},"SEPARATE_PASSKEYS_NOT_READY")
        checks.append("real-provider-p256-signatures-for-separate-privileged-accounts")

        def commit(transaction,expected_sessions):
            sessions=set();stop=threading.Event()
            def watch():
                while not stop.wait(.002):
                    for name in ("identity.json","access.json"):
                        try:sessions.add(Q.P['cache_token'](Path("/run/mrjam-kanidm-worker-login",name).read_bytes()))
                        except (OSError,ValueError,KeyError):pass
            observer=threading.Thread(target=watch);observer.start()
            try:require(act("commit",{"transaction":transaction})=={"status":"COMPLETE"},"REAL_COMMIT_NOT_COMPLETE")
            finally:stop.set();observer.join()
            require(len(sessions)==expected_sessions,"PRIVATE_SYNTHETIC_SESSIONS_NOT_OBSERVED")
            require(not Path("/run/mrjam-kanidm-worker-login").exists(),"CACHE_REMAINS")
            require(all(f.request(token,"GET","/v1/self")[0]==401 for token in sessions),"DEDICATED_SESSION_NOT_REVOKED")

        commit(nonce,2)
        require((admitted.stat().st_ino,admitted.stat().st_mtime_ns,admitted.read_bytes())==admission_original,"ADMISSION_TOKEN_REPLACED")
        before=fingerprint()
        checks.append("real-loadcredential-systemd-v2-created-worker-capabilities-and-preserved-admission")
        checks.append("fresh-administrative-sessions-revoked-and-login-cache-removed")
        result=subprocess.run([str(result_probe/"bin/mrjam-kanidm-worker-result-probe")],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
        require(result.returncode==0,"RESULT_PROBE_REFUSED")
        observed=json.loads(result.stdout)
        require(observed.get("write_authorization_proved") is False and observed.get("all_tokens_present") is True
                and observed.get("tokens_distinct") is True and observed.get("all_expected_memberships") is True
                and not Path("/run/mrjam-kanidm-worker-login").exists(),"PROBE_SCOPE_CHANGED")
        checks.append("real-closed-result-probe-validates-three-tokens-without-writing")
        code,_=request("commit",{"transaction":nonce});require(code==400,"COMMIT_REPLAY_ACCEPTED")
        require(fingerprint()==before,"REPLAY_CHANGED_TOKENS")
        checks.append("completed-transaction-replay-refused-with-credentials-unchanged")

        # A fresh process is required after the one allowed committed action.
        manager("stop","mrjam-passkey-nginx-route")
        manager("stop","mrjam-kanidm-passkey-portal")
        reopen();wait_socket();N.ready()
        one=act("begin",{"identity":names[2],"access":None})
        require(act("assert",{"transaction":one["transaction"],"assertion":keys[names[2]].assertion(one["challenge"])})=={"status":"READY"},"SINGLE_ACCOUNT_NOT_READY")
        commit(one["transaction"],1)
        require(fingerprint()==before,"SINGLE_ACCOUNT_ROTATED_TOKENS")
        checks.append("single-account-new-session-and-real-v2-idempotence")

        require(f.request(identity_admin,"GET","/v1/self")[0]==200 and f.request(access_admin,"GET","/v1/self")[0]==200,"UNRELATED_ADMIN_SESSION_REVOKED")
        private=[admission,identity_admin,access_admin,*f.passwords.values(),*(path.read_text().strip() for path in state.glob("kanidm-*.token"))]
        journal=subprocess.check_output(["journalctl","-u","mrjam-kanidm-passkey-portal","-u","mrjam-kanidm-worker-provision","--no-pager"],stderr=subprocess.DEVNULL)
        require(not any(secret.encode() in b"".join(responses)+journal for secret in private),"PRIVATE_SYNTHETIC_VALUE_LEAK")
        checks.append("browser-and-journal-exclude-private-values-unrelated-sessions-retained")
        # Observe the actual unit runtime limit, its rollback and the portal's
        # signal-aware cleanup. No manual stop substitutes for expiration.
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if not N.DROPIN.exists() and not N.WORK.joinpath("state.json").exists() and not Path('/run/mrjam-kanidm-passkey-portal').exists():break
            time.sleep(.2)
        require(not N.DROPIN.exists() and not N.WORK.joinpath("state.json").exists(),"ROUTE_NOT_RESTORED")
        require(not Path("/run/mrjam-kanidm-passkey-portal").exists() and not Path("/run/mrjam-kanidm-worker-login").exists(),"RUNTIME_NOT_CLEANED")
        checks.append("natural-unit-expiration-restores-route-and-cleans-portal-runtime")
    return {"passed":True,"checks":checks,"actual_proton_pass_browser":False,"software_webauthn":True,
            "real_https_unix_portal":True,"real_loadcredential_provisioner":True,"real_kanidm":True,
            "opener_functions_unchanged":True,"opener_invented_bindings":opener_bindings}


if __name__=="__main__":
    try:print(json.dumps(qualify(*(Path(value) for value in sys.argv[1:])),sort_keys=True))
    except Exception as error:
        locations=[{"file":Path(frame.filename).name,"line":frame.lineno,"function":frame.name} for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({"passed":False,"code":str(error) if isinstance(error,RuntimeError) else type(error).__name__,"synthetic_failure_locations":locations}))
        raise SystemExit(1)
