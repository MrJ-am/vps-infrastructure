"""Closed local protocol for collector exports and detached validation evidence."""
from __future__ import annotations
import array,base64,fcntl,hashlib,json,os,re,socket,stat,struct,time

MAX_DOCUMENT=131072
MAX_RECEIPT=4096
ARTIFACTS=(('server',64*1024**2),('frontend.tar',64*1024**2),('verification.json',65536))
HEX=re.compile(r'[0-9a-f]{64}\Z')
REV=re.compile(r'[0-9a-f]{40}\Z')
STORE=re.compile(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]{1,100}\Z')
SEALS=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_WRITE
DOMAIN=b'MRJAM-VALIDATION-CONTENT-ATTESTATION-V1\0'
PUBLIC_PREFIX=bytes.fromhex('302a300506032b6570032100')

class Refused(Exception):pass

def require(condition,code='AUTHORITY_INPUT_REFUSED'):
    if not condition:raise Refused(code)

def exact(value,keys):
    require(type(value) is dict and set(value)==set(keys));return value

def integer(value,low,high):require(type(value) is int and low<=value<=high)
def text(value,pattern):require(type(value) is str and pattern.fullmatch(value) is not None)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('ascii')

def parse(raw,limit=MAX_DOCUMENT):
    require(type(raw) is bytes and 0<len(raw)<=limit,'DOCUMENT_LIMIT')
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,'DUPLICATE_FIELD');value[key]=item
        return value
    def number(_):raise Refused('INVALID_NUMBER')
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=number,parse_constant=number)
    except Refused:raise
    except (ValueError,UnicodeError,RecursionError):raise Refused('INVALID_JSON') from None

def public_key(value):
    require(type(value) is str and len(value)==60)
    try:raw=base64.b64decode(value,validate=True)
    except ValueError:raise Refused('PUBLIC_KEY_REFUSED') from None
    require(len(raw)==44 and raw.startswith(PUBLIC_PREFIX) and base64.b64encode(raw).decode()==value,'PUBLIC_KEY_REFUSED')
    return raw

def source_binding(value):
    exact(value,{'id','repository','revision','tree_sha'})
    text(value['id'],re.compile(r'[a-z][a-z0-9-]{0,39}\Z'))
    text(value['repository'],re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,60}/[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\Z'))
    for key in ['revision','tree_sha']:text(value[key],REV)

def policy(value):
    exact(value,{'schema_version','scope','rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256','collector_uid','signer_uid','requester_uid','key_id','public_key_der','not_before','expires_at','required_steps','sources','accepted_proposals','not_established','producer'})
    require(type(value['schema_version']) is int and value['schema_version']==1)
    require(value['scope']=='mrjam-validation-content-authority-v1')
    text(value['rules_revision'],REV);text(value['verifier'],STORE)
    require(not value['verifier'].endswith('.drv'))
    text(value['verifier_nar_hash'],re.compile(r'sha256-[A-Za-z0-9+/]{43}=\Z'))
    for key in ['closure_sha256','report_policy_sha256','key_id']:text(value[key],HEX)
    require(sha(public_key(value['public_key_der']))==value['key_id'],'KEY_ID_REFUSED')
    for key in ['collector_uid','signer_uid','requester_uid']:integer(value[key],1,2**31-1)
    require(len({value[k] for k in ['collector_uid','signer_uid','requester_uid']})==3,'IDENTITY_SEPARATION_REFUSED')
    for key in ['not_before','expires_at']:integer(value[key],0,2**63-1)
    require(0<value['expires_at']-value['not_before']<=31*86400,'POLICY_WINDOW_REFUSED')
    steps=value['required_steps'];require(type(steps) is list and 1<=len(steps)<=128)
    for step in steps:text(step,re.compile(r'[a-z][a-z0-9-]{0,100}\Z'))
    require(len(set(steps))==len(steps))
    sources=value['sources'];require(type(sources) is list and 1<=len(sources)<=16)
    for source in sources:source_binding(source)
    require(len({s['id'] for s in sources})==len(sources))
    proposals=value['accepted_proposals'];require(type(proposals) is list and 1<=len(proposals)<=16)
    for proposal in proposals:text(proposal,HEX)
    require(proposals==sorted(set(proposals)))
    limits=value['not_established'];require(type(limits) is list and 1<=len(limits)<=16)
    for limit in limits:require(type(limit) is str and 0<len(limit)<=200 and all(32<=ord(c)<127 for c in limit))
    producer_binding(value['producer'])
    for key in ['rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256']:
        require(value[key]==value['producer'][key],'POLICY_PRODUCER_REFUSED')
    return value

def active_policy(value,proposal,now=None):
    policy(value);text(proposal,HEX);now=int(time.time()) if now is None else now
    integer(now,0,2**63-1)
    require(value['not_before']<=now<value['expires_at'],'POLICY_EXPIRED')
    require(proposal in value['accepted_proposals'],'PROPOSAL_NOT_ADOPTED')

def peer_uid(connection):
    require(connection.family==socket.AF_UNIX and connection.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_SEQPACKET,'TRANSPORT_REFUSED')
    return struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))[1]

def deadline(connection,end):
    remaining=end-time.monotonic();require(remaining>0,'PROTOCOL_TIMEOUT');connection.settimeout(remaining)

def close_fds(fds):
    for fd in fds:
        try:os.close(fd)
        except OSError:pass

