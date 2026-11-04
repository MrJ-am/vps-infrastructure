"""Separate Ed25519 content authority; never an approval or deployment service."""
from __future__ import annotations
import base64,fcntl,hashlib,os,socket,stat,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C
import collector as S

POLICY_PATH='@authority-policy@'
OPENSSL='@openssl@'
EXPORT_SOCKET='/run/mrjam-validation-authority/export.sock'
PRIVATE_KEY='/run/credentials/mrjam-validation-authority.service/signing-key'
AUTHORITY_SOCKET='/run/mrjam-validation-authority/request.sock'

def receive_export(connection,proposal,value,*,end):
    fds=[]
    try:
        C.require(C.peer_uid(connection) in (0,value['collector_uid']),'COLLECTOR_PEER_REFUSED')
        connection.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        C.send_packet(connection,proposal.encode('ascii')+b'\n',[],end=end)
        raw,fds=C.packet(connection,C.MAX_RECEIPT,end=end,expected_fds=3,expected_uid=value['collector_uid'])
        receipt=C.bound_receipt(C.parse(raw,C.MAX_RECEIPT),proposal,value['rules_revision'],value['producer'])
        extra,unexpected=C.packet(connection,1,end=end)
        C.require(extra==b'','EXPORT_SUFFIX_REFUSED')
        C.require(len({(os.fstat(fd).st_dev,os.fstat(fd).st_ino) for fd in fds})==3,'ARTIFACT_ALIAS_REFUSED')
        report=None
        for descriptor,entry,(name,limit) in zip(fds,receipt['artifacts'],C.ARTIFACTS):
            C.require(time.monotonic()<end,'AUTHORITY_TIMEOUT')
            raw=C.sealed_bytes(descriptor,limit,expected_size=entry['bytes'],expected_sha=entry['sha256'])
            if name=='verification.json':report=C.parse(raw,65536)
        return receipt,report
    finally:C.close_fds(fds)

def check_report(report,receipt,proposal,value):
    C.exact(report,{'schema_version','decision','authority','independent_adoption_established','production_authorized','proposal_sha256','rules_revision','policy_sha256','steps','sources','artifacts','not_established'})
    C.require(type(report['schema_version']) is int and report['schema_version']==1 and report['decision']=='passed' and report['authority']=='local-verifier-content-receipt','REPORT_AUTHORITY_REFUSED')
    C.require(report['independent_adoption_established'] is False and report['production_authorized'] is False,'HISTORICAL_CLAIM_REFUSED')
    C.require(report['proposal_sha256']==proposal and report['rules_revision']==value['rules_revision'] and report['policy_sha256']==value['report_policy_sha256'],'REPORT_BINDING_REFUSED')
    C.require(report['steps']==[{'name':name,'status':'passed'} for name in value['required_steps']],'REQUIRED_STEPS_REFUSED')
    C.require(report['sources']==value['sources'],'SOURCE_BINDING_REFUSED')
    C.require(type(report['artifacts']) is list and len(report['artifacts'])==2,'REPORT_ARTIFACTS_REFUSED')
    for entry,(name,limit) in zip(report['artifacts'],C.ARTIFACTS[:2]):
        C.exact(entry,{'name','bytes','sha256'});C.require(entry['name']==name,'REPORT_ARTIFACTS_REFUSED');C.integer(entry['bytes'],1,limit);C.text(entry['sha256'],C.HEX)
    C.require(report['artifacts']==receipt['artifacts'][:2],'REPORT_ARTIFACTS_REFUSED')
    C.require(report['not_established']==value['not_established'],'LIMITS_BINDING_REFUSED')

def openssl(arguments,descriptors,*,executable=OPENSSL,timeout=5,end=None):
    try:
        if end is not None:
            timeout=min(timeout,end-time.monotonic());C.require(timeout>0,'AUTHORITY_TIMEOUT')
        process=subprocess.run([executable,*arguments],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,pass_fds=tuple(descriptors),close_fds=True,env={'LANG':'C','LC_ALL':'C'},timeout=timeout,check=False)
        C.require(process.returncode==0 and len(process.stdout)<=4096,'CRYPTO_REFUSED');return process.stdout
    except (OSError,subprocess.TimeoutExpired):raise C.Refused('CRYPTO_REFUSED') from None

