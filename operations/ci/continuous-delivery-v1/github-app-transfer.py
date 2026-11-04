"""Transfer the newly generated automation credential privately to the VPS."""
from pathlib import Path
import hashlib,json,os,shlex,stat,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EXPECTED='a7cf5861b184e765a456f1cfe479e3c963f41b9921ea383b6fb5d566d60a9367'
def main():
    assert len(sys.argv)==1
    source=HERE/'github-app-receive.py';code=source.read_bytes()
    assert hashlib.sha256(code).hexdigest()==EXPECTED
    directory=ROOT/'.local/deployment-20261101/github-app-bootstrap-001'
    info=directory.lstat();assert stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700
    fd=os.open(directory/'app-credentials.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
        assert stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=32768
        raw=os.read(fd,32769);assert len(raw)==info.st_size
    finally:os.close(fd)
    command='exec /nix/store/kp6p38x6zb21n7gdlnp9nsm2aagq7sg2-python3-3.13.17/bin/python3 -I -S -c '+shlex.quote(code.decode())
    result=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10',
        '-o','StrictHostKeyChecking=yes','-o','ClearAllForwardings=yes','-o','ForwardAgent=no',
        '-o','ForwardX11=no','-o','PermitLocalCommand=no','-o','RemoteCommand=none','vps',command],
        input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    assert result.returncode==0 and len(result.stdout)<=1024
    receipt=json.loads(result.stdout)
    assert set(receipt)=={'code','app_id','slug','installation_verified','pipeline_activated'}
    assert receipt['code']=='APP_IDENTITY_INSTALLED' and receipt['installation_verified'] is False and receipt['pipeline_activated'] is False
    # Only closed, public identity metadata is retained in the receipt.
    (directory/'transfer-receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
    print(json.dumps(receipt,sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception:
        print('{"code":"PRIVATE_APP_TRANSFER_STOPPED_VERIFY_STATE_BEFORE_RETRY"}')
        raise SystemExit(1) from None
