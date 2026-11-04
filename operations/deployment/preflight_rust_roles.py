#!/usr/bin/env python3
"""Read-only catalogue projection for the three unchanged Vision runtime roles.

The exact database::verify_role predicate is projected for fixed subjects.
Matheval roles are changed during adoption and the journal DB is created then;
this probe deliberately makes no claim about those future catalogues.
"""
import json
import os
import resource
import signal
import subprocess
import sys

PREVIOUS = '/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80'
ROLES = ('vision', 'vision_administration', 'audition_app')
SQL = """
BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='1s';
SET LOCAL search_path=pg_catalog;
WITH required(role,schema) AS (VALUES
 ('vision','public'),('vision_administration','public'),('audition_app','audition'))
SELECT json_object_agg(q.role,coalesce((
 SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
 AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid)
 AND EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname=q.schema AND n.nspowner<>r.oid)
 AND has_schema_privilege(r.oid,q.schema,'USAGE')
 AND NOT has_schema_privilege(r.oid,q.schema,'CREATE')
 AND NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=q.schema AND c.relowner=r.oid)
 FROM pg_roles r WHERE rolname=q.role),false)) FROM required q;
ROLLBACK;
"""


def parse(raw):
    value = json.loads(raw)
    if type(value) is not dict or set(value) != set(ROLES) or any(type(v) is not bool for v in value.values()):
        raise ValueError()
    return value


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or os.path.realpath('/run/current-system') != PREVIOUS:
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
    signal.alarm(20)
    try:
        result = subprocess.run([PREVIOUS+'/sw/bin/runuser','-u','postgres','--',
            PREVIOUS+'/sw/bin/psql','-X','-w','-qAt','-h','/run/postgresql','-p','5432',
            '-d','vision','-v','ON_ERROR_STOP=1','-c',SQL], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12, check=True,
            env={'PATH':PREVIOUS+'/sw/bin','LANG':'C','LC_ALL':'C','PGPASSFILE':'/dev/null',
                 'PGSERVICEFILE':'/dev/null','PGCONNECT_TIMEOUT':'5',
                 'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog'})
        if len(result.stdout)>1024:
            raise ValueError()
        value={'schema_version':1,'code':'RUST_EXISTING_ROLES_OBSERVED','checks':parse(result.stdout),
               'application_rows_read':False,'secrets_read':False,'mutation_performed':False,
               'matheval_and_journal_post_adoption_not_observed':True}
        code=0
    except Exception:
        value={'schema_version':1,'code':'RUST_EXISTING_ROLES_UNAVAILABLE'}
        code=1
    finally:
        signal.alarm(0)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return code


if __name__=='__main__':
    raise SystemExit(main())
