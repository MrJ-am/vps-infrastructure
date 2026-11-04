import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).with_name('preflight_closure_catalog.py')
spec=importlib.util.spec_from_file_location('closure_catalog_probe',SOURCE)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')

class Parsing(unittest.TestCase):
    def test_boolean_contract(self):
        good={name:True for name in probe.FIELDS}
        self.assertTrue(probe.catalog(json.dumps(good))['all_checks_accepted'])
        for value in (None,1,'private'):
            with self.assertRaises(ValueError):probe.catalog(json.dumps({**good,'role_present':value}))
        with self.assertRaises(ValueError):probe.catalog(json.dumps({**good,'unexpected':True}))

    def test_pid1_only_exact_fixed_unit(self):
        def row(**values):return json.dumps({'_PID':'1','UNIT':probe.UNIT,**values})
        control=probe.UNIT+': Control process exited, code=exited, status=1/FAILURE'
        main=probe.UNIT+': Main process exited, code=exited, status=1/FAILURE'
        result=probe.pid1('\n'.join((row(MESSAGE=control),row(MESSAGE=main,_PID='2'),
            row(MESSAGE=main,UNIT='other.service'),row(MESSAGE='invented private text',JOB_RESULT='failed'))))
        self.assertTrue(result['exec_start_pre_exited_one'])
        self.assertTrue(result['job_failed'])
        self.assertFalse(result['exec_start_main_exited_one'])
        self.assertNotIn('invented',json.dumps(result))

@unittest.skipUnless(PG.joinpath('initdb').exists() and os.geteuid()!=0,'non-root PostgreSQL fixture')
class NativeCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mrj-closure-catalog-')
        cls.root=Path(cls.temp.name);cls.data=cls.root/'data'
        subprocess.run([str(PG/'initdb'),'-D',str(cls.data),'--no-locale','--auth=trust'],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run([str(PG/'pg_ctl'),'-D',str(cls.data),'-l',str(cls.root/'log'),'-o',
            '-c listen_addresses= -c unix_socket_directories='+str(cls.root),'-w','start'],check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.sql('CREATE DATABASE vision;')
        ddl='CREATE ROLE vision_fermeture LOGIN; CREATE ROLE vision_migration NOLOGIN; CREATE SCHEMA vision_gestion AUTHORIZATION vision_migration; REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA vision_gestion TO vision_fermeture;'
        for index in range(14):ddl+=f'CREATE TABLE public.vision_{index}(opaque integer); ALTER TABLE public.vision_{index} OWNER TO vision_migration;'
        for signature in ('comptes_identite(text,text)','engager_fermeture_identite(text,text,text)','effacer_identite_cycle(text,text,text)'):
            ddl+=f"CREATE FUNCTION vision_gestion.{signature} RETURNS boolean LANGUAGE sql SECURITY DEFINER AS 'SELECT true'; ALTER FUNCTION vision_gestion.{signature} OWNER TO vision_migration; REVOKE ALL ON FUNCTION vision_gestion.{signature} FROM PUBLIC; GRANT EXECUTE ON FUNCTION vision_gestion.{signature} TO vision_fermeture;"
        cls.sql(ddl,'vision')

    @classmethod
    def sql(cls,text,database='postgres'):
        return subprocess.run([str(PG/'psql'),'-X','-w','-qAt','-h',str(cls.root),'-d',database,
            '-v','ON_ERROR_STOP=1','-c',text],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode()

    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(PG/'pg_ctl'),'-D',str(cls.data),'-m','immediate','-w','stop'],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.temp.cleanup()

    def test_native_clean_and_specific_failures(self):
        self.assertTrue(probe.catalog(self.sql(probe.SQL,'vision'))['all_checks_accepted'])
        alterations=(
            ('GRANT SELECT ON public.vision_0 TO vision_fermeture;', 'REVOKE SELECT ON public.vision_0 FROM vision_fermeture;', 'no_public_table_privilege'),
            ('ALTER ROLE vision_migration LOGIN;', 'ALTER ROLE vision_migration NOLOGIN;', 'required_function_owners_no_login'),
            ("CREATE FUNCTION vision_gestion.unexpected() RETURNS boolean LANGUAGE sql AS 'SELECT true';",'DROP FUNCTION vision_gestion.unexpected();','no_other_management_function_executable'),
            ('REVOKE EXECUTE ON FUNCTION vision_gestion.comptes_identite(text,text) FROM vision_fermeture;','GRANT EXECUTE ON FUNCTION vision_gestion.comptes_identite(text,text) TO vision_fermeture;','all_required_functions_executable'),
            ('ALTER FUNCTION vision_gestion.comptes_identite(text,text) RENAME TO absent;','ALTER FUNCTION vision_gestion.absent(text,text) RENAME TO comptes_identite;','accounts_function_present'))
        for change,restore,field in alterations:
            with self.subTest(field=field):
                self.sql(change,'vision')
                try:
                    result=probe.catalog(self.sql(probe.SQL,'vision'))
                    self.assertFalse(result['checks'][field]);self.assertFalse(result['all_checks_accepted'])
                finally:self.sql(restore,'vision')
        self.assertTrue(probe.catalog(self.sql(probe.SQL,'vision'))['all_checks_accepted'])

if __name__=='__main__':unittest.main()
