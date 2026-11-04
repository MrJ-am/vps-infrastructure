"""One real local validation, no Forgejo job or production signing identity."""
import hashlib,importlib.util,json,os,shutil,stat,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'operations/ci/continuous-delivery-v1'
RUN=ROOT/'.local/deployment-20261101/aligned-native-validation-002'
WORKER=ROOT/'operations/forgejo/worker.py'
VALIDATOR='/nix/store/crhzij9iqk4pya3p9l52n6kraiq3hzg0-mrjam-validate-aligned-workspace-1'
SOURCE=Path('/nix/store/hqh3b9b2z13rqbkn4hy73m2vln3apl1r-mrjam-aligned-public-source-proposal-003')
CLOSURE=Path('/nix/store/wh11knbrrym183s924k8giqcx2918qmd-closure-info/store-paths')
AUTHORITY=Path('/nix/store/19r3a6ylzp32vg3bkfr9wfhd1n8cwm71-mrjam-validation-authority-credentials-2')
BWRAP='/nix/store/f2bsh1n6snqdldnjdshdy1lw3hnlfxwi-bubblewrap-0.12.0'
PROPOSAL='04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d'
RULES='b02bdf1b5d63dcf0e0610723788a7ca7e384932c'

def require(value,code):
    if not value:raise RuntimeError(code)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def cgroup():
    line=Path('/proc/self/cgroup').read_text().strip()
    require(line.startswith('0::/'),'LOCAL_CGROUP_REQUIRED')
    path=Path('/sys/fs/cgroup')/line.split(':',2)[2].lstrip('/')
    limits={name:(path/file).read_text().strip() for name,file in [('memory','memory.max'),('cpu','cpu.max'),('tasks','pids.max')]}
    require(limits=={'memory':'2147483648','cpu':'100000 100000','tasks':'256'},'LOCAL_CGROUP_LIMITS_REQUIRED')
    return path,limits
