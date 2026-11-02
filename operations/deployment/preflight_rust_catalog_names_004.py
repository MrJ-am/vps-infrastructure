"""Fixed catalogue-only classification of public names relevant to witnesses.

No application function calls, bodies, arbitrary names or application rows.
Equality operators owned by pgvector are distinguished from runtime-type ones.
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
QUERIES={
    'public_pg_proc_relation_absent':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_class WHERE relnamespace='public'::pg_catalog.regnamespace AND relname='pg_proc')"),
    'public_md5_homonym_absent':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_proc WHERE pronamespace='public'::pg_catalog.regnamespace AND proname='md5')"),
    'public_string_agg_homonym_absent':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_proc WHERE pronamespace='public'::pg_catalog.regnamespace AND proname='string_agg')"),
    'public_pg_get_functiondef_homonym_absent':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_proc WHERE pronamespace='public'::pg_catalog.regnamespace AND proname='pg_get_functiondef')"),
    'public_equality_operators_present':('pg_catalog',"SELECT EXISTS(SELECT FROM pg_catalog.pg_operator WHERE oprnamespace='public'::pg_catalog.regnamespace AND oprname='=')"),
    'public_runtime_type_equality_homonyms_absent':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_operator WHERE oprnamespace='public'::pg_catalog.regnamespace AND oprname='=' AND oprleft IN ('pg_catalog.oid'::pg_catalog.regtype,'pg_catalog.name'::pg_catalog.regtype,'pg_catalog.text'::pg_catalog.regtype) AND oprright IN ('pg_catalog.oid'::pg_catalog.regtype,'pg_catalog.name'::pg_catalog.regtype,'pg_catalog.text'::pg_catalog.regtype))"),
    'public_equality_operators_all_pgvector_members':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_operator o WHERE o.oprnamespace='public'::pg_catalog.regnamespace AND o.oprname='=' AND NOT EXISTS(SELECT FROM pg_catalog.pg_depend d JOIN pg_catalog.pg_extension e ON e.oid=d.refobjid WHERE d.classid='pg_catalog.pg_operator'::pg_catalog.regclass AND d.objid=o.oid AND d.refclassid='pg_catalog.pg_extension'::pg_catalog.regclass AND d.deptype='e' AND e.extname='vector'))"),
    'public_equality_operands_all_expected_vector_types':('pg_catalog',"SELECT NOT EXISTS(SELECT FROM pg_catalog.pg_operator o JOIN pg_catalog.pg_type l ON l.oid=o.oprleft JOIN pg_catalog.pg_type r ON r.oid=o.oprright WHERE o.oprnamespace='public'::pg_catalog.regnamespace AND o.oprname='=' AND NOT(l.typnamespace='public'::pg_catalog.regnamespace AND r.typnamespace=l.typnamespace AND l.oid=r.oid AND l.typname IN ('vector','halfvec','sparsevec')))"),
}

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
        print(json.dumps({'schema_version':3,'code':'RUST_CATALOG_NAMES_CLASSIFIED',
            'checks':checks,'application_functions_called':False,'private_application_rows_read':False,
            'migration_version_metadata_read':False,'secret_content_read':False,
            'function_bodies_exported':False,'mutation_performed':False},sort_keys=True,separators=(',',':')))
        return 0
    except BaseException:
        print('{"schema_version":3,"code":"RUST_CATALOG_NAMES_CLASSIFICATION_REFUSED"}')
        return 1
    finally:
        signal.alarm(0)

if __name__=='__main__':
    raise SystemExit(main())
