"""The exact generated stdin program, never real credential paths."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT/'probe-standalone.py').read_text()
candidate = types.ModuleType('standalone_candidate')
exec(compile(SOURCE, 'probe-standalone.py', 'exec'), candidate.__dict__)


class Standalone(unittest.TestCase):
    def test_generation_matches_recorded_hash_and_qualified_function_asts(self):
        proof = json.loads((ROOT/'standalone-source.json').read_text())
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), proof['sha256'])
        for path, digest in proof['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(candidate.PUBLIC_CA).hexdigest(), proof['public_ca_sha256'])
        final = {node.name:ast.dump(node) for node in ast.parse(SOURCE).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        for filename,names in [('adapt.py',('Refused','strict_json','open_directory','read_file')),
                               ('probe.py',('parse_json','tls_context','Loopback','request','identity','expired','examine'))]:
            reference={node.name:ast.dump(node) for node in ast.parse((ROOT/filename).read_text()).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
            for name in names:self.assertEqual(final[name],reference[name])

    def test_stdin_cli_does_not_import_a_file_from_current_directory(self):
        if os.geteuid()==0:self.skipTest('CLI root filesystem behavior requires the isolated independent fixture')
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('adapt.py','probe.py','json.py'):
                (Path(tmp)/name).write_text('raise RuntimeError("MALICIOUS_CWD_IMPORT")\n')
            result=subprocess.run([sys.executable,'-I','-S','-'],input=SOURCE.encode(),cwd=tmp,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,b'')
        self.assertEqual(result.stderr,b'{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}\n')

    def test_root_entry_uses_120_second_alarm_and_outputs_only_closed_boolean_report(self):
        out,err=io.StringIO(),io.StringIO()
        old_handler=object()
        with patch.object(candidate.os,'geteuid',return_value=0),patch.object(candidate.sys,'argv',['-']), \
                patch.object(candidate,'standalone_tokens',return_value={n:None for n in candidate.NAMES}) as reader, \
                patch.object(candidate,'request',side_effect=AssertionError('NO_NETWORK_WITHOUT_TOKEN')), \
                patch.object(candidate.resource,'setrlimit') as limits, \
                patch.object(candidate.signal,'signal',return_value=old_handler) as handler, \
                patch.object(candidate.signal,'alarm') as alarm, \
                contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(candidate.main(),0)
        reader.assert_called_once_with()
        limits.assert_called_once_with(candidate.resource.RLIMIT_CORE,(0,0))
        self.assertEqual([c.args[0] for c in alarm.call_args_list],[120,0])
        self.assertIs(handler.call_args_list[-1].args[1],old_handler)
        self.assertEqual(err.getvalue(),'')
        report=json.loads(out.getvalue())
        self.assertFalse(report['all_tokens_present'])
        self.assertFalse(report['write_authorization_proved'])

    def test_reader_uses_only_three_fixed_files_and_does_not_scan_directory(self):
        fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
        requested=[]
        def read(parent,name,maximum):
            self.assertEqual(parent,fd);self.assertEqual(maximum,4096)
            requested.append(name)
            if name!='kanidm-admission.token':raise FileNotFoundError()
            return b'A'*43+b'\n'
        with patch.object(candidate,'open_directory',return_value=fd) as directory, \
                patch.object(candidate.os,'fstat',return_value=types.SimpleNamespace(st_uid=0,st_mode=0o40700)), \
                patch.object(candidate,'read_file',side_effect=read), \
                patch.object(candidate.os,'listdir',side_effect=AssertionError('NO_DIRECTORY_SCAN')):
            result=candidate.standalone_tokens()
        directory.assert_called_once_with('/var/lib/mrjam-identite')
        self.assertEqual(requested,['kanidm-admission.token','kanidm-cycle.token','kanidm-replay.token'])
        self.assertEqual(result,{'admission':'A'*43,'cycle':None,'replay':None})

    def test_arguments_or_reader_failure_never_echo_credentials(self):
        for argv in (['-','unexpected'],['-']):
            out,err=io.StringIO(),io.StringIO()
            with patch.object(candidate.os,'geteuid',return_value=0),patch.object(candidate.sys,'argv',argv), \
                    patch.object(candidate,'standalone_tokens',side_effect=ValueError('PRIVATE_INVENTED_TOKEN')), \
                    contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(candidate.main(),1)
            self.assertEqual(out.getvalue(),'')
            self.assertEqual(err.getvalue(),'{"error":"KANIDM_CAPABILITY_PROBE_REFUSED"}\n')


if __name__=='__main__':unittest.main()
