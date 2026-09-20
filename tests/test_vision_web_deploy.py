import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('web_deploy',Path(__file__).resolve().parents[1]/'scripts/vision-web-activate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
prepare_spec=importlib.util.spec_from_file_location('web_prepare',Path(__file__).resolve().parents[1]/'scripts/vision-web-prepare.py')
prepare=importlib.util.module_from_spec(prepare_spec);prepare_spec.loader.exec_module(prepare)

class WebDeploymentTests(unittest.TestCase):
    def test_missing_openssl_is_reported_before_activation(self):
        with patch.object(module.shutil,'which',return_value=None),patch.object(module.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'aucune activation'):
                module.probe_credential()
            run.assert_not_called()

    def test_recovery_requires_completed_return_and_no_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory); database=state/'sessions.sqlite'
            (state/'rollback-started').touch()
            (state/'rollback.json').write_text(json.dumps({'commit':prepare.RECOVERED_COMMIT,'restored':True}))
            (state/'prepared.json').write_text(json.dumps({'commit':prepare.RECOVERED_COMMIT,'old_system':'previous'}))
            db=sqlite3.connect(database); db.execute('CREATE TABLE sessions (digest TEXT)'); db.commit()
            prepare.validate_recovery(state,{'old_system':'previous'},database)
            with self.assertRaisesRegex(RuntimeError,'État modifié'):
                prepare.validate_recovery(state,{'old_system':'different'},database)
            db.execute("INSERT INTO sessions VALUES ('session')"); db.commit(); db.close()
            with self.assertRaisesRegex(RuntimeError,'sessions existent'):
                prepare.validate_recovery(state,{'old_system':'previous'},database)
            (state/'committed.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'déjà été enregistré'):
                prepare.validate_recovery(state,{'old_system':'previous'},database)

    def test_late_finalization_cannot_override_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'ready.json').write_text('{}');(state/'rollback-started').touch()
            with patch.object(module,'paths',return_value=(state,{})),patch.object(module,'run') as run:
                with self.assertRaises(RuntimeError):module.finalize('a'*40)
                run.assert_not_called();self.assertFalse((state/'committed.json').exists())
    def test_no_finalization_without_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module,'paths',return_value=(Path(directory),{})),patch.object(module,'run') as run:
                with self.assertRaises(RuntimeError):module.finalize('a'*40)
                run.assert_not_called()
    def test_committed_operation_cannot_be_rolled_back_by_late_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'committed.json').write_text('{}')
            with patch.object(module,'paths',return_value=(state,{})),patch.object(module,'atomic') as atomic,patch.object(module,'run') as run:
                module.rollback('a'*40,stop_apply=False)
                atomic.assert_not_called();run.assert_not_called()
    def test_http_probe_retries_rate_limits(self):
        class Response:
            def __init__(self,status):self.status=status;self.headers={}
            def read(self,*args):return b'{"ok":true}'
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch.object(module.urllib.request,'urlopen',side_effect=[Response(429),Response(200)]) as opener,patch.object(module.time,'sleep'):
            self.assertEqual(module.web_request('https://vision.mrj.am','/auth/session',cookie='test-cookie')[0],200)
            self.assertEqual(opener.call_count,2)

if __name__=='__main__':unittest.main()
