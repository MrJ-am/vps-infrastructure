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

def main(activate=True):
    require(os.geteuid()==0 and os.uname().nodename=='srv1982677','HOST_REFUSED');os.umask(0o077)
    fd=os.open('/var/lib/mrjam-cutover/first-deployment/transaction.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(all(os.path.realpath(p)==OLD for p in ['/run/current-system','/nix/var/nix/profiles/system']),'BASELINE_CHANGED')
        require(json.loads(private(STATE/'adopted.json'))=={'schema_version':1,'phase':'restricted-role-verified'},'ADOPTION_REQUIRED')
        require(json.loads(private(Path('/var/lib/mrjam-cutover/first-deployment/phase.json')))['phase']=='public-writes-open','CUTOVER_NOT_FINISHED')
        require(not (STATE/'activation-002.json').exists(),'ACTIVATION_ALREADY_ATTEMPTED')
        original=private(MASKS);m=json.loads(original)
        require(set(m)=={'schema_version','units'} and m['schema_version']==1 and type(m['units']) is list
            and all(type(n) is str and re.fullmatch('[A-Za-z0-9@_.-]+',n) for n in m['units'])
            and m['units']==sorted(set(m['units'])) and 'vise.service' in m['units'],'MASK_RECORD_REFUSED')
        unmasked=json.dumps({'schema_version':1,'units':[n for n in m['units'] if n!='vise.service']},sort_keys=True).encode()+b'\n'
        require(run([S,'show','vise.service','-p','ActiveState','--value'],capture=True).strip()==b'inactive','VISE_NOT_OFFLINE')
        require(run([S,'show','vise.service','-p','FragmentPath','--value'],capture=True).strip()==b'/run/systemd/generator.early/vise.service','FOREIGN_MASK_REFUSED')
        running();pg_pid=run([S,'show','postgresql.service','-p','MainPID','--value'],capture=True)
        for unit in (Path(OLD)/'etc/systemd/system').iterdir():
            if unit.is_file() and unit.suffix in ('.service','.socket') and unit.name not in ('nginx.service','postgresql.service'):
                require(unit.read_bytes()==(Path(NEW)/'etc/systemd/system'/unit.name).read_bytes(),'UNRELATED_UNIT_CHANGED')
        old_conf=Path(PG_OLD).read_text();new_conf=Path(PG_NEW).read_text()
        require(old_conf.replace('/nix/store/7i184rdm90kn4h9wh89g66i60lfsly3j-pg_hba.conf','/nix/store/bjhrnyax73g7w7jc5nwzdwvfhbh3k94c-pg_hba.conf')==new_conf,'PG_DELTA_REFUSED')
        old_hba=Path('/nix/store/7i184rdm90kn4h9wh89g66i60lfsly3j-pg_hba.conf').read_text()
        new_hba=Path('/nix/store/bjhrnyax73g7w7jc5nwzdwvfhbh3k94c-pg_hba.conf').read_text()
        block='local "etp_carnet" "etp_carnet" peer\nlocal all "etp_carnet" reject\nhost all "etp_carnet" 0.0.0.0/0 reject\nhost all "etp_carnet" ::0/0 reject\n'
        require(new_hba.count(block)==1 and new_hba.replace(block,'')==old_hba,'PG_HBA_DELTA_REFUSED')
        run([NGINX,'-t','-c',NGINX_CONF])
        if not activate:
            print(json.dumps({'schema_version':1,'code':'VISE_ACTIVATION_PREFLIGHT_PASSED','nginx_configuration_valid':True,'postgresql_delta_only_vise':True,'other_units_unchanged':True}));return
        atomic(STATE/'original-masks.json',original)
        atomic(STATE/'activation-002.json',b'{"phase":"activation-started"}\n')
        try:
            run([NEW+'/bin/switch-to-configuration','test'],180)
            require(os.path.realpath('/run/current-system')==NEW,'ACTIVATION_MISMATCH')
            require(run([S,'show','postgresql.service','-p','MainPID','--value'],capture=True)==pg_pid,'POSTGRESQL_RESTARTED')
            pg_config(PG_NEW)
            require(run([S,'show','postgresql.service','-p','MainPID','--value'],capture=True)!=pg_pid,'POSTGRESQL_NOT_RESTARTED')
            require(private(MASKS)==original,'MASKS_CHANGED')
            atomic(MASKS,unmasked);run([S,'daemon-reload'],60)
            run([S,'start','vise.service'],60);wait_health('http://127.0.0.1:3017/api/health')
            # The old nginx master has an immutable old config path; HUP cannot switch it.
            run([S,'restart','nginx.service'],60)
            wait_health('https://vise.mrj.am/api/health');running()
            atomic(STATE/'activation-002.json',b'{"phase":"staged-service-verified"}\n')
            print(json.dumps({'schema_version':1,'code':'VISE_STAGED_SERVICE_VERIFIED','https_health':True,'other_services_active':True,'postgresql_restarted':True,'boot_promoted':False,'database_restored':False}))
        except Exception as original_error:
            atomic(STATE/'activation-failure-002.json',json.dumps({'type':type(original_error).__name__,'code':str(original_error) if type(original_error) is RuntimeError else 'OPERATION_EXCEPTION'}).encode())
            try:
                run([S,'stop','vise.service'],120)
                require(private(MASKS) in (original,unmasked),'MASKS_CHANGED_DURING_RETURN')
                atomic(MASKS,original)
                run([OLD+'/bin/switch-to-configuration','test'],180)
                pg_config(PG_OLD);run([S,'daemon-reload'],60);run([S,'restart','nginx.service'],60);running()
                require(os.path.realpath('/run/current-system')==OLD,'RETURN_MISMATCH')
                atomic(STATE/'activation-002.json',b'{"phase":"returned-with-data-preserved"}\n')
                raise RuntimeError('VISE_ACTIVATION_RETURNED_DATA_PRESERVED')
            except RuntimeError:raise
            except Exception:raise RuntimeError('VISE_RETURN_REQUIRES_INSPECTION') from None
    finally:os.close(fd)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'code':'VISE_ACTIVATION_REFUSED','reason':str(e) if type(e) is RuntimeError else type(e).__name__}));raise SystemExit(1)
