"""Real-generation VM qualification; authority/acceptance are explicitly synthetic."""
import fcntl,json,os,sys,signal
from pathlib import Path
config=json.loads(Path(os.environ['VM_CONFIG']).read_bytes())
sys.path.insert(0,config['package']+'/lib')
import promotion_service as S
sys.path.extend([S.RECIPE+'/operations/vise/delivery',S.RECIPE+'/operations/ci/continuous-delivery-v1'])
import transition_adapter as A,transition as T
original_run=A.subprocess.run
def diagnostic_run(*args,**kwargs):
    hidden=kwargs.get('stderr')==A.subprocess.DEVNULL
    if hidden:kwargs['stderr']=A.subprocess.PIPE
    result=original_run(*args,**kwargs)
    if result.returncode and hidden:
        print('VM_COMMAND_STDERR',result.stderr[:8192].decode(errors='replace'),file=sys.stderr)
    return result
A.subprocess.run=diagnostic_run
original_identity=A.P.running_identity
def diagnostic_identity(executable,**kwargs):
    try:return original_identity(executable,**kwargs)
    except Exception:
        status=A.P.query();pid=status['MainPID'];root=Path('/proc')/str(pid)
        try:
            print('VM_PROCESS_DIAGNOSTIC',json.dumps({'expected':executable,
                'observed':os.readlink(root/'exe'),'uid':[line for line in
                (root/'status').read_text().splitlines() if line.startswith('Uid:')],
                'status':status}),file=sys.stderr)
        except OSError:print('VM_PROCESS_DIAGNOSTIC exited',file=sys.stderr)
        raise
A.P.running_identity=diagnostic_identity

state=Path('/var/lib/mrjam-promotion')
jobid='a'*64;digest='b'*64
for path in (state,A.JOBS,A.JOBS/jobid,A.ACCEPTANCE,A.ACCEPTANCE/'vise-plans',A.ACCEPTANCE/jobid,
             Path('/var/lib/mrjam-cutover/first-deployment'),Path('/var/lib/mrjam-staging')):
    path.mkdir(parents=True,mode=0o700,exist_ok=True);path.chmod(0o700)
