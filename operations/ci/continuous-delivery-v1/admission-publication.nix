# Fixed initial admission only, not an API accepting candidate policy documents.
{ pkgs, control, anchorControl ? control }:
pkgs.runCommand "mrjam-publish-fixed-admission-1" {
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./admission_publish.py} "$out/lib/admission_publish.py"
  cat > "$out/lib/main.py" <<'PY'
import fcntl,json,os,stat,sys
from pathlib import Path
sys.path.insert(0,'${anchorControl}/lib')
sys.path.insert(0,os.path.dirname(__file__))
import contract as C
import admission_registry as R
import admission_control as A
import admission_publish as P
import frozen_worker as W

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1,'FIXED_ADMISSION_ADMIN_REQUIRED')
    raw=R.store_bytes('${control.recordFile}',16384)
    record=C.parse(raw,16384)
    proposal='${control.bindings.proposal}'
    C.require(record['proposal_sha256']==proposal,'FIXED_ADMISSION_DIGEST_REFUSED')
    profile='${control.profile or "platform"}'
    # Preserve compatibility with the installed single-profile platform anchor.
    # ViSe always requires the new explicit installed profile selection.
    anchor=(C.parse(R.store_bytes(A.ANCHOR_PATH)) if profile=='platform' else A.anchor_for(profile))
    documents={}
    seed=Path('${control.metadataSeed}')
    def read(path,maximum=131072):
        value=R.store_bytes(path,maximum)
        name=C.sha(path.encode())+'.data'
        C.require(R.store_bytes(str(seed/name),maximum)==value,'FIXED_ADMISSION_METADATA_REFUSED')
        documents[name]=value
        return value
    def resolve(record,read):
        if profile=='platform':return R.resolve(record,proposal,anchor,A.BUBBLEWRAP,read=read)
        return R.resolve(record,proposal,anchor,A.BUBBLEWRAP,read=read,profile=profile)
    resolve(record,read)
    C.require(len(documents)==(8 if profile=='platform' else 7)
              and set(os.listdir(seed))==set(documents),'FIXED_ADMISSION_METADATA_SET_REFUSED')
    lock=os.open(W.LOCK,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(lock)
        C.require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1
                  and stat.S_IMODE(info.st_mode)==0o440,'FIXED_ADMISSION_LOCK_REFUSED')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        W.verify_input(Path('/var/lib/mrjam-validation-input'),proposal,anchor['rules_revision'])
        P.publish(R.REGISTRY,proposal,raw,documents,document_count=(8 if profile=='platform' else 7))
        resolve(R.entry(proposal),R.metadata_bytes)
    finally:os.close(lock)
    print(json.dumps({'code':'FIXED_ADMISSION_PUBLISHED','proposal_sha256':proposal},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"FIXED_ADMISSION_PUBLICATION_REFUSED"}')
        raise SystemExit(1) from None
PY
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-publish-fixed-admission" \
    --add-flags "-I -S $out/lib/main.py"
''
