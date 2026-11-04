"""Root observer only inside an invented NixOS VM. No production paths supplied."""
import base64,hashlib,json,os,pwd,socket,stat,subprocess,sys,time
from pathlib import Path

CONFIG=json.loads(Path('@fixture-config@').read_bytes())
sys.path.insert(0,CONFIG['authority']+'/lib')
import contract as C
import signer as A
import signing_credential as K
POLICY=C.policy(C.parse(Path(CONFIG['authority_policy']).read_bytes()))
STATE=Path('/var/lib/mrjam-ci-synthetic-observer')
KEY=Path('/var/lib/mrjam-validation-authority/invented-key')
CACHE=Path('/var/lib/mrjam-validation-collector/authority-v1/artifacts')/CONFIG['proposal']
ATTESTATION=Path('/var/lib/mrjam-forgejo-runner/attestations')/(CONFIG['proposal']+'.json')
RUNNER='mrjam-forgejo-runner.service'
AUTH='mrjam-validation-authority.service'

class Refused(Exception):pass
def require(value,code):
    if not value:raise Refused(code)
def run(args,*,data=None,checked=True,timeout=100):
    process=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    if checked:require(process.returncode==0,'SYNTHETIC_COMMAND_REFUSED')
    return process
def service(*args,checked=True):return run([CONFIG['systemctl'],*args],checked=checked).stdout.decode().strip()
def property(unit,name):return service('show',unit,'--property='+name,'--value')
def as_user(user,args,*,data=None,checked=True):return run([CONFIG['runuser'],'-u',user,'--',*args],data=data,checked=checked)
def write(path,raw,mode=0o400):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw);path.chmod(mode)
def reset():
    service('stop',RUNNER,AUTH,checked=False)
    service('reset-failed',RUNNER,AUTH,'mrjam-validation-export@*','mrjam-validation-collector@*','mrjam-validation-worker@*',checked=False)
def timestamps():
    result={}
    # Successful Accept=yes instances may already have been unloaded. Observe
    # only PID1 start metadata, never application journal contents.
    output=run([CONFIG['journalctl'],'--boot=0','--quiet','--no-pager','--output=json','--unit=mrjam-validation-worker@*.service','_PID=1']).stdout
    require(len(output)<=1048576,'PID1_METADATA_LIMIT')
    for line in output.splitlines():
        item=json.loads(line);unit=item.get('UNIT','')
        if unit.startswith('mrjam-validation-worker@') and item.get('MESSAGE_ID')=='39f53479d3a045ac8e11786248231fbf':
            result[unit]=item['__MONOTONIC_TIMESTAMP']
    return result
def coordinator(*,expect=True):
    reset()
    process=run([CONFIG['systemctl'],'start',RUNNER],checked=False,timeout=120)
    require((process.returncode==0)==expect,'COORDINATOR_RESULT_UNEXPECTED')
    require(property(RUNNER,'Result')==('success' if expect else 'exit-code'),'COORDINATOR_UNIT_RESULT_UNEXPECTED')
    return process
def client(*,expect):
    reset()
    process=as_user('mrjam-forgejo-runner',[CONFIG['python'],'-I','-S','-c',
        'import os;os.environ["MRJAM_PROPOSAL_DIGEST"]='+repr(CONFIG['proposal'])+';os.execv('+repr(CONFIG['authority']+'/bin/mrjam-validation-request-attestation')+',['+repr(CONFIG['authority']+'/bin/mrjam-validation-request-attestation')+'])'],checked=False)
    require((process.returncode==0)==expect,'CLIENT_RESULT_UNEXPECTED')
    if expect:
        envelope=C.parse(process.stdout);require(A.verify(envelope,POLICY,executable=CONFIG['openssl']),'SIGNATURE_NOT_VERIFIED');return envelope
    require(process.stdout==b'{"code":"VALIDATION_ATTESTATION_REFUSED","schema_version":1}\n' and process.stderr==b'','CLIENT_REFUSAL_NOT_CLOSED')
