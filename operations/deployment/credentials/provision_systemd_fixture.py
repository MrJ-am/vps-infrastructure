"""Independent private-unit and human-terminal test, invented disposable VM only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import time
import termios
import traceback

spec=importlib.util.spec_from_file_location('invented_provider',Path(__file__).with_name('qualify_provision.py'))
provider=importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


def require(value,code):
    if not value:
        raise RuntimeError(code)


def human_login(fixture, package):
    master,slave=pty.openpty()
    process=subprocess.Popen([str(package/'bin/mrjam-kanidm-worker-login')],stdin=slave,stdout=slave,stderr=slave,
                             env={'PATH':'/run/current-system/sw/bin','TERM':'dumb','LANG':'C.UTF-8'})
    os.close(slave)
    prompts=[('Compte autorisé à gérer les comptes de service'.encode(),'idm_admin'),
             (b'password',fixture.passwords['idm_admin']),
             ('Compte autorisé à gérer les accès'.encode(),'admin'),
             (b'password',fixture.passwords['admin'])]
    pending=b''
    success=False
    flags=set()
    sessions=set()
    deadline=time.monotonic()+160
    try:
        while process.poll() is None and time.monotonic()<deadline:
            # This observer exists ONLY in the invented VM, to prove revocation.
            # The production human helper has no such observer or output.
            for name in ('identity.json','access.json'):
                path=Path('/run/mrjam-kanidm-worker-login')/name
                if path.is_file():
                    try:
                        sessions.add(provider.P['cache_token'](path.read_bytes()))
                    except Exception:
                        pass
            readable,_,_=select.select([master],[],[],0.02)
            if readable:
                try:
                    part=os.read(master,4096)
                except OSError:
                    break
                pending=(pending+part)[-16384:]
                for marker in (b'password',b'error',b'certificate',b'connect',b'not authenticated',b'WORKER_PROVISION_NOT_COMPLETED'):
                    if marker.lower() in pending.lower(): flags.add(marker.decode('ascii').replace(' ','_'))
                success=success or b'WORKER_CREDENTIALS_PREPARED' in pending
            if prompts and prompts[0][0].lower() in pending.lower():
                # Wait for the real CLI to put the PTY in hidden-input mode.
                # Sending at the first word "password" can race its terminal
                # flush and discard the invented answer before it is read.
                password_prompt=prompts[0][0]==b'password'
                hidden=not (termios.tcgetattr(master)[3]&termios.ECHO)
                if not password_prompt or hidden:
                    _,answer=prompts.pop(0)
                    os.write(master,(answer+'\n').encode())
                    pending=b''
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                raise RuntimeError('HUMAN_TIMEOUT_PROMPTS_'+str(len(prompts))+'_'+','.join(sorted(flags))) from None
        require(process.returncode==0 and not prompts,'HUMAN_LOGIN_OR_UNIT_REFUSED')
        require(success,'HUMAN_SUCCESS_NOT_REPORTED')
        require(len(sessions)==2,'TEMPORARY_SYNTHETIC_SESSIONS_NOT_OBSERVED')
        require(not Path('/run/mrjam-kanidm-worker-login').exists(),'HUMAN_CACHE_NOT_REMOVED')
        for token in sessions:
            require(fixture.request(token,'GET','/v1/self')[0] in (401,403),'HUMAN_SESSION_NOT_REVOKED')
    finally:
        if process.poll() is None:
            process.kill();process.wait()
        os.close(master)
        pending=b''


def fingerprint(root):
    result={}
    for role in ('admission','cycle','replay'):
        path=root/('kanidm-'+role+'.token')
        item=path.lstat()
        require((item.st_uid,item.st_gid,item.st_nlink,item.st_mode&0o777)==(0,0,1,0o600),'PRIVATE_TOKEN_METADATA')
        result[role]=(item.st_ino,item.st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def qualify(tls,package):
    checks=[]
    with provider.Fixture(port=8443,ca_directory=tls,openssl='/run/current-system/sw/bin/openssl') as f:
        identity,access=f.login('idm_admin'),f.login('admin')
        f.ok(identity,'POST','/v1/service_account',{'attrs':{'name':['mrjam-admission'],
             'displayname':['Invented admission'],'entry_managed_by':['idm_admin']}})
        f.ok(identity,'POST','/v1/group/idm_people_on_boarding/_attr/member',['mrjam-admission'])
        f.ok(access,'POST','/v1/group/idm_account_mail_read/_attr/member',['mrjam-admission'])
        admission=f.ok(identity,'POST','/v1/service_account/mrjam-admission/_api_token',
                        {'label':'invented-admission','expiry':int(time.time())+86400,'read_write':True})
        state=Path('/var/lib/mrjam-identite');state.mkdir(mode=0o700)
        old=state/'kanidm-admission.token';old.write_text(admission+'\n');old.chmod(0o600)
        original=(old.stat().st_ino,old.stat().st_mtime_ns,old.read_bytes())
        refusal=subprocess.run([str(package/'bin/mrjam-kanidm-worker-login')],stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
        require(refusal.returncode!=0 and not Path('/run/mrjam-kanidm-worker-login').exists(),'NONHUMAN_ENTRY_ACCEPTED')
        checks.append('human-terminal-required-without-side-effects')
        human_login(f,package)
        checks.append('official-cli-human-pty-and-real-loadcredential-unit')
        require((old.stat().st_ino,old.stat().st_mtime_ns,old.read_bytes())==original,'ADMISSION_REPLACED')
        before=fingerprint(state)
        checks.append('three-private-tokens-and-admission-preserved')
        for role in ('cycle','replay'):
            token=(state/('kanidm-'+role+'.token')).read_text().strip()
            provider.P['token_identity'](provider.P['Api'](f.context),token,role)
        checks.append('real-native-capabilities-and-distinct-upstream-scopes')
        human_login(f,package)
        require(fingerprint(state)==before,'REPEAT_ROTATED_CREDENTIAL')
        checks.append('second-human-authentication-preserves-all-token-inodes-and-values')
        checks.append('temporary-cli-sessions-revoked-and-caches-removed')
        unit='mrjam-kanidm-worker-provision.service'
        failed=subprocess.run(['systemctl','start',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        require(failed.returncode!=0,'MISSING_SESSION_ACCEPTED')
        require(fingerprint(state)==before,'MISSING_SESSION_CHANGED_TOKEN')
        journal=subprocess.run(['journalctl','-u',unit,'--no-pager'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True).stdout
        private=[admission,*f.passwords.values(),*(p.read_text().strip() for p in state.glob('kanidm-*.token'))]
        require(not any(value.encode() in journal for value in private),'PRIVATE_UNIT_LOG_LEAK')
        require(b'"prepared":true' in journal,'CLOSED_SUCCESS_MISSING')
        checks.append('missing-session-fails-with-no-token-change-or-log-leak')
    return {'schema_version':1,'passed':True,'checks':checks}


if __name__=='__main__':
    try:
        result=qualify(Path(sys.argv[1]),Path(sys.argv[2]))
    except Exception as error:
        # All values are synthetic, but keep this runner's diagnostics closed.
        code=str(error) if isinstance(error,RuntimeError) else type(error).__name__
        print(json.dumps({'passed':False,'code':code,'frames':[(Path(frame.filename).name,frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1)
    print(json.dumps(result,sort_keys=True))