def sign(payload,private_key,value,*,executable=OPENSSL,end=None):
    key=message=None
    try:
        key=C.memfd(private_key)
        public=openssl(['pkey','-in','/proc/self/fd/'+str(key),'-pubout','-outform','DER'],[key],executable=executable,end=end)
        C.require(public==C.public_key(value['public_key_der']),'PRIVATE_KEY_BINDING_REFUSED')
        message=C.memfd(C.DOMAIN+C.canonical(payload))
        signature=openssl(['pkeyutl','-sign','-rawin','-inkey','/proc/self/fd/'+str(key),'-in','/proc/self/fd/'+str(message)],[key,message],executable=executable,end=end)
        C.require(len(signature)==64,'SIGNATURE_REFUSED')
        return {'schema_version':1,'algorithm':'Ed25519','key_id':value['key_id'],'payload':payload,'signature':base64.b64encode(signature).decode('ascii')}
    finally:C.close_fds([fd for fd in [key,message] if fd is not None])

def verify(envelope,value,*,executable=OPENSSL,now=None,end=None):
    C.policy(value)
    C.exact(envelope,{'schema_version','algorithm','key_id','payload','signature'})
    C.require(type(envelope['schema_version']) is int and envelope['schema_version']==1 and envelope['algorithm']=='Ed25519' and envelope['key_id']==value['key_id'],'SIGNATURE_IDENTITY_REFUSED')
    validate_payload(envelope['payload'],value,now=now)
    C.require(type(envelope['signature']) is str and len(envelope['signature'])==88,'SIGNATURE_REFUSED')
    try:signature=base64.b64decode(envelope['signature'],validate=True)
    except ValueError:raise C.Refused('SIGNATURE_REFUSED') from None
    C.require(len(signature)==64 and base64.b64encode(signature).decode()==envelope['signature'],'SIGNATURE_REFUSED')
    key=message=sig=None
    try:
        key=C.memfd(C.public_key(value['public_key_der']));message=C.memfd(C.DOMAIN+C.canonical(envelope['payload']));sig=C.memfd(signature)
        openssl(['pkeyutl','-verify','-rawin','-pubin','-keyform','DER','-inkey','/proc/self/fd/'+str(key),'-in','/proc/self/fd/'+str(message),'-sigfile','/proc/self/fd/'+str(sig)],[key,message,sig],executable=executable,end=end)
        return True
    finally:C.close_fds([fd for fd in [key,message,sig] if fd is not None])

def validate_payload(payload,value,*,now=None):
    C.exact(payload,{'schema_version','scope','key_id','policy_sha256','issued_at','policy_expires_at','rules_revision','proposal_sha256','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256','collector_receipt_sha256','artifacts','sources','steps','claims','not_established','producer'})
    C.active_policy(value,payload['proposal_sha256'],now)
    C.require(type(payload['schema_version']) is int and payload['schema_version']==1 and payload['scope']=='mrjam-validation-content-attestation-v1','ATTESTATION_SCOPE_REFUSED')
    C.require(payload['policy_sha256']==C.sha(C.canonical(value)),'ATTESTATION_POLICY_REFUSED')
    for key in ['key_id','rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256','sources','not_established','producer']:
        C.require(payload[key]==value[key],'ATTESTATION_BINDING_REFUSED')
    C.integer(payload['issued_at'],value['not_before'],value['expires_at']-1)
    current=int(time.time()) if now is None else now
    C.require(payload['issued_at']<=current and payload['policy_expires_at']==value['expires_at'],'ATTESTATION_TIME_REFUSED')
    C.require(payload['steps']==[{'name':name,'status':'passed'} for name in value['required_steps']],'REQUIRED_STEPS_REFUSED')
    C.require(payload['claims']==['locked-tests-passed','artifact-content-bound'],'ATTESTATION_CLAIMS_REFUSED')
    receipt={'schema_version':2,'decision':'passed','proposal_sha256':payload['proposal_sha256'],'rules_revision':value['rules_revision'],'authority':'bound-local-controller-receipt','artifacts':payload['artifacts'],'producer':value['producer']}
    C.bound_receipt(receipt,payload['proposal_sha256'],value['rules_revision'],value['producer'])
    C.require(payload['collector_receipt_sha256']==C.sha(C.canonical(receipt)),'ATTESTATION_RECEIPT_REFUSED')

