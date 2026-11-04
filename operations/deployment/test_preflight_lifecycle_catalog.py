"""Native catalogue predicates with invented PostgreSQL objects only."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

BASE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,BASE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
probe=load('lifecycle_probe','preflight_lifecycle_catalog.py')
support=load('closure_test','test_preflight_closure_catalog.py')

class OutputContract(unittest.TestCase):
    def test_only_boolean_results(self):
        self.assertEqual(probe.parse('t\n'),{'observed':True,'accepted':True})
        self.assertEqual(probe.parse('f\n'),{'observed':True,'accepted':False})
        for value in ('','private text','t\nf','true','1'):
            with self.assertRaises(ValueError):probe.parse(value)

class NativeLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster=support.NativeCatalog;cls.cluster.setUpClass()
        ddl=''.join('CREATE ROLE '+role+' LOGIN;' for role in ('vision_cycle','vision','vision_administration','audition_app'))
        signatures=('preavis_a_traiter()','constater_preavis(uuid,text)','engager_effacement(text,uuid)','effacer_cycle(text,text,uuid)',
                    'administrer(text,text,jsonb)','effacer(text,text)','activer(text,text,text,text,text)')
        for signature in signatures:
            ddl+=f"CREATE FUNCTION vision_gestion.{signature} RETURNS boolean LANGUAGE sql SECURITY DEFINER AS 'SELECT true'; ALTER FUNCTION vision_gestion.{signature} OWNER TO vision_migration; REVOKE ALL ON FUNCTION vision_gestion.{signature} FROM PUBLIC;"
        for signature in signatures[:4]:ddl+='GRANT EXECUTE ON FUNCTION vision_gestion.'+signature+' TO vision_cycle;'
        ddl+='GRANT EXECUTE ON FUNCTION vision_gestion.administrer(text,text,jsonb) TO vision_administration;'
        names=('vision_contextes','vision_embeddings','vision_episodes','vision_fiches','vision_items','vision_journal','vision_liens',
               'vision_migrations_metier','vision_observations','vision_preparations_items','vision_profils','vision_recherches','vision_requetes','vision_seances')
        for name in names:
            ddl+=f"CREATE TABLE public.{name}(utilisateur text); ALTER TABLE public.{name} OWNER TO vision_migration; ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY; ALTER TABLE public.{name} FORCE ROW LEVEL SECURITY; CREATE POLICY proprietaire ON public.{name} USING(utilisateur=current_setting('vision.utilisateur',true)) WITH CHECK(utilisateur=current_setting('vision.utilisateur',true));"
        ddl+='CREATE SCHEMA audition AUTHORIZATION vision_migration;'
        for name in ('administrateurs','groupes','membres','objets','versions','requetes','audit'):
            ddl+=f'CREATE TABLE audition.{name}(opaque integer); ALTER TABLE audition.{name} OWNER TO vision_migration; ALTER TABLE audition.{name} ENABLE ROW LEVEL SECURITY;'
        cls.cluster.sql(ddl,'vision')

    @classmethod
    def tearDownClass(cls):cls.cluster.tearDownClass()

    def observe(self):
        return {name:probe.parse(self.cluster.sql('BEGIN READ ONLY;SET LOCAL search_path=pg_catalog;SELECT coalesce(('+query+'),false);ROLLBACK;','vision'))
                for name,query in probe.QUERIES.items()}

    def test_real_predicates_and_independent_failures(self):
        self.assertTrue(all(v['accepted'] for v in self.observe().values()))
        cases=(('REVOKE EXECUTE ON FUNCTION vision_gestion.preavis_a_traiter() FROM vision_cycle;',
                'GRANT EXECUTE ON FUNCTION vision_gestion.preavis_a_traiter() TO vision_cycle;','cycle_fixed_capabilities'),
               ('ALTER TABLE public.vision_contextes NO FORCE ROW LEVEL SECURITY;',
                'ALTER TABLE public.vision_contextes FORCE ROW LEVEL SECURITY;','vision_row_security'),
               ('GRANT SELECT ON public.vision_0 TO vision_administration;',
                'REVOKE SELECT ON public.vision_0 FROM vision_administration;','vision_administration_capabilities'),
               ('ALTER TABLE audition.audit DISABLE ROW LEVEL SECURITY;',
                'ALTER TABLE audition.audit ENABLE ROW LEVEL SECURITY;','audition_row_security'))
        for change,restore,field in cases:
            self.cluster.sql(change,'vision')
            try:
                values=self.observe();self.assertFalse(values[field]['accepted'])
                self.assertTrue(all(v['accepted'] for k,v in values.items() if k!=field))
            finally:self.cluster.sql(restore,'vision')
        self.assertTrue(all(v['accepted'] for v in self.observe().values()))

    def test_predicates_match_immutable_worker_source(self):
        source=Path('/nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source')
        for field,name,role in (('vision_row_security','postgres.rs','vision'),('vision_administration_capabilities','gestion.rs','vision_administration')):
            expected=re.search(r'const PRECONDITIONS: &str = r#"(.*?)"#;',(source/'src'/name).read_text(),re.S).group(1).strip()
            self.assertEqual(probe.QUERIES[field],expected.replace('current_user',"'"+role+"'"))
        lifecycle=(source/'src/lifecycle.rs').read_text()
        expected=re.search(r'query_scalar\(r#"(.*?)"#\)',lifecycle,re.S).group(1)
        signatures=re.findall(r'"([^"]+)"',re.search(r'const CYCLE: &\[&str\] = &\[(.*?)\];',lifecycle,re.S).group(1))
        expected=expected.replace('$1','ARRAY['+','.join("'"+s+"'" for s in signatures)+']').replace('current_user',"'vision_cycle'")
        self.assertEqual(probe.QUERIES['cycle_fixed_capabilities'],expected)

if __name__=='__main__':unittest.main()
