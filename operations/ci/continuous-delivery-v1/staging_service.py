"""Fixed protected staging worker. Read-only Forgejo identity; no merge calls."""
import fcntl,json,os,re,sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),
 '/nix/store/zf97rkdq655qhfa9zijwyzvjinambdkv-mrjam-separated-acceptance-services-1/lib',
 '/nix/store/qmzbv6zskr9qzhh3ifqs010jz26q2jlh-mrjam-protected-admission-controller-1/lib',
 '/nix/store/ixhqrvgq1vixg0g0fc01lwkdprxxkmn7-mrjam-validation-admission-control-1/lib']
import contract as C,github_proposals as G,admission_orchestrator as O
import acceptance_adapter as A,delivery_environment as E,delivery_constructor as D
import staging_queue as Q,staging_plan as P,staging_lease as L,staging_adapter as S,staging_transaction as T
import promotion_enqueue as N,verified_delivery as V,staging_gate as Gate

JOBS=Path('/var/lib/mrjam-intake-admission/jobs')
ACCEPTANCE=Path('/var/lib/mrjam-acceptance')
PROMOTION=Path('/var/lib/mrjam-promotion')
PREPARED=Path('/var/lib/mrjam-delivery-preparation')

class Driver:
    def __init__(self,state,token):self.state=state;self.token=token;self.observer=A.Adapter('sync',{},token)
    def environment(self):return E.read()
    def supports(self,job):return job['capture']['proposal']['repository'] in D.SUPPORTED
    def prepare(self,work,directory,job,environment):
        C.require(E.read()==environment,'STAGING_ENVIRONMENT_CHANGED')
        return P.create(work,directory,job,environment,self.observer.verified)
    def acquire(self,plan):return L.acquire(self.state,plan,ACCEPTANCE,JOBS,S.actual)
    def stage(self,plan):
        adapter=S.Adapter(self.state,ACCEPTANCE,JOBS,self.observer.verified)
        C.require(adapter.plan==plan,'STAGING_SELECTED_PLAN_CHANGED')
        result=T.stage(adapter)
        if result['code']!='STAGING_READY':return result
        job=O.read(JOBS/plan['job']/'state.json')
        directory=ACCEPTANCE/plan['job']
        if not (directory/'state.json').exists():return result
        O.W.private_directory(directory);ledger=N.A.checked(L.read(directory/'state.json'),job)
        if set(ledger['receipts'])!=set(N.A.STAGES):return result
        promotion=N.compose(plan,job,ledger)
        def authorize(value):
            bundle=V.verify(value,self.token)
            C.require({k:bundle[k] for k in ('server','runtime')}==plan['staged']['slots'][plan['slot']],
                'ENQUEUE_RUNTIME_BINDING_CHANGED')
        return N.enqueue(PROMOTION,Path('/nix/var/nix/gcroots/mrjam-delivery'),JOBS,promotion,
            authorize=authorize,ready=lambda:Gate.ready(self.state,job),observe=S.actual)
    def complete(self,plan,job):return L.complete(self.state,plan,job,PROMOTION,S.actual)

def credential():
    path=Path(os.environ['CREDENTIALS_DIRECTORY'])/'forgejo-observer'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:G.credential_metadata(os.fstat(fd),0,0);return os.read(fd,32769).decode().strip()
    finally:os.close(fd)

def main():
    C.require(os.getuid()==0 and os.uname().nodename=='srv1982677' and len(sys.argv)==1,'STAGING_HOST_REFUSED')
    state=O.W.private_directory(Path(os.environ['STATE_DIRECTORY']))
    with open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('{"code":"STAGING_ENVIRONMENT_BUSY"}');return
        print(json.dumps(Q.tick(state,JOBS,PREPARED,Driver(state,credential()))))

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=str(error) if type(error).__name__=='Refused' and re.fullmatch('[A-Z_]{1,80}',str(error)) else 'STAGING_SERVICE_RETRY'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}));raise SystemExit(2) from None