def packet(connection,maximum,*,end,expected_fds=0,expected_uid=None):
    fds=[];credentials=[];invalid_ancillary=False
    try:
        deadline(connection,end)
        data,ancillary,flags,_=connection.recvmsg(maximum+1,socket.CMSG_SPACE(16*array.array('i').itemsize)+socket.CMSG_SPACE(struct.calcsize('3i')),socket.MSG_CMSG_CLOEXEC)
        for level,kind,raw in ancillary:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                items=array.array('i');items.frombytes(raw[:len(raw)-(len(raw)%items.itemsize)]);fds.extend(items)
            elif level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and expected_uid is not None:
                if len(raw)==struct.calcsize('3i'):credentials.append(struct.unpack('3i',raw))
                else:invalid_ancillary=True
            else:invalid_ancillary=True
        # recvmsg already installed every received descriptor in this process.
        # Collect all SCM_RIGHTS first, including those after an unknown item,
        # so every refusal below closes them instead of leaking descriptors.
        require(not invalid_ancillary,'ANCILLARY_REFUSED')
        require(not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(data)<=maximum,'PACKET_LIMIT')
        require(len(fds)==expected_fds,'DESCRIPTORS_REFUSED')
        if expected_uid is not None:require(len(credentials)==1 and credentials[0][0]>0 and credentials[0][1]==expected_uid,'SENDER_UID_REFUSED')
        return data,fds
    except BaseException:
        close_fds(fds);raise

def request(connection,*,end):
    raw,fds=packet(connection,65,end=end)
    require(re.fullmatch(rb'[0-9a-f]{64}\n',raw) is not None,'REQUEST_REFUSED')
    extra,fds=packet(connection,1,end=end)
    require(extra==b'','REQUEST_SUFFIX_REFUSED')
    return raw[:-1].decode('ascii')

def send_packet(connection,raw,fds,*,end):
    deadline(connection,end)
    ancillary=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',fds))] if fds else []
    require(connection.sendmsg([raw],ancillary)==len(raw),'SEND_REFUSED')
    connection.shutdown(socket.SHUT_WR)

def sealed_bytes(fd,limit,*,expected_size=None,expected_sha=None):
    info=os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,'UNSEALED_ARTIFACT')
    require(0<info.st_size<=limit,'ARTIFACT_LIMIT')
    require(expected_size is None or info.st_size==expected_size,'ARTIFACT_SIZE_REFUSED')
    raw=bytearray();offset=0
    while offset<info.st_size:
        block=os.pread(fd,min(65536,info.st_size-offset),offset);require(block,'ARTIFACT_TRUNCATED');raw.extend(block);offset+=len(block)
    require(expected_sha is None or sha(raw)==expected_sha,'ARTIFACT_HASH_REFUSED')
    return bytes(raw)

def memfd(raw):
    fd=os.memfd_create('mrjam-authority-export',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    try:
        view=memoryview(raw)
        while view:
            count=os.write(fd,view);require(count>0,'ARTIFACT_WRITE_REFUSED');view=view[count:]
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,SEALS);os.lseek(fd,0,os.SEEK_SET);return fd
    except BaseException:os.close(fd);raise

def regular_file(path,*,owner,mode,maximum):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        metadata=os.fstat(fd)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid==owner and stat.S_IMODE(metadata.st_mode)==mode and metadata.st_nlink==1 and 0<metadata.st_size<=maximum,'FILE_METADATA_REFUSED')
        raw=os.read(fd,maximum+1);after=os.fstat(fd)
        require(len(raw)==metadata.st_size and (metadata.st_ino,metadata.st_size,metadata.st_mtime_ns,metadata.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'FILE_CHANGED')
        return raw
    finally:os.close(fd)


def producer_binding(value):
    exact(value,{'schema_version','rules_revision','verifier','verifier_nar_hash','closure_sha256','report_policy_sha256','worker_policy_sha256','producer_recipe_sha256','worker_core_sha256','collector_recipe_sha256','contract_sha256'})
    require(type(value['schema_version']) is int and value['schema_version']==1)
    text(value['rules_revision'],REV);text(value['verifier'],STORE)
    text(value['verifier_nar_hash'],re.compile(r'sha256-[A-Za-z0-9+/]{43}=\Z'))
    for key in ['closure_sha256','report_policy_sha256','worker_policy_sha256','producer_recipe_sha256','worker_core_sha256','collector_recipe_sha256','contract_sha256']:text(value[key],HEX)
    return value


def bound_receipt(value,proposal,rules,binding):
    producer_binding(binding)
    exact(value,{'schema_version','decision','proposal_sha256','rules_revision','artifacts','authority','producer'})
    require(type(value['schema_version']) is int and value['schema_version']==2 and value['authority']=='bound-local-controller-receipt','UNBOUND_RECEIPT_REFUSED')
    producer_binding(value['producer'])
    require(value['producer']==binding,'PRODUCER_BINDING_REFUSED')
    require(value['decision']=='passed' and value['proposal_sha256']==proposal and value['rules_revision']==rules==binding['rules_revision'],'RECEIPT_BINDING_REFUSED')
    require(type(value['artifacts']) is list and len(value['artifacts'])==3,'ARTIFACTS_REFUSED')
    for entry,(name,limit) in zip(value['artifacts'],ARTIFACTS):
        exact(entry,{'name','bytes','sha256'});require(entry['name']==name,'ARTIFACT_NAME_REFUSED');integer(entry['bytes'],1,limit);text(entry['sha256'],HEX)
    return value
