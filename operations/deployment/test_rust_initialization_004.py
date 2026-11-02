import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
spec=importlib.util.spec_from_file_location('initialization',BASE/'preflight_rust_initialization_004.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
PG=Path('/nix/store/hfk2znm53zp4x7hjjh35didm9znjw8jn-postgresql-17.11/bin')
SOURCE=ROOT/'.local/ci-artifact-recovery-20261102/proposal-base/sources'

class ClosedPredicates(unittest.TestCase):
    def test_secret_formats_match_exact_loaders(self):
        self.assertTrue(p.credential_format(b'a'*64,'sha256'))
        self.assertTrue(p.credential_format(b'f'*64+b'\n','sha256'))
        for value in (b'A'*64,b'a'*63,b'a'*64+b'\n\n',b'a'*64+b'\r\n',b'x'*64,b'\xff'*64):
            self.assertFalse(p.credential_format(value,'sha256'))
        self.assertTrue(p.credential_format(b'aB0-_'*20+b'\n','approval'))
        for value in (b'a'*31,b'a'*513,b'a'*31+b'=',b'a'*31+b' ',b'a'*32+b'\x00'):
            self.assertFalse(p.credential_format(value,'approval'))

    def test_symlinks_and_non_regular_references_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'good').write_bytes(b'a'*64)
            self.assertTrue(p.credential_observation(str(path/'good'),'sha256')['runtime_format_accepted'])
            (path/'link').symlink_to(path/'good')
            self.assertEqual(p.credential_observation(str(path/'link'),'sha256'),{'observed':False})
            os.mkfifo(path/'fifo')
            self.assertEqual(p.credential_observation(str(path/'fifo'),'sha256'),{'observed':False})
            (path/'parent-link').symlink_to(path,target_is_directory=True)
            self.assertEqual(p.credential_observation(str(path/'parent-link/good'),'sha256'),{'observed':False})

    def test_output_cannot_contain_credentials_or_unexpected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'private';secret=b'InventedSecret1234567890123456789012345';file.write_bytes(secret)
            output=json.dumps(p.credential_observation(str(file),'approval'))
            self.assertNotIn(secret.decode(),output)
        expected={key+'_required_columns':True for key in p.COLUMNS}
        expected.update(administrator_sequence_present=True,public_bank_equal=True,
            baseline_application_role_present=True,adopted_admin_role_absent_after_return=True)
        self.assertEqual(p.parse_catalogue(json.dumps(expected)),expected)
        for invalid in ({**expected,'unexpected':'private'},{**expected,'public_bank_equal':1}):
            with self.assertRaises(ValueError):p.parse_catalogue(json.dumps(invalid))

    def test_public_assets_bound_and_original_binary_passes_assets(self):
        self.assertIsInstance(p.public_bank()['version'],str)
        binary='/nix/store/hf08v9mbbr9hrjzp5j53691zv0b5dvq5-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a/bin/mrjam-server'
        self.assertEqual(hashlib.sha256(Path(binary).read_bytes()).hexdigest(),'f896cd1c17cc85d331474622747f4c019258a1023dfb5963125b235f4a6236cd')
        # Set an ambient selector to stop at connect() before any DB access.
        run=subprocess.run([binary,'serve','--config',p.CONFIG],env={'PG_PROBE_SENTINEL':'1',
            'MRJAM_LISTEN_ADDR':'127.0.0.1:38101','MRJAM_INSTANCE':'blue','MRJAM_WORKERS_ENABLED':'false'},
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(run.returncode,2);self.assertEqual(run.stdout,b'')
        self.assertEqual(json.loads(run.stderr),{'code':'AMBIENT_DATABASE_CONFIGURATION_REFUSED'})

class NativeMatheval(unittest.TestCase):
    def test_catalogue_projection_and_exact_post_adoption_runtime_guards(self):
        self.assertNotEqual(os.geteuid(),0)
        with tempfile.TemporaryDirectory(prefix='mrjam-init-readonly-') as tmp:
            root=Path(tmp);data=root/'pg'
            def run(args):
                return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertEqual(run([str(PG/'initdb'),'-D',str(data),'--no-locale','--auth=trust']).returncode,0)
            self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-l',str(root/'log'),'-o',
                '-c listen_addresses= -c unix_socket_directories='+tmp,'-w','start']).returncode,0)
            try:
                def sql(text,database='matheval',role=None):
                    args=[str(PG/'psql'),'-X','-w','-qAt','-h',tmp,'-d',database,'-v','ON_ERROR_STOP=1']
                    if role:args+=['-U',role]
                    value=run(args+['-c',text]);self.assertEqual(value.returncode,0,'closed native SQL outcome')
                    return value.stdout.decode().strip()
                sql('CREATE DATABASE matheval;','postgres')
                sql('CREATE ROLE matheval_app LOGIN;')
                for file in sorted((SOURCE/'mateval/migrations').glob('*.sql')):sql(file.read_text())
                bank={'version':"invented'v1",'content':"';DROP TABLE corpus;--"}
                sql("INSERT INTO corpus(version,digest,bank,codebook) VALUES("+p.sql_literal(bank['version'])+",'invented',"+
                    p.sql_literal(json.dumps(bank))+"::jsonb,'{}');")
                baseline=p.parse_catalogue(sql(p.catalogue_query(bank)))
                self.assertTrue(all(baseline.values()))
                wrong={**bank,'content':'different'}
                self.assertFalse(p.parse_catalogue(sql(p.catalogue_query(wrong)))['public_bank_equal'])
                sql('ALTER TABLE public.administrator_sessions RENAME last_seen TO missing;')
                self.assertFalse(p.parse_catalogue(sql(p.catalogue_query(bank)))['administrator_sessions_required_columns'])
                sql('ALTER TABLE public.administrator_sessions RENAME missing TO last_seen;')
                sql((BASE/'adopt-matheval.sql').read_text())
                source=(SOURCE/'platform/crates/server/src/database.rs').read_text()
                predicate=re.search(r'let safe:bool=sqlx::query_scalar\("(.*?)"\)',source,re.S).group(1).replace('$1',"'public'")
                for role in ('matheval_app','matheval_admin'):
                    self.assertEqual(sql('BEGIN READ ONLY;'+predicate+';ROLLBACK;',role=role),'t')
                privileges=re.search(r'let privileges:bool=sqlx::query_scalar\("(.*?)"\)',source,re.S).group(1)
                self.assertEqual(sql('BEGIN READ ONLY;'+privileges+';ROLLBACK;',role='matheval_app'),'t')
                admin=(SOURCE/'mateval/src/administration.rs').read_text()
                health=re.search(r'let healthy: bool = sqlx::query_scalar\("(.*?)"\)',admin,re.S).group(1)
                self.assertEqual(sql('BEGIN READ ONLY;'+health+';ROLLBACK;',role='matheval_admin'),'t')
                for role,tables in (('matheval_app',list(p.COLUMNS)[:4]),('matheval_admin',list(p.COLUMNS)[4:])):
                    for table in tables:sql('BEGIN READ ONLY;SELECT '+p.COLUMNS[table]+' FROM '+table+' LIMIT 0;ROLLBACK;',role=role)
                self.assertEqual(sql('SELECT count(*) FROM public.corpus;'),'1')
                self.assertEqual(sql('SELECT count(*) FROM public.participations;'),'0')
            finally:
                self.assertEqual(run([str(PG/'pg_ctl'),'-D',str(data),'-m','immediate','-w','stop']).returncode,0)

if __name__=='__main__':unittest.main()
