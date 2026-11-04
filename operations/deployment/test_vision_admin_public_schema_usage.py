"""Native PostgreSQL proof of the minimal existing Vision role correction."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import unittest

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
spec=importlib.util.spec_from_file_location('closure_test',BASE/'test_preflight_closure_catalog.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)

class NativeVisionAdministration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster=support.NativeCatalog
        cls.cluster.setUpClass()
        source=(ROOT/'.local/mrjam-plateforme-identity/crates/server/src/database.rs').read_text()
        lock=json.loads((ROOT/'operations/builds/sources-runtime-20261031.lock.json').read_text())
        if hashlib.sha256(source.encode()).hexdigest()!=lock['sources']['platform']['files']['crates/server/src/database.rs']:
            raise AssertionError('RUNTIME_SOURCE_BINDING_REFUSED')
        cls.predicate=re.search(r'let safe:bool=sqlx::query_scalar\("(.*?)"\)',source,re.S).group(1).replace('$1',"'public'")
        cls.cluster.sql("CREATE ROLE vision_administration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
            "GRANT USAGE ON SCHEMA vision_gestion TO vision_administration;"
            "CREATE FUNCTION vision_gestion.administrer(text,text,jsonb) RETURNS boolean LANGUAGE sql SECURITY DEFINER AS 'SELECT true';"
            "ALTER FUNCTION vision_gestion.administrer(text,text,jsonb) OWNER TO vision_migration;"
            "REVOKE ALL ON FUNCTION vision_gestion.administrer(text,text,jsonb) FROM PUBLIC;"
            "GRANT EXECUTE ON FUNCTION vision_gestion.administrer(text,text,jsonb) TO vision_administration;"
            "ALTER TABLE public.vision_0 ADD COLUMN utilisateur text; ALTER TABLE public.vision_0 ENABLE ROW LEVEL SECURITY;"
            "ALTER TABLE public.vision_0 FORCE ROW LEVEL SECURITY;"
            "CREATE POLICY proprietaire ON public.vision_0 USING(utilisateur=current_setting('vision.utilisateur',true)) WITH CHECK(utilisateur=current_setting('vision.utilisateur',true));",'vision')

    @classmethod
    def tearDownClass(cls):cls.cluster.tearDownClass()

    def sql(self,query):return self.cluster.sql(query,'vision').strip()

    def apply(self,database='vision'):
        return subprocess.run([str(support.PG/'psql'),'-X','-w','-qAt','-h',str(self.cluster.root),'-d',database,
            '-v','ON_ERROR_STOP=1','-f',str(BASE/'vision-admin-public-schema-usage.sql')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)

    def immutable_state(self):
        return self.sql("SELECT json_build_object('roles',(SELECT json_agg(row_to_json(r) ORDER BY rolname) FROM pg_roles r),"
            "'relations',(SELECT json_agg(json_build_array(c.oid,c.relowner,c.relacl,c.relrowsecurity,c.relforcerowsecurity) ORDER BY c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','vision_gestion')),"
            "'functions',(SELECT json_agg(json_build_array(p.oid,p.proowner,p.proacl,p.prosrc) ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','vision_gestion')),"
            "'policies',(SELECT json_agg(row_to_json(p) ORDER BY oid) FROM pg_policy p),"
            "'memberships',(SELECT json_agg(row_to_json(m) ORDER BY oid) FROM pg_auth_members m),"
            "'other_schema_acl',(SELECT nspacl::text FROM pg_namespace WHERE nspname='vision_gestion'))")

    def test_exact_runtime_predicate_and_no_other_rights(self):
        before=self.immutable_state()
        self.assertEqual(self.sql('BEGIN READ ONLY; SET LOCAL ROLE vision_administration;'+self.predicate+';ROLLBACK;'),'f')
        self.assertEqual(self.sql("SELECT NOT has_schema_privilege('vision_administration','public','USAGE') AND NOT has_schema_privilege('vision_administration','public','CREATE')"),'t')
        self.assertEqual(self.apply().returncode,0)
        self.assertEqual(self.sql('BEGIN READ ONLY; SET LOCAL ROLE vision_administration;'+self.predicate+';ROLLBACK;'),'t')
        self.assertEqual(self.immutable_state(),before)
        acl=json.loads(self.sql("SELECT json_agg(json_build_array(a.privilege_type,a.is_grantable) ORDER BY a.privilege_type) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='public' AND r.rolname='vision_administration'"))
        self.assertEqual(acl,[['USAGE',False]])
        self.assertEqual(self.sql("SELECT NOT has_schema_privilege('vision_fermeture','public','USAGE') AND NOT has_schema_privilege('vision_administration','public','CREATE')"),'t')
        self.assertEqual(self.apply().returncode,0)
        self.assertEqual(self.immutable_state(),before)

    def test_wrong_database_refused(self):
        result=self.apply('postgres')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'vision_admin_namespace_database_refused',result.stderr)

    def test_fixed_adoption_order(self):
        source=(BASE/'database-adoption.nix').read_text()
        journal='${psql} --dbname=vision_journal --file=${./journal-public-schema-usage.sql}'
        vision='${psql} --dbname=vision --file=${./vision-admin-public-schema-usage.sql}'
        self.assertEqual(source.count(vision),1)
        self.assertIn(journal+'\n    '+vision,source)

if __name__=='__main__':unittest.main()
