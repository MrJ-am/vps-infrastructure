import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bounded
import observe


class Bootstrap(unittest.TestCase):
    def test_command_has_no_free_path_or_action(self):
        command = observe.command({'python': '/nix/store/python/bin/python3', 'systemd_run': '/nix/store/systemd/bin/systemd-run'})
        self.assertEqual(command[0], '/nix/store/systemd/bin/systemd-run')
        self.assertIn('--unit=mrjam-observe-adoption', command)
        self.assertIn('--property=User=mrjam-inventory', command)
        self.assertIn('--property=PrivateNetwork=yes', command)
        self.assertIn('--property=NoNewPrivileges=yes', command)
        self.assertIn('--property=CapabilityBoundingSet=', command)
        self.assertIn('--property=TimeoutStartSec=20s', command)
        self.assertIn('--property=RuntimeMaxSec=60s', command)
        self.assertIn('--property=KillMode=control-group', command)
        self.assertEqual(command[command.index('--') + 1:], ['/nix/store/python/bin/python3', '-I', '-S', str(ROOT / 'collect.py')])

    def test_unsupported_arguments_never_submit_unit(self):
        with patch.object(sys, 'argv', ['observe', 'sh']), patch.object(observe, 'run') as run, patch.object(sys, 'stderr', io.StringIO()):
            self.assertEqual(observe.main(), 65)
            run.assert_not_called()

    def test_non_root_never_submits_unit(self):
        with patch.object(sys, 'argv', ['observe']), patch.object(os, 'getuid', return_value=1000), patch.object(observe, 'run') as run, patch.object(sys, 'stderr', io.StringIO()):
            self.assertEqual(observe.main(), 65)
            run.assert_not_called()

    def test_checkout_entry_is_refused_even_as_root(self):
        with self.assertRaises(bounded.Refused):
            observe.immutable_entry()

    def test_good_child_output_preserved(self):
        self.assertEqual(bounded.run([sys.executable, '-I', '-S', '-c', 'print("ok")'], environment={}, seconds=2), b'ok\n')

    def test_input_sent_only_to_selected_child(self):
        value=b'x' * 8192
        output=bounded.run([sys.executable, '-I', '-S', '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'], environment={}, seconds=2, input_bytes=value)
        self.assertEqual(output,value)

    def test_output_flood_refused(self):
        with self.assertRaises(bounded.Refused):
            bounded.run([sys.executable, '-I', '-S', '-c', 'print("x"*100000)'], environment={}, seconds=2)

    def test_partial_success_output_is_not_accepted_after_failure(self):
        with self.assertRaises(bounded.Refused):
            bounded.run([sys.executable, '-I', '-S', '-c', 'print("PRIVATE_MARKER"); raise SystemExit(1)'], environment={}, seconds=2)

    def test_timeout_is_bounded(self):
        start=time.monotonic()
        with self.assertRaises(bounded.Refused):
            bounded.run([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(10)'], environment={}, seconds=0.2)
        self.assertLess(time.monotonic()-start, 2)

    def test_oversized_input_refused_before_spawn(self):
        with patch.object(subprocess, 'Popen') as popen:
            with self.assertRaises(bounded.Refused):
                bounded.run(['not-used'], environment={}, seconds=1, input_bytes=b'x'*8193)
            popen.assert_not_called()

    def test_stderr_is_discarded(self):
        self.assertEqual(bounded.run([sys.executable, '-I', '-S', '-c', 'import sys; sys.stderr.write("PRIVATE_MARKER")'], environment={}, seconds=2), b'')


if __name__ == '__main__':
    unittest.main()
