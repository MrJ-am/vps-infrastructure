"""Read only fixed unit states and closed component codes; no human cache."""
import json
import os
from pathlib import Path
import subprocess
import stat
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
UNITS=('mrjam-kanidm-worker-provision.service','mrjam-kanidm-passkey-portal.service','mrjam-passkey-nginx-route.service','nginx.service')
PROPERTIES=('LoadState','ActiveState','SubState','Result','ExecMainCode','ExecMainStatus','ExecMainStartTimestampMonotonic','ExecMainExitTimestampMonotonic')
ALLOWED={
    'LoadState':{'loaded','not-found','masked','error','bad-setting'},
    'ActiveState':{'active','inactive','failed','activating','deactivating','reloading','refreshing'},
    'SubState':{'dead','running','exited','failed','start','start-pre','start-post','stop','stop-sigterm','stop-sigkill','stop-post','auto-restart'},
    'Result':{'success','resources','timeout','exit-code','signal','core-dump','watchdog','start-limit-hit','oom-kill','protocol','exec-condition','assert','dependency',''},
}
ERRORS={'KANIDM_WORKER_PROVISION_REFUSED','KANIDM_WORKER_PROVISION_SESSION_CLEANUP_REQUIRED'}
SUCCESS={'schema_version':1,'prepared':True,'admission_preserved':True,'tokens_distinct':True,'replay_upstream_people_admins':True,'replay_credential_requires_isolated_adapter':True}
LOCK=Path('/var/lib/mrjam-identite/.worker-provision.lock')
STAGES=('INITIALIZE','ADMIN_CACHE','CREDENTIAL_STATE','IDENTITY_RIGHTS','ACCESS_RIGHTS','ADMISSION','EXISTING_STATE','SERVICE_CREATE','GROUP_CHANGE','TOKEN_CREATE','TOKEN_WRITE','TOKEN_VERIFY','FINAL_CONSISTENCY')

def require(value):
    if not value:raise RuntimeError()

def command(args,limit):
    value=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                         check=False,timeout=15,env={'LANG':'C','LC_ALL':'C','SYSTEMD_COLORS':'0'})
    require(value.returncode==0 and len(value.stdout)<=limit)
    return value.stdout.decode('utf-8','strict')

def main():
    require(len(sys.argv)==1 and os.geteuid()==0 and os.path.realpath('/run/current-system')==PREVIOUS)
    states={}
    for unit in UNITS:
        raw=command([PREVIOUS+'/sw/bin/systemctl','show','--no-pager','--property='+','.join(PROPERTIES),unit],4096)
        values={}
        for line in raw.splitlines():
            key,separator,value=line.partition('=')
            require(separator and key in PROPERTIES and key not in values)
            if key in ALLOWED:require(value in ALLOWED[key]);values[key]=value
            else:require(value.isdigit() and 0<=int(value)<2**63);values[key]=int(value)
        require(set(values)==set(PROPERTIES))
        states[unit]=values
    codes={code:0 for code in sorted(ERRORS)}
    provision_success=False
    expected={json.dumps({'error':code},sort_keys=True,separators=(',',':')):code for code in ERRORS}
    diagnostics={json.dumps({'error':'KANIDM_WORKER_PROVISION_REFUSED','stage':stage},sort_keys=True,separators=(',',':')):('KANIDM_WORKER_PROVISION_REFUSED',stage) for stage in STAGES}
    diagnostics[json.dumps({'error':'KANIDM_WORKER_PROVISION_SESSION_CLEANUP_REQUIRED','stage':'CLEANUP'},sort_keys=True,separators=(',',':'))]=('KANIDM_WORKER_PROVISION_SESSION_CLEANUP_REQUIRED','CLEANUP')
    stages={stage:0 for stage in (*STAGES,'CLEANUP')}
    success=json.dumps(SUCCESS,sort_keys=True,separators=(',',':'))
    raw=command([PREVIOUS+'/sw/bin/journalctl','--unit='+UNITS[0],'--since=-20min','--no-pager','--output=json','--lines=64'],262144)
    for line in raw.splitlines():
        value=json.loads(line)
        require(isinstance(value,dict))
        message=value.get('MESSAGE')
        if not isinstance(message,str):continue
        if message in expected:codes[expected[message]]+=1
        if message==success:provision_success=True
        if message in diagnostics:
            code,stage=diagnostics[message]
            codes[code]+=1;stages[stage]+=1
    try:
        metadata=LOCK.lstat()
    except FileNotFoundError:
        lock_present=False;lock_metadata_valid=False
    else:
        lock_present=True
        lock_metadata_valid=(stat.S_ISREG(metadata.st_mode) and metadata.st_uid==metadata.st_gid==0
                             and stat.S_IMODE(metadata.st_mode)==0o600 and metadata.st_nlink==1)
    result={'schema_version':1,'read_only':True,'human_cache_read':False,'journal_messages_exported':False,
            'units':states,'closed_codes_last_20_minutes':codes,'closed_stages_last_20_minutes':stages,'provision_success_observed':provision_success,
            'worker_lock_present':lock_present,'worker_lock_metadata_valid':lock_metadata_valid,
            'worker_lock_contents_read':False,
            'provision_process_started':states[UNITS[0]]['ExecMainStartTimestampMonotonic']>0,
            'provision_started_after_portal':states[UNITS[0]]['ExecMainStartTimestampMonotonic']>=states[UNITS[1]]['ExecMainStartTimestampMonotonic']>0}
    print(json.dumps(result,sort_keys=True,separators=(',',':')))

if __name__=='__main__':
    try:main()
    except Exception:
        print('{"error":"PASSKEY_FAILURE_PROBE_REFUSED"}')
        raise SystemExit(1)
