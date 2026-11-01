#!@python@
"""Fixed preflight: schema/privilege metadata and deletion-ledger stat only.

No arguments, SQL input, application row, journal content or diagnostic output.
The application itself replays its ledger before opening its HTTP listener.
"""
import json
import os
import stat
import subprocess
import sys

QUERY = """
SELECT json_build_object(
 'context', current_user='etp_carnet' AND current_database()='etp_carnet'
   AND current_setting('server_version_num')::int BETWEEN 170000 AND 179999,
 'versions', (SELECT json_agg(version ORDER BY version) FROM public.schema_migrations),
 'columns', (SELECT json_object_agg(name, cols) FROM (
   SELECT c.relname AS name, json_agg(json_build_object('name',a.attname,
     'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull) ORDER BY a.attnum) AS cols
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
   WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') GROUP BY c.relname) entries),
 'primary_keys', (SELECT json_object_agg(name, cols) FROM (
   SELECT c.relname AS name, json_agg(a.attname ORDER BY k.position) AS cols
   FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   CROSS JOIN LATERAL unnest(x.conkey) WITH ORDINALITY k(attnum,position)
   JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
   WHERE n.nspname='public' AND x.contype='p' GROUP BY c.relname) entries),
 'unique_keys', (SELECT json_object_agg(name, keys) FROM (
   SELECT name,json_agg(cols ORDER BY id) AS keys FROM (
     SELECT x.oid AS id,c.relname AS name,json_agg(a.attname ORDER BY k.position) AS cols
     FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
     CROSS JOIN LATERAL unnest(x.conkey) WITH ORDINALITY k(attnum,position)
     JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
     WHERE n.nspname='public' AND x.contype='u' GROUP BY x.oid,c.relname) keys GROUP BY name) entries),
 'cascade_accounts', (SELECT json_agg(c.relname ORDER BY c.relname) FROM pg_constraint x
   JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND x.contype='f' AND x.confrelid='public.comptes'::regclass
     AND x.confdeltype='c' AND x.convalidated AND NOT x.condeferrable
     AND x.conkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=c.oid AND attname='compte')]
     AND x.confkey=ARRAY[(SELECT attnum FROM pg_attribute WHERE attrelid=x.confrelid AND attname='id')]),
 'runtime_ddl_forbidden', NOT (
   has_database_privilege(current_user,current_database(),'CREATE') OR
   has_database_privilege(current_user,current_database(),'TEMP') OR
   EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname<>'information_schema'
     AND has_schema_privilege(current_user,oid,'CREATE')) OR
   EXISTS (SELECT FROM pg_roles WHERE rolname=current_user AND
     (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) OR
   EXISTS (SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_database WHERE datname=current_database() AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_type WHERE typowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND p.prosecdef
       AND has_function_privilege(current_user,p.oid,'EXECUTE'))
 )
);
"""


def main():
    if len(sys.argv) != 1:
        return 2
    try:
        with open("@contract@", encoding="utf-8") as source:
            contract = json.load(source)
        descriptor = os.open("/var/lib/etp-carnet/deletions.log",
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid() or metadata.st_gid != os.getgid()
                or metadata.st_nlink != 1 or metadata.st_size > contract["limits"]["ledger_max_bytes"]):
            return 10
        observed = subprocess.run(
            ["@psql@", "-X", "-w", "--host=/run/postgresql", "--username=etp_carnet",
             "--dbname=etp_carnet", "--no-align", "--tuples-only", "--set=ON_ERROR_STOP=1", "--command=" + QUERY],
            env={"LC_ALL": "C", "PGCONNECT_TIMEOUT": "5", "PGOPTIONS":
                 "-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=10, check=False)
        if observed.returncode or len(observed.stdout) > 65536:
            return 11
        expected = {key: contract[key] for key in
                    ("versions", "columns", "primary_keys", "unique_keys", "cascade_accounts")}
        expected.update(context=True, runtime_ddl_forbidden=True)
        if json.loads(observed.stdout) != expected:
            return 12
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 13
    return 0


if __name__ == "__main__":
    sys.exit(main())