def verified_file():
    meta=ATTESTATION.lstat()
    require(stat.S_ISREG(meta.st_mode) and meta.st_uid==POLICY['requester_uid'] and stat.S_IMODE(meta.st_mode)==0o400 and meta.st_nlink==1,'ATTESTATION_METADATA_REFUSED')
    envelope=C.parse(ATTESTATION.read_bytes());A.verify(envelope,POLICY,executable=CONFIG['openssl'])
    require(envelope['payload']['proposal_sha256']==CONFIG['proposal'],'ATTESTATION_PROPOSAL_REFUSED')
    return envelope
def prepare():
    require(not STATE.exists(),'FIXTURE_ALREADY_PRESENT');STATE.mkdir(mode=0o700)
    seed=hashlib.sha256(b'MRJAM AUTHORITY V1 PUBLIC SYNTHETIC TEST KEY ONLY').digest()
    der=bytes.fromhex('302e020100300506032b657004220420')+seed
    key=run([CONFIG['openssl'],'pkey','-inform','DER'],data=der).stdout
    public=run([CONFIG['openssl'],'pkey','-pubout','-outform','DER'],data=key).stdout
    require(base64.b64encode(public).decode()==POLICY['public_key_der'],'PUBLIC_TEST_KEY_MISMATCH')
    write(KEY,key);KEY.parent.chmod(0o700)
    write(STATE/'key',key)
    registration=Path('/var/lib/mrjam-forgejo-registration/registration');registration.mkdir(parents=True,mode=0o700)
    write(registration/'identity.json',b'{"invented":true}\n')
    write(registration/'runner-token',b'INVENTED UNUSED RUNNER TOKEN\n')
    write(registration/'connection.json',b'{}\n')
    service('start','mrjam-validation-staging.service')
    require(Path('/var/lib/mrjam-validation-input',CONFIG['proposal'],'manifest.json').is_file(),'REAL_STAGING_MISSING')
    require(hashlib.sha256(Path(CONFIG['authority']+'/lib/frozen_worker.py').read_bytes()).hexdigest()==CONFIG['worker_source_sha256'],'WORKER_SOURCE_CHANGED')
    require(property(RUNNER,'RootDirectory')==CONFIG['expected_root'],'PRIVATE_ROOT_CHANGED')
def inactive_boundaries():
    for unit in [RUNNER,AUTH,'mrjam-validation-authority.socket','mrjam-validation-export.socket','mrjam-validation-collector.socket','mrjam-validation-worker.socket']:
        require(property(unit,'ActiveState')=='inactive','IMPLICIT_ACTIVATION')
    users=['mrjam-validation-worker','mrjam-validation-collector','mrjam-validation-authority','mrjam-forgejo-runner','mrjam-forgejo-registration','invented-outsider']
    require(len({pwd.getpwnam(name).pw_uid for name in users})==6,'IDENTITY_COLLISION')
    require(not CACHE.exists() and not ATTESTATION.exists(),'CACHE_PREEXISTS')
def fresh_chain():
    coordinator()
    envelope=verified_file()
    receipt=C.bound_receipt(C.parse((CACHE/'receipt.json').read_bytes()),CONFIG['proposal'],POLICY['rules_revision'],POLICY['producer'])
    require(envelope['payload']['collector_receipt_sha256']==C.sha(C.canonical(receipt)),'RECEIPT_NOT_BOUND')
    require(receipt['producer']==POLICY['producer'],'PRODUCER_NOT_BOUND')
    require(len(timestamps())==1 and all(int(v)>0 for v in timestamps().values()),'WORKER_EXECUTION_MISSING')
    write(STATE/'worker-timestamps.json',C.canonical(timestamps()))
    write(STATE/'receipt', (CACHE/'receipt.json').read_bytes())
    write(STATE/'server',(CACHE/'server').read_bytes())
    require(property(AUTH,'ExecMainStatus')=='0' and property(AUTH,'Result')=='success','SIGNER_UNIT_FAILED')
    for name in ['server','frontend.tar','verification.json']:
        meta=(CACHE/name).stat();require(meta.st_uid==POLICY['collector_uid'] and stat.S_IMODE(meta.st_mode)==0o400,'COLLECTOR_OWNERSHIP_CHANGED')
