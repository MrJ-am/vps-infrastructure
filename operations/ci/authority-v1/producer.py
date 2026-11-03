"""Fresh worker receipt bound to immutable recipe, tools and configuration.

The candidate execution and artifact isolation functions are the unchanged,
separately packaged worker core. Only this supervisor adds producer provenance.
"""
import fcntl,json,os,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import contract as C
import frozen_worker as W
BINDING=Path('/etc/mrjam-validation-authority/producer.json')

def verify_configuration(binding,configuration,policy_raw,closure_raw,*,recipe_file=Path(__file__),core_file=Path(W.__file__)):
    C.producer_binding(binding)
    C.require(C.sha(Path(C.__file__).read_bytes())==binding['contract_sha256'],'PRODUCER_CONTRACT_REFUSED')
    C.require(configuration['rules_revision']==binding['rules_revision'] and configuration['validator_store']==binding['verifier'],'PRODUCER_CONFIGURATION_REFUSED')
    C.require(C.sha(policy_raw)==binding['worker_policy_sha256'] and C.sha(closure_raw)==binding['closure_sha256'],'PRODUCER_INPUT_BINDING_REFUSED')
    C.require(C.sha(recipe_file.read_bytes())==binding['producer_recipe_sha256'] and C.sha(core_file.read_bytes())==binding['worker_core_sha256'],'PRODUCER_RECIPE_REFUSED')

def receipt(binding,proposal,artifacts):
    value={'schema_version':2,'decision':'passed','proposal_sha256':proposal,'rules_revision':binding['rules_revision'],'artifacts':artifacts,'authority':'bound-local-controller-receipt','producer':binding}
    return C.bound_receipt(value,proposal,binding['rules_revision'],binding)

def main():
    outputs={}
    try:
        C.require(len(sys.argv)==1 and os.getuid()!=0,'INVOCATION_REFUSED')
        proposal=W.request_digest()
        binding=C.producer_binding(C.parse(W.checked_bytes(BINDING,16384),16384))
        policy_raw=W.checked_bytes(W.POLICY,16384);configuration=W.policy(W.parse(policy_raw))
        closure_raw=W.checked_bytes(Path(configuration['closure_file']),262144);paths=W.closure(closure_raw,configuration['validator_store'])
        verify_configuration(binding,configuration,policy_raw,closure_raw)
        lock=os.open(W.LOCK,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(lock,'rb') as stream:
            info=os.fstat(stream.fileno());C.require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o440,'LOCK_REFUSED')
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            source=W.verify_input(W.INPUT_ROOT,proposal,configuration['rules_revision'])
            outputs={name:os.memfd_create('mrjam-'+name,os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING) for name,_ in W.ARTIFACTS}
            success=W.run_with_artifacts(lambda channel,seccomp:W.command(configuration,paths,source,channel=channel,seccomp=seccomp),outputs)
            C.require(success,'VALIDATION_FAILED')
            artifacts=W.seal_artifacts(outputs)
        value=receipt(binding,proposal,artifacts)
        sys.stdout.buffer.write(C.canonical(value)+b'\n')
        for name,_ in W.ARTIFACTS:
            while block:=os.read(outputs[name],65536):sys.stdout.buffer.write(block)
        sys.stdout.buffer.flush();return 0
    except BaseException:
        # No candidate output, filename, exception detail or secret is logged.
        try:sys.stdout.buffer.write(b'{"code":"BOUND_VALIDATION_REFUSED","schema_version":1}\n');sys.stdout.buffer.flush()
        except BaseException:pass
        return 1
    finally:C.close_fds(list(outputs.values()))
if __name__=='__main__':raise SystemExit(main())
