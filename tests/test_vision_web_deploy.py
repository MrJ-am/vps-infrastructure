import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('web_deploy',Path(__file__).resolve().parents[1]/'scripts/vision-web-activate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class WebDeploymentTests(unittest.TestCase):
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
