"""Fixed code/version guards missing from the earlier catalogue-only probe.

The two Vision witness functions are never invoked. Their SQL bodies are
compared to the exact migration construction using the current catalogue hash.
Only migration version metadata and PostgreSQL catalogues are read.
"""
import json
import os
import resource
import signal
import subprocess
import sys

PREVIOUS='/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
CREATION="""SELECT md5(string_agg(pg_get_functiondef(oid),'' ORDER BY proname))
    FROM pg_proc WHERE pronamespace='public'::regnamespace
      AND proname IN ('vision_ecrire_item','vision_rechercher','vision_preparer_creation_item',
        'vision_stocker_embedding','vision_invalider_embedding')"""
REVISION="""SELECT md5(string_agg(pg_get_functiondef(oid),'' ORDER BY proname))
    FROM pg_proc WHERE pronamespace='public'::regnamespace
      AND proname IN ('vision_evaluer','vision_clore_seance','vision_clore_seance_v2',
        'vision_dater_seance','vision_instant','vision_date_civile','vision_commande','vision_politique')"""

def literal(text):return "'"+text.replace("'","''")+"'"

def witness_query(name,lecture,result):
    # No dynamic execution: fixed catalogue SELECT nested in a fixed SELECT.
    # Matching includes the stored digest, so stale witnesses return false.
    return ("SELECT coalesce((SELECT p.prosrc=format('SELECT CASE WHEN (%s)=%L THEN "+str(result)+
        " ELSE 0 END',"+literal(lecture)+",("+lecture+"))"
        " AND l.lanname='sql' AND p.provolatile='s' AND NOT p.prosecdef"
        " AND p.prorettype='int4'::regtype AND p.pronargs=0"
        " AND has_function_privilege('vision',p.oid,'EXECUTE')"
        " FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang"
        " WHERE p.oid=to_regprocedure('public."+name+"()')),false)")

QUERIES={
 'vision_schema_versions_1_through_27':"SELECT coalesce((SELECT array_agg(version ORDER BY version) FROM public.vision_schema_migrations)=ARRAY(SELECT generate_series(1,27)::bigint),false) AND has_table_privilege('vision','public.vision_schema_migrations','SELECT')",
 'vision_creation_witness_matches_current_catalog':witness_query('vision_creation_contrat',CREATION,1),
 'vision_revision_witness_matches_current_catalog':witness_query('vision_revision_contrat',REVISION,7),
 'audition_schema_version_2':"SELECT coalesce((SELECT max(version) FROM audition.schema_migrations)=2,false) AND has_table_privilege('audition_app','audition.schema_migrations','SELECT')",
}

def parse(raw):
    if raw not in (b't\n',b'f\n'):raise ValueError()
    return {'observed':True,'accepted':raw==b't\n'}

def main():
    try:
        if len(sys.argv)!=1 or os.geteuid()!=0 or os.uname().nodename!='srv1982677' or os.path.realpath('/run/current-system')!=PREVIOUS:raise ValueError()
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
        signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
        signal.alarm(45)
        checks={}
        for name,query in QUERIES.items():
            sql="BEGIN READ ONLY;SET LOCAL statement_timeout='5s';SET LOCAL lock_timeout='1s';SET LOCAL search_path=pg_catalog;"+query+";ROLLBACK;"
            try:
                process=subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',
                    PREVIOUS+'/sw/bin/psql','-X','-w','-qAt','-h','/run/postgresql','-p','5432',
                    '-d','vision','-v','ON_ERROR_STOP=1'],input=sql.encode(),stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,timeout=9,
                    env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null',
                        'PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'3',
                        'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog'})
                if process.returncode:raise ValueError()
                checks[name]=parse(process.stdout)
            except (OSError,ValueError,subprocess.SubprocessError):checks[name]={'observed':False}
        result={'schema_version':1,'code':'RUST_CODE_VERSION_GUARDS_OBSERVED','checks':checks,
            'application_functions_called':False,'private_application_rows_read':False,
            'migration_version_metadata_read':True,'secret_content_read':False,
            'function_bodies_exported':False,'mutation_performed':False,
            'all_code_version_guards_accepted':all(v.get('accepted') is True for v in checks.values())}
        print(json.dumps(result,sort_keys=True,separators=(',',':')))
        return 0
    except BaseException:
        print('{"schema_version":1,"code":"RUST_CODE_VERSION_GUARDS_REFUSED"}')
        return 1
    finally:signal.alarm(0)

if __name__=='__main__':raise SystemExit(main())
