"""Explicit fixed ViSe activation; failures return configuration, never old SQL data."""
import fcntl, json, os, re, stat, subprocess, tempfile, time, urllib.request
from pathlib import Path

OLD='/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/h7gsm02w34zbacxamwjl98qmbqyb3kci-nixos-system-srv1982677-26.05pre-git'
S='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
NGINX='/nix/store/hrsgwp6dqnr9y9svhjzvxw0phgmqvnqk-nginx-1.30.4/bin/nginx'
NGINX_CONF='/nix/store/xd09wn3p20nks136nar0i20pzx2s61xc-nginx.conf'
PG_OLD='/nix/store/ajk3pfg27lypy99s35nhxjq2xsji7xfj-postgresql.conf/postgresql.conf'
PG_NEW='/nix/store/yvv28i27yrn3cbivknyc1frdnf87ix5y-postgresql.conf/postgresql.conf'
PG_LINK=Path('/var/lib/postgresql/17/postgresql.conf')
MASKS=Path('/run/mrjam-cutover/masks.json')
STATE=Path('/var/lib/mrjam-cutover/vise-adoption-20261103')
SERVICES=['nginx','postgresql','forgejo','kanidm','mrjam-rust-blue','mrjam-identity',
          'mrjam-identity-deletion','mrjam-vision-admission','mrjam-vision-closure','mrjam-forgejo-runner',
          'phpfpm-nextcloud','redis-nextcloud','vision-embeddings']

def require(value, code):
    if not value: raise RuntimeError(code)

def run(args, timeout=30, capture=False):
    r=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,timeout=timeout,env={'LC_ALL':'C','LANG':'C','NIX_PATH':''})
    require(r.returncode==0,'FIXED_OPERATION_REFUSED_'+str(r.returncode))
    if capture: require(len(r.stdout)<=8192,'OUTPUT_LIMIT');return r.stdout

def private(path):
    s=path.lstat();require(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'PRIVATE_RECORD_REFUSED')
    require(s.st_size<=65536,'PRIVATE_RECORD_LIMIT');return path.read_bytes()

