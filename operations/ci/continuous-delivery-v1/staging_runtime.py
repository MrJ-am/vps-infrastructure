"""Read-only readiness probe bound to the process qualified by the root stager.

Acceptance cannot access systemd's control socket or ptrace another account.
It reobserves the cgroup PID, kernel start time and boot ID captured by the
stager after checking /proc/PID/exe. No application content is read or returned.
"""
import http.client,json,os,re
from pathlib import Path
from source_snapshot import require

PORTS={'blue':38101,'green':38102}
STORE=re.compile('/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+\\Z')
FIELDS={'slot','server','runtime','pid','starttime','boot_id'}

def code(path,maximum=65536):
    with open(path,'rb') as stream:raw=stream.read(maximum+1)
    require(len(raw)<=maximum,'STAGING_RUNTIME_SIZE_REFUSED');return raw

def process(slot):
    require(slot in PORTS,'STAGING_RUNTIME_SLOT_REFUSED')
    pids=code('/sys/fs/cgroup/mrjam.slice/mrjam-rust.slice/mrjam-rust-'+slot+'.service/cgroup.procs').decode().split()
    require(len(pids)==1 and pids[0].isdigit() and int(pids[0])>0,'STAGING_RUNTIME_PROCESS_REFUSED')
    pid=int(pids[0]);raw=code('/proc/'+str(pid)+'/stat').decode()
    fields=raw.rsplit(') ',1)[1].split()
    require(len(fields)>=20 and fields[19].isdigit(),'STAGING_RUNTIME_STARTTIME_REFUSED')
    boot=code('/proc/sys/kernel/random/boot_id').decode().strip()
    require(re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'STAGING_RUNTIME_BOOT_ID_REFUSED')
    return {'pid':pid,'starttime':int(fields[19]),'boot_id':boot}

def probe(slot):
    connection=http.client.HTTPConnection('127.0.0.1',PORTS[slot],timeout=3)
    try:
        connection.request('GET','/readyz',headers={'Host':'audition.mrj.am'})
        response=connection.getresponse();raw=response.read(8193)
        require(response.status==200 and len(raw)<=8192,'STAGING_RUNTIME_NOT_READY')
        return json.loads(raw)
    finally:connection.close()

def checked(record):
    require(type(record) is dict and set(record)==FIELDS
        and record['slot'] in PORTS and all(type(record[k]) is str and STORE.fullmatch(record[k]) for k in ('server','runtime'))
        and all(type(record[k]) is int and record[k]>0 for k in ('pid','starttime'))
        and type(record['boot_id']) is str and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',record['boot_id']),
        'STAGING_RUNTIME_RECORD_REFUSED')

def verify(record,environment,*,observe=process,request=probe,read=code):
    checked(record);slot=record['slot']
    require(slot!=environment['active_slot'] and environment['slots'][slot]=={
        'server':record['server'],'runtime':record['runtime']},'STAGING_RUNTIME_BINDING_REFUSED')
    identity={k:record[k] for k in ('pid','starttime','boot_id')}
    require(observe(slot)==identity,'STAGING_RUNTIME_PROCESS_CHANGED')
    capabilities=json.loads(read(record['runtime']+'/runtime.json'))['required_capabilities']
    require(request(slot)=={'status':'ready','scope':'configured-capabilities-only','capabilities':capabilities},
        'STAGING_RUNTIME_CAPABILITIES_REFUSED')
    require(observe(slot)==identity,'STAGING_RUNTIME_PROCESS_CHANGED')

def capture(slot,environment):
    """Only the privileged staging adapter calls this after its unit checks."""
    require(slot in PORTS and slot!=environment['active_slot'],'STAGING_RUNTIME_SLOT_REFUSED')
    record={'slot':slot,**environment['slots'][slot],**process(slot)};checked(record)
    require(os.readlink('/proc/'+str(record['pid'])+'/exe')==record['server']+'/libexec/mrjam-server',
        'STAGING_RUNTIME_EXECUTABLE_REFUSED')
    verify(record,environment)
    return record