def cache_reuse():
    before=json.loads((STATE/'worker-timestamps.json').read_bytes())
    coordinator();verified_file()
    require(timestamps()==before,'CACHE_REUSE_RERAN_WORKER')
    require((CACHE/'receipt.json').read_bytes()==(STATE/'receipt').read_bytes(),'CACHE_RECEIPT_CHANGED')
def wrong_peers():
    reset();service('start','mrjam-validation-authority.socket','mrjam-validation-export.socket')
    for path,code in [('/run/mrjam-validation-authority/request.sock','VALIDATION_AUTHORITY_REFUSED'),('/run/mrjam-validation-authority/export.sock','COLLECTOR_EXPORT_REFUSED')]:
        before=len(os.listdir('/proc/self/fd'))
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(5);connection.connect(path)
            try:
                connection.sendall((CONFIG['proposal']+'\n').encode());connection.shutdown(socket.SHUT_WR)
                raw,fds=C.packet(connection,4096,end=time.monotonic()+5)
                require(not fds and C.parse(raw)=={'schema_version':1,'code':code},'WRONG_PEER_NOT_REFUSED')
            except (BrokenPipeError,ConnectionResetError):
                # The wrong UID is rejected before reading its request. Unit
                # exit can reset its unread socket; refusal output is best effort.
                # C.packet closes any received FD before propagating an error.
                pass
        require(len(os.listdir('/proc/self/fd'))==before,'WRONG_PEER_RECEIVED_DESCRIPTOR')
    require((CACHE/'receipt.json').read_bytes()==(STATE/'receipt').read_bytes(),'WRONG_PEER_CHANGED_CACHE')
def key_separation():
    def credentials(unit):
        require(property(unit,'DropInPaths')=='','UNEXPECTED_UNIT_DROPIN')
        path=Path(property(unit,'FragmentPath')).resolve(strict=True)
        require(str(path).startswith('/nix/store/') and path.is_file() and path.stat().st_size<=32768,'UNIT_FRAGMENT_REFUSED')
        directives=[]
        for line in path.read_text().splitlines():
            if line.startswith('LoadCredential='):directives.append(line.removeprefix('LoadCredential='))
            require(not line.startswith('LoadCredentialEncrypted='),'UNEXPECTED_ENCRYPTED_CREDENTIAL')
        return directives
    # LoadCredential is not exposed by `systemctl show` in a stable printable
    # form. Inspect only the exact immutable fragment selected by PID1.
    require(credentials(AUTH)==['signing-key:'+str(KEY)],'SIGNER_CREDENTIAL_CHANGED')
    for user in ['mrjam-validation-worker','mrjam-validation-collector','mrjam-forgejo-runner','invented-outsider']:
        result=as_user(user,[CONFIG['python'],'-I','-S','-c','from pathlib import Path;Path('+repr(str(KEY))+').read_bytes()'],checked=False)
        require(result.returncode!=0,'KEY_READABLE_BY_OTHER_IDENTITY')
    for unit in ['mrjam-validation-worker@probe.service','mrjam-validation-collector@probe.service','mrjam-validation-export@probe.service']:
        require(credentials(unit)==[],'UNEXPECTED_CREDENTIAL')
    require(credentials(RUNNER)==['runner-token:/var/lib/mrjam-forgejo-registration/registration/runner-token','runner-config:/var/lib/mrjam-forgejo-registration/registration/connection.json'],'COORDINATOR_CREDENTIALS_CHANGED')
