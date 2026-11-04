"""Real discovery and source-preparation package under an isolated identity."""
import json,os,sqlite3,subprocess
from pathlib import Path
SYSTEMD='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin'
PACKAGE='/nix/store/vs5dc3klynsc1xm83sm9l55s4aqrz60f-mrjam-exact-intake-preparation-1'
DISCOVERY='/nix/store/pp91fpraqdkassx2v09qvx4kqj00pk76-mrjam-persistent-intake-discovery-1'
ADOPTED='/nix/store/5zc3h26gkpkfqhyvdpsrz1yim6nsmy8v-mrjam-adopted-source.json'
STATE=Path('/var/lib/private/mrjam-intake-preparation-qualification')
def main():
    assert os.getuid()==0 and os.uname().nodename=='srv1982677'
    properties={
        'DynamicUser':'yes','User':'mrjam-prepare-qual',
        'StateDirectory':'mrjam-intake-preparation-qualification','StateDirectoryMode':'0700',
        'LoadCredential':'github-app:/var/lib/mrjam-github-app/app-credentials.json',
        'UMask':'0077','ProtectSystem':'strict','ProtectHome':'yes','PrivateDevices':'yes',
        'TemporaryFileSystem':'/tmp:rw,size=512M,mode=1777',
        'NoNewPrivileges':'yes','CapabilityBoundingSet':'','MemoryMax':'768M','TasksMax':'32',
        'RestrictAddressFamilies':'AF_UNIX AF_INET AF_INET6','TimeoutStartSec':'840','StandardError':'null',
        'Environment':'MRJAM_ADOPTED_BASE='+ADOPTED}
    observations=[]
    for name,executable in [('discovery',DISCOVERY+'/bin/mrjam-github-discover'),
        ('prepare',PACKAGE+'/bin/mrjam-intake-prepare'),('resume',PACKAGE+'/bin/mrjam-intake-prepare')]:
        args=[SYSTEMD+'/systemd-run','--quiet','--wait','--pipe','--unit=mrjam-intake-prepare-qualification-'+name]
        for key,value in properties.items():args+=['--property='+key+'='+value]
        p=subprocess.run(args+[executable],capture_output=True,timeout=870)
        codes=[]
        for line in p.stdout.splitlines():
            try:
                code=json.loads(line).get('code','')
                if type(code) is str and len(code)<=80 and code.replace('_','').isupper():codes.append(code)
            except Exception:pass
        if p.returncode!=0:
            print(json.dumps({'code':'LIVE_PREPARATION_UNIT_REFUSED','phase':name,'exit':p.returncode,'closed_codes':codes}))
            raise SystemExit(2)
        observations.append({'phase':name,'codes':codes})
    snapshot=json.loads((STATE/'proposals.json').read_bytes())
    assert snapshot['read_token_revoked'] and snapshot['deployment_authorized'] is False
    db=sqlite3.connect('file:'+str(STATE/'intake.sqlite')+'?mode=ro',uri=True)
    try:states={row[0]:row[1] for row in db.execute('SELECT state,count(*) FROM jobs GROUP BY state')}
    finally:db.close()
    assert 'running' not in states
    if not snapshot['proposals']:
        assert observations[1]['codes']==['PREPARATION_IDLE'] and observations[2]['codes']==['PREPARATION_IDLE']
    print(json.dumps({'code':'LIVE_PREPARATION_QUALIFIED','observations':observations,'proposals':len(snapshot['proposals']),
        'queue_states':states,'discovery_token_revoked':True,'admission_or_deployment_performed':False}))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'LIVE_PREPARATION_QUALIFICATION_FAILED','exception_type':type(error).__name__}));raise SystemExit(2)