def write(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

def main():
    require(len(sys.argv)==1 and os.getuid()!=0 and not RUN.exists(),'LOCAL_SINGLE_RUN_REQUIRED')
    require(Path('/proc/self/uid_map').read_text().split()==[str(os.getuid()),str(os.getuid()),'1'],'LOCAL_SINGLE_UID_NAMESPACE_REQUIRED')
    group,limits=cgroup()
    require(sha(WORKER)=='22053e2e002f3e95fe0ca2317cf722c601e207339ef58ad4bab49655e63370d5','WORKER_SOURCE_CHANGED')
    require(sha(SOURCE/'manifest.json')==PROPOSAL,'PUBLIC_PROPOSAL_CHANGED')
    RUN.mkdir(mode=0o700)
    specification=importlib.util.spec_from_file_location('qualified_worker',WORKER)
    worker=importlib.util.module_from_spec(specification);specification.loader.exec_module(worker)
    # Local qualification substitutes only the staging owner/path. The real
    # root-owned systemd staging and distinct UID boundary have separate proofs.
    input_root=RUN/'input';source=input_root/PROPOSAL
    shutil.copytree(SOURCE,source)
    for path in sorted(input_root.rglob('*'),reverse=True):path.chmod(0o555 if path.is_dir() else 0o444)
    input_root.chmod(0o555)
    worker.INPUT_ROOT=input_root
    verified=worker.verify_input(input_root,PROPOSAL,RULES,owner=os.getuid())
    require(verified==source,'LOCAL_SOURCE_BINDING_REFUSED')
    paths=worker.closure(CLOSURE.read_bytes(),VALIDATOR)
    configuration={'schema_version':1,'rules_revision':RULES,'validator_store':VALIDATOR,'bubblewrap_store':BWRAP,'closure_file':str(CLOSURE)}
    worker.policy(configuration)
    outputs={name:os.memfd_create('mrjam-local-public-'+name,os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING) for name,_ in worker.ARTIFACTS}
    started=time.monotonic();actual_popen=subprocess.Popen
    write(RUN/'invocation.json',{'schema_version':1,'validator':VALIDATOR,'source':str(SOURCE),'proposal_sha256':PROPOSAL,'rules_revision':RULES,'closure_sha256':sha(CLOSURE),'worker_sha256':sha(WORKER),'limits':limits,'timeout_seconds':1800,'production_access':False,'private_key_accessed':False,'substitutions':['Native local UID owns readonly staged copies; root/systemd staging is not exercised here.','A preceding single-UID user namespace isolates RLIMIT_NPROC accounting from unrelated desktop threads; all worker limits remain unchanged.','Only the outer process stderr is retained locally for closed validator/bubblewrap diagnostics; candidate commands remain silenced by the unchanged supervisor.']})
    try:
        with (RUN/'validator.stderr').open('xb') as diagnostic:
            def observed_popen(arguments,*args,**kwargs):
                require(arguments[0]==BWRAP+'/bin/bwrap' and kwargs.get('stderr') is subprocess.DEVNULL,'UNEXPECTED_LOCAL_PROCESS')
                kwargs['stderr']=diagnostic
                return actual_popen(arguments,*args,**kwargs)
            with patch.object(worker.subprocess,'Popen',observed_popen):
                success=worker.run_with_artifacts(lambda channel,seccomp:worker.command(configuration,paths,source,channel=channel,seccomp=seccomp),outputs,timeout=1800)
        require(success,'LOCAL_VALIDATION_FAILED')
        artifacts=worker.seal_artifacts(outputs)
        destination=RUN/'artifacts';destination.mkdir(mode=0o700)
        for item in artifacts:
            target=destination/item['name'];fd=outputs[item['name']]
            with target.open('xb') as stream:
                offset=0
                while offset<item['bytes']:
                    raw=os.pread(fd,min(65536,item['bytes']-offset),offset);require(bool(raw),'ARTIFACT_TRUNCATED')
                    stream.write(raw);offset+=len(raw)
                stream.flush();os.fsync(stream.fileno())
            target.chmod(0o400);require(sha(target)==item['sha256'],'ARTIFACT_HASH_CHANGED')
        sys.path.insert(0,str(AUTHORITY/'lib'))
        import contract,signer
        # Only report-content matching, no claim of an adopted signing policy.
        previous=contract.policy(contract.parse(Path(signer.POLICY_PATH).read_bytes()))
        report_policy=json.loads((HERE/'aligned-policy.json').read_bytes())
        value={
            'rules_revision':RULES,'report_policy_sha256':sha(HERE/'aligned-policy.json'),
            'required_steps':[s for s in previous['required_steps'] if s!='rust-reviewed-readiness-overlay'],
            'sources':[{k:s[k] for k in ('id','repository','revision','tree_sha')} for s in report_policy['sources']],
            'not_established':previous['not_established'],
        }
        report=contract.parse((destination/'verification.json').read_bytes(),65536)
        signer.check_report(report,{'artifacts':artifacts},PROPOSAL,value)
        result={'schema_version':1,'status':'passed','elapsed_seconds':round(time.monotonic()-started,3),'artifacts':artifacts,'required_steps_passed':len(report['steps']),'proposal_sha256':PROPOSAL,'rules_revision':RULES,'report_matches_local_expected_content_only':True,'production_access':False,'forgejo_dispatch_performed':False,'production_attestation_emitted':False,'private_key_accessed':False,'application_test_commands_unchanged':True,'limits':['Normal cargo test retains the explicit ignored memory measurement; this run is not production signing or admission']}
        write(RUN/'result.json',result);print(json.dumps(result,sort_keys=True))
    except BaseException as failure:
        result={'schema_version':1,'status':'failed','elapsed_seconds':round(time.monotonic()-started,3),'code':str(failure) if isinstance(failure,(RuntimeError,worker.Refused)) else type(failure).__name__,'production_access':False,'forgejo_dispatch_performed':False,'production_attestation_emitted':False,'private_key_accessed':False}
        write(RUN/'result.json',result);print(json.dumps(result,sort_keys=True));raise SystemExit(1) from None
    finally:
        for descriptor in outputs.values():os.close(descriptor)
if __name__=='__main__':main()