def legacy_cache_refused():
    receipt=json.loads((STATE/'receipt').read_bytes());receipt.pop('producer');receipt['schema_version']=1;receipt['authority']='local-controller-receipt'
    path=CACHE/'receipt.json';path.chmod(0o600);path.write_bytes(C.canonical(receipt));path.chmod(0o400)
    before=ATTESTATION.read_bytes()
    try:coordinator(expect=False);require(ATTESTATION.read_bytes()==before,'LEGACY_CACHE_REPLACED_ATTESTATION')
    finally:path.chmod(0o600);path.write_bytes((STATE/'receipt').read_bytes());path.chmod(0o400)
def tamper_refused():
    path=CACHE/'server';path.chmod(0o600);path.write_bytes(b'X'*len((STATE/'server').read_bytes()));path.chmod(0o400)
    try:client(expect=False)
    finally:path.chmod(0o600);path.write_bytes((STATE/'server').read_bytes());path.chmod(0o400)
def wrong_key_refused():
    wrong=run([CONFIG['openssl'],'genpkey','-algorithm','ED25519']).stdout
    write(KEY,wrong)
    try:client(expect=False)
    finally:write(KEY,(STATE/'key').read_bytes())
    client(expect=True)
def expiry_refused():
    now=int(time.time())
    try:
        run([CONFIG['date'],'--set=@'+str(POLICY['expires_at']+2)])
        before=property(AUTH,'ExecMainStartTimestampMonotonic');client(expect=False)
        require(property(AUTH,'ExecMainStartTimestampMonotonic')==before,'EXPIRED_POLICY_STARTED_SIGNER')
    finally:run([CONFIG['date'],'--set=@'+str(now)])

def diagnose_signer():
    reset();service('start','mrjam-validation-authority.socket','mrjam-validation-export.socket',AUTH)
    pid=int(property(AUTH,'MainPID'));require(pid>1,'SIGNER_DIAGNOSTIC_NOT_RUNNING')
    credential=Path('/proc',str(pid),'root/run/credentials/mrjam-validation-authority.service/signing-key')
    parent=credential.parent
    meta=credential.stat();parent_meta=parent.stat()
    metadata={'uid':meta.st_uid,'gid':meta.st_gid,'mode':stat.S_IMODE(meta.st_mode),'nlink':meta.st_nlink,'directory_uid':parent_meta.st_uid,'directory_mode':stat.S_IMODE(parent_meta.st_mode),'readonly':bool(os.statvfs(credential).f_flag&os.ST_RDONLY)}
    try:metadata['acl_hex']=os.getxattr(credential,'system.posix_acl_access').hex()
    except OSError:metadata['acl_hex']=''
    try:metadata['directory_acl_hex']=os.getxattr(parent,'system.posix_acl_access').hex()
    except OSError:metadata['directory_acl_hex']=''
    service('stop',AUTH)
    drop=Path('/run/systemd/system/mrjam-validation-authority.service.d/synthetic-diagnostic.conf')
    write(drop,('[Service]\nExecStart=\nExecStart='+CONFIG['python']+' -I -S '+CONFIG['diagnostic_signer']+'\nStandardError=journal\n').encode(),0o644)
    try:
        service('daemon-reload');client(expect=False)
        codes=[]
        output=run([CONFIG['journalctl'],'--quiet','--no-pager','--output=cat','_SYSTEMD_UNIT='+AUTH]).stdout
        require(len(output)<=65536,'DIAGNOSTIC_LOG_LIMIT')
        for line in output.splitlines():
            try:value=json.loads(line)
            except ValueError:continue
            if type(value) is dict and set(value)=={'authority_diagnostic'}:codes.append(value['authority_diagnostic'])
        print(json.dumps({'synthetic_diagnostic_only':True,'credential_metadata':metadata,'closed_codes':codes},sort_keys=True))
    finally:drop.unlink();service('daemon-reload')

