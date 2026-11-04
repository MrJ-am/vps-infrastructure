"""Read fixed PR5 deployment metadata and health; never activate or expose data."""
import datetime,http.client,json,os,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/nix/store/chl7jblpb5c3jl2xgyldjspsmcx9l9n2-mrjam-protected-delivery-recipe-1/operations/ci/continuous-delivery-v1')
import delivery_environment as E
JOB='85e9d595fdd178399721f94816c88cfe20b65056541552eb6e07747537848d89'
DIGEST='76cfaec0736cc5a52cc4ec4bd4312b724789481dce518cf67cebb747e5855d1f'
HEAD='8977c76717006f562b2ca3123ad1f3283007e568'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'

def read(path,maximum=65536):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and s.st_size<=maximum
        return json.load(f)

def main():
    assert os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1
    job=read('/var/lib/mrjam-intake-admission/jobs/'+JOB+'/state.json')
    assert job['id']==JOB and job['capture']['proposal_sha256']==DIGEST and job['capture']['proposal']['head']==HEAD
    result={'schema_version':1,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'fixed-pr5-live-metadata-and-health','job':JOB,'proposal_sha256':DIGEST,'head':HEAD,
        'phase':job['phase'],'code':job.get('code'),'attempts':job['attempts'],'run':job.get('run'),
        'delivery':job.get('delivery'),'promotion_marker':job.get('promotion')}
    path=Path('/var/lib/mrjam-acceptance')/JOB/'state.json'
    acceptance=read(path) if path.exists() else None
    result['acceptance']=acceptance
    result['environment']=E.read()
    state=result['environment']
    lease=Path('/var/lib/mrjam-staging/lease.json')
    result['staging_lease_present']=lease.exists() or lease.is_symlink()
    plan=read('/var/lib/mrjam-promotion/plan.json')
    result['promotion_plan_matches']=plan.get('job')==JOB and plan.get('proposal_sha256')==DIGEST
    delivery=job.get('delivery') or {}
    result['promotion_journal']=None
    if delivery.get('plan_sha256'):
        key=delivery['plan_sha256']
        assert len(key)==64 and all(c in '0123456789abcdef' for c in key)
        result['promotion_journal']=read('/var/lib/mrjam-promotion/'+key+'.json')
    units=['nginx','postgresql','forgejo','mrjam-forgejo-runner','vise','mrjam-rust-blue','mrjam-rust-green']
    result['services']={}
    for name in units:
        raw=subprocess.check_output([CTL,'show',name+'.service','-p','MainPID','-p','ActiveState'],timeout=10,text=True)
        value=dict(line.split('=',1) for line in raw.splitlines());pid=int(value['MainPID'])
        value['MainPID']=pid
        if name.startswith('mrjam-rust-') and pid:
            value['executable']=os.path.realpath('/proc/'+str(pid)+'/exe')
            slot=name.removeprefix('mrjam-rust-')
            value['executable_matches']=value['executable']==state['slots'][slot]['server']+'/libexec/mrjam-server'
        result['services'][name]=value
    result['readiness']={}
    for slot,port in [('blue',38101),('green',38102)]:
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        try:
            c.request('GET','/readyz');r=c.getresponse();result['readiness'][slot]=r.status
        finally:c.close()
    fd=os.open('/var/lib/mrjam-ci-credentials/forgejo-policy-token',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o400 and s.st_size<4096
        token=f.read().strip()
    def forge(path):
        c=http.client.HTTPConnection('127.0.0.1',3004,timeout=10)
        try:
            c.request('GET','/api/v1/repos/MrJ-am/'+path,headers={'Host':'forge.mrj.am','Authorization':'token '+token})
            r=c.getresponse();raw=r.read(1048577);assert r.status==200 and len(raw)<=1048576
            return json.loads(raw)
        finally:c.close()
    run=forge('mrjam-validation/actions/runs/7');assert run['id']==7
    result['forge_run']={'id':7,'status':run['status']}
    branch=forge('mrjam-plateforme/branches/main')
    result['forge_main']=branch['commit']['id']
    receipts=acceptance['receipts'] if acceptance else {}
    result['forge_pull']=None
    if 'mirror' in receipts:
        number=receipts['mirror']['number'];assert type(number) is int and number>0
        pull=forge('mrjam-plateforme/pulls/'+str(number))
        result['forge_pull']={'number':number,'merged':pull['merged'],'head':pull['head']['sha']}
    result['complete_observed']=(job['phase']=='deployed' and job.get('promotion') is None
        and result['promotion_plan_matches'] and not result['staging_lease_present']
        and result['promotion_journal'] is not None and result['promotion_journal']['phase']=='complete'
        and result['forge_main']==HEAD and result['forge_pull']=={'number':receipts.get('mirror',{}).get('number'),'merged':True,'head':HEAD}
        and set(receipts)=={'mirror','review','merge','sync'} and receipts['sync'].get('token_revoked') is True
        and result['readiness']=={'blue':200,'green':200}
        and all(v['ActiveState']=='active' for v in result['services'].values())
        and all(result['services']['mrjam-rust-'+s].get('executable_matches') for s in ['blue','green'])
        and delivery.get('generation')==state['system'])
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'code':'PR5_OBSERVATION_REFUSED','exception_type':type(error).__name__}));raise SystemExit(1) from None
