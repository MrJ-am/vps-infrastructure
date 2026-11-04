"""Read only PID1 lifecycle fields for the fixed fourth-attempt Rust unit.

No MESSAGE field, application journal, credential, data row or process argv.
"""
import json
import os
import resource
import signal
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
UNIT='mrjam-rust-blue.service'
FIELDS='_PID,UNIT,EXIT_CODE,EXIT_STATUS,JOB_RESULT'

def main():
    try:
        assert len(sys.argv)==1 and os.geteuid()==0 and os.uname().nodename=='srv1982677'
        assert os.path.realpath('/run/current-system')==PREVIOUS
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,128*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
        signal.alarm(20)
        p=subprocess.run([PREVIOUS+'/sw/bin/journalctl','_PID=1','UNIT='+UNIT,
            '--since=2026-11-02 21:59:00 UTC','--until=2026-11-02 22:11:00 UTC',
            '--no-pager','--output=json','--output-fields='+FIELDS,'--lines=128'],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,
            env={'LANG':'C','LC_ALL':'C','SYSTEMD_COLORS':'0'})
        assert p.returncode==0 and len(p.stdout)<=262144
        result={'pid1_event_count':0,'job_done_count':0,'job_failed_count':0,
            'exited_status_counts':{},'killed_status_counts':{},'other_exit_count':0}
        for line in p.stdout.splitlines():
            row=json.loads(line)
            assert type(row) is dict
            if row.get('_PID')!='1' or row.get('UNIT')!=UNIT:continue
            result['pid1_event_count']+=1
            for label in ('done','failed'):
                if row.get('JOB_RESULT')==label:result['job_'+label+'_count']+=1
            code=row.get('EXIT_CODE');status=row.get('EXIT_STATUS')
            if code is None:continue
            if code=='exited' and type(status) is str and status.isascii() and status.isdecimal() and len(status)<=3 and int(status)<=255:
                key=str(int(status));dest=result['exited_status_counts']
            elif code in ('killed','dumped') and status in ('HUP','INT','KILL','TERM','SEGV','ABRT','BUS','FPE','ILL','SYS'):
                key=status;dest=result['killed_status_counts']
            else:
                result['other_exit_count']+=1
                continue
            dest[key]=dest.get(key,0)+1
        print(json.dumps({'schema_version':1,'code':'RUST_UNIT_INCIDENT_METADATA_OBSERVED',
            'attempt':4,'unit':UNIT,'checks':result,'application_journal_read':False,
            'message_field_read':False,'secret_content_read':False,'mutation_performed':False},sort_keys=True))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"RUST_UNIT_INCIDENT_METADATA_REFUSED"}')
        return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
