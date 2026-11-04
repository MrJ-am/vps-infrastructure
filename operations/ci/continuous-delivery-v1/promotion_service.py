"""Installed root recovery service; immutable root plan, no candidate commands."""
import fcntl,http.client,json,os,re,ssl,subprocess,sys,time
from pathlib import Path
ADMISSION='/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1'
ANCHOR='/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1'
ENABLE_VISE=False
RECIPE='@delivery-recipe@'
sys.path.insert(0,ADMISSION+'/lib')
sys.path.insert(0,ANCHOR+'/lib')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C,admission_control as A,admission_orchestrator as O,github_proposals as G
import promotion_transaction as T,promotion_reservation as R,verified_delivery as V
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
UNITS=['nginx','postgresql','forgejo','mrjam-rust-blue','mrjam-rust-green','mrjam-forgejo-runner']
PORTS={'blue':38101,'green':38102}

def run(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    C.require(p.returncode==0 and len(p.stdout)<=65536,'PROMOTION_COMMAND_REFUSED');return p.stdout
def credential():
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/'forgejo-observer';fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:G.credential_metadata(os.fstat(fd),0,0);return os.read(fd,32769).decode().strip()
    finally:os.close(fd)
def public_health():
    ctx=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt');result={}
    for host,path,allowed in [('audition.mrj.am','/',[200]),('log.mrj.am','/',[200]),('logique.echos.systems','/',[200]),
        ('vision.mrj.am','/',[200]),('forge.mrj.am','/',[200,303]),('principiipetit.io','/matheval/',[200])]:
        c=http.client.HTTPSConnection(host,443,timeout=10,context=ctx)
        try:
            c.request('GET',path);response=c.getresponse();status=response.status;response.read(1024)
            C.require(status in allowed,'PROMOTION_PUBLIC_HEALTH_REFUSED');result[host]=status
        finally:c.close()
    return result

class Adapter:
    def __init__(self,state):
        self.state=O.W.private_directory(state)
        self.plan=C.parse(C.regular_file(state/'plan.json',owner=0,mode=0o600,maximum=65536))
        C.exact(self.plan,{'schema_version','job','proposal_sha256','old','new','slot','bundle','forge_pull','review'})
        self.marker=R.identity(self.plan);self.key=self.marker['plan_sha256'];self.journal=state/(self.key+'.json')
        C.require(self.plan['slot'] in PORTS and type(self.plan['forge_pull']) is int and self.plan['forge_pull']>0,'PROMOTION_SCOPE_REFUSED')
        self.job=Path('/var/lib/mrjam-intake-admission/jobs')/self.plan['job']/'state.json'
        self.routes={k:Path(self.plan[k], 'etc/nginx/nginx.conf').read_bytes() for k in ['old','new']}
        self.slots={'new':self.plan['slot'],'old':'green' if self.plan['slot']=='blue' else 'blue'}
        old_port=('127.0.0.1:'+str(PORTS[self.slots['old']])).encode();new_port=('127.0.0.1:'+str(PORTS[self.slots['new']])).encode()
        C.require(self.routes['old'].count(old_port)==11 and new_port not in self.routes['old']
            and self.routes['old'].replace(old_port,new_port)==self.routes['new'],'PROMOTION_ROUTE_DIFF_REFUSED')
        self.bindings={}
        for slot in PORTS:
            texts=[Path(self.plan[k], 'etc/systemd/system/mrjam-rust-'+slot+'.service').read_text() for k in ['old','new']]
            # WantedBy lives in [Install], not [Service], and intentionally
            # changes on promotion. Compare the complete service section only.
            sections=[text.split('[Service]\n',1)[1].split('\n[',1)[0].rstrip() for text in texts]
            C.require(sections[0]==sections[1], 'PROMOTION_SLOT_COMMAND_CHANGED')
            matches=re.findall(r'^ExecStart=(/nix/store/[^\s]+)/bin/mrjam-server serve --config (/nix/store/[^\s]+)/runtime.json$',texts[0],re.M)
            C.require(len(matches)==1 and all(V.STORE.fullmatch(p) for p in matches[0]),'PROMOTION_SLOT_BINDING_REFUSED')
            self.bindings[slot]=matches[0]
        self.before=self.retained()
    def retained(self):return {u:run([CTL,'show',u+'.service','-p','MainPID','-p','ActiveState','-p','SubState']).decode() for u in UNITS}
    def record(self):
        if not self.journal.exists():return {'schema_version':1,'plan_sha256':self.key,'phase':'prepared'}
        value=C.parse(C.regular_file(self.journal,owner=0,mode=0o600,maximum=65536))
        C.exact(value,{'schema_version','plan_sha256','phase'})
        C.require(value['schema_version']==1 and value['plan_sha256']==self.key and value['phase'] in T.PHASES,'PROMOTION_JOURNAL_REFUSED');return value
    def phase(self):return self.record()['phase']
    def checkpoint(self,phase):
        C.require(phase in T.PHASES,'PROMOTION_PHASE_REFUSED')
        O.save(self.journal,{'schema_version':1,'plan_sha256':self.key,'phase':phase})
    def reserve(self):
        C.require(all(p in [self.plan['old'],self.plan['new']] for p in R.actual()),'PROMOTION_BASELINE_CHANGED')
        if not self.journal.exists():self.checkpoint('prepared')
        R.reserve(self.job,self.plan)
    def authorize(self):
        bundle=V.verify(self.plan,credential());server,runtime=self.bindings[self.slots['new']]
        C.require((server,runtime)==(bundle['server'],bundle['runtime']),'PROMOTION_UNBOUND_SLOT')
        adopted=C.parse(Path(self.plan['new'],'etc/mrjam-delivery-adopted.json').read_bytes())
        C.exact(adopted,{'schema_version','source','policy','proposal_sha256'})
        C.require(adopted['schema_version']==1 and adopted['proposal_sha256']==self.plan['proposal_sha256']
            and all(V.STORE.fullmatch(adopted[k]) for k in ['source','policy']),'PROMOTION_ADOPTED_DESCRIPTOR_REFUSED')
        C.require(C.sha(Path(adopted['source'],'manifest.json').read_bytes())==self.plan['proposal_sha256']
            and C.sha(Path(adopted['policy']).read_bytes())==A.load(self.plan['proposal_sha256'])['authority']['report_policy_sha256'],
            'PROMOTION_ADOPTED_CONTENT_CHANGED')
    def ready(self,target):
        slot=self.slots[target];server,runtime=self.bindings[slot]
        # Both generations retain the exact same slot commands. Starting a
        # stopped rollback slot after reboot never installs unverified code.
        active=Path('/etc/systemd/system/mrjam-rust-'+slot+'.service').read_text()
        C.require('ExecStart='+server+'/bin/mrjam-server serve --config '+runtime+'/runtime.json\n' in active,'PROMOTION_RUNNING_UNIT_CHANGED')
        run([CTL,'start','mrjam-rust-'+slot+'.service'])
        expected=C.parse(Path(runtime,'runtime.json').read_bytes())['required_capabilities'];end=time.monotonic()+60
        while time.monotonic()<end:
            try:
                c=http.client.HTTPConnection('127.0.0.1',PORTS[slot],timeout=3)
                try:
                    c.request('GET','/readyz',headers={'Host':'audition.mrj.am'});r=c.getresponse();raw=r.read(8193)
                finally:c.close()
                if r.status==200 and len(raw)<=8192:
                    C.require(json.loads(raw)=={'status':'ready','scope':'configured-capabilities-only','capabilities':expected},'PROMOTION_READINESS_REFUSED')
                    pid=int(run([CTL,'show','mrjam-rust-'+slot+'.service','-p','MainPID','--value']))
                    C.require(os.readlink('/proc/'+str(pid)+'/exe')==server+'/libexec/mrjam-server','PROMOTION_PROCESS_IDENTITY_REFUSED')
                    self.before=self.retained();return
            except (OSError,http.client.HTTPException,json.JSONDecodeError):pass
            time.sleep(.5)
        raise C.Refused('PROMOTION_SLOT_NOT_READY')
    def switch(self,target):
        if os.path.realpath('/run/current-system')!=self.plan[target]:run([self.plan[target]+'/bin/switch-to-configuration','test'])
    def boot(self,target):
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',self.plan[target]])
        run([self.plan[target]+'/bin/switch-to-configuration','boot'])
    def verify(self,target,*,boot):
        C.require(os.path.realpath('/run/current-system')==self.plan[target],'PROMOTION_CURRENT_REFUSED')
        if boot:C.require(os.path.realpath(PROFILE)==self.plan[target],'PROMOTION_BOOT_REFUSED')
        C.require(Path('/etc/nginx/nginx.conf').read_bytes()==self.routes[target],'PROMOTION_ROUTE_NOT_INSTALLED')
        C.require(Path('/etc/mrjam-delivery-adopted.json').read_bytes()==Path(self.plan[target],'etc/mrjam-delivery-adopted.json').read_bytes(),'PROMOTION_ADOPTED_NOT_INSTALLED')
        C.require(self.retained()==self.before,'PROMOTION_RETAINED_PROCESS_CHANGED')
        public_health()
    def commit_job(self):R.commit(self.job,self.plan)
    def abort_job(self):R.abort(self.job,self.plan)
    def verify_complete(self):
        # Historical completion remains valid after a subsequent delivery.
        # Do not attempt to reactivate this old generation on later timer ticks.
        value=O.read(self.job)
        C.require(value['phase']=='deployed' and value.get('delivery',{}).get('plan_sha256')==self.key
            and value.get('promotion') is None,'PROMOTION_COMPLETION_RECEIPT_REFUSED')

def resume(state):
    plan=C.parse(C.regular_file(state/'plan.json',owner=0,mode=0o600,maximum=65536))
    if plan.get('profile')=='vise-v1':
        C.require(ENABLE_VISE,'PROMOTION_PROFILE_NOT_INSTALLED')
        sys.path.extend([str(Path(RECIPE)/'operations/vise/delivery'),
            str(Path(RECIPE)/'operations/ci/continuous-delivery-v1')])
        import transition_adapter as VA,transition as VT
        adapter=VA.Adapter(state,credential());result=VT.promote(adapter)
    else:
        C.require('profile' not in plan,'PROMOTION_PROFILE_REFUSED')
        adapter=Adapter(state);result=T.promote(adapter)
    return {**result,'plan_sha256':adapter.key,'job':adapter.plan['job']}

def tick(state):
    if ENABLE_VISE:
        sys.path.extend([str(Path(RECIPE)/'operations/vise/delivery'),
            str(Path(RECIPE)/'operations/ci/continuous-delivery-v1')])
        import queue_tick as Q
        result=Q.tick(state,credential)
        if result is not None:return result
    return resume(state)

def main():
    C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','PROMOTION_HOST_REFUSED')
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('{"code":"PROMOTION_ENVIRONMENT_BUSY"}');return
        result=tick(Path(os.environ['STATE_DIRECTORY']))
        print(json.dumps(result))
        if result['code'] not in {'PROMOTION_COMPLETE','VISE_COMPLETE','PROMOTION_PLAN_ENQUEUED',
                'VISE_QUEUE_IDLE','VISE_QUEUE_PLATFORM_PENDING','VISE_QUEUE_ACCEPTANCE_PENDING',
                'VISE_QUEUE_RETURNED'}:raise SystemExit(2)
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'PROMOTION_RETRY_REQUIRED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
