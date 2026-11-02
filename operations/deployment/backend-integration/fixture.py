"""Invented VM only. Real control backend; explicit synthetic app contracts."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import ssl
import subprocess
import sys
import threading
import time

sys.path.insert(0,'/etc/integrated-control')
import release_backend as B
from cutover import Cutover, Phase, Refused
from recovery import recover_before_opening
from snapshot import ROOTS, REQUIRED
from system_control import ALLOWED, DATABASE, GATE_NAME, GENERATOR_DIRECTORY, GENERATOR_NAME

CFG=json.loads(Path('/etc/integrated-tools.json').read_text())
PRIVATE=Path('/var/lib/integrated-qualification')
CASE=Path('/run/integrated-case')
EVIDENCE=Path('/run/integrated-evidence')
MARKER='INVENTED_INTEGRATION_VM_ONLY\n'


def require(value,code):
    if not value: raise RuntimeError(code)


def run(args,data=None,checked=True,timeout=240):
    result=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=False,timeout=timeout)
    if checked: require(result.returncode==0,'FIXTURE_COMMAND_FAILED')
    return result


def ctl(*args,checked=True):
    return run([CFG['tools']['systemctl'],*args],checked=checked).stdout.strip()


def sql(statement):
    return run([CFG['runuser'],'-u','postgres','--',CFG['psql'],'-X','-w','-qAt',
                '--host=/run/postgresql','--dbname=integration_fixture','--set=ON_ERROR_STOP=1'],statement).stdout.strip()


def phase():
    try:return json.loads((B.STATE/'phase.json').read_text())['phase']
    except FileNotFoundError:return 'no-transaction'


def pair_files(value):
    for name in REQUIRED-{'postgresql/17'}:
        (Path('/var/lib')/name/'paired-marker').write_text(value+'\n')


def pair(value,offline=False):
    require(all((Path('/var/lib')/name/'paired-marker').read_text()==value+'\n'
                for name in REQUIRED-{'postgresql/17'}),'PAIRED_FILE_MISMATCH')
    if offline:
        result=run([CFG['runuser'],'-u','postgres','--',CFG['postgres'],'--single','-D',
                    '/var/lib/postgresql/17','integration_fixture'],
                   "SELECT generation FROM paired_state WHERE id=1;\n")
        require('"'+value+'"' in result.stdout,'PAIRED_OFFLINE_SQL_MISMATCH')
    else:
        require(sql('SELECT generation FROM paired_state WHERE id=1;')==value,'PAIRED_SQL_MISMATCH')


def external(blocked):
    result=run([CFG['ip'],'netns','exec','cutover-observer',CFG['tools']['curl'],'--silent',
                '--insecure','--noproxy','*','--max-time','1','https://10.88.0.1/'],checked=False,timeout=5)
    require((result.returncode!=0)==blocked,'REAL_NFT_INGRESS_BOUNDARY_MISMATCH')


def observe_worker():
    EVIDENCE.mkdir(mode=0o700,exist_ok=True)
    while True:
        with (EVIDENCE/'worker.jsonl').open('a') as output:
            output.write(json.dumps({'phase':phase(),'generation':Path('/etc/synthetic-generation').read_text().strip()})+'\n')
            output.flush()
        time.sleep(.05)


def app_adopt():
    require(phase()==Phase.CANDIDATE,'SYNTHETIC_ADOPTION_PHASE_REFUSED')
    sql("UPDATE paired_state SET generation='synthetic-candidate' WHERE id=1;")
    pair_files('synthetic-candidate')
    for name in set(ROOTS)-REQUIRED:
        root=Path('/var/lib')/name
        root.mkdir(mode=0o700,exist_ok=True)
        (root/'invented-candidate').write_text('invented\n')


class HTTP(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def do_GET(self):
        try:
            current=phase()
            scenario=CASE.read_text().strip() if CASE.exists() else ''
            status=200
            body=b'INVENTED_HTTP_CONTRACT\n'
            if self.server.server_port==3002:
                value={'status':'refused' if scenario=='private-failure' and current==Phase.ADOPTED else 'ready'}
                body=json.dumps(value).encode()
            elif self.server.server_port==38101:
                body=json.dumps({'status':'ready','scope':'configured-capabilities-only','capabilities':list(B.READY_CAPABILITIES)}).encode()
            elif current==Phase.OPEN:
                # This is an invented accepted public write, executed after
                # the real controller durably opens, before its health check.
                with self.server.write_lock:
                    sql("UPDATE paired_state SET generation='synthetic-public-write' WHERE id=1;")
                    pair_files('synthetic-public-write')
                if scenario=='opening-failure':status=503
            self.send_response(status)
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        except Exception:
            self.send_response(500);self.send_header('Content-Length','0');self.end_headers()


def http():
    servers=[]
    for port in (443,3002,38101):
        server=ThreadingHTTPServer(('0.0.0.0' if port==443 else '127.0.0.1',port),HTTP)
        server.daemon_threads=True
        server.write_lock=threading.Lock()
        if port==443:
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(CFG['ca_file'],CFG['tls_key'])
            server.socket=context.wrap_socket(server.socket,server_side=True)
        servers.append(server)
        threading.Thread(target=server.serve_forever,daemon=True).start()
    while True:time.sleep(60)


def initialize():
    require(Path('/etc/integrated-marker').read_text()==MARKER,'SYNTHETIC_MARKER_REQUIRED')
    PRIVATE.mkdir(mode=0o700,exist_ok=True)
    roots={'previous':os.path.realpath('/run/current-system'),
           'staged':os.path.realpath('/run/current-system/specialisation/staged'),
           'promoted':os.path.realpath('/run/current-system/specialisation/promoted')}
    selected=set(roots.values())|{str(Path(p).parents[1]) for p in (*CFG['tools'].values(),*CFG['helpers'].values())}
    selected|={str(Path(CFG['ca_file']).parent),str(Path(CFG['generator']).parents[1])}
    closure=sorted(set(run([CFG['tools']['nix_store'],'--query','--requisites',*sorted(selected)]).stdout.splitlines()))
    artifacts={}
    for index in range(0,len(closure),64):
        entries=json.loads(run([CFG['tools']['nix'],'--extra-experimental-features','nix-command','path-info','--json',*closure[index:index+64]]).stdout)
        if isinstance(entries,list):entries={entry['path']:entry for entry in entries}
        artifacts.update({path:value['narHash'] for path,value in entries.items()})
    release={'schema_version':1,'target':'integrated-synthetic','generations':roots,'tools':CFG['tools'],
             'helpers':CFG['helpers'],'ca_file':CFG['ca_file'],'generator':CFG['generator'],
             'artifacts':artifacts,'forgejo_binding_sha256':'a'*64}
    (PRIVATE/'release.json').write_text(json.dumps(release,sort_keys=True)+'\n')
    (PRIVATE/'release.json').chmod(0o600)
    for arguments in ([CFG['ip'],'netns','add','cutover-observer'],
                      [CFG['ip'],'link','add','cutover-host','type','veth','peer','name','cutover-peer'],
                      [CFG['ip'],'link','set','cutover-peer','netns','cutover-observer'],
                      [CFG['ip'],'addr','add','10.88.0.1/24','dev','cutover-host'],
                      [CFG['ip'],'link','set','cutover-host','up'],
                      [CFG['ip'],'netns','exec','cutover-observer',CFG['ip'],'addr','add','10.88.0.2/24','dev','cutover-peer'],
                      [CFG['ip'],'netns','exec','cutover-observer',CFG['ip'],'link','set','cutover-peer','up']):
        run(arguments)


def release():
    raw=(PRIVATE/'release.json').read_bytes()
    # Only the exact synthetic hostname/old generation constants differ.
    B.HOST='integrated-synthetic'
    B.PREVIOUS=json.loads(raw)['generations']['previous']
    return B.Release(raw,hashlib.sha256(raw).hexdigest())


def baseline(scenario):
    sealed=release()
    # A separate invented transaction is prepared between cases. This cleanup
    # is test orchestration, never part of Backend/Cutover/Recovery.
    ctl('stop',*sorted(ALLOWED),checked=False)
    run([CFG['tools']['nft'],'delete','table','inet',GATE_NAME],checked=False)
    (GENERATOR_DIRECTORY/GENERATOR_NAME).unlink(missing_ok=True)
    shutil.rmtree(B.STATE,ignore_errors=True)
    shutil.rmtree(B.VOLATILE,ignore_errors=True)
    for name in ('mrjam-worker-credential-adaptation','mrjam-admission-adoption','mrjam-cycle-mail-adoption','mrjam-archive-mail-adoption'):
        shutil.rmtree(Path('/run')/name,ignore_errors=True)
    ctl('daemon-reload')
    run([CFG['tools']['nix_env'],'--profile','/nix/var/nix/profiles/system','--set',sealed.generations['previous']])
    run([sealed.generations['previous']+'/bin/switch-to-configuration','boot'])
    run([sealed.generations['previous']+'/bin/switch-to-configuration','test'])
    ctl('stop','vision-cycle.service')
    for name in REQUIRED-{'postgresql/17'}:
        root=Path('/var/lib')/name
        root.mkdir(mode=0o700,exist_ok=True)
    for name in set(ROOTS)-REQUIRED:
        shutil.rmtree(Path('/var/lib')/name,ignore_errors=True)
    source_inputs=Path('/var/lib/mrjam-source-import');source_inputs.mkdir(mode=0o700,exist_ok=True)
    for name in B.SOURCE_REPOSITORIES:
        target=source_inputs/(name+'.bundle');target.write_text('INVENTED_BUNDLE_CONTRACT_ONLY\n');target.chmod(0o600)
    identity=Path('/var/lib/mrjam-identite');identity.chmod(0o700)
    for name in B.REQUIRED_PRIVATE:
        target=identity/name;target.write_text('INVENTED_'+name+'\n');target.chmod(0o600)
    import stage_adoption
    for _,(_,_,entries) in stage_adoption.PROFILES.items():
        for relative,_ in entries:
            path=Path('/var/lib/mrjam-metier')/relative
            path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            path.unlink(missing_ok=True)
            with sqlite3.connect(path) as database:
                database.execute('CREATE TABLE invented(value TEXT NOT NULL)')
                database.execute("INSERT INTO invented VALUES('synthetic-old')")
            os.chown(path,984,984);path.chmod(0o600)
    pair_files('synthetic-old')
    ctl('reset-failed')
    ctl('start','postgresql.target')
    sql("CREATE TABLE IF NOT EXISTS paired_state(id integer PRIMARY KEY,generation text NOT NULL);"
        "INSERT INTO paired_state VALUES(1,'synthetic-old') ON CONFLICT(id) DO UPDATE SET generation=EXCLUDED.generation;")
    CASE.write_text(scenario+'\n')
    EVIDENCE.mkdir(mode=0o700,exist_ok=True)
    (EVIDENCE/'worker.jsonl').write_text('')
    (EVIDENCE/'closed-failures.jsonl').write_text('')
    ctl('start','nginx.service','vision-cycle.service')
    pair('synthetic-old')
    external(False)


def checkpoint_observer(backend,scenario):
    original=backend.checkpoint.write
    def write(value,elapsed):
        if value==Phase.RETURNED:
            require(ctl('show','vision-cycle.service','--property=ActiveState','--value') in ('inactive','failed')
                    and ctl('show','vision-cycle.service','--property=MainPID','--value')=='0','OLD_PERIODIC_STARTED_BEFORE_RETURNED')
            require(os.path.realpath('/run/current-system')==backend.generations.previous,'RETURN_OLD_LIVE_GENERATION_MISSING')
            require(os.path.realpath('/nix/var/nix/profiles/system')==backend.generations.staged,'RETURN_GUARDED_BOOT_RELEASED_EARLY')
            pair('synthetic-old')
        original(value,elapsed)
        if value==Phase.VERIFIED:external(True)
        if (scenario=='interrupt-return-before-snapshot' and value==Phase.RETURNING) or (scenario=='interrupt-after-adoption' and value==Phase.ADOPTED):
            os._exit(70)
    backend.checkpoint.write=write


def execute(scenario,recovery=False):
    with B.Backend(release()) as backend:
        # Observe only closed stage/error labels; no arguments or response data.
        for name in ('preflight','freeze','verify_quiescent','snapshot','verify_snapshot','install_candidate',
                     'adopt_private_state','start_private_services','verify_private_services','open_public_writes',
                     'verify_public_services','restore_snapshot','restore_previous_generation',
                     'verify_previous_private_services','reopen_previous_services','hold_current_state'):
            original=getattr(backend,name)
            def observed(*args,_name=name,_method=original,**kwargs):
                try:return _method(*args,**kwargs)
                except Exception as error:
                    value=str(error)
                    code=value if re.fullmatch('[A-Z0-9_]{1,80}',value) else 'UNCLASSIFIED_EXCEPTION'
                    with (EVIDENCE/'closed-failures.jsonl').open('a') as output:
                        output.write(json.dumps({'stage':_name,'code':code,'phase':phase()})+'\n')
                    raise
            setattr(backend,name,observed)
        checkpoint_observer(backend,'' if recovery else scenario)
        if scenario=='interrupt-prepared' and not recovery:
            original=backend.claim_lease
            def claim():original();os._exit(70)
            backend.claim_lease=claim
        try:
            result=recover_before_opening(backend,backend.checkpoint) if recovery else Cutover(backend,backend.checkpoint).execute()
        except Refused as failure:
            code=str(failure)
        else:
            code=result['code']
    if scenario=='private-failure' and not recovery:
        expected=[{'stage':'verify_private_services','code':'PRIVATE_READINESS_REFUSED','phase':Phase.ADOPTED.value}]
        require([json.loads(line) for line in (EVIDENCE/'closed-failures.jsonl').read_text().splitlines()]==expected,
                'UNEXPECTED_PRIVATE_FAILURE_STAGE')
    (EVIDENCE/'outcome.json').write_text(json.dumps({'code':code,'phase':phase()},sort_keys=True)+'\n')
    print(json.dumps({'outcome':code,'phase':phase(),'closed_failures':[json.loads(line) for line in (EVIDENCE/'closed-failures.jsonl').read_text().splitlines()]}))
    return code


def preflight_retry():
    require((B.STATE/'initial.json').exists() and not (B.STATE/'phase.json').exists(),'EXPECTED_PREPARED_GAP_MISSING')
    before=(B.STATE/'initial.json').stat().st_ino
    with B.Backend(release()) as backend:
        backend.preflight()
        require((B.STATE/'initial.json').stat().st_ino!=before,'INITIAL_RECORD_NOT_REOBSERVED')
        require(os.path.realpath('/run/current-system')==backend.generations.previous,'PREFLIGHT_CHANGED_LIVE_GENERATION')
        require(os.path.realpath('/nix/var/nix/profiles/system')==backend.generations.previous,'PREFLIGHT_CHANGED_BOOT_GENERATION')
        require(ctl('show','vision-cycle.service','--property=ActiveState','--value')=='active','PREFLIGHT_STOPPED_OLD_WRITER')
    require(not (B.STATE/'phase.json').exists(),'PREFLIGHT_CREATED_DURABLE_PHASE')
    external(False)


def verify(scenario):
    sealed=release()
    records=[json.loads(line) for line in (EVIDENCE/'worker.jsonl').read_text().splitlines()]
    require(all(item['phase']!=Phase.RETURNING for item in records),'OLD_PERIODIC_RAN_DURING_RETURNING')
    if scenario in ('private-failure','interrupt-return-before-snapshot','interrupt-after-adoption'):
        require(phase()==Phase.RETURNED,'EXPECTED_RETURNED')
        pair('synthetic-old')
        require(os.path.realpath('/run/current-system')==sealed.generations['previous'],'OLD_LIVE_GENERATION_NOT_RESTORED')
        require(os.path.realpath('/nix/var/nix/profiles/system')==sealed.generations['previous'],'OLD_BOOT_NOT_RESTORED')
        require(ctl('show','vision-cycle.service','--property=ActiveState','--value')=='active','OLD_PERIODIC_NOT_REOPENED')
        external(False)
        if scenario=='interrupt-return-before-snapshot':
            require(not (B.STATE/'snapshot/paired-state.tar').exists(),'EARLY_RETURN_UNEXPECTED_SNAPSHOT')
        else:
            require((B.STATE/'snapshot/candidate-state-retained').is_dir(),'CANDIDATE_NOT_RETAINED')
            require((B.STATE/'snapshot/candidate-state-retained/forgejo/paired-marker').read_text()=='synthetic-candidate\n','CANDIDATE_ADOPTION_NOT_OBSERVED')
            require(not (Path('/var/lib/mrjam-vision-cycle')).exists(),'CANDIDATE_WORKER_SURVIVED_RETURN')
    elif scenario=='opening-failure':
        require(phase()==Phase.HELD,'EXPECTED_HELD')
        require(os.path.realpath('/run/current-system')==sealed.generations['promoted'],'PUBLIC_FAILURE_RESTORED_GENERATION')
        require(not (B.STATE/'snapshot/candidate-state-retained').exists(),'PUBLIC_FAILURE_RESTORED_SNAPSHOT')
        require(ctl('show','postgresql.service','--property=ActiveState','--value')=='inactive','HELD_POSTGRESQL_ACTIVE')
        require(run([CFG['tools']['nft'],'list','table','inet',GATE_NAME],checked=False).returncode==0,'HELD_NFT_BOUNDARY_MISSING')
        pair('synthetic-public-write',offline=True)
        with B.Backend(sealed) as backend:
            try:recover_before_opening(backend,backend.checkpoint)
            except Refused as failure:require(str(failure)=='INTERRUPTED_STATE_NOT_AUTOMATICALLY_RESTORABLE','WRONG_HELD_RECOVERY_CODE')
            else:raise RuntimeError('HELD_AUTO_RECOVERY_ACCEPTED')
    elif scenario=='success':
        require(phase()==Phase.OPEN,'EXPECTED_OPEN')
        pair('synthetic-public-write')
        require(os.path.realpath('/run/current-system')==sealed.generations['promoted'],'PROMOTED_LIVE_MISSING')
        require(os.path.realpath('/nix/var/nix/profiles/system')==sealed.generations['promoted'],'PROMOTED_BOOT_MISSING')
        for unit in B.PUBLIC_TIMERS:
            require(ctl('show',unit,'--property=ActiveState','--value')=='active','PROMOTED_TIMER_INACTIVE')
        external(False)
    else:raise RuntimeError('UNKNOWN_VERIFY_CASE')


if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else ''
    try:
        if action=='http':http()
        elif action=='worker':observe_worker()
        elif action=='adopt':app_adopt()
        elif action=='initialize':initialize()
        elif action=='baseline' and len(sys.argv)==3:baseline(sys.argv[2])
        elif action=='execute' and len(sys.argv)==3:execute(sys.argv[2])
        elif action=='recover' and len(sys.argv)==3:execute(sys.argv[2],recovery=True)
        elif action=='retry':preflight_retry()
        elif action=='verify' and len(sys.argv)==3:verify(sys.argv[2])
        else:raise RuntimeError('UNKNOWN_FIXTURE_ACTION')
    except Exception as failure:
        print(json.dumps({'status':'failed','action':action,'code':str(failure) if isinstance(failure,(RuntimeError,Refused,B.Refused)) else type(failure).__name__},sort_keys=True))
        raise SystemExit(1)
    print(json.dumps({'status':'ok','action':action},sort_keys=True))
