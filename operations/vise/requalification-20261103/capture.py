"""Fixed offline ViSe capture. Private data never leaves the VPS or enters output."""
import fcntl, hashlib, json, os, pwd, stat, subprocess
from pathlib import Path

CURRENT='/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git'
PG='/nix/store/f5bx5vyjvfc52a93q6p7gy7aidwg3jpx-postgresql-17.11/bin/'
SYSTEMCTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
DEST=Path('/var/lib/mrjam-cutover/vise-adoption-20261103')
LEDGER=Path('/var/lib/etp-carnet/deletions.log')

def require(value, code):
    if not value: raise RuntimeError(code)

def pg_identity():
    p=pwd.getpwnam('postgres');os.setgroups([]);os.setgid(p.pw_gid);os.setuid(p.pw_uid)

def offline():
    require(all(os.path.realpath(p)==CURRENT for p in ['/run/current-system','/nix/var/nix/profiles/system']),'GENERATION_CHANGED')
    r=subprocess.run([SYSTEMCTL,'show','vise.service','-p','ActiveState','--value'],capture_output=True,timeout=10)
    require(r.returncode==0 and r.stdout.strip()==b'inactive','VISE_NOT_OFFLINE')
    r=subprocess.run([PG+'psql','-XwqAt','-h','/run/postgresql','-d','postgres','-c',
        "SELECT count(*) FROM pg_stat_activity WHERE datname='etp_carnet'"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,preexec_fn=pg_identity,
        env={'LC_ALL':'C','PGCONNECT_TIMEOUT':'5'})
    require(r.returncode==0 and r.stdout.strip()==b'0','VISE_CONNECTION_PRESENT')
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try: require(p.stat().st_uid!=981,'VISE_PROCESS_PRESENT')
            except FileNotFoundError: pass

def metadata(path, mode, uid, directory=False):
    s=path.lstat()
    require((stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1)
            and stat.S_IMODE(s.st_mode)==mode and s.st_uid==s.st_gid==uid,'METADATA_REFUSED')
    return s

def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def save(name, value):
    with (DEST/name).open('x') as f:
        json.dump(value,f,sort_keys=True);f.flush();os.fsync(f.fileno())

def main():
    require(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED')
    os.umask(0o077)
    metadata(DEST.parent,0o700,0,True)
    lock=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);offline()
        metadata(LEDGER.parent,0o700,981,True)
        before=metadata(LEDGER,0o600,981)
        require(before.st_size<=67108864,'LEDGER_LIMIT')
        size=subprocess.run([PG+'psql','-XwqAt','-h','/run/postgresql','-d','postgres','-c',"SELECT pg_database_size('etp_carnet')"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,preexec_fn=pg_identity,env={'LC_ALL':'C'})
        require(size.returncode==0 and size.stdout.strip().isdigit(),'DATABASE_SIZE_REFUSED')
        require(os.statvfs(DEST.parent).f_bavail*os.statvfs(DEST.parent).f_frsize>2*int(size.stdout)+before.st_size+2*1024**3,'FREE_SPACE_REFUSED')
        DEST.mkdir(mode=0o700) # A partial earlier capture is never overwritten.
        save('intent.json',{'schema_version':1,'phase':'capture-started','current':CURRENT})
        with (DEST/'database.dump').open('xb') as f:
            r=subprocess.run([PG+'pg_dump','-h','/run/postgresql','-w','-Fc','--no-owner','--no-privileges','etp_carnet'],
                stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.DEVNULL,timeout=180,
                preexec_fn=pg_identity,env={'LC_ALL':'C','PGCONNECT_TIMEOUT':'5'})
            require(r.returncode==0,'DUMP_REFUSED');f.flush();os.fsync(f.fileno())
        fd=os.open(LEDGER,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as source, (DEST/'deletions.log').open('xb') as out:
            s=os.fstat(source.fileno());require((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)==(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns),'LEDGER_CHANGED')
            data=source.read(67108865);require(len(data)==before.st_size,'LEDGER_CHANGED')
            out.write(data);out.flush();os.fsync(out.fileno())
        offline()
        after=metadata(LEDGER,0o600,981)
        require((after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)==(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns),'LEDGER_CHANGED')
        require(digest(LEDGER)==digest(DEST/'deletions.log'),'LEDGER_CHANGED')
        r=subprocess.run([PG+'pg_restore','--list',str(DEST/'database.dump')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        require(r.returncode==0,'ARCHIVE_FORMAT_REFUSED')
        save('captured.json',{'schema_version':1,'phase':'offline-capture-verified',
            'files':{n:{'sha256':digest(DEST/n),'bytes':(DEST/n).stat().st_size} for n in ['database.dump','deletions.log']}})
        fd=os.open(DEST,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        print(json.dumps({'schema_version':1,'code':'VISE_OFFLINE_CAPTURE_VERIFIED','private_capture_retained_on_vps':True,'application_started':False,'database_restored':False}))
    finally:os.close(lock)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'code':'VISE_CAPTURE_REFUSED','reason':str(e) if type(e) is RuntimeError else type(e).__name__}));raise SystemExit(1)
