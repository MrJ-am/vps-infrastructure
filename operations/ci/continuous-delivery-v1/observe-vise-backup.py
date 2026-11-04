"""Verify the fixed installed backup without exporting private contents."""
import fcntl,http.client,json,os,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1/operations/vise/backup')
import capture as C,retention as R,transaction as T
SYSTEM='/nix/store/04j3v1y76rx8l762zp5dc4059wfcnhhw-nixos-system-srv1982677-26.05pre-git'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'

def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'VISE_OBSERVATION_HOST_REFUSED')
    C.require(os.path.realpath('/run/current-system')==SYSTEM and os.path.realpath('/nix/var/nix/profiles/system')==SYSTEM,'VISE_OBSERVATION_GENERATION_REFUSED')
    fd,_=C.regular(Path('/var/lib/mrjam-cutover/first-deployment/transaction.lock'),0,1024)
    with os.fdopen(fd,'rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fd,_=C.regular(Path('/var/lib/mrjam-vise-backup/state.json'),0,16384)
        with os.fdopen(fd,'rb') as source:journal=T.checked(json.load(source))
        C.require(journal['phase']=='complete','VISE_OBSERVATION_CAPTURE_INCOMPLETE')
        # Hash only encrypted files inside the protected process. No private
        # manifest, hash, identifier, SQL, ledger or key is emitted.
        R.inspect(Path('/var/backup/mrjam/vise-v1')/journal['capture_id'])
        units={}
        for name in ['vise.service','postgresql.service','nginx.service','forgejo.service',
                'mrjam-rust-blue.service','mrjam-rust-green.service',
                'mrjam-vise-backup.timer','mrjam-vise-backup-recovery.timer']:
            result=subprocess.check_output([CTL,'show',name,'-p','ActiveState','-p','MainPID'],text=True,timeout=10)
            units[name]=dict(line.split('=',1) for line in result.splitlines())
            C.require(units[name]['ActiveState']=='active','VISE_OBSERVATION_SERVICE_INACTIVE')
        connection=http.client.HTTPConnection('127.0.0.1',3017,timeout=5)
        try:
            connection.request('GET','/api/health');response=connection.getresponse()
            C.require(response.status==200 and json.loads(response.read(1025))=={'status':'ok','prototype':True},'VISE_OBSERVATION_HEALTH_REFUSED')
        finally:connection.close()
    print(json.dumps({'code':'VISE_BACKUP_VERIFIED','generation':SYSTEM,'capture_complete':True,
        'encrypted_pair_hashes_verified':True,'private_permissions_verified':True,'health':200,
        'units':units,'private_contents_exported':False,'production_restore_performed':False},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'VISE_BACKUP_OBSERVATION_REFUSED','exception_type':type(error).__name__}))
        raise SystemExit(1) from None
