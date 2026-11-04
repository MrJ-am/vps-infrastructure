"""Independent direct-role PostgreSQL check of namespace-only correction.

Invented objects only. Does not import the author's fixture or inspect VPS state.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
SQL=BASE/'vision-admin-public-schema-usage.sql'
SQL_HASH='c355bf1d930042cc99e59ee4235597298fa51ff7426625f5ed6da68d94cdbf9e'


class IndependentAdmin(unittest.TestCase):
    def test_actual_role_gains_only_namespace_lookup(self):
        self.assertNotEqual(os.geteuid(),0)
        self.assertEqual(hashlib.sha256(SQL.read_bytes()).hexdigest(),SQL_HASH)
        source=ROOT/'.local/mrjam-plateforme-identity/crates/server/src/database.rs'
        lock=json.loads((ROOT/'operations/builds/sources-runtime-20261031.lock.json').read_bytes())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),lock['sources']['platform']['files']['crates/server/src/database.rs'])
        query=re.findall(r'let safe:bool=sqlx::query_scalar\("(.*?)"\)',source.read_text(),re.S)
        self.assertEqual(len(query),1)
        predicate=query[0].replace('$1',"'public'")
        with tempfile.TemporaryDirectory(prefix='mrjam-independent-admin-') as temporary:
            root=Path(temporary);data=root/'data'
            def command(args):
                return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(command([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            started=command([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+str(root),'-w','start'])
            self.assertEqual(started.returncode,0)
            try:
                def sql(statement=None,role=None,database='vision',file=None,ok=True):
                    args=[str(PG/'psql'),'-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h',str(root),'-d',database]
                    if role:args+=['-U',role]
                    args+=['-f',str(file)] if file else ['-c',statement]
                    value=command(args)
                    self.assertEqual(value.returncode==0,ok,'native statement outcome mismatch')
                    return value.stdout.decode().strip()
                sql('CREATE DATABASE vision;',database='postgres')
                sql("CREATE ROLE vision_migration NOLOGIN; CREATE ROLE vision_administration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
                    "CREATE ROLE synthetic_outsider LOGIN; REVOKE ALL ON SCHEMA public FROM PUBLIC;"
                    "CREATE TABLE public.synthetic_private(id integer PRIMARY KEY,opaque text);"
                    "ALTER TABLE public.synthetic_private OWNER TO vision_migration;"
                    "INSERT INTO public.synthetic_private VALUES(1,'invented unchanged');"
                    "CREATE SCHEMA vision_gestion AUTHORIZATION vision_migration;"
                    "CREATE FUNCTION vision_gestion.synthetic_permitted() RETURNS boolean LANGUAGE sql SECURITY DEFINER AS 'SELECT true';"
                    "ALTER FUNCTION vision_gestion.synthetic_permitted() OWNER TO vision_migration;"
                    "REVOKE ALL ON FUNCTION vision_gestion.synthetic_permitted() FROM PUBLIC;"
                    "GRANT USAGE ON SCHEMA vision_gestion TO vision_administration;"
                    "GRANT EXECUTE ON FUNCTION vision_gestion.synthetic_permitted() TO vision_administration;")
                role='vision_administration'
                self.assertEqual(sql('SELECT current_user',role),role)
                self.assertEqual(sql(predicate,role),'f')
                self.assertEqual(sql('SELECT vision_gestion.synthetic_permitted()',role),'t')
                baseline=sql("SELECT json_build_array((SELECT json_agg(row_to_json(r) ORDER BY rolname) FROM pg_roles r),"
                    "(SELECT json_agg(row_to_json(m) ORDER BY oid) FROM pg_auth_members m),"
                    "(SELECT json_agg(row(c.oid,c.relowner,c.relacl)::text ORDER BY c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','vision_gestion')),"
                    "(SELECT json_agg(row(p.oid,p.proowner,p.proacl)::text ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='vision_gestion'),"
                    "(SELECT json_agg(row_to_json(t) ORDER BY id) FROM public.synthetic_private t))::text")
                sql(file=SQL)
                self.assertEqual(sql(predicate,role),'t')
                self.assertEqual(sql('SELECT vision_gestion.synthetic_permitted()',role),'t')
                for statement in ('SELECT * FROM public.synthetic_private',
                    "INSERT INTO public.synthetic_private VALUES(2,'denied')",'DELETE FROM public.synthetic_private',
                    'CREATE TABLE public.synthetic_denied(id integer)'):
                    sql(statement,role,ok=False)
                # PostgreSQL may warn and succeed while granting nothing.
                sql('GRANT USAGE ON SCHEMA public TO synthetic_outsider',role)
                self.assertEqual(sql("SELECT has_schema_privilege('synthetic_outsider','public','USAGE')"),'f')
                self.assertEqual(sql("SELECT has_schema_privilege(current_user,'public','CREATE')",role),'f')
                self.assertEqual(sql("SELECT json_agg(json_build_array(a.privilege_type,a.is_grantable)) FROM pg_namespace n,aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='public' AND r.rolname='vision_administration'"),'[["USAGE", false]]')
                # Reuse the literal projection without creating, dropping or mutating objects.
                after=sql("SELECT json_build_array((SELECT json_agg(row_to_json(r) ORDER BY rolname) FROM pg_roles r),"
                    "(SELECT json_agg(row_to_json(m) ORDER BY oid) FROM pg_auth_members m),"
                    "(SELECT json_agg(row(c.oid,c.relowner,c.relacl)::text ORDER BY c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','vision_gestion')),"
                    "(SELECT json_agg(row(p.oid,p.proowner,p.proacl)::text ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='vision_gestion'),"
                    "(SELECT json_agg(row_to_json(t) ORDER BY id) FROM public.synthetic_private t))::text")
                self.assertEqual(after,baseline)
                sql(file=SQL,database='postgres',ok=False)
                sql(file=SQL)
                self.assertEqual(sql(predicate,role),'t')
            finally:
                self.assertEqual(command([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)


if __name__=='__main__':unittest.main()