def atomic(path, raw):
    fd,name=tempfile.mkstemp(prefix='vise-',suffix='.next',dir=path.parent)
    with os.fdopen(fd,'wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(name,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def pg_config(target):
    require(PG_LINK.is_symlink() and str(PG_LINK.resolve()) in (PG_OLD,PG_NEW),'PG_CONFIGURATION_CHANGED')
    temporary=PG_LINK.with_name('postgresql.conf.vise-next')
    os.symlink(target,temporary);os.replace(temporary,PG_LINK)
    run([S,'restart','postgresql.service'],150)
    # Restore the fixed previously active dependent services; never run setup/migration units.
    run([S,'start',*[n+'.service' for n in SERVICES if n not in ('nginx','postgresql')]],180)

def running():
    for n in SERVICES:run([S,'is-active','--quiet',n+'.service'])
    for n in ['worker','collector','export','authority']:run([S,'is-active','--quiet','mrjam-validation-'+n+'.socket'])

def health(url):
    with urllib.request.urlopen(url,timeout=5) as r:
        require(r.status==200 and json.loads(r.read(1025))=={'status':'ok','prototype':True},'HEALTH_REFUSED')

def wait_health(url):
    end=time.monotonic()+20
    while True:
        try:health(url);return
        except Exception:
            if time.monotonic()>=end:raise
            time.sleep(.5)


BOOT=OLD
OLD=NEW
NEW='/nix/store/3a6gyg9bvy1g2gp5rr1qsjcw1h00lznm-nixos-system-srv1982677-26.05pre-git'
NGINX_CONF='/nix/store/s7fp8ah2x5wgvnigxckzpsprqihr1g46-nginx.conf'
NIX='/nix/store/i4bv0lvk0gfzllcy2kqgz3iam0aw4c4i-nix-2.34.8/bin/nix-env'

def boot(target):
    run([NIX,'--profile','/nix/var/nix/profiles/system','--set',target],120)
    run([target+'/bin/switch-to-configuration','boot'],180)
    require(os.path.realpath('/nix/var/nix/profiles/system')==target,'BOOT_MISMATCH')

def main(activate=True):
    require(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED');os.umask(0o077)
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(os.path.realpath('/run/current-system')==OLD and os.path.realpath('/nix/var/nix/profiles/system')==BOOT,'BASELINE_CHANGED')
        require(json.loads(private(STATE/'activation-002.json'))=={'phase':'staged-service-verified'},'STAGED_SERVICE_REQUIRED')
        require(not (STATE/'promotion.json').exists(),'PROMOTION_ALREADY_ATTEMPTED')
        original=private(MASKS);m=json.loads(original)
        require(set(m)=={'schema_version','units'} and m['schema_version']==1 and m['units']==sorted(set(m['units'])) and 'vise.service' not in m['units'],'MASK_RECORD_REFUSED')
        renewal=['mrjam-acme-renew-vise.mrj.am.service','mrjam-acme-renew-vise.mrj.am.timer']
        unmasked=json.dumps({'schema_version':1,'units':[n for n in m['units'] if n not in renewal]},sort_keys=True).encode()+b'\n'
        for unit in (Path(OLD)/'etc/systemd/system').iterdir():
            if unit.is_file() and unit.suffix in ('.service','.socket') and unit.name not in ('nginx.service','vise.service'):
                require(unit.read_bytes()==(Path(NEW)/'etc/systemd/system'/unit.name).read_bytes(),'UNRELATED_UNIT_CHANGED')
        a=(Path(OLD)/'etc/systemd/system/vise.service').read_text()
        b=(Path(NEW)/'etc/systemd/system/vise.service').read_text()
        require(b==a+'\n[Install]\nWantedBy=multi-user.target\n','VISE_EXECUTION_CHANGED')
        require((Path(NEW)/'etc/systemd/system/multi-user.target.wants/vise.service').exists(),'VISE_BOOT_LINK_MISSING')
        require((Path(NEW)/'etc/systemd/system/timers.target.wants'/renewal[1]).exists(),'RENEWAL_BOOT_LINK_MISSING')
        running();wait_health('https://vise.mrj.am/api/health');run([NGINX,'-t','-c',NGINX_CONF])
        pg_pid=run([S,'show','postgresql.service','-p','MainPID','--value'],capture=True)
        vise_pid=run([S,'show','vise.service','-p','MainPID','--value'],capture=True)
        if not activate:
            print(json.dumps({'code':'VISE_PROMOTION_PREFLIGHT_PASSED'}));return
        atomic(STATE/'promotion.json',b'{"phase":"promotion-started"}\n')
        try:
            run([NEW+'/bin/switch-to-configuration','test'],180)
            require(os.path.realpath('/run/current-system')==NEW,'ACTIVATION_MISMATCH')
            require(private(MASKS)==original,'MASKS_CHANGED');atomic(MASKS,unmasked);run([S,'daemon-reload'],60)
            run([S,'restart','nginx.service'],60)
            run([S,'start',renewal[0]],600)
            require(run([S,'show',renewal[0],'-p','Result','--value'],capture=True).strip()==b'success','RENEWAL_FAILED')
            run([S,'start',renewal[1]],60)
            run([S,'is-active','--quiet',renewal[1]])
            running();wait_health('https://vise.mrj.am/api/health')
            require(run([S,'show','postgresql.service','-p','MainPID','--value'],capture=True)==pg_pid,'POSTGRESQL_RESTARTED')
            require(run([S,'show','vise.service','-p','MainPID','--value'],capture=True)==vise_pid,'VISE_RESTARTED')
            boot(NEW)
            atomic(STATE/'promotion.json',b'{"phase":"boot-and-renewal-verified"}\n')
            print(json.dumps({'schema_version':1,'code':'VISE_PROMOTED','current_and_boot':NEW,'https_health':True,'renewal_service_success':True,'renewal_timer_active':True,'other_services_active':True,'postgresql_restarted':False,'vise_restarted':False,'database_restored':False}))
        except Exception as original_error:
            atomic(STATE/'promotion-failure.json',json.dumps({'type':type(original_error).__name__,'code':str(original_error) if type(original_error) is RuntimeError else 'OPERATION_EXCEPTION'}).encode())
            run([S,'stop',renewal[1]],60)
            require(private(MASKS) in (original,unmasked),'MASKS_CHANGED_DURING_RETURN');atomic(MASKS,original)
            run([OLD+'/bin/switch-to-configuration','test'],180);run([S,'daemon-reload'],60);run([S,'restart','nginx.service'],60)
            require(os.path.realpath('/nix/var/nix/profiles/system') in (BOOT,NEW),'FOREIGN_BOOT_PROFILE')
            boot(BOOT);running();wait_health('https://vise.mrj.am/api/health')
            atomic(STATE/'promotion.json',b'{"phase":"returned-to-staged-service"}\n')
            raise RuntimeError('VISE_PROMOTION_RETURNED_TO_WORKING_SERVICE') from None
    finally:os.close(fd)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'code':'VISE_PROMOTION_REFUSED','reason':str(e) if type(e) is RuntimeError else type(e).__name__}));raise SystemExit(1)