def attest(receipt,report,proposal,value,private_key,*,now=None,executable=OPENSSL,end=None):
    now=int(time.time()) if now is None else now
    C.active_policy(value,proposal,now)
    C.bound_receipt(receipt,proposal,value['rules_revision'],value['producer']);check_report(report,receipt,proposal,value)
    payload={'schema_version':1,'scope':'mrjam-validation-content-attestation-v1','key_id':value['key_id'],'policy_sha256':C.sha(C.canonical(value)),'issued_at':now,'policy_expires_at':value['expires_at'],'rules_revision':value['rules_revision'],'proposal_sha256':proposal,'verifier':value['verifier'],'verifier_nar_hash':value['verifier_nar_hash'],'closure_sha256':value['closure_sha256'],'report_policy_sha256':value['report_policy_sha256'],'collector_receipt_sha256':C.sha(C.canonical(receipt)),'artifacts':receipt['artifacts'],'sources':value['sources'],'steps':report['steps'],'claims':['locked-tests-passed','artifact-content-bound'],'not_established':value['not_established'],'producer':value['producer']}
    return sign(payload,private_key,value,executable=executable,end=end)

def serve(connection,value,*,export_socket=EXPORT_SOCKET,private_key_path=PRIVATE_KEY,executable=OPENSSL,budget=15):
    end=time.monotonic()+budget
    try:
        C.policy(value);C.require(os.getuid()==value['signer_uid'],'SIGNER_UID_REFUSED')
        C.require(C.peer_uid(connection)==value['requester_uid'],'REQUESTER_PEER_REFUSED')
        proposal=C.request(connection,end=end);C.active_policy(value,proposal)
        meta=os.lstat(export_socket)
        C.require(stat.S_ISSOCK(meta.st_mode) and meta.st_uid==0 and stat.S_IMODE(meta.st_mode)==0o660,'EXPORT_SOCKET_REFUSED')
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as upstream:
            C.deadline(upstream,end);upstream.connect(export_socket)
            receipt,report=receive_export(upstream,proposal,value,end=end)
        C.require(time.monotonic()<end,'AUTHORITY_TIMEOUT')
        key=C.regular_file(private_key_path,owner=os.getuid(),mode=0o400,maximum=4096)
        envelope=attest(receipt,report,proposal,value,key,executable=executable,end=end)
        C.require(time.monotonic()<end,'AUTHORITY_TIMEOUT')
        C.active_policy(value,proposal)
        C.send_packet(connection,C.canonical(envelope),[],end=end)
        return True
    except BaseException:
        try:C.send_packet(connection,b'{"code":"VALIDATION_AUTHORITY_REFUSED","schema_version":1}',[],end=end)
        except BaseException:pass
        return False

def main():
    try:
        C.require(len(sys.argv)==1 and os.getuid()!=0,'INVOCATION_REFUSED')
        path=Path(POLICY_PATH);C.require(str(path).startswith('/nix/store/'),'POLICY_PATH_REFUSED')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as stream:
            meta=os.fstat(stream.fileno());C.require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o222 and 0<meta.st_size<=C.MAX_DOCUMENT,'POLICY_METADATA_REFUSED');value=C.parse(stream.read(C.MAX_DOCUMENT+1))
        C.require(os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1' and os.environ.get('LISTEN_FDNAMES')=='authority-request','ACTIVATION_REFUSED')
        with socket.socket(fileno=os.dup(3)) as listener:
            C.require(listener.family==socket.AF_UNIX and listener.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_SEQPACKET and listener.getsockname()==AUTHORITY_SOCKET and listener.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)==1,'ACTIVATION_REFUSED')
            listener.settimeout(5)
            connection,_=listener.accept()
            with connection:return 0 if serve(connection,value) else 1
    except BaseException:return 1
if __name__=='__main__':raise SystemExit(main())
