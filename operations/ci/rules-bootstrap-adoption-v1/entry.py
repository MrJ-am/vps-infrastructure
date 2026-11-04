"""Fixed initial rules adoption entry; never a general merge command."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

sys.path.insert(0,'@PROPOSAL@/libexec')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import entry as proposal_entry
import core as proposal
import adoption
import identity

SAFE=frozenset(('HUMAN_REVIEW_REQUIRED','HUMAN_REVIEW_REFUSED','HUMAN_IDENTITY_REFUSED',
    'REVIEW_REQUEST_UNRESOLVED','SELECTED_REVIEW_CHANGED','PREMERGE_OBSERVATION_CHANGED',
    'POSTMERGE_OBSERVATION_CHANGED','RULES_BOOTSTRAP_HELD','ADOPTION_JOURNAL_REFUSED',
    'ADOPTION_PHASE_REFUSED','ADOPTION_JOURNAL_WRITE_REFUSED'))


def main():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677':return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    def interrupted(*_):raise adoption.Refused('BOOTSTRAP_INTERRUPTED')
    saved={n:signal.signal(n,interrupted) for n in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM)}
    signal.alarm(300);fd=None
    try:
        spec=importlib.util.spec_from_file_location('qualified_bootstrap',proposal_entry.BOOTSTRAP)
        bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        fd=os.open(proposal_entry.STATE/'transaction.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
        info=os.fstat(fd)
        proposal.require(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and info.st_nlink==1
            and stat.S_IMODE(info.st_mode)==0o600,'TRANSACTION_LOCK_REFUSED')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proposal_entry.gate(bootstrap)
        binding=proposal.Binding(Path(proposal_entry.BINDING).read_bytes(),proposal_entry.BINDING_SHA256)
        git=proposal.Git(proposal_entry.GIT,'@PROPOSAL@/bin/mrjam-rules-proposal-credential','@PROPOSAL@/hooks',binding)
        result=adoption.adopt(binding,git,bootstrap)
        proposal_entry.gate(bootstrap)
        print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0
    except Exception as error:
        code=str(error) if isinstance(error,(adoption.Refused,identity.Refused)) and str(error) in SAFE else 'RULES_BOOTSTRAP_ADOPTION_REFUSED'
        print(json.dumps({'schema_version':1,'code':code,'ci_attestation_issued':False,'activation_performed':False},sort_keys=True));return 1
    finally:
        if fd is not None:os.close(fd)
        signal.alarm(0)
        for n,handler in saved.items():signal.signal(n,handler)


if __name__=='__main__':raise SystemExit(main())
