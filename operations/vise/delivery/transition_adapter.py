"""Fixed root ViSe operations; caller owns the shared deployment/backup lock.

Only old/new immutable generations from the protected plan can be selected.
No SQL, filesystem data rollback, or erasure-ledger replacement is implemented.
"""
import http.client,json,os,subprocess,time
from pathlib import Path
import contract as C,admission_orchestrator as O,acceptance_commit as K
import promotion_reservation as R,staging_lease as S,generation_views as G
import process_state as P,transition as T,generation_layout as L
import vise_verified_delivery as V

PROFILE='/nix/var/nix/profiles/system'
JOBS=Path('/var/lib/mrjam-intake-admission/jobs')
ACCEPTANCE=Path('/var/lib/mrjam-acceptance')
HOLD=Path('/run/mrjam-vise-transition/hold.json')
DROPIN=Path('/run/systemd/system/vise.service.d/90-mrjam-transition.conf')
INHIBITOR=b'[Unit]\nConditionPathExists=!/run/mrjam-vise-transition/hold.json\n'
RETAINED=('nginx','postgresql','forgejo','mrjam-rust-blue','mrjam-rust-green','mrjam-forgejo-runner')
FIELDS={'schema_version','profile','job','proposal_sha256','old','new','candidate','bundle','adopted',
    'previous_artifact','environment','accepted_plan_sha256','acceptance_sha256','forge_pull','review'}

