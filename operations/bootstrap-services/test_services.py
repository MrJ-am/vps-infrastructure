import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parent / "bootstrap-observation")]
import contract
import collect
import observe

STORE = "/nix/store/00000000000000000000000000000000-synthetic-code"
EXE = STORE + "/bin/server"
RUNTIME = {"nix": "/qualified/bin/nix", "systemctl": "/qualified/bin/systemctl",
           "systemd_run": "/qualified/bin/systemd-run", "python": "/qualified/bin/python3"}


def report():
    return {"schema_version": 1, "authority": "unverified_observation",
            "generation": {"store_path": STORE, "nar_hash": None, "nar_size": None},
            "accounts": {name: {"state": "unknown", "uid": None, "gid": None} for name in contract.ACCOUNTS},
            "services": {name: {"state": "unknown", "executable": None,
                "store_path": None, "nar_hash": None, "nar_size": None} for name in contract.UNITS}}


class ContractTests(unittest.TestCase):
    def test_unknown_is_preserved_without_claiming_absence(self):
        data = report()
        self.assertEqual(json.loads(contract.decode(json.dumps(data).encode())), data)

    def test_exact_accounts_and_services_only(self):
        for field in ("accounts", "services"):
            data = report(); data[field]["arbitrary-target"] = {}
            with self.assertRaises(ValueError): contract.validate(data)

    def test_private_fields_and_authenticity_claims_are_refused(self):
        for change in ({"secret": "synthetic"}, {"authority": "authenticated"}, {"schema_version": True}):
            data = report(); data.update(change)
            with self.assertRaises(ValueError): contract.validate(data)
        data = report(); data["services"]["forgejo"]["argv"] = "synthetic-secret"
        with self.assertRaises(ValueError): contract.validate(data)

    def test_numeric_identities_are_closed(self):
        for uid in (0, -1, True, "977", 2**31):
            data = report(); data["accounts"]["forgejo"].update(state="observed", uid=uid, gid=977)
            with self.assertRaises(ValueError): contract.validate(data)
        data = report(); data["accounts"]["forgejo"].update(state="observed", uid=977, gid=977)
        contract.validate(data)

    def test_executable_must_belong_to_declared_store_and_active_unit(self):
        for exe in ("/tmp/server", STORE + "/../secret", STORE + "/bin/server\n", EXE):
            data = report(); data["services"]["forgejo"].update(executable=exe, store_path=STORE)
            with self.assertRaises(ValueError): contract.validate(data)
        data = report(); data["services"]["forgejo"].update(state="active", executable=EXE, store_path=STORE)
        contract.validate(data)
        data["services"]["forgejo"]["store_path"] = None
        with self.assertRaises(ValueError): contract.validate(data)

    def test_nar_is_metadata_and_must_be_complete(self):
        data = report(); data["generation"].update(nar_hash="sha256-" + "A" * 43 + "=", nar_size=64)
        contract.validate(data)
        for change in ({"nar_size": 0}, {"nar_size": True}, {"nar_hash": None}, {"store_path": None}):
            broken = copy.deepcopy(data); broken["generation"].update(change)
            with self.assertRaises(ValueError): contract.validate(broken)

    def test_duplicate_keys_and_excessive_input_are_refused(self):
        with self.assertRaises(ValueError): contract.decode(b'{"authority":1,"authority":2}')
        with self.assertRaises(ValueError): contract.decode(b' ' * (contract.MAX_BYTES + 1))


