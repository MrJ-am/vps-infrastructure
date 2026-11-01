import copy
import importlib.util
import json
import socket
import struct
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

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
    def broker_reply(self, raw, flags=0, sent=4):
        channel = MagicMock()
        channel.__enter__.return_value = channel
        channel.send.return_value = sent
        channel.recvmsg.return_value = (raw, [], flags, None)
        with patch.object(collect.os, "dup", return_value=42) as dup, patch.object(collect.socket, "socket", return_value=channel) as opened:
            result = collect.executable_link(731)
        dup.assert_called_once_with(3)
        opened.assert_called_once_with(fileno=42)
        channel.send.assert_called_once_with(struct.pack("=I", 731))
        channel.settimeout.assert_called_once_with(5)
        return result

    def test_private_broker_selects_only_exe_bytes(self):
        data = EXE.encode()
        self.assertEqual(self.broker_reply(struct.pack("=II", 0, len(data)) + data + bytes(4096-len(data))), EXE)

    def test_private_broker_malformed_error_or_truncated_reply_is_refused(self):
        for code, length in ((1, 0), (0, 0), (0, 4096), (2, 4)):
            with self.assertRaises(collect.Refused):
                self.broker_reply(struct.pack("=II", code, length) + bytes(4096))
        data = struct.pack("=II", 0, 1) + b"a" + bytes(4095)
        for raw, flags, sent in ((data[:-1],0,4),(data,socket.MSG_TRUNC,4),(data,0,3),(data[:-1]+b"x",0,4)):
            with self.assertRaises(collect.Refused): self.broker_reply(raw, flags, sent)

    def test_private_broker_non_ascii_reply_is_refused(self):
        with self.assertRaises(UnicodeError):
            self.broker_reply(struct.pack("=II", 0, 1) + b"\xff" + bytes(4095))

    def test_only_selected_systemd_properties_are_requested(self):
        with patch.object(collect, "run", return_value=b"LoadState=loaded\nActiveState=active\nMainPID=731\n") as call:
            self.assertEqual(collect.status(RUNTIME, "forgejo"), ("active", 731))
        self.assertEqual(call.call_args.args[0], ["/qualified/bin/systemctl", "--system", "show",
            "--property=LoadState,ActiveState,MainPID", "forgejo.service"])
        self.assertEqual(call.call_args.kwargs["limit"], 256)

    def test_no_executable_read_for_inactive_or_absent_unit(self):
        for status in (("inactive", 0), ("failed", 0), ("absent", None), ("unknown", None)):
            with patch.object(collect, "status", return_value=status), patch.object(collect, "executable_link") as read:
                result = collect.service(RUNTIME, "forgejo")
                self.assertEqual(result["state"], status[0]); self.assertIsNone(result["executable"])
                read.assert_not_called()

    def test_executable_denial_is_unknown_build_not_absent_software(self):
        with patch.object(collect, "status", return_value=("active",731)), patch.object(collect, "executable_link", side_effect=PermissionError):
            result = collect.service(RUNTIME, "forgejo")
        self.assertEqual(result["state"], "active"); self.assertIsNone(result["executable"])

    def test_restart_or_exec_race_does_not_bind_wrong_build(self):
        with patch.object(collect, "status", side_effect=[("active",731),("active",732)]), patch.object(collect, "executable_link", return_value=EXE):
            self.assertIsNone(collect.service(RUNTIME, "forgejo")["store_path"])
        with patch.object(collect, "status", return_value=("active",731)), patch.object(collect, "executable_link", side_effect=[EXE, STORE + "/bin/other"]):
            self.assertIsNone(collect.service(RUNTIME, "forgejo")["store_path"])

    def test_nonstore_path_and_deleted_executable_never_escape(self):
        for value in ("/var/lib/private/secret", EXE + " (deleted)", STORE + "/../secret"):
            with patch.object(collect, "status", return_value=("active",731)), patch.object(collect, "executable_link", return_value=value):
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
                         "CapabilityBoundingSet=CAP_SYS_PTRACE", "SystemCallFilter=@system-service", "SystemCallErrorNumber=EPERM", "RuntimeMaxSec=120s"):
            self.assertIn(required, props)
        mask = next(x for x in props if x.startswith("InaccessiblePaths="))
        for path in ("/var/lib", "/var/log", "/var/backups", "/run/credentials", "/run/postgresql"):
            self.assertIn(path, mask)
        self.assertTrue(command[-1].endswith("/collect-confined"))
        self.assertEqual(command[-2], "--")
        deny = next(p for p in props if p.startswith("SystemCallFilter=~"))
        self.assertEqual(set(deny.removeprefix("SystemCallFilter=~").split()), {"ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd", "process_madvise", "process_mrelease", "kcmp", "get_robust_list", "io_uring_setup", "io_uring_enter", "io_uring_register"})


if __name__ == "__main__":
    unittest.main()
