"""Closed, read-only classification of the three incident-004 code guards.

Compare witness bodies under the runtime search_path separately from the
catalogue-only path. Never invoke application functions or export bodies.
Migration-version metadata is separate from the application's SELECT right.
"""
import json
import os
import resource
import signal
import subprocess
import sys

class ProbeDeadline(RuntimeError):
    pass

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
CREATION="""SELECT md5(string_agg(pg_get_functiondef(oid),'' ORDER BY proname))
    FROM pg_proc WHERE pronamespace='public'::regnamespace
      AND proname IN ('vision_ecrire_item','vision_rechercher','vision_preparer_creation_item',
        'vision_stocker_embedding','vision_invalider_embedding')"""
REVISION="""SELECT md5(string_agg(pg_get_functiondef(oid),'' ORDER BY proname))
    FROM pg_proc WHERE pronamespace='public'::regnamespace
      AND proname IN ('vision_evaluer','vision_clore_seance','vision_clore_seance_v2',
        'vision_dater_seance','vision_instant','vision_date_civile','vision_commande','vision_politique')"""

def literal(text):
    return "'"+text.replace("'","''")+"'"

def witness_body_query(name,lecture,result):
    # The witness's literal SQL is exact. Only the external computation is
    # catalogue-qualified, preventing a public homonym from being executed.
    digest=(lecture.replace('md5(', 'pg_catalog.md5(')
        .replace('string_agg(', 'pg_catalog.string_agg(')
        .replace('pg_get_functiondef(', 'pg_catalog.pg_get_functiondef(')
        .replace('FROM pg_proc ', 'FROM pg_catalog.pg_proc ')
        .replace("pronamespace=", "pronamespace OPERATOR(pg_catalog.=) ")
        .replace('::regnamespace', '::pg_catalog.regnamespace')
        .replace('proname IN (', 'proname OPERATOR(pg_catalog.=) ANY(ARRAY['))
    assert digest.endswith(')')
    digest=digest[:-1]+']::pg_catalog.name[])'
    return ("SELECT coalesce((SELECT p.prosrc OPERATOR(pg_catalog.=) pg_catalog.format('SELECT CASE WHEN (%s)=%L THEN "+str(result)+
        " ELSE 0 END',"+literal(lecture)+",("+digest+"))"
        " FROM pg_catalog.pg_proc p WHERE p.oid OPERATOR(pg_catalog.=) pg_catalog.to_regprocedure('public."+name+"()')),false)")

def witness_shape_query(name):
    return ("SELECT coalesce((SELECT l.lanname='sql' AND p.provolatile='s' AND NOT p.prosecdef"
        " AND p.prorettype='pg_catalog.int4'::pg_catalog.regtype AND p.pronargs=0 AND p.proconfig IS NULL"
        " FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid=p.prolang"
        " WHERE p.oid=pg_catalog.to_regprocedure('public."+name+"()')),false)")

QUERIES={
    'vision_witness_runtime_names_unshadowed':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_class c WHERE c.relnamespace='public'::pg_catalog.regnamespace AND c.relname='pg_proc') AND NOT EXISTS(SELECT FROM pg_catalog.pg_proc p WHERE p.pronamespace='public'::pg_catalog.regnamespace AND p.proname IN ('md5','string_agg','pg_get_functiondef')) AND NOT EXISTS(SELECT FROM pg_catalog.pg_operator o WHERE o.oprnamespace='public'::pg_catalog.regnamespace AND o.oprname='=')"),
    'vision_schema_versions_1_through_27':('pg_catalog',"SELECT coalesce((SELECT array_agg(version ORDER BY version) FROM public.vision_schema_migrations)=ARRAY(SELECT generate_series(1,27)::bigint),false)"),
    'vision_version_select_granted':('pg_catalog',"SELECT has_table_privilege('vision','public.vision_schema_migrations','SELECT')"),
    'vision_public_usage_granted':('pg_catalog',"SELECT has_schema_privilege('vision','public','USAGE')"),
    'audition_versions_exactly_1':('pg_catalog',"SELECT coalesce((SELECT array_agg(version ORDER BY version) FROM audition.schema_migrations)=ARRAY[1]::integer[],false)"),
    'audition_versions_exactly_1_and_2':('pg_catalog',"SELECT coalesce((SELECT array_agg(version ORDER BY version) FROM audition.schema_migrations)=ARRAY[1,2]::integer[],false)"),
    'audition_maximum_version_is_2':('pg_catalog',"SELECT coalesce((SELECT max(version) FROM audition.schema_migrations)=2,false)"),
    'audition_version_select_granted':('pg_catalog',"SELECT has_table_privilege('audition_app','audition.schema_migrations','SELECT')"),
    'audition_schema_usage_granted':('pg_catalog',"SELECT has_schema_privilege('audition_app','audition','USAGE')"),
}
for prefix,name,lecture,number in (
    ('vision_creation','vision_creation_contrat',CREATION,1),
    ('vision_revision','vision_revision_contrat',REVISION,7),
):
    QUERIES[prefix+'_witness_expected_shape']=('pg_catalog',witness_shape_query(name))
    QUERIES[prefix+'_witness_execute_granted']=('pg_catalog',
        "SELECT coalesce(pg_catalog.has_function_privilege('vision',pg_catalog.to_regprocedure('public."+name+"()'),'EXECUTE'),false)")
    QUERIES[prefix+'_witness_matches_runtime_context']=('public,pg_catalog',witness_body_query(name,lecture,number))
    QUERIES[prefix+'_witness_matches_catalog_context']=('pg_catalog',witness_body_query(name,lecture,number))

def parse(raw):
    if raw not in (b't\n',b'f\n'):
        raise ValueError()
    return {'observed':True,'accepted':raw==b't\n'}

def sql_for(context,query):
    if context not in ('pg_catalog','public,pg_catalog') or (context,query) not in QUERIES.values():
        raise ValueError()
    return ("BEGIN READ ONLY;SET LOCAL statement_timeout='2s';SET LOCAL lock_timeout='1s';"
            "SET LOCAL search_path="+context+";"+query+";ROLLBACK;")

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:
            raise ValueError()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(ProbeDeadline()))
        signal.alarm(45)
        checks={}
        for name,(context,query) in QUERIES.items():
            try:
                process=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',
                    PREVIOUS+'/sw/bin/psql','-X','-w','-qAt','-h','/run/postgresql','-p','5432',
                    '-d','vision','-v','ON_ERROR_STOP=1'],input=sql_for(context,query).encode(),
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=4,
                    env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null',
                        'PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'2',
                        'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=2000 -c search_path=pg_catalog'})
                if process.returncode:
                    raise ValueError()
                checks[name]=parse(process.stdout)
            except (OSError,ValueError,subprocess.SubprocessError):
                checks[name]={'observed':False}
        print(json.dumps({'schema_version':2,'code':'RUST_CODE_VERSION_GUARDS_CLASSIFIED',
            'checks':checks,'application_functions_called':False,'private_application_rows_read':False,
            'migration_version_metadata_read':True,'secret_content_read':False,
            'function_bodies_exported':False,'mutation_performed':False},sort_keys=True,separators=(',',':')))
        return 0
    except BaseException:
        print('{"schema_version":2,"code":"RUST_CODE_VERSION_CLASSIFICATION_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)

if __name__=='__main__':
    raise SystemExit(main())
