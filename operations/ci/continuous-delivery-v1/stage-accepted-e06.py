"""Install accepted signed bytes in blue, retain public green, exercise return."""
import fcntl,hashlib,http.client,json,os,re,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/nix/store/dlphwj3kmxmljjg4dj6flihqah9jghgy-mrjam-protected-admission-controller-1/lib')
sys.path.insert(0,'/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C,admission_control as A,signer,admission_orchestrator as O
import forge_merge as M,validation_dispatch as D,delivery_frontends as F,stage_transaction as T
OLD='/nix/store/mp6b02wzn3pj5fn1g8j8gp9nzfr4fsq0-nixos-system-srv1982677-26.05pre-git'
NEW='/nix/store/iiac77hsa8mrlcf87n7jripg7vdic77x-nixos-system-srv1982677-26.05pre-git'
BUNDLE=Path('/nix/store/cqajrssk884jfr32mh65kr0gr13id2im-mrjam-delivery-bundle-e06f030310ae-blue')
JOB=Path('/var/lib/mrjam-intake-admission/jobs/18ff551f7e7062936b962f6d162a2835a43df087795456c9bf46e7b447a7f230')
DIGEST='e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7'
HEAD='e4cc836d76c4104b4d356e583a2e5f34a827f90b'
CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
PROFILE='/nix/var/nix/profiles/system'
JOURNAL=Path('/var/lib/mrjam-delivery-captures/accepted-e06-stage-001.json')
UNITS=['nginx.service','postgresql.service','forgejo.service','vise.service','mrjam-rust-green.service','mrjam-forgejo-runner.service']

def run(args,timeout=180):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
    C.require(p.returncode==0 and len(p.stdout)<=65536,'STAGE_COMMAND_REFUSED');return p.stdout
def property(unit):return run([CTL,'show',unit,'-p','MainPID','-p','ActiveState','-p','SubState']).decode()
def state(path):return C.parse(Path(path).read_bytes())
def credential():
    import github_proposals as P
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/'forgejo-observer'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:P.credential_metadata(os.fstat(fd),0,0);return os.read(fd,32769).decode().strip()
    finally:os.close(fd)

class Adapter:
    old=OLD;new=NEW
    def retained(self):return {u:property(u) for u in UNITS}
    def no_clients(self):
        for name in ['tcp','tcp6']:
            rows=Path('/proc/net/'+name).read_text().splitlines()[1:]
            # Only count states, never export addresses or connection data.
            active=[r for r in rows if int(r.split()[1].split(':')[1],16)==38101 and r.split()[3] not in {'0A','06'}]
            C.require(not active,'OFF_TRAFFIC_CLIENTS_REMAIN')
    def checkpoint(self,phase):
        raw=C.canonical({'schema_version':1,'phase':phase,'old':OLD,'staged':NEW,'proposal_sha256':DIGEST})
        temporary=JOURNAL.with_suffix('.next')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(temporary,JOURNAL);O.W.sync_directory(JOURNAL.parent)
    def stop_slot(self):run([CTL,'stop','mrjam-rust-blue.service'],timeout=60)
    def start_slot(self):run([CTL,'start','mrjam-rust-blue.service'],timeout=60)
    def switch(self,target):run([target+'/bin/switch-to-configuration','test'])
    def verify(self,target,before):
        C.require(os.path.realpath('/run/current-system')==target and os.path.realpath(PROFILE)==OLD,'STAGE_GENERATION_REFUSED')
        C.require(self.retained()==before,'PUBLIC_PROCESS_CHANGED')
        C.require(Path('/etc/nginx/nginx.conf').read_bytes()==self.nginx,'PUBLIC_ROUTE_CHANGED')
        expected=state(self.bundle['runtime']+'/runtime.json')['required_capabilities']
        end=time.monotonic()+60
        while time.monotonic()<end:
            try:
                c=http.client.HTTPConnection('127.0.0.1',38101,timeout=3)
                c.request('GET','/readyz',headers={'Host':'audition.mrj.am'});r=c.getresponse();raw=r.read(8193);c.close()
                if r.status==200 and len(raw)<=8192:
                    C.require(json.loads(raw)=={'status':'ready','scope':'configured-capabilities-only','capabilities':expected},'READINESS_CONTRACT_REFUSED')
                    pid=int(run([CTL,'show','mrjam-rust-blue.service','-p','MainPID','--value']))
                    executable=os.readlink('/proc/'+str(pid)+'/exe')
                    C.require(executable==(self.bundle['server']+'/libexec/mrjam-server' if target==NEW else self.old_executable),
                        'STAGE_EXECUTABLE_REFUSED');return
            except (OSError,http.client.HTTPException,json.JSONDecodeError):pass
            time.sleep(.5)
        raise C.Refused('STAGE_NOT_READY')
    def preflight(self):
        C.require(os.getuid()==0 and len(sys.argv)==1 and os.uname().nodename=='srv1982677','STAGE_HOST_REFUSED')
        C.require(os.path.realpath('/run/current-system')==OLD and os.path.realpath(PROFILE)==OLD and not JOURNAL.exists(),'STAGE_BASELINE_REFUSED')
        self.nginx=Path('/etc/nginx/nginx.conf').read_bytes()
        C.require(b'127.0.0.1:38101' not in self.nginx and self.nginx.count(b'127.0.0.1:38102')==11
            and Path(NEW+'/etc/nginx/nginx.conf').read_bytes()==self.nginx,'OFF_TRAFFIC_ROUTE_REFUSED')
        C.require(all('ActiveState=active\n' in v for v in self.retained().values()),'RETAINED_SERVICE_INACTIVE')
        pid=int(run([CTL,'show','mrjam-rust-blue.service','-p','MainPID','--value']))
        self.old_executable=os.readlink('/proc/'+str(pid)+'/exe');self.no_clients()
        value=O.read(JOB/'state.json');proposal=value['capture']['proposal']
        C.require(value['phase']=='validated' and value['capture']['proposal_sha256']==DIGEST and proposal['head']==HEAD,'STAGE_JOB_REFUSED')
        admitted=A.load(DIGEST);policy=admitted['authority']
        envelope=C.parse(C.regular_file(JOB/'artifacts/attestation.json',owner=0,mode=0o400,maximum=C.MAX_DOCUMENT))
        C.require(signer.verify(envelope,policy) and envelope['payload']['proposal_sha256']==DIGEST,'STAGE_SIGNATURE_REFUSED')
        artifacts={}
        for item in envelope['payload']['artifacts']:
            raw=C.regular_file(JOB/'artifacts'/item['name'],owner=0,mode=0o400,maximum=dict(C.ARTIFACTS)[item['name']])
            C.require(len(raw)==item['bytes'] and C.sha(raw)==item['sha256'],'STAGE_ARTIFACT_CHANGED');artifacts[item['name']]=raw
        self.bundle=state(BUNDLE/'descriptor.json')
        C.require(self.bundle['proposal_sha256']==DIGEST and self.bundle['slot']=='blue','STAGE_BUNDLE_REFUSED')
        C.require(Path(self.bundle['server']+'/libexec/mrjam-server').read_bytes()==artifacts['server'],'STAGE_SERVER_BYTES_CHANGED')
        policy_raw=Path(admitted['details']['report_policy']).read_bytes()
        C.require(C.sha(policy_raw)==policy['report_policy_sha256'],'STAGE_REPORT_POLICY_CHANGED')
        report=C.parse(policy_raw);sources={s['id']:s['revision'] for s in report['sources']}
        groups=F.validate(artifacts['frontend.tar'],archive_sha256=C.sha(artifacts['frontend.tar']),proposal=DIGEST,
            sources=sources,styles={f['id']:sources[f['style_source']] for f in report['frontends']},
            toolchains_sha256='27c05033dd0a7347ccdba0afb4caed5bb359eaeeeb1dd1fedb92ef8dc5701eae')
        inventory=state(self.bundle['frontends']+'/inventory.json')
        for name,files in groups.items():
            root=Path(inventory['outputs'][name]['store_path'])
            C.require({p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir()}==set(files),'STAGE_FRONTEND_INVENTORY_CHANGED')
            C.require(all(not (root/name).is_symlink() and (root/name).read_bytes()==raw for name,raw in files.items()),'STAGE_FRONTEND_BYTES_CHANGED')
        token=credential();api=M.API(proposal,2,token,token)
        C.require(api('GET','/pulls/2').get('merged') is True,'STAGE_MERGE_REQUIRED')
        c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
        try:
            c.request('GET',D.BASE+'/actions/runs/5',headers={'Host':'forge.mrj.am','Authorization':'token '+token})
            response=c.getresponse();raw=response.read(1048577)
            C.require(response.status==200 and len(raw)<=1048576,'STAGE_CI_OBSERVATION_REFUSED');row=json.loads(raw)
        finally:c.close()
        C.require(row.get('id')==5,'STAGE_CI_IDENTITY_REFUSED')
        ci=D.identify(row,DIGEST,policy['rules_revision']);C.require(ci is not None,'STAGE_CI_BINDING_REFUSED')
        receipt=C.parse(C.regular_file('/var/lib/mrjam-forge-reviews-first/receipt.json',owner=0,mode=0o600,maximum=65536))
        M.merge(proposal,2,ci,policy,envelope,receipt,api,verify=signer.verify)

def main():
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=T.stage(Adapter());print(json.dumps(result))
        if result['code']!='ACCEPTED_OFF_TRAFFIC_READY':raise SystemExit(2)
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'ACCEPTED_STAGE_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
