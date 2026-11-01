#!@python@
"""Fixed read-only preflight for the qualified Forgejo build, no caller input.

Only migration and privilege metadata is queried. This is not a general SQL
interface. The runtime role must lack DDL rights before Forgejo may start;
upstream SyncAllTables cannot use it to alter the schema.
"""
import json
import subprocess
import sys

QUERY = """
SELECT json_build_object(
 'runtime_ddl_forbidden', NOT (
   has_database_privilege(current_user, current_database(), 'CREATE') OR
   has_database_privilege(current_user, current_database(), 'TEMP') OR
   EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
     AND has_schema_privilege(current_user, oid, 'CREATE')) OR
   EXISTS (SELECT FROM pg_roles WHERE rolname=current_user AND
     (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) OR
   EXISTS (SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_database WHERE datname=current_database() AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_type WHERE typowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR
   EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND p.prosecdef
       AND has_function_privilege(current_user, p.oid, 'EXECUTE'))
 ),
 'gitea', (SELECT json_agg(r ORDER BY id) FROM
   (SELECT id, version FROM public.version ORDER BY id LIMIT 257) r),
 'forgejo', (SELECT json_agg(r ORDER BY id) FROM
   (SELECT id, version FROM public.forgejo_version ORDER BY id LIMIT 257) r),
 'migrations', (SELECT json_agg(id ORDER BY id COLLATE "C") FROM
   (SELECT left(id,128) AS id FROM public.forgejo_migration ORDER BY id COLLATE "C" LIMIT 257) r)
);
"""


def main():
    if len(sys.argv) != 1:
        return 2
    try:
        with open("@contract@", encoding="utf-8") as source:
            expected = json.load(source)["metadata"]
        result = subprocess.run(
            ["@psql@", "-X", "-w", "--host=/run/postgresql",
             "--username=forgejo", "--dbname=forgejo", "--no-align",
             "--tuples-only", "--set=ON_ERROR_STOP=1", "--command=" + QUERY],
            env={"LC_ALL": "C", "PGCONNECT_TIMEOUT": "5",
                 "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=5000 -c search_path=pg_catalog"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        if result.returncode or len(result.stdout) > 65536:
            return 10
        observed = json.loads(result.stdout)
        if observed != expected:
            return 11
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 12
    return 0


if __name__ == "__main__":
    sys.exit(main())
