"""Fixed content-attestation client; no command, path or policy from a request."""
from __future__ import annotations
import os,socket,stat,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C
import signer as A

POLICY_PATH='@authority-policy@'
AUTHORITY_SOCKET='/run/mrjam-validation-authority/request.sock'

def receive(connection,proposal,value,*,end,executable=A.OPENSSL,now=None):
    C.active_policy(value,proposal,now)
    # systemd owns the listener; kernel ancillary credentials identify the
    # separate signer that actually sends the signed document.
    C.require(C.peer_uid(connection) in (0,value['signer_uid']),'AUTHORITY_PEER_REFUSED')
    connection.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
    C.send_packet(connection,proposal.encode('ascii')+b'\n',[],end=end)
    raw,fds=C.packet(connection,C.MAX_DOCUMENT,end=end,expected_uid=value['signer_uid'])
    extra,unexpected=C.packet(connection,1,end=end)
    C.require(extra==b'','AUTHORITY_SUFFIX_REFUSED')
    envelope=C.parse(raw)
    A.verify(envelope,value,executable=executable,now=now,end=end)
    C.require(envelope['payload']['proposal_sha256']==proposal,'REQUEST_BINDING_REFUSED')
    C.require(time.monotonic()<end,'AUTHORITY_TIMEOUT')
    return envelope

def request(proposal,value,*,socket_path=AUTHORITY_SOCKET,budget=20,executable=A.OPENSSL):
    C.policy(value);C.require(os.getuid()==value['requester_uid'],'REQUESTER_UID_REFUSED')
    C.active_policy(value,proposal)
    meta=os.lstat(socket_path)
    C.require(stat.S_ISSOCK(meta.st_mode) and meta.st_uid==0 and stat.S_IMODE(meta.st_mode)==0o660,'AUTHORITY_SOCKET_REFUSED')
    end=time.monotonic()+budget
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
        C.deadline(connection,end);connection.connect(socket_path)
        return receive(connection,proposal,value,end=end,executable=executable)

def main():
    try:
        C.require(len(sys.argv)==1 and os.getuid()!=0,'INVOCATION_REFUSED')
        proposal=os.environ.get('MRJAM_PROPOSAL_DIGEST','');C.text(proposal,C.HEX)
        path=Path(POLICY_PATH);C.require(str(path).startswith('/nix/store/'),'POLICY_PATH_REFUSED')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as stream:
            meta=os.fstat(stream.fileno());C.require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o222 and 0<meta.st_size<=C.MAX_DOCUMENT,'POLICY_METADATA_REFUSED')
            value=C.parse(stream.read(C.MAX_DOCUMENT+1))
        envelope=request(proposal,value)
        # This is public signed provenance, not the report contents or a key.
        sys.stdout.buffer.write(C.canonical(envelope)+b'\n');return 0
    except BaseException:
        try:sys.stdout.buffer.write(b'{"code":"VALIDATION_ATTESTATION_REFUSED","schema_version":1}\n')
        except BaseException:pass
        return 1

if __name__=='__main__':raise SystemExit(main())
