"""Synthetic user-systemd dependency test; never touches production units."""
import json,os,shutil,subprocess,time
from pathlib import Path

def run(*args):
    return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15).stdout.decode().strip()

def main():
    base=Path('/run/user')/str(os.getuid())/'systemd/user'
    assert os.getuid()!=0 and base.parent.is_dir()
    base.mkdir(exist_ok=True)
    prefix='mrjam-synthetic-recovery-'+str(os.getpid())
    upstream=prefix+'-forge.service';child=prefix+'-runner.service'
    paths=[base/upstream,base/child];wants=base/(upstream+'.wants')
    sleep=shutil.which('sleep')  # Preserve argv[0] for multicall coreutils.
    ctl=lambda *args:run('systemctl','--user',*args)
    state=lambda name:ctl('show',name,'-p','ActiveState','--value')
    def stopped(name):
        end=time.monotonic()+5
        while state(name) not in ('inactive','failed') and time.monotonic()<end:time.sleep(.05)
        assert state(name)=='inactive'
    before=set(base.iterdir())
    try:
        with paths[0].open('x') as f:f.write('[Service]\nExecStart='+sleep+' infinity\n')
        with paths[1].open('x') as f:f.write('[Unit]\nRequires='+upstream+'\nAfter='+upstream+
            '\n[Service]\nExecStart='+sleep+' infinity\nRestart=no\n')
        ctl('daemon-reload');ctl('start',child)
        assert state(child)==state(upstream)=='active'
        ctl('stop',upstream);stopped(child)
        ctl('start',upstream)
        assert state(upstream)=='active' and state(child)=='inactive'
        # Exact effect of Nix wantedBy=["forgejo.service"] on the unit graph.
        wants.mkdir();(wants/child).symlink_to(paths[1])
        ctl('daemon-reload');ctl('stop',upstream);ctl('start',upstream)
        assert state(child)==state(upstream)=='active'
        ctl('stop',upstream);stopped(child)
        ctl('start',upstream)
        assert state(child)==state(upstream)=='active'
        assert ctl('show',child,'-p','Restart','--value')=='no'
        result={'schema_version':1,'synthetic_only':True,'systemd':ctl('show','-p','Version','--value'),
            'requires_stops_runner':True,'original_does_not_resume_runner':True,
            'wanted_by_resumes_runner':True,'second_recovery_passed':True,
            'restart_policy_unchanged':True,'production_units_touched':False}
    finally:
        for name in (upstream,child):
            subprocess.run(['systemctl','--user','stop',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            subprocess.run(['systemctl','--user','reset-failed',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        if wants.exists():(wants/child).unlink();wants.rmdir()
        for path in paths:path.unlink(missing_ok=True)
        ctl('daemon-reload')
    assert set(base.iterdir())==before
    result['synthetic_units_removed']=True
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
