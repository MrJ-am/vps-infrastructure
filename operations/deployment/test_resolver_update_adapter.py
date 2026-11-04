import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import configuration_update as C
import resolver_update_adapter as A


class Tests(unittest.TestCase):
    def setUp(self):
        self.adapter = A.Adapter()
        self.config = (Path(A.CANDIDATE) / "etc/systemd/resolved.conf").read_bytes()

    def verify(self, port=None, failed_service=None):
        header = b"sl local_address rem_address st\n"
        raw = header if port is None else header + ("0: 00000000:%04X 00000000:0000 07\n" % port).encode()
        calls = []
        def execute(args, timeout=30):
            calls.append(args)
            if failed_service and args[-1] == failed_service + ".service":
                raise C.Refused("FIXED_OPERATION_REFUSED")
        with patch.object(A.Path, "read_bytes", return_value=self.config), \
                patch.object(A, "run", side_effect=execute), \
                patch("builtins.open", side_effect=lambda *a, **k: io.BytesIO(raw)):
            self.adapter.verify_candidate()
        return calls

    def test_all_services_checked_individually_and_dns_kept(self):
        calls = self.verify(port=53)
        self.assertEqual(len(calls), len(A.SERVICES) + 1)
        self.assertEqual([call[-1] for call in calls[:-1]], [s + ".service" for s in A.SERVICES])
        self.assertEqual(calls[-1], [A.SYSTEMD + "resolvectl", "query", "--cache=no", "log.mrj.am"])

    def test_one_service_failure_cannot_hide_behind_other_active_units(self):
        for service in A.SERVICES:
            with self.subTest(service=service), self.assertRaises(C.Refused):
                self.verify(failed_service=service)

    def test_port5355_refused_even_if_not_tcp_listening(self):
        with self.assertRaisesRegex(C.Refused, "LLMNR_STILL_BOUND"):
            self.verify(port=5355)

    def test_changed_resolver_bytes_refused_before_operations(self):
        with patch.object(A.Path, "read_bytes", return_value=self.config + b"#changed\n"), \
                patch.object(A, "run") as run, self.assertRaises(C.Refused):
            self.adapter.verify_candidate()
        run.assert_not_called()

    def test_observer_never_accepts_arbitrary_generation(self):
        with patch.object(A.os.path, "realpath", side_effect=[A.CANDIDATE, "/nix/store/foreign"]):
            self.assertEqual(self.adapter.observe(), ("candidate", "foreign"))

    def test_checkpoint_survives_prior_incomplete_write_and_binds_pins(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(A, "STATE", Path(directory)):
            retained = Path(directory) / "checkpoint-incomplete.next"
            retained.write_bytes(b"incomplete")
            self.adapter.checkpoint("activating")
            self.adapter.checkpoint("returning")
            value = json.loads((Path(directory) / "checkpoint.json").read_bytes())
            self.assertEqual(value, {"previous": A.PREVIOUS, "candidate": A.CANDIDATE, "phase": "returning"})
            self.assertEqual(retained.read_bytes(), b"incomplete")
            self.assertEqual((Path(directory) / "checkpoint.json").stat().st_mode & 0o777, 0o600)

    def test_generation_operations_use_only_pinned_targets(self):
        with patch.object(self.adapter.generations, "activate") as active, \
                patch.object(self.adapter.generations, "select_boot") as boot:
            self.adapter.activate_candidate()
            self.adapter.activate_previous()
            self.adapter.select_candidate_boot()
            self.adapter.select_previous_boot()
        self.assertEqual([c.args[0] for c in active.call_args_list], [A.CANDIDATE, A.PREVIOUS])
        self.assertEqual([c.args[0] for c in boot.call_args_list], [A.CANDIDATE, A.PREVIOUS])


if __name__ == "__main__": unittest.main()
