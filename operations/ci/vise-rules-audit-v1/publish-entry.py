"""Operator-selected external audit publication; fixed input, no CLI arguments."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import core
import proposal_entry as E
import publish

def main():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677':return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    def interrupted(*_):raise core.Refused('AUDIT_INTERRUPTED')
    for number in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM):signal.signal(number,interrupted)
    signal.alarm(180)
    fd=None
    try:
        spec=importlib.util.spec_from_file_location('qualified_bootstrap',E.BOOTSTRAP)
        bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        fd=os.open(E.STATE/'transaction.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
        info=os.fstat(fd)
        core.require(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0
            and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'TRANSACTION_LOCK_REFUSED')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        E.gate(bootstrap)
        binding=core.Binding(Path(E.BINDING).read_bytes(),E.BINDING_SHA256)
        git=core.Git(E.GIT,E.SELF+'/bin/mrjam-rules-proposal-credential',E.SELF+'/hooks',binding)
        result=publish.publish(Path('@AUDIT@/report.json').read_bytes(),binding,bootstrap,git)
        E.gate(bootstrap)
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as error:
        # Never print an exception containing API data, subprocess output or tokens.
        known={'AUDIT_BYTES_REFUSED','AUDIT_RESULT_REFUSED','AUDIT_BODY_REFUSED',
            'AUDIT_PULL_REFUSED','AUDIT_COMMIT_REFUSED','AUDIT_STATUS_PAGE_REFUSED',
            'AUDIT_STATUS_CONFLICT','AUDIT_OBSERVATION_CHANGED','AUDIT_READBACK_REFUSED','AUDIT_INTERRUPTED'}
        code=str(error) if isinstance(error,core.Refused) and str(error) in known else E.failure(error)
        print(json.dumps({'schema_version':1,'code':code},sort_keys=True));return 1
    finally:
        if fd is not None:os.close(fd)
        signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
