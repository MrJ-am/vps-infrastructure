"""Fixed VPS operations for the durable, exclusively reserved staging plan."""
import os,subprocess,time
from pathlib import Path
import contract as C,admission_orchestrator as O
import staging_lease as L,staging_runtime as R,staging_transaction as T
import delivery_constructor as D
from source_snapshot import Refused

CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'

def actual():return os.path.realpath('/run/current-system'),os.path.realpath(PROFILE)

def run(args,timeout=180):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    C.require(p.returncode==0 and len(p.stdout)<=65536,'STAGING_COMMAND_REFUSED');return p.stdout

class Adapter:
    def __init__(self,state,acceptance,jobs,verify):
        self.state=O.W.private_directory(state);self.acceptance=acceptance;self.jobs=jobs;self.verify_authority=verify
        self.lease=L.read(state/'lease.json')
        C.require(type(self.lease) is dict and L.G.digest(self.lease.get('plan_sha256')),'STAGING_LEASE_REFUSED')
        self.plan=L.read(O.W.private_directory(state/'plans')/(self.lease['plan_sha256']+'.json'))
        C.require(L.identity(self.plan)==self.lease,'STAGING_PLAN_BINDING_REFUSED')
        self.journal=O.W.private_directory(state/'records')/(self.lease['plan_sha256']+'.json')
        self.targets={'old':self.plan['old'],'new':self.plan['staged']};self.slot=self.plan['slot']
        self.unit='mrjam-rust-'+self.slot+'.service'
        self.units=['nginx.service','postgresql.service','forgejo.service','mrjam-forgejo-runner.service',
            'mrjam-rust-'+self.plan['old']['active_slot']+'.service']
        self.before=self.retained()
        C.require(all('ActiveState=active\n' in value for value in self.before.values()),'STAGING_PUBLIC_SERVICE_INACTIVE')
        self.routes=Path(self.plan['old']['system'],'etc/nginx/nginx.conf').read_bytes()
        C.require(self.routes==Path(self.plan['staged']['system'],'etc/nginx/nginx.conf').read_bytes(),
            'STAGING_ROUTE_CHANGE_REFUSED')
        off=('127.0.0.1:'+str(R.PORTS[self.slot])).encode()
        on=('127.0.0.1:'+str(R.PORTS[self.plan['old']['active_slot']])).encode()
        C.require(off not in self.routes and self.routes.count(on)==11,'STAGING_SLOT_IS_PUBLIC')
        C.require(self.plan['old']['adopted']==self.plan['staged']['adopted'],'STAGING_ADOPTION_CHANGE_REFUSED')
    def retained(self):
        return {u:run([CTL,'show',u,'-p','MainPID','-p','ActiveState','-p','SubState']).decode() for u in self.units}
    def phase(self):
        record=L.read(self.journal)
        C.require(set(record)==set(self.lease)|{'phase','runtime'}
            and all(record[k]==v for k,v in self.lease.items()) and record['phase'] in T.PHASES,'STAGING_JOURNAL_REFUSED')
        return record['phase']
    def bind(self):
        # A historical ready record never authorizes reactivation after promotion.
        C.require(L.read(self.state/'lease.json')==self.lease,'STAGING_LEASE_CHANGED')
        C.require(all(p in {s['system'] for s in self.targets.values()} for p in actual()),'STAGING_LIVE_BASE_CHANGED')
        if self.phase() not in {'ready','failed'}:
            owner=L.pending_commit(self.acceptance,self.jobs)
            C.require(owner is None,'STAGING_ACCEPTANCE_ALREADY_STARTED')
    def authorize(self):
        directory=O.W.private_directory(self.jobs/self.plan['job']);job=O.read(directory/'state.json')
        C.require(L.K.identity(job)=={k:self.plan[k] for k in ('schema_version','job','proposal_sha256','base_sha256')},
            'STAGING_JOB_CHANGED')
        binding=D.binding(directory,job,self.slot,self.plan['old']['slots'][self.slot]['runtime'],self.verify_authority)
        candidate=C.parse(Path(self.plan['candidate'],'descriptor.json').read_bytes())
        C.require(candidate['binding_sha256']==C.sha(O.encode(binding)) and candidate['bundle']==self.plan['bundle'],
            'STAGING_AUTHORITY_BINDING_CHANGED')
    def no_clients(self):
        for name in ('tcp','tcp6'):
            rows=Path('/proc/net/'+name).read_text().splitlines()[1:]
            C.require(not any(int(r.split()[1].split(':')[1],16)==R.PORTS[self.slot]
                and r.split()[3] not in {'0A','06'} for r in rows),'STAGING_CLIENTS_REMAIN')
    def stop_slot(self):run([CTL,'stop',self.unit],timeout=60)
    def start_slot(self):run([CTL,'start',self.unit],timeout=60)
    def switch(self,target):
        run([self.targets[target]['system']+'/bin/switch-to-configuration','test'])
    def boot(self,target):
        system=self.targets[target]['system']
        run(['/run/current-system/sw/bin/nix-env','--profile',PROFILE,'--set',system])
        run([system+'/bin/switch-to-configuration','boot'])
    def verify(self,target,*,boot):
        expected=self.targets[target];current,profile=actual()
        C.require(current==expected['system'] and (not boot or profile==current),'STAGING_GENERATION_REFUSED')
        C.require(self.retained()==self.before,'STAGING_PUBLIC_PROCESS_CHANGED')
        C.require(Path('/etc/nginx/nginx.conf').read_bytes()==self.routes,'STAGING_PUBLIC_ROUTE_CHANGED')
        C.require(os.path.realpath('/etc/mrjam-delivery-adopted.json')==expected['adopted'],'STAGING_ADOPTION_DRIFT')
        for slot,binding in expected['slots'].items():
            name='mrjam-rust-'+slot+'.service'
            C.require(Path('/etc/systemd/system',name).read_bytes()==Path(current,'etc/systemd/system',name).read_bytes(),
                'STAGING_RUNNING_UNIT_CHANGED')
            for root in ('/etc/systemd/system','/run/systemd/system'):
                dropin=Path(root,name+'.d')
                C.require(not dropin.exists() or not any(dropin.iterdir()),'STAGING_DROPIN_REFUSED')
        deadline=time.monotonic()+60
        while True:
            try:self.runtime=R.capture(self.slot,expected);break
            except (OSError,C.Refused,Refused):
                if time.monotonic()>=deadline:raise
                time.sleep(.5)
        # Recheck public process identities after the readiness wait.
        C.require(self.retained()==self.before,'STAGING_PUBLIC_PROCESS_CHANGED')
        if target=='new' and boot and self.phase()=='ready':
            # A reboot may change PID/starttime. This refresh performs reads
            # only and cannot undo a merge whose response was lost.
            self.checkpoint('ready')
    def checkpoint(self,phase):
        L.checkpoint(self.state,self.plan,phase,self.runtime if phase=='ready' else None)
    def release(self):L.release(self.state,self.plan,self.acceptance,self.jobs,actual)
