"""Protected construction service. Observer only; no merge or activation calls."""
import fcntl,json,os,re,sys
from pathlib import Path
RECIPE=Path(os.environ['MRJAM_DELIVERY_RECIPE'])
ENABLE_VISE='@enable-vise@'=='true'
# Resolve the installed trust anchor before adding the recipe source inventory.
# The inventory contains unexpanded source templates for admission_control.py;
# importing those would search for the literal @admission-anchor@ filename.
sys.path[:0]=[
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib',
 '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib']
import contract,admission_control,signer
sys.path[:0]=[str(RECIPE/'operations/ci/continuous-delivery-v1'),
 '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib',
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib']
import contract as C,github_proposals as G,admission_orchestrator as O
import acceptance_adapter as A,delivery_constructor as D,generation_builder as B
import delivery_environment as E,preparation_queue as Q
import delivery_profiles as Profiles

class Adapter:
    def __init__(self,token):
        self.observer=A.Adapter('sync',{},token,enable_vise=ENABLE_VISE)
        self.nix=os.environ['MRJAM_DELIVERY_NIX']
    def environment(self):return E.read()
    def supports(self,job):
        proposal=job['capture']['proposal'];profile=Profiles.selected(proposal)
        return (ENABLE_VISE if profile=='vise' else proposal['repository'] in D.SUPPORTED)
    def prepare(self,directory,work,job,environment):
        C.require(E.read()==environment,'PREPARATION_ENVIRONMENT_CHANGED')
        vise=Profiles.selected(job['capture']['proposal'])=='vise'
        C.require(not vise or ENABLE_VISE,'PREPARATION_PROFILE_NOT_INSTALLED')
        if vise:
            binding=D.vise_binding(directory,job,self.observer.verified)
            expression=RECIPE/'operations/vise/delivery/content-candidate.nix'
        else:
            slot='green' if environment['active_slot']=='blue' else 'blue'
            binding=D.binding(directory,job,slot,environment['slots'][slot]['runtime'],self.observer.verified)
            expression=RECIPE/'operations/ci/continuous-delivery-v1/delivery-candidate.nix'
        path=work/'binding.json'
        if path.exists():C.require(O.W.read_file(path,65536)==O.encode(binding),'PREPARATION_BINDING_CHANGED')
        else:O.save(path,binding)
        candidate=B.Builder.command([self.nix+'/bin/nix-build',str(expression),
            '--argstr','bindingFile',str(path),'--out-link',str(work/'candidate'),
            '--option','builders','','--max-jobs','1','--cores','2']).decode('ascii').strip()
        C.require(B.G.store(candidate),'PREPARATION_CANDIDATE_REFUSED')
        descriptor=C.parse(Path(candidate,'descriptor.json').read_bytes())
        C.require(descriptor['binding_sha256']==O.sha(O.W.read_file(path,65536))
            and descriptor['proposal_sha256']==binding['proposal_sha256']
            and descriptor['source']==binding['source'] and descriptor['policy']==binding['report_policy']
            and descriptor['deployment_authorized'] is False,'PREPARATION_CANDIDATE_BINDING_REFUSED')
        if vise:
            C.require(descriptor.get('schema_version')==2 and descriptor.get('profile')=='vise-v1'
                and descriptor.get('verification_sha256')==binding['verification_sha256'],
                'PREPARATION_CANDIDATE_PROFILE_REFUSED')
            sys.path.insert(0,str(RECIPE/'operations/vise/delivery'))
            import host_builder as H
            builder=H.Builder(RECIPE/'operations/vise/delivery/generations.nix',
                self.nix+'/bin/nix-instantiate',self.nix+'/bin/nix-build')
        else:
            C.require(descriptor['slot']==slot,'PREPARATION_CANDIDATE_BINDING_REFUSED')
            builder=B.Builder(RECIPE/'operations/ci/continuous-delivery-v1/delivery-generations.nix',
                self.nix+'/bin/nix-instantiate',self.nix+'/bin/nix-build')
        proof=builder.construct(work,environment,candidate,observe=lambda:E.read()['system'])
        # Fresh signature/base/run after construction, before publishing readiness.
        self.observer.verified(directory,job)
        C.require(E.read()==environment,'PREPARATION_ENVIRONMENT_CHANGED')
        return {**proof,'job':job['id'],'proposal_sha256':binding['proposal_sha256'],
            'environment_sha256':O.sha(O.encode(environment)),'ready_for_staging':True,'deployment_authorized':False}

def credential():
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/'forgejo-observer'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:G.credential_metadata(os.fstat(fd),0,0);return os.read(fd,32769).decode().strip()
    finally:os.close(fd)

def tick(state,token,*,lease=Path('/var/lib/mrjam-staging/lease.json')):
    # Staging intentionally changes the live environment while retaining the
    # validated job. Do not mistake that transition for a new preparation:
    # the reserved stage owns it through acceptance and promotion/recovery.
    if lease.exists() or lease.is_symlink():return {'code':'PREPARATION_STAGING_BUSY'}
    return Q.tick(Path('/var/lib/mrjam-intake-admission/jobs'),state,Adapter(token))

def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'PREPARATION_HOST_REFUSED')
    state=O.W.private_directory(Path(os.environ['STATE_DIRECTORY']))
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('{"code":"PREPARATION_ENVIRONMENT_BUSY"}');return
        print(json.dumps(tick(state,credential())))
if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'PREPARATION_SERVICE_RETRY'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
