"""Run the real read-only intake package twice in an isolated systemd identity."""
import hashlib,json,os,sqlite3,stat,subprocess
from pathlib import Path
SYSTEMD='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin'
PACKAGE='/nix/store/pp91fpraqdkassx2v09qvx4kqj00pk76-mrjam-persistent-intake-discovery-1'
STATE=Path('/var/lib/private/mrjam-intake-discovery-qualification')
def main():
    assert os.getuid()==0 and os.uname().nodename=='srv1982677'
    properties={
        'DynamicUser':'yes','User':'mrjam-intake-qual',
        'StateDirectory':'mrjam-intake-discovery-qualification','StateDirectoryMode':'0700',
        'LoadCredential':'github-app:/var/lib/mrjam-github-app/app-credentials.json',
        'UMask':'0077','ProtectSystem':'strict','ProtectHome':'yes','PrivateTmp':'yes','PrivateDevices':'yes',
        'NoNewPrivileges':'yes','CapabilityBoundingSet':'','MemoryMax':'128M','TasksMax':'32',
        'RestrictAddressFamilies':'AF_UNIX AF_INET AF_INET6','TimeoutStartSec':'180','StandardError':'null'}
    keys=set();counts=[]
    for index in (1,2):
        args=[SYSTEMD+'/systemd-run','--quiet','--wait','--pipe','--unit=mrjam-intake-discovery-qualification-'+str(index)]
        for name,value in properties.items():args+=['--property='+name+'='+value]
        args+=[PACKAGE+'/bin/mrjam-github-discover']
        p=subprocess.run(args,capture_output=True,timeout=210)
        if p.returncode!=0:
            codes=[]
            for line in p.stdout.splitlines():
                try:
                    value=json.loads(line).get('code','')
                    if type(value) is str and value.replace('_','').isupper() and len(value)<=80:codes.append(value)
                except Exception:pass
            print(json.dumps({'code':'QUALIFICATION_UNIT_REFUSED','exit':p.returncode,
                'invalid':b'Invalid' in p.stderr or b'invalid' in p.stderr,
                'already_exists':b'already' in p.stderr,'credential':b'credential' in p.stderr,
                'property':b'property' in p.stderr,'user':b'user' in p.stderr,
                'stdout_bytes':len(p.stdout),'closed_codes':codes}))
            raise SystemExit(2)
        assert len(p.stdout)<=4096
        lines=[json.loads(line) for line in p.stdout.splitlines()]
        assert len(lines)==2 and lines[0]['code']=='PROPOSALS_OBSERVED' and lines[1]['code']=='PROPOSALS_QUEUED'
        snapshot=json.loads((STATE/'proposals.json').read_bytes())
        assert snapshot['read_token_revoked'] and snapshot['deployment_authorized'] is False
        for proposal in snapshot['proposals']:
            keys.add(hashlib.sha256(json.dumps(proposal,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        db=sqlite3.connect('file:'+str(STATE/'intake.sqlite')+'?mode=ro',uri=True)
        try:
            actual={r[0] for r in db.execute('SELECT key FROM jobs')}
            assert actual==keys
            assert db.execute("SELECT count(*) FROM jobs WHERE state!='pending'").fetchone()[0]==0
            counts.append(len(actual))
        finally:db.close()
        for name in ('proposals.json','intake.sqlite'):
            info=(STATE/name).lstat();assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
    print(json.dumps({'code':'LIVE_PERSISTENT_INTAKE_QUALIFIED','observations':2,'queue_counts':counts,
        'tokens_revoked':True,'private_state':True,'admission_or_deployment_performed':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'LIVE_INTAKE_QUALIFICATION_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
