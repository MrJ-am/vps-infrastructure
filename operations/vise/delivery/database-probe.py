"""Qualify synthetic database isolation; no candidate admission or deployment."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_stage import Build
from synthetic_database import Database
import source_policy as P

def main():
    P.require(sys.argv[1:]==['/input'],'VISE_PROBE_ARGUMENTS_REFUSED')
    database=Database(Build(json.loads(Path('@runtime@').read_bytes())))
    checks=[]
    try:
        database.start();database.initialize()
        P.require(database.metadata(),'VISE_SYNTHETIC_SCHEMA_REFUSED')
        checks.append('protected-schema-and-idempotent-adoption')
        for sql in ['CREATE TABLE forbidden(id int)','CREATE ROLE forbidden LOGIN',
                    'ALTER TABLE comptes ADD COLUMN forbidden integer']:
            P.require(database.sql(sql,runtime=True,ok=False).returncode!=0,'VISE_SYNTHETIC_PRIVILEGE_LEAK')
        checks.append('runtime-ddl-and-role-management-refused')
        env={**database.env,'PGPASSWORD':database.runtime_password}
        result=database.command([database.tools['psql'],*database.connection,'-X','-w','-c','SELECT 1'],env=env,ok=False)
        P.require(result.returncode!=0,'VISE_SYNTHETIC_ADMIN_AUTH_LEAK')
        checks.append('runtime-password-cannot-authenticate-admin')
        database.sql('UPDATE schema_migrations SET version=2')
        P.require(not database.metadata(),'VISE_SYNTHETIC_VERSION_CHECK_FAILED')
        database.sql('UPDATE schema_migrations SET version=1')
        database.sql('GRANT CREATE ON SCHEMA public TO etp_carnet')
        P.require(not database.metadata(),'VISE_SYNTHETIC_PRIVILEGE_CHECK_FAILED')
        database.sql('REVOKE CREATE ON SCHEMA public FROM etp_carnet')
        P.require(database.metadata(),'VISE_SYNTHETIC_SCHEMA_REFUSED')
        checks.append('schema-version-and-privilege-drift-detected')
    finally:database.stop()
    print(json.dumps({'scope':'synthetic-database-only','checks':checks,'full_validation':False,
        'production_access':False}),file=sys.stderr)

if __name__=='__main__':
    try:main()
    except Exception as error:
        import re
        code=str(error) if re.fullmatch('VISE_[A-Z_]+',str(error)) else 'VISE_DATABASE_PROBE_REFUSED'
        print(json.dumps({'code':code,'exception_type':type(error).__name__}),file=sys.stderr)
        raise SystemExit(1) from None