def credential_reader_boundaries():
    unit='synthetic-credential-reader.service';view=STATE/'credential-view';key=view/'signing-key'
    view.mkdir(mode=0o700)
    def baseline():
        key.unlink(missing_ok=True)
        write(key,b'INVENTED CREDENTIAL VIEW ONLY\n',0o400)
        os.setxattr(view,'system.posix_acl_access',K.acl(POLICY['signer_uid'],5))
        os.setxattr(key,'system.posix_acl_access',K.acl(POLICY['signer_uid'],4))
    def probe(*,accepted,readonly=True):
        def records():
            output=run([CONFIG['journalctl'],'--quiet','--no-pager','--output=cat','_SYSTEMD_UNIT='+unit]).stdout
            require(len(output)<=16384,'READER_PROBE_LOG_LIMIT')
            found=[]
            for line in output.splitlines():
                try:value=json.loads(line)
                except ValueError:continue
                if type(value) is dict and set(value)=={'synthetic_reader'}:found.append(value['synthetic_reader'])
            return found
        before=len(records())
        service('reset-failed',unit,checked=False)
        result=run([CONFIG['systemctl'],'start',unit],checked=False)
        require((result.returncode==0)==accepted,'READER_BOUNDARY_RESULT_UNEXPECTED')
        observed=records()
        require(len(observed)==before+1 and observed[-1]['accepted']==accepted and observed[-1]['readonly']==readonly,'READER_BOUNDARY_OBSERVATION_MISSING')
    baseline();probe(accepted=True)
    key.chmod(0o640);probe(accepted=False)
    baseline();raw=K.acl(POLICY['signer_uid'],4)
    import struct
    os.setxattr(key,'system.posix_acl_access',raw[:20]+struct.pack('<HHI',2,4,61006)+raw[20:]);probe(accepted=False)
    baseline();os.setxattr(key,'system.posix_acl_access',K.acl(POLICY['requester_uid'],4));probe(accepted=False)
    baseline();raw=K.acl(POLICY['signer_uid'],5)
    os.setxattr(view,'system.posix_acl_access',raw[:20]+struct.pack('<HHI',2,5,61006)+raw[20:]);probe(accepted=False)
    baseline();alias=STATE/'key-alias';os.link(key,alias)
    try:probe(accepted=False)
    finally:alias.unlink()
    baseline();key.chmod(0o600);key.write_bytes(b'X'*4097);os.setxattr(key,'system.posix_acl_access',K.acl(POLICY['signer_uid'],4));probe(accepted=False)
    baseline();drop=Path('/run/systemd/system/'+unit+'.d/synthetic-writable.conf')
    target='/run/credentials/mrjam-validation-authority.service'
    write(drop,('[Service]\nBindReadOnlyPaths=\nBindPaths='+str(view)+':'+target+'\nReadWritePaths='+target+'\n').encode(),0o644)
    try:service('daemon-reload');probe(accepted=False,readonly=False)
    finally:drop.unlink();service('daemon-reload')
    baseline();probe(accepted=True)

CASES={'prepare':prepare,'inactive-boundaries':inactive_boundaries,'fresh-chain':fresh_chain,'cache-reuse':cache_reuse,'wrong-peers':wrong_peers,'key-separation':key_separation,'legacy-cache-refused':legacy_cache_refused,'tamper-refused':tamper_refused,'wrong-key-refused':wrong_key_refused,'expiry-refused':expiry_refused,'credential-reader-boundaries':credential_reader_boundaries,'diagnose-signer':diagnose_signer}
if __name__=='__main__':
    name=sys.argv[1] if len(sys.argv)==2 else 'invalid'
    try:
        require(os.getuid()==0 and Path('/etc/mrjam-ci-synthetic-fixture').read_text()=='INVENTED_VM_ONLY\n','NOT_SYNTHETIC_VM')
        require(name in CASES,'UNKNOWN_CASE');CASES[name]()
    except BaseException as failure:
        code=str(failure) if isinstance(failure,Refused) else type(failure).__name__
        print(json.dumps({'case':name,'status':'failed','code':code},sort_keys=True));raise SystemExit(1)
    print(json.dumps({'case':name,'status':'passed'},sort_keys=True))