class CollectorTests(unittest.TestCase):
    def test_only_selected_systemd_properties_are_requested(self):
        with patch.object(collect, "run", return_value=b"LoadState=loaded\nActiveState=active\nMainPID=731\n") as call:
            self.assertEqual(collect.status(RUNTIME, "forgejo"), ("active", 731))
        self.assertEqual(call.call_args.args[0], ["/qualified/bin/systemctl", "--system", "show",
            "--property=LoadState,ActiveState,MainPID", "forgejo.service"])
        self.assertEqual(call.call_args.kwargs["limit"], 256)

    def test_no_executable_read_for_inactive_or_absent_unit(self):
        for status in (("inactive", 0), ("failed", 0), ("absent", None), ("unknown", None)):
            with patch.object(collect, "status", return_value=status), patch.object(collect.os, "readlink") as read:
                result = collect.service(RUNTIME, "forgejo")
                self.assertEqual(result["state"], status[0]); self.assertIsNone(result["executable"])
                read.assert_not_called()

    def test_executable_denial_is_unknown_build_not_absent_software(self):
        with patch.object(collect, "status", return_value=("active",731)), patch.object(collect.os, "readlink", side_effect=PermissionError):
            result = collect.service(RUNTIME, "forgejo")
        self.assertEqual(result["state"], "active"); self.assertIsNone(result["executable"])

    def test_restart_or_exec_race_does_not_bind_wrong_build(self):
        with patch.object(collect, "status", side_effect=[("active",731),("active",732)]), patch.object(collect.os, "readlink", return_value=EXE):
            self.assertIsNone(collect.service(RUNTIME, "forgejo")["store_path"])
        with patch.object(collect, "status", return_value=("active",731)), patch.object(collect.os, "readlink", side_effect=[EXE, STORE + "/bin/other"]):
            self.assertIsNone(collect.service(RUNTIME, "forgejo")["store_path"])

    def test_nonstore_path_and_deleted_executable_never_escape(self):
        for value in ("/var/lib/private/secret", EXE + " (deleted)", STORE + "/../secret"):
            with patch.object(collect, "status", return_value=("active",731)), patch.object(collect.os, "readlink", return_value=value):
                self.assertIsNone(collect.service(RUNTIME, "forgejo")["executable"])

    def test_nar_selects_only_hash_and_size_and_forces_offline(self):
        data = {STORE: {"narHash": "sha256-" + "A"*43 + "=", "narSize": 64, "references": ["not-returned"]}}
        with patch.object(collect, "run", return_value=json.dumps(data).encode()) as call:
            result = collect.nar(RUNTIME, STORE)
        self.assertEqual(set(result), {"store_path","nar_hash","nar_size"})
        self.assertIn("--offline", call.call_args.args[0]); self.assertEqual(call.call_args.args[0][-1], STORE)

    def test_failed_nix_query_does_not_invent_hash(self):
        with patch.object(collect, "run", side_effect=collect.Refused):
            self.assertEqual(collect.nar(RUNTIME, STORE), {"store_path": STORE, "nar_hash": None, "nar_size": None})

    def test_unknown_and_absent_account_are_distinct(self):
        with patch.object(collect.pwd, "getpwnam", side_effect=KeyError):
            self.assertEqual(collect.account("forgejo")["state"], "absent")
        with patch.object(collect.pwd, "getpwnam", side_effect=OSError):
            self.assertEqual(collect.account("forgejo")["state"], "unknown")


class BoundaryTests(unittest.TestCase):
    def test_no_free_argument_or_nonroot_launcher(self):
        with patch.object(sys, "argv", ["observe", "anything"]), patch.object(observe, "immutable_entry") as check:
            self.assertEqual(observe.main(), 65); check.assert_not_called()
        with patch.object(sys, "argv", ["observe"]), patch.object(observe.os, "getuid", return_value=1000), patch.object(observe, "immutable_entry") as check:
            self.assertEqual(observe.main(), 65); check.assert_not_called()

    def test_immutable_entry_refuses_workspace_code(self):
        with self.assertRaises(observe.Refused): observe.immutable_entry()

    def test_root_collector_is_confined_and_has_no_caller_target(self):
        command = observe.command(RUNTIME)
        props = [x.removeprefix("--property=") for x in command if x.startswith("--property=")]
        for required in ("User=root", "PrivateNetwork=yes", "ProtectSystem=strict", "ProtectHome=yes",
                         "CapabilityBoundingSet=CAP_SYS_PTRACE", "SystemCallFilter=@system-service", "RuntimeMaxSec=120s"):
            self.assertIn(required, props)
        mask = next(x for x in props if x.startswith("InaccessiblePaths="))
        for path in ("/var/lib", "/var/log", "/var/backups", "/run/credentials", "/run/postgresql"):
            self.assertIn(path, mask)
        self.assertEqual(command[-4:-1], ["/qualified/bin/python3", "-I", "-S"])
        self.assertTrue(command[-1].endswith("/collect.py"))


if __name__ == "__main__":
    unittest.main()
