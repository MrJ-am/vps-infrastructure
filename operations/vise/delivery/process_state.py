"""Read-only ViSe process identity and complete-stop observations.

The caller holds the shared deployment lock. A stop command succeeding is not
enough: PID1 must be idle and the entire fixed service cgroup unpopulated.
"""
import os,re,subprocess,time
from pathlib import Path

CTL='/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
GROUP='/system.slice/vise.service'
FIELDS={'ActiveState','SubState','MainPID','ControlPID','ControlGroup','Job','ExecMainStartTimestampMonotonic'}

def require(value,code):
    if not value:raise ValueError(code)

def parse(raw):
    require(type(raw) is bytes and len(raw)<=8192,'VISE_PROCESS_STATUS_LIMIT')
    result={}
    for line in raw.decode('ascii').splitlines():
        key,separator,value=line.partition('=')
        require(separator and key in FIELDS and key not in result,'VISE_PROCESS_STATUS_REFUSED')
        result[key]=value
    require(set(result)==FIELDS and result['ControlGroup'] in ('',GROUP),'VISE_PROCESS_STATUS_REFUSED')
    for name in ('MainPID','ControlPID','ExecMainStartTimestampMonotonic'):
        require(re.fullmatch(r'[0-9]{1,20}',result[name]),'VISE_PROCESS_STATUS_REFUSED')
        result[name]=int(result[name])
    return result

def query():
    result=subprocess.run([CTL,'show','vise.service',*['--property='+name for name in sorted(FIELDS)]],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False)
    require(result.returncode==0,'VISE_PROCESS_QUERY_FAILED')
    return parse(result.stdout)

def stopped_evidence(before,populated,after,*,allow_failed=False):
    state=(before['ActiveState'],before['SubState'])
    require(type(allow_failed) is bool and before==after
        and (state==('inactive','dead') or (allow_failed and state==('failed','failed')))
        and before['MainPID']==before['ControlPID']==0 and before['Job']==''
        and populated is False,'VISE_PROCESS_NOT_STOPPED')

def stopped(*,allow_failed=False):
    before=query()
    try:raw=Path('/sys/fs/cgroup'+GROUP+'/cgroup.events').read_text()
    except FileNotFoundError:populated=False
    else:
        rows=[line.split() for line in raw.splitlines()]
        entries=[row[1] for row in rows if len(row)==2 and row[0]=='populated']
        require(entries in (['0'],['1']),'VISE_CGROUP_STATUS_REFUSED')
        populated=entries==['1']
    stopped_evidence(before,populated,query(),allow_failed=allow_failed)

def running_identity(executable,*,uid=981):
    require(type(executable) is str and re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+/(server|libexec/mrjam-server)',executable),
        'VISE_PROCESS_EXECUTABLE_REFUSED')
    before=query();pid=before['MainPID']
    require(before['ActiveState']=='active' and before['SubState']=='running' and pid>1
        and before['ControlPID']==0 and before['Job']=='' and before['ControlGroup']==GROUP,
        'VISE_PROCESS_NOT_RUNNING')
    root=Path('/proc',str(pid));stat=(root/'stat').read_text().rsplit(') ',1)[1].split()
    require(len(stat)>=20 and stat[19].isdigit(),'VISE_PROCESS_STARTTIME_REFUSED')
    user=[line.split()[1:] for line in (root/'status').read_text().splitlines() if line.startswith('Uid:')]
    require(user==[[str(uid)]*4] and os.readlink(root/'exe')==executable,'VISE_PROCESS_IDENTITY_CHANGED')
    groups=(root/'cgroup').read_text().splitlines()
    require(groups==['0::'+GROUP] and before==query(),'VISE_PROCESS_IDENTITY_CHANGED')
    return {'pid':pid,'starttime':int(stat[19]),'executable':executable,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}

def wait_running_identity(executable,*,uid=981,timeout=10):
    # Type=simple reports start before setuid/exec completes. Each attempt still
    # requires the exact UID/executable/cgroup and stable PID1 observations.
    require(type(timeout) in (int,float) and 0<timeout<=60,'VISE_PROCESS_WAIT_REFUSED')
    deadline=time.monotonic()+timeout
    while True:
        try:return running_identity(executable,uid=uid)
        except ValueError as error:
            if str(error) not in {'VISE_PROCESS_NOT_RUNNING','VISE_PROCESS_IDENTITY_CHANGED'}:raise
        except FileNotFoundError:pass
        require(time.monotonic()<deadline,'VISE_PROCESS_START_TIMEOUT')
        time.sleep(.1)
