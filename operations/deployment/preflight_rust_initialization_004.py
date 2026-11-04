"""Closed read-only projection of unchanged Rust initialization prerequisites.

Only public assets, fixed credential format predicates, and catalogue/public
corpus equality are inspected. No application identities, sessions, answers or
participations are selected. The returned generation has neither the new HBA
nor its UIDs: this is explicitly not a live candidate connection qualification.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
CONFIG='/nix/store/i6sihwyslybsjf3qxx8k6pqb18n0wcak-mrjam-runtime-blue/runtime.json'
CONFIG_SHA='96813c225a279cb96be091ed055871f92af61c9a8928238c9c9e604fcc424ca1'
BANK_ROOT='/nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval'
CREDENTIALS={
    'mateval_activation':('/var/lib/mrjam-metier/secrets/matheval-setup-hash','sha256'),
    'admission_approval':('/var/lib/mrjam-worker-credentials/v1/approval','approval'),
}
COLUMNS={
 'corpus':'version,digest,bank,codebook',
 'participations':'id,token_hash,bank_version,levels,seed,question_order,production_order,started_at,updated_at,completed_at,revision,payload_hash,snapshot',
 'answers':'participation_id,question_id,production_id,note,initial_note,x,y,z,evaluated_axes',
 'interaction_events':'participation_id,sequence,event,occurred_at,elapsed_ms,payload',
 'administrators':'id,username,password_hash',
 'administrator_sessions':'token_hash,administrator_id,expires_at,last_seen',
}

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result

def closed_read(path,maximum):
    # Match runtime_files' parent walk: no symlinks, even in a parent.
    parts=Path(path).parts
    if parts[0]!='/' or any(p in ('.','..') for p in parts):raise ValueError()
    flags=os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW
    directory=os.open('/',flags|os.O_DIRECTORY)
    try:
        for component in parts[1:-1]:
            following=os.open(component,flags|os.O_DIRECTORY,dir_fd=directory)
            os.close(directory);directory=following
        descriptor=os.open(parts[-1],flags|os.O_NONBLOCK,dir_fd=directory)
        try:
            metadata=os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>maximum:raise ValueError()
            content=b''
            while len(content)<=maximum:
                chunk=os.read(descriptor,min(65536,maximum+1-len(content)))
                if not chunk:break
                content+=chunk
            if len(content)!=metadata.st_size or len(content)>maximum:raise ValueError()
            return metadata,content
        finally:os.close(descriptor)
    finally:os.close(directory)

def credential_format(content,kind):
    # runtime_files::credential removes exactly one LF, refuses all controls;
    # AdminService::new then requires 64 hexadecimal digits; ApprovalClient
    # accepts only 32..512 ASCII alphanumeric, '-' and '_'. Never return value.
    try:text=content.decode('utf-8')
    except UnicodeDecodeError:return False
    if text.endswith('\n'):text=text[:-1]
    if not text or any(ord(c)<32 or 127<=ord(c)<=159 for c in text):return False
    if kind=='sha256':return re.fullmatch('[0-9a-f]{64}',text) is not None
    if kind=='approval':return re.fullmatch('[A-Za-z0-9_-]{32,512}',text) is not None
    raise ValueError()

def credential_observation(path,kind):
    try:
        metadata,content=closed_read(path,4096)
        return {'observed':True,'root_owned':metadata.st_uid==0,
            'single_link':metadata.st_nlink==1,
            'source_mode_private':stat.S_IMODE(metadata.st_mode) in (0o400,0o600),
            'runtime_format_accepted':credential_format(content,kind)}
    except (OSError,ValueError):return {'observed':False}

def public_bank():
    _,raw=closed_read(CONFIG,65536)
    if hashlib.sha256(raw).hexdigest()!=CONFIG_SHA:raise ValueError()
    config=json.loads(raw,object_pairs_hook=unique)
    asset=next(a for a in config['assets'] if a['directory']==BANK_ROOT)
    _,manifest=closed_read(BANK_ROOT+'/artifact.json',524288)
    if hashlib.sha256(manifest).hexdigest()!=asset['manifest_sha256']:raise ValueError()
    manifest=json.loads(manifest,object_pairs_hook=unique)
    _,raw=closed_read(BANK_ROOT+'/data/bank.json',2*1024**2)
    if hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']['data/bank.json']:raise ValueError()
    bank=json.loads(raw,object_pairs_hook=unique)
    if type(bank) is not dict or type(bank.get('version')) is not str or not 0<len(bank['version'])<=64:raise ValueError()
    return bank

def sql_literal(value):
    return "'"+value.replace("'","''")+"'"

def catalogue_query(bank):
    checks=[]
    for table,columns in COLUMNS.items():
        names=columns.split(',')
        checks += [sql_literal(table+'_required_columns'),
            "(SELECT count(*)="+str(len(names))+" FROM pg_attribute WHERE attrelid=to_regclass('public."+table+
            "') AND NOT attisdropped AND attnum>0 AND attname IN ("+','.join(sql_literal(n) for n in names)+"))"]
    checks += ["'administrator_sequence_present'","to_regclass('public.administrators_id_seq') IS NOT NULL",
        "'public_bank_equal'", "EXISTS(SELECT 1 FROM public.corpus WHERE version="+sql_literal(bank['version'])+
        " AND bank="+sql_literal(json.dumps(bank,ensure_ascii=True,separators=(',',':')))+"::jsonb)",
        "'baseline_application_role_present'","EXISTS(SELECT 1 FROM pg_roles WHERE rolname='matheval_app')",
        "'adopted_admin_role_absent_after_return'","NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='matheval_admin')"]
    return ("BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='1s'; "
        "SET LOCAL search_path=pg_catalog; SELECT json_build_object("+','.join(checks)+
        "); ROLLBACK;")

def parse_catalogue(raw):
    expected={t+'_required_columns' for t in COLUMNS}|{'administrator_sequence_present',
        'public_bank_equal','baseline_application_role_present','adopted_admin_role_absent_after_return'}
    if len(raw)>4096:raise ValueError()
    result=json.loads(raw,object_pairs_hook=unique)
    if type(result) is not dict or set(result)!=expected or any(type(v) is not bool for v in result.values()):raise ValueError()
    return result

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:raise ValueError()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
        signal.alarm(25)
        credentials={name:credential_observation(*spec) for name,spec in CREDENTIALS.items()}
        bank=public_bank()
        process=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',
            PREVIOUS+'/sw/bin/psql','-X','-w','-qAt','-h','/run/postgresql','-p','5432',
            '-d','matheval','-v','ON_ERROR_STOP=1'],input=catalogue_query(bank).encode(),
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,
            env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null',
                 'PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'5',
                 'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog'})
        catalogue={'observed':False}
        if process.returncode==0:catalogue={'observed':True,'checks':parse_catalogue(process.stdout)}
        result={'schema_version':1,'code':'RUST_INITIALIZATION_BASELINE_OBSERVED',
            'credentials':credentials,'matheval':catalogue,
            'public_bank_manifest_verified':True,'private_application_rows_read':False,
            'secret_values_exported':False,'mutation_performed':False,
            'candidate_hba_uids_and_systemd_credential_namespace_observed':False,
            'post_adoption_role_privileges_observed':False}
        print(json.dumps(result,sort_keys=True,separators=(',',':')))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"RUST_INITIALIZATION_BASELINE_REFUSED"}')
        return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
