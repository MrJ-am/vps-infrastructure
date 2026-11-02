"""Deterministic builder of the fixed Audition 001 -> 002 adoption SQL."""
import hashlib
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent

def documents():
    source=json.loads((BASE/'source.json').read_text())
    for name,digest in source['files'].items():
        assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==digest
    catalogue=(BASE/'catalogue.sql').read_text().strip().removesuffix(';')
    version=lambda values:"coalesce((SELECT pg_catalog.array_agg(version ORDER BY version) FROM audition.schema_migrations)=ARRAY["+values+"]::integer[],false)"
    checks={
        'database_is_vision':"pg_catalog.current_database()='vision'",
        'postgresql_is_17':"pg_catalog.current_setting('server_version_num')::integer BETWEEN 170000 AND 179999",
        'known_schema_001':"("+catalogue+")='"+source['catalogue_sha256']['version_1']+"'",
        'known_schema_002':"("+catalogue+")='"+source['catalogue_sha256']['version_2']+"'",
        'versions_exactly_1':version('1'),
        'versions_exactly_1_and_2':version('1,2'),
        'runtime_role_unprivileged':"coalesce((SELECT NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls) AND NOT EXISTS(SELECT FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid) FROM pg_catalog.pg_roles r WHERE rolname='audition_app'),false)",
        'runtime_metadata_access':"pg_catalog.has_schema_privilege('audition_app','audition','USAGE') AND NOT pg_catalog.has_schema_privilege('audition_app','audition','CREATE') AND pg_catalog.has_table_privilege('audition_app','audition.schema_migrations','SELECT')",
        'owners_separate_and_consistent':"coalesce((SELECT NOT pg_catalog.pg_has_role('audition_app',n.nspowner,'MEMBER') AND NOT EXISTS(SELECT FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relowner<>n.nspowner) AND NOT EXISTS(SELECT FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid AND p.proowner<>n.nspowner) FROM pg_catalog.pg_namespace n WHERE n.nspname='audition'),false)",
    }
    public="SELECT pg_catalog.jsonb_build_object("+','.join("'"+name+"',coalesce(("+query+"),false)" for name,query in checks.items())+");\n"
    preflight="BEGIN READ ONLY;\nSET LOCAL search_path=pg_catalog;\nSET LOCAL statement_timeout='5s';\nSET LOCAL lock_timeout='1s';\n"+public+"ROLLBACK;\n"
    common=' AND '.join('('+checks[name]+')' for name in ('database_is_vision','postgresql_is_17','runtime_role_unprivileged','runtime_metadata_access','owners_separate_and_consistent'))
    before='('+checks['known_schema_001']+') AND ('+checks['versions_exactly_1']+')'
    after='('+checks['known_schema_002']+') AND ('+checks['versions_exactly_1_and_2']+')'
    original=(BASE/'002-additive.sql').read_text()
    assert original.splitlines().count('BEGIN;')==original.splitlines().count('COMMIT;')==1
    body='\n'.join(line for line in original.splitlines() if line not in ('BEGIN;','COMMIT;'))
    adopt="""-- Fixed, additive schema-002 operation. Never select application rows.
BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='5s';
LOCK TABLE audition.schema_migrations,audition.administrateurs,audition.groupes,
 audition.membres,audition.objets,audition.versions,audition.requetes,audition.audit IN ACCESS EXCLUSIVE MODE;
DO $guarded_audition$
BEGIN
"""
    adopt+="IF NOT ("+common+") THEN RAISE EXCEPTION 'AUDITION_ADOPTION_PRECONDITION_REFUSED'; END IF;\n"
    adopt+="IF "+after+" THEN\n NULL; -- Exact already-adopted state is unchanged.\nELSIF "+before+" THEN\n"+body+"\nELSE\n RAISE EXCEPTION 'AUDITION_SCHEMA_NOT_RECOGNIZED';\nEND IF;\n"
    adopt+="IF NOT ("+after+") THEN RAISE EXCEPTION 'AUDITION_ADOPTION_POSTCONDITION_REFUSED'; END IF;\nEND $guarded_audition$;\nCOMMIT;\n"
    return preflight,adopt

if __name__=='__main__':
    assert len(sys.argv)==2
    destination=Path(sys.argv[1]);destination.mkdir(parents=True,exist_ok=True)
    preflight,adopt=documents()
    (destination/'preflight.sql').write_text(preflight)
    (destination/'adopt.sql').write_text(adopt)