def run(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    C.require(p.returncode==0 and len(p.stdout)<=65536,'VISE_TRANSITION_COMMAND_REFUSED');return p.stdout

class Adapter:
    def __init__(self,state,token):
        self.state=O.W.private_directory(state);self.plan=S.read(state/'plan.json');C.exact(self.plan,FIELDS)
        self.marker=R.identity(self.plan);self.key=self.marker['plan_sha256'];self.journal=state/(self.key+'.json')
        C.require(self.plan['profile']=='vise-v1' and all(G.store(self.plan[k]) for k in
            ('candidate','bundle','adopted','previous_artifact')) and all(G.digest(self.plan[k]) for k in
            ('accepted_plan_sha256','acceptance_sha256')),'VISE_TRANSITION_PLAN_REFUSED')
        G.state_checked(self.plan['environment'])
        C.require(self.plan['environment']['system']==self.plan['old'],'VISE_TRANSITION_BASE_REFUSED')
        self.job=JOBS/self.plan['job']/'state.json';self.token=token
        self.before=None
    def record(self):
        if not self.journal.exists():return {'schema_version':1,'plan_sha256':self.key,'phase':'prepared'}
        record=S.read(self.journal);C.exact(record,{'schema_version','plan_sha256','phase'})
        C.require(type(record['schema_version']) is int and record['schema_version']==1
            and record['plan_sha256']==self.key and record['phase'] in T.PHASES,'VISE_TRANSITION_JOURNAL_REFUSED')
        return record
    def phase(self):return self.record()['phase']
    def checkpoint(self,phase):
        C.require(phase in T.PHASES,'VISE_TRANSITION_PHASE_REFUSED')
        O.save(self.journal,{'schema_version':1,'plan_sha256':self.key,'phase':phase})
    def retained(self):
        return {u:run([P.CTL,'show',u+'.service','-p','MainPID','-p','ActiveState','-p','SubState']) for u in RETAINED}
    def bind(self):
        C.require(S.read(self.state/'plan.json')==self.plan,'VISE_TRANSITION_PLAN_CHANGED')
        # Historical completion needs its job receipt, not the current owner of
        # commit.json, which can legitimately belong to a subsequent delivery.
        if self.phase()=='complete':return
        job=O.read(self.job);owner=S.read(ACCEPTANCE/'commit.json')
        C.require(owner==K.identity(job) and job['id']==self.plan['job']
            and owner['proposal_sha256']==self.plan['proposal_sha256'],'VISE_TRANSITION_OWNER_CHANGED')
        prepared=S.read(ACCEPTANCE/'vise-plans'/(self.plan['job']+'.json'))
        ledger=S.read(ACCEPTANCE/self.plan['job']/'state.json')
        C.require(O.sha(O.encode(prepared))==self.plan['accepted_plan_sha256']
            and O.sha(O.encode(ledger))==self.plan['acceptance_sha256'],'VISE_TRANSITION_ACCEPTANCE_CHANGED')
        L.verify(self.plan['old'],self.plan['new'],self.plan['candidate'],
            previous_adopted=self.plan['environment'].get('vise',{}).get('adopted'))
        text=L.read(Path(self.plan['old'],'etc/systemd/system/vise.service')).decode()
        C.require('ExecStart='+self.plan['previous_artifact']+'/server\n' in text,'VISE_TRANSITION_OLD_ARTIFACT_CHANGED')
        self.before=self.retained()
    def reserve(self):
        self.backup_idle()
        C.require(all(p in (self.plan['old'],self.plan['new']) for p in R.actual()),'VISE_TRANSITION_LIVE_BASE_CHANGED')
        if not self.journal.exists():self.checkpoint('prepared')
        R.reserve(self.job,self.plan)
    def backup_idle(self):
        path=Path('/var/lib/mrjam-vise-backup/state.json')
        if not path.exists() and not path.is_symlink():return
        value=S.read(path)
        C.exact(value,{'schema_version','phase','restart_required','capture_id'})
        C.require(type(value['schema_version']) is int and value['schema_version']==1
            and type(value['restart_required']) is bool and type(value['capture_id']) is str
            and len(value['capture_id'])==32 and all(c in '0123456789abcdef' for c in value['capture_id'])
            and value['phase'] in {'complete','aborted'},'VISE_TRANSITION_BACKUP_RECOVERY_PENDING')
    def authorize(self):V.verify(self.plan,self.token)
    def inhibitor(self,enabled):
        marker={'schema_version':1,'plan_sha256':self.key}
        for directory in (HOLD.parent,DROPIN.parent):
            directory.mkdir(mode=0o700,exist_ok=True);O.W.private_directory(directory)
        if HOLD.exists() or HOLD.is_symlink():
            C.require(S.read(HOLD)==marker,'VISE_TRANSITION_HOLD_CHANGED')
        if DROPIN.exists() or DROPIN.is_symlink():
            C.require(C.regular_file(DROPIN,owner=os.getuid(),mode=0o600,maximum=4096)==INHIBITOR,
                'VISE_TRANSITION_DROPIN_CHANGED')
        if enabled:
            O.save(HOLD,marker)
            temporary=DROPIN.with_suffix('.next')
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as output:output.write(INHIBITOR);output.flush();os.fsync(output.fileno())
            os.replace(temporary,DROPIN);O.W.sync_directory(DROPIN.parent)
        else:
            # Remove the condition before its marker, so a crash leaves either
            # a safe stopped unit or an explicitly restartable one.
            if DROPIN.exists():DROPIN.unlink();O.W.sync_directory(DROPIN.parent)
            if HOLD.exists():HOLD.unlink();O.W.sync_directory(HOLD.parent)
        run([P.CTL,'daemon-reload'])
    def stop(self):
        self.inhibitor(True);run([P.CTL,'stop','vise.service'])
    def stopped(self):
        P.stopped(allow_failed=self.phase()=='recovering')
        if self.phase()!='recovering':
            raw=run([P.CTL,'show','vise.service','-p','Result','-p','ExecMainCode','-p','ExecMainStatus'])
            C.require(set(raw.decode().splitlines())=={'Result=success','ExecMainCode=1','ExecMainStatus=0'},
                'VISE_TRANSITION_STOP_NOT_GRACEFUL')
    def target(self,target):
        C.require(target in ('old','new'),'VISE_TRANSITION_TARGET_REFUSED');return self.plan[target]
    def switch(self,target):
        generation=self.target(target);self.stopped()
        if os.path.realpath('/run/current-system')!=generation:run([generation+'/bin/switch-to-configuration','test'])
        self.stopped()  # The fixed recipe must not implicitly restart the writer.
    def start(self):
        self.inhibitor(False);run([P.CTL,'start','vise.service'])
    def boot(self,target):
        generation=self.target(target)
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',generation])
        run([generation+'/bin/switch-to-configuration','boot'])
    def health(self):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            c=http.client.HTTPConnection('127.0.0.1',3017,timeout=3)
            try:
                c.request('GET','/api/health');response=c.getresponse();raw=response.read(1025)
                if response.status==200 and len(raw)<=1024 and json.loads(raw)=={'status':'ok','prototype':True}:return
            except (OSError,ValueError,http.client.HTTPException):pass
            finally:c.close()
            time.sleep(.5)
        raise C.Refused('VISE_TRANSITION_HEALTH_REFUSED')
    def verify(self,target,*,boot):
        generation=self.target(target)
        C.require(os.path.realpath('/run/current-system')==generation,'VISE_TRANSITION_CURRENT_CHANGED')
        if boot:C.require(os.path.realpath(PROFILE)==generation,'VISE_TRANSITION_BOOT_CHANGED')
        for relative in ('etc/nginx/nginx.conf','etc/systemd/system/vise.service','etc/mrjam-delivery-adopted.json'):
            C.require(L.read(Path('/')/relative)==L.read(Path(generation)/relative),'VISE_TRANSITION_INSTALLED_CONFIG_CHANGED')
        adopted=Path('/etc/mrjam-vise-delivery-adopted.json')
        expected=self.plan['adopted'] if target=='new' else self.plan['environment'].get('vise',{}).get('adopted')
        if expected is None:C.require(not adopted.exists() and not adopted.is_symlink(),'VISE_TRANSITION_ADOPTION_CHANGED')
        else:C.require(str(adopted.resolve(strict=True))==expected,'VISE_TRANSITION_ADOPTION_CHANGED')
        artifact=self.plan['bundle'] if target=='new' else self.plan['previous_artifact']
        manifest=Path(artifact,'artifact.json')
        executable=artifact+'/server'
        if Path(artifact,'server').is_symlink():
            server=C.parse(V.read(manifest,1048576))['server'];C.require(G.store(server),'VISE_TRANSITION_SERVER_PATH_REFUSED')
            executable=server+'/libexec/mrjam-server'
        first=P.wait_running_identity(executable);self.health()
        C.require(P.running_identity(executable)==first,'VISE_TRANSITION_PROCESS_CHANGED')
        C.require(self.retained()==self.before,'VISE_TRANSITION_RETAINED_PROCESS_CHANGED')
    def commit_job(self):R.commit(self.job,self.plan)
    def abort_job(self):R.abort(self.job,self.plan)
    def verify_complete(self):
        job=O.read(self.job)
        C.require(job['phase']=='deployed' and job.get('promotion') is None and job.get('delivery')=={
            'plan_sha256':self.key,'proposal_sha256':self.plan['proposal_sha256'],
            'generation':self.plan['new'],'previous_generation':self.plan['old']},'VISE_TRANSITION_COMPLETION_REFUSED')