lockpath=Path('/var/lib/mrjam-cutover/first-deployment/transaction.lock');lockpath.touch(mode=0o600,exist_ok=True)
with lockpath.open('rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not (state/'plan.json').exists():
        old=os.path.realpath('/run/current-system');new=os.path.realpath(old+'/specialisation/candidate')
        A.run(['/run/current-system/sw/bin/nix-env','--profile',A.PROFILE,'--set',old])
        environment={'schema_version':1,'system':old,'active_slot':'blue','adopted':config['platformAdopted'],
            'slots':{slot:{'server':config['old'],'runtime':config['old']} for slot in ('blue','green')}}
        prepared={'fixture':'synthetic acceptance plan'};ledger={'fixture':'synthetic acceptance receipts'}
        plan={'schema_version':1,'profile':'vise-v1','job':jobid,'proposal_sha256':digest,'old':old,'new':new,
            'candidate':config['candidate'],'bundle':config['new'],'adopted':config['adopted'],
            'previous_artifact':config['old'],'environment':environment,
            'accepted_plan_sha256':A.O.sha(A.O.encode(prepared)),'acceptance_sha256':A.O.sha(A.O.encode(ledger)),
            'forge_pull':1,'review':{'fixture':'synthetic'}}
        job={'schema_version':1,'id':jobid,'phase':'validated','capture':{'proposal_sha256':digest},
            'ready':{'base_sha256':'c'*64}}
        if config.get('queueCase'):
            proposal={'repository':'etp-vie-affective','repository_id':1433178398,'head':'d'*40}
            job['capture']['proposal']=proposal
            row={'repository':proposal['repository'],'head':proposal['head'],'number':1,'proposal_sha256':digest}
            ledger={'schema_version':1,'job':jobid,'proposal_sha256':digest,'receipts':{
                'mirror':row,'review':{**row,'review_id':1},
                'merge':{**row,'review_id':1,'protected_fast_forward':True,'merger':'mrjam-release-merge'},
                'sync':{'repository':proposal['repository'],'head':proposal['head'],
                    'canonical_forgejo_main':True,'github_main_synchronized':True,'token_revoked':True}},
                'inflight':None,'next_attempt':0,'attempts':0,'code':None}
            prepared={k:plan[k] for k in ('schema_version','profile','job','proposal_sha256',
                'old','new','candidate','bundle','adopted','previous_artifact','environment')}
            prepared.update(base_sha256='c'*64,preparation_sha256='e'*64,deployment_authorized=False)
        A.O.save(A.JOBS/jobid/'state.json',job)
        A.O.save(A.ACCEPTANCE/'commit.json',A.K.identity(job))
        A.O.save(A.ACCEPTANCE/'vise-plans'/(jobid+'.json'),prepared)
        A.O.save(A.ACCEPTANCE/jobid/'state.json',ledger)
        if not config.get('queueCase'):A.O.save(state/'plan.json',plan)
    # Only cryptographic/remote authority is synthetic. Generation, layout,
    # process, stop/start, health, boot, journal and job reservation are real.
    def authority(plan,token,**kwargs):
        assert token=='synthetic-observer'
        if (state/'plan.json').exists():assert plan==A.S.read(state/'plan.json')
        else:
            import accepted_plan
            assert plan==accepted_plan.load(A.ACCEPTANCE,A.JOBS,jobid)
        assert not (state/'injected-failure.json').exists(),'Recovery must not request candidate authority'
        return {'fixture':'no real signature or remote merge'}
    A.V.verify=authority
    if config.get('queueCase') and not (state/'plan.json').exists():
        import queue_tick as Q
        original_publish=Q.E.publish
        # The VM has synthetic retained sleep services, not platform HTTP
        # runtimes. Supply their declared environment; all file bindings,
        # real generation layout, boot/current observation and GC roots remain real.
        Q.E.publish=lambda *args,**kwargs:original_publish(*args,**kwargs,environment=lambda:environment)
        queued=Q.tick(state,lambda:'synthetic-observer')
        assert queued['code']=='PROMOTION_PLAN_ENQUEUED',queued
        assert Q.tick(state,lambda:(_ for _ in ()).throw(AssertionError('unexpected credential'))) is None
        plan=A.S.read(state/'plan.json')
        for target in ('old','new'):
            assert os.readlink(Q.ROOTS/(queued['plan_sha256']+'-'+target))==plan[target]
        A.O.save(state/'queue-proof.json',{'result':queued,'receipt_files_checked':True,
            'generation_layout_checked':True,'gc_roots_bound':True,'pending_plan_resumed':True,
            'synthetic_environment_provider':True})
    def interrupt_once(point):
        if config.get('crashPoint')!=point or (state/'interrupted.json').exists():return
        A.O.save(state/'interrupted.json',{'point':point,'signal':'SIGKILL'})
        os.kill(os.getpid(),signal.SIGKILL)
    class Observed(A.Adapter):
        def __getattribute__(self,name):
            value=super().__getattribute__(name)
            if name not in {'authorize','stop','stopped','switch','start','verify','boot','reserve','commit_job'}:return value
            def traced(*args,**kwargs):
                try:
                    result=value(*args,**kwargs)
                    if config.get('recoveryCase') and name=='verify' and args==('new',):
                        A.O.save(state/'injected-failure.json',{'point':'after-new-health'})
                        raise RuntimeError('SYNTHETIC_POST_HEALTH_FAILURE')
                    interrupt_once('after-'+name)
                    return result
                except Exception:
                    import traceback
                    print('VM_ADAPTER_OPERATION_FAILED',name,file=sys.stderr);traceback.print_exc();raise
            return traced
        def checkpoint(self,phase):
            super().checkpoint(phase)
            path=state/'events.json';events=A.S.read(path) if path.exists() else []
            events.append({'phase':phase,'current':os.path.realpath('/run/current-system'),
                'boot':os.path.realpath(A.PROFILE)})
            A.O.save(path,events)
            interrupt_once('checkpoint-'+phase)
    adapter=Observed(state,'synthetic-observer');result=T.promote(adapter)
    expected='VISE_FAILED' if config.get('recoveryCase') else 'VISE_COMPLETE'
    assert result['code']==expected,result
    if config.get('recoveryCase'):
        assert result['previous_restored']
        adapter.verify('old',boot=True)
        job=A.O.read(adapter.job)
        assert job['phase']=='validated' and job.get('promotion') is None
        assert A.K.returned(job)
        assert A.S.pending_commit(A.ACCEPTANCE,A.JOBS) is None
    else:adapter.verify_complete()
    A.O.save(state/'proof.json',{'result':result,'real_generation_transition':True,
        'real_return':True,'real_boot_profile':True,'synthetic_authority':True,'production_access':False,
        'queue':A.S.read(state/'queue-proof.json') if config.get('queueCase') else None})
