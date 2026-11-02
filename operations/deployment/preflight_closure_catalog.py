#!/usr/bin/env python3
"""Fixed, read-only post-return closure diagnosis. No application rows/secrets.

The Vision catalogue survived the failed attempt unchanged. The candidate-only
journal database was rolled back and is deliberately NOT diagnosed here.
Only PID1 messages for the fixed unit and incident window are classified.
"""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
UNIT='mrjam-vision-closure.service'
SQL=r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SET LOCAL search_path=pg_catalog;
WITH subject AS (SELECT * FROM pg_roles WHERE rolname='vision_fermeture'),
required(name) AS (VALUES
 ('vision_gestion.comptes_identite(text,text)'),
 ('vision_gestion.engager_fermeture_identite(text,text,text)'),
 ('vision_gestion.effacer_identite_cycle(text,text,text)')),
functions AS (SELECT name,to_regprocedure(name)::oid AS oid FROM required),
properties AS (SELECT f.name,p.oid,p.prosecdef,p.proowner,r.rolcanlogin,r.rolsuper,r.rolbypassrls
 FROM functions f LEFT JOIN pg_proc p ON p.oid=f.oid LEFT JOIN pg_roles r ON r.oid=p.proowner)
SELECT json_build_object(
 'role_present',EXISTS(SELECT FROM subject),
 'role_login',coalesce((SELECT rolcanlogin FROM subject),false),
 'role_unprivileged',coalesce((SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb FROM subject),false),
 'database_connect',coalesce((SELECT has_database_privilege(oid,current_database(),'CONNECT') FROM subject),false),
 'schema_usage',coalesce((SELECT has_schema_privilege(oid,'vision_gestion','USAGE') FROM subject),false),
 'no_management_schema_create',coalesce((SELECT NOT has_schema_privilege(oid,'vision_gestion','CREATE') FROM subject),false),
 'no_public_schema_create',coalesce((SELECT NOT has_schema_privilege(oid,'public','CREATE') FROM subject),false),
 'minimum_public_tables',(SELECT count(*)>=14 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind='r'),
 'no_public_table_privilege',coalesce((SELECT bool_and(NOT has_table_privilege(s.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN subject s
    WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind='r'),false),
 'no_public_table_owner_membership',coalesce((SELECT bool_and(NOT pg_has_role(s.oid,c.relowner,'MEMBER'))
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN subject s
    WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind='r'),false),
 'all_required_functions_present',(SELECT count(oid)=3 FROM properties),
 'required_functions_security_definer',coalesce((SELECT bool_and(prosecdef) FROM properties),false),
 'required_function_owners_no_login',coalesce((SELECT bool_and(NOT rolcanlogin) FROM properties),false),
 'required_function_owners_unprivileged',coalesce((SELECT bool_and(NOT rolsuper AND NOT rolbypassrls) FROM properties),false),
 'no_function_owner_membership',coalesce((SELECT bool_and(NOT pg_has_role(s.oid,p.proowner,'MEMBER')) FROM properties p CROSS JOIN subject s),false),
 'all_required_functions_executable',coalesce((SELECT bool_and(has_function_privilege(s.oid,p.oid,'EXECUTE')) FROM properties p CROSS JOIN subject s),false),
 'no_other_management_function_executable',NOT EXISTS(SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN subject s
    WHERE n.nspname='vision_gestion' AND has_function_privilege(s.oid,p.oid,'EXECUTE')
    AND NOT p.oid=ANY(ARRAY(SELECT oid FROM functions WHERE oid IS NOT NULL))),
 'accounts_function_present',(SELECT oid IS NOT NULL FROM functions WHERE name='vision_gestion.comptes_identite(text,text)'),
 'engage_function_present',(SELECT oid IS NOT NULL FROM functions WHERE name='vision_gestion.engager_fermeture_identite(text,text,text)'),
 'delete_function_present',(SELECT oid IS NOT NULL FROM functions WHERE name='vision_gestion.effacer_identite_cycle(text,text,text)'));
ROLLBACK;
"""
FIELDS=('role_present','role_login','role_unprivileged','database_connect','schema_usage',
 'no_management_schema_create','no_public_schema_create','minimum_public_tables',
 'no_public_table_privilege','no_public_table_owner_membership','all_required_functions_present',
 'required_functions_security_definer','required_function_owners_no_login',
 'required_function_owners_unprivileged','no_function_owner_membership',
 'all_required_functions_executable','no_other_management_function_executable',
 'accounts_function_present','engage_function_present','delete_function_present')

def command(args,limit):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        timeout=12,check=False,env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C',
        'PGPASSFILE':'/dev/null','PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'5',
        'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog',
        'SYSTEMD_COLORS':'0'})
    if result.returncode!=0 or len(result.stdout)>limit:raise ValueError()
    return result.stdout.decode('utf-8','strict')

def catalog(raw):
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!=set(FIELDS) or any(type(x) is not bool for x in value.values()):
        raise ValueError()
    return {'observed':True,'checks':value,'all_checks_accepted':all(value.values())}

def pid1(raw):
    result={'observed':True,'exec_start_pre_exited_one':False,'exec_start_main_exited_one':False,
            'job_failed':False,'unclassified_messages_exported':False}
    allowed={UNIT+': Control process exited, code=exited, status=1/FAILURE':'exec_start_pre_exited_one',
             UNIT+': Main process exited, code=exited, status=1/FAILURE':'exec_start_main_exited_one'}
    for line in raw.splitlines():
        value=json.loads(line)
        if not isinstance(value,dict):raise ValueError()
        if value.get('_PID')!='1' or value.get('UNIT')!=UNIT:continue
        message=value.get('MESSAGE')
        if isinstance(message,str) and message in allowed:result[allowed[message]]=True
        if value.get('JOB_RESULT')=='failed':result['job_failed']=True
    return result

def collect():
    result={'schema_version':1,'code':'CLOSURE_CATALOG_OBSERVED','read_only':True,
            'application_rows_read':False,'secret_content_read':False,'application_journal_read':False,
            'private_values_exported':False,'mutation_performed':False,
            'candidate_journal_catalog':{'observed':False,'reason':'CANDIDATE_DATABASE_ROLLED_BACK'}}
    try:result['vision_catalog']=catalog(command([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',
        PREVIOUS+'/sw/bin/psql','-X','-w','-qAt','-h','/run/postgresql','-p','5432','-d','vision',
        '-v','ON_ERROR_STOP=1','-c',SQL],8192))
    except Exception:result['vision_catalog']={'observed':False}
    try:result['incident_process']=pid1(command([PREVIOUS+'/sw/bin/journalctl','_PID=1','UNIT='+UNIT,
        '--since=2026-11-02 20:27:00 UTC','--until=2026-11-02 20:35:00 UTC',
        '--no-pager','--output=json','--lines=64'],262144))
    except Exception:result['incident_process']={'observed':False}
    return result

def main():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.path.realpath('/run/current-system')!=PREVIOUS:return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
    signal.alarm(30)
    try:result=collect()
    except Exception:result={'schema_version':1,'code':'CLOSURE_CATALOG_UNAVAILABLE','private_values_exported':False}
    finally:signal.alarm(0)
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0 if result.get('vision_catalog',{}).get('observed') else 1

if __name__=='__main__':raise SystemExit(main())
