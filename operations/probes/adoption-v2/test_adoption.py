"""Synthetic account/filesystem fixtures only: never observe the host."""
import contextlib
import errno
import importlib.util
import io
import json
from pathlib import Path
import stat
import time
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("adoption_probe", HERE / "adoption_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
STORE_A = "/nix/store/" + "1" * 32 + "-synthetic-system-private-name"
STORE_B = "/nix/store/" + "2" * 32 + "-synthetic-other-system"


def user(**changes):
    return SimpleNamespace(**dict({"pw_uid": 601, "pw_gid": 602,
                                  "pw_dir": probe.ROOT + "/home", "pw_shell": probe.ROOT + "/login"}, **changes))


def metadata(mode=stat.S_IFDIR | 0o755, uid=0, gid=0, inode=71):
    return SimpleNamespace(st_mode=mode, st_uid=uid, st_gid=gid, st_ino=inode,
                           st_dev=10, st_mtime_ns=100, st_ctime_ns=100)


def account():
    with patch.object(probe.pwd, "getpwnam", return_value=user()), \
            patch.object(probe.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=602)), \
            patch.object(probe.os, "getgrouplist", return_value=[602]):
        return probe.observe_account()


def report():
    subject = account()
    def fixture(path):
        if path == probe.ROOT + "/work":
            return metadata(stat.S_IFDIR | 0o700, 601, 602)
        for value, directory, mode, _owned in probe.PATHS.values():
            if path == value:
                return metadata((stat.S_IFDIR if directory else stat.S_IFREG) | mode)
        raise AssertionError("Non-fixed path requested")
    with patch.object(probe, "safe_lstat", side_effect=fixture):
        paths = probe.observe_paths(subject)
    with patch.object(probe, "safe_readlink", side_effect=lambda path: {
            "/run/current-system": STORE_A,
            "/nix/var/nix/profiles/system": "system-18-link",
            "/nix/var/nix/profiles/system-18-link": STORE_A,
    }[path]):
        generation = probe.observe_generation()
    return {"schema_version": 1, "operation": "mrjam-inventory-adoption-v2",
            "authority": "unverified_observation", "account": subject,
            "paths": paths, "generation": generation}


class AccountTest(unittest.TestCase):
    def test_one_account_and_no_extra_groups(self):
        self.assertEqual(account(), {"state": "observed", "code": "OK", "uid": 601, "gid": 602,
                         "home_matches": True, "shell_matches": True, "group_matches": True,
                         "supplementary_groups_absent": True})

    def test_extra_group_and_unexpected_home_are_only_booleans(self):
        with patch.object(probe.pwd, "getpwnam", return_value=user(pw_dir="SYNTHETIC_PERSONAL_MARKER")), \
                patch.object(probe.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=602)), \
                patch.object(probe.os, "getgrouplist", return_value=[602, 603]):
            result = probe.observe_account()
        self.assertFalse(result["home_matches"])
        self.assertFalse(result["supplementary_groups_absent"])
        self.assertNotIn("SYNTHETIC_PERSONAL_MARKER", json.dumps(result))

    def test_absence_and_error_differ(self):
        for error, state, code in [(KeyError(), "absent", "NOT_FOUND"),
                                    (OSError("SYNTHETIC_SECRET"), "unknown", "UNAVAILABLE")]:
            with self.subTest(error=type(error)), patch.object(probe.pwd, "getpwnam", side_effect=error):
                result = probe.observe_account()
                self.assertEqual((result["state"], result["code"]), (state, code))
                self.assertIsNone(result["uid"])
                self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_root_boolean_and_out_of_range_identity_are_unknown(self):
        for uid in [0, -1, True, 2**31, "601"]:
            with self.subTest(uid=uid), patch.object(probe.pwd, "getpwnam", return_value=user(pw_uid=uid)):
                result = probe.observe_account()
                self.assertEqual(result["code"], "INVALID_OUTPUT")
                self.assertIsNone(result["uid"])

    def test_group_list_failures_do_not_claim_no_extra_group(self):
        for groups in [[], [True], [0], [602] * 257, [602, "SECRET"]]:
            with self.subTest(groups=type(groups)), \
                    patch.object(probe.pwd, "getpwnam", return_value=user()), \
                    patch.object(probe.grp, "getgrnam", side_effect=KeyError()), \
                    patch.object(probe.os, "getgrouplist", return_value=groups):
                result = probe.observe_account()
                self.assertFalse(result["group_matches"])
                self.assertIsNone(result["supplementary_groups_absent"])


class FilesystemTest(unittest.TestCase):
    def test_fixed_metadata_never_opens_target_content(self):
        with patch.object(probe, "_parent_fd", return_value=30) as parent, \
                patch.object(probe.os, "stat", return_value=metadata()) as lookup, \
                patch.object(probe.os, "close") as close:
            probe.safe_lstat(probe.ROOT + "/home/.ssh/authorized_keys")
        parent.assert_called_once_with(probe.ROOT + "/home/.ssh/authorized_keys")
        lookup.assert_called_once_with("authorized_keys", dir_fd=30, follow_symlinks=False)
        close.assert_called_once_with(30)

    def test_parent_open_always_nofollow_and_root_owned(self):
        with patch.object(probe.os, "open", side_effect=[10, 11, 12]) as opened, \
                patch.object(probe.os, "fstat", return_value=metadata()), \
                patch.object(probe.os, "close") as closed:
            descriptor = probe._parent_fd("/var/lib/synthetic")
        self.assertEqual(descriptor, 12)
        for args in opened.call_args_list:
            self.assertTrue(args.args[1] & probe.os.O_NOFOLLOW)
            self.assertTrue(args.args[1] & probe.os.O_DIRECTORY)
        self.assertEqual([item.args[0] for item in opened.call_args_list], ["/", "var", "lib"])
        self.assertEqual(closed.call_args_list, [call(10), call(11)])

    def test_writable_or_nonroot_parent_stops_traversal(self):
        for unsafe in [metadata(stat.S_IFDIR | 0o777), metadata(uid=601), metadata(gid=602)]:
            with self.subTest(unsafe=unsafe), patch.object(probe.os, "open", return_value=10) as opened, \
                    patch.object(probe.os, "fstat", return_value=unsafe), patch.object(probe.os, "close"):
                with self.assertRaises(probe.Unavailable) as caught:
                    probe._parent_fd("/var/lib/synthetic")
                self.assertEqual(caught.exception.code, "PARENT_UNSAFE")
                opened.assert_called_once()

    def test_symlink_parent_errors_closed(self):
        for err in [errno.ELOOP, errno.ENOTDIR]:
            with patch.object(probe.os, "open", side_effect=OSError(err, "PRIVATE_MARKER")):
                with self.assertRaises(probe.Unavailable) as caught:
                    probe._parent_fd("/var/lib/synthetic")
                self.assertEqual(caught.exception.code, "PARENT_UNSAFE")

    def test_target_symlink_does_not_count_as_regular_file(self):
        with patch.object(probe, "safe_lstat", return_value=metadata(stat.S_IFLNK | 0o777)):
            result = probe.observe_paths(account())
        self.assertFalse(result["runner"]["type_matches"])
        self.assertFalse(result["authorized_keys"]["mode_matches"])

    def test_missing_and_unreadable_metadata_are_distinct(self):
        for code, state in [("NOT_FOUND", "absent"), ("UNAVAILABLE", "unknown"), ("PARENT_UNSAFE", "unknown")]:
            with self.subTest(code=code), patch.object(probe, "safe_lstat", side_effect=probe.Unavailable(code)):
                result = probe.observe_paths(account())
            self.assertTrue(all(item["state"] == state for item in result.values()))
            self.assertTrue(all(item["owner_matches"] is None for item in result.values()))

    def test_missing_account_does_not_assign_work_to_root(self):
        with patch.object(probe.pwd, "getpwnam", side_effect=KeyError()):
            subject = probe.observe_account()
        with patch.object(probe, "safe_lstat", return_value=metadata()):
            result = probe.observe_paths(subject)
        self.assertIsNone(result["work"]["owner_matches"])
        self.assertTrue(result["base"]["owner_matches"])

    def test_link_change_or_nonroot_owner_refuses_target(self):
        initial = metadata(stat.S_IFLNK | 0o777)
        for sequence, code in [([initial, metadata(stat.S_IFLNK | 0o777, inode=72)], "CHANGED"),
                               ([metadata(stat.S_IFLNK | 0o777, uid=601)], "INVALID_OUTPUT")]:
            with self.subTest(code=code), patch.object(probe, "_parent_fd", return_value=10), \
                    patch.object(probe.os, "stat", side_effect=sequence), \
                    patch.object(probe.os, "readlink", return_value=STORE_A), patch.object(probe.os, "close"):
                with self.assertRaises(probe.Unavailable) as caught:
                    probe.safe_readlink("/run/current-system")
                self.assertEqual(caught.exception.code, code)


class GenerationTest(unittest.TestCase):
    def test_generation_emits_only_number_and_store_hash(self):
        result = report()["generation"]
        self.assertEqual(result["profile"]["number"], 18)
        self.assertTrue(result["profile"]["matches_current"])
        self.assertNotIn("private-name", json.dumps(result))
        self.assertNotIn("/nix/store/", json.dumps(result))

    def test_arbitrary_link_target_is_never_followed(self):
        with patch.object(probe, "safe_readlink", return_value="/home/SYNTHETIC_SECRET") as lookup:
            result = probe.observe_generation()
        self.assertEqual(lookup.call_args_list, [call("/run/current-system"), call("/nix/var/nix/profiles/system")])
        self.assertEqual(result["profile"]["code"], "INVALID_OUTPUT")
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))

    def test_profile_number_bounds_and_normalization(self):
        for target in ["system-0-link", "system-01-link", "system-2147483648-link", "../../etc/shadow", "system-9-link\n"]:
            with self.subTest(target=target), patch.object(probe, "safe_readlink", side_effect=[STORE_A, target]) as lookup:
                result = probe.observe_generation()
                self.assertEqual(result["profile"]["code"], "INVALID_OUTPUT")
                self.assertEqual(lookup.call_count, 2)

    def test_current_and_selected_profile_are_not_assumed_equal(self):
        with patch.object(probe, "safe_readlink", side_effect=[STORE_A, "system-18-link", STORE_B, "system-18-link"]):
            result = probe.observe_generation()
        self.assertFalse(result["profile"]["matches_current"])

    def test_profile_change_is_unknown(self):
        with patch.object(probe, "safe_readlink", side_effect=[STORE_A, "system-18-link", STORE_A, "system-19-link"]):
            result = probe.observe_generation()
        self.assertEqual(result["profile"]["code"], "CHANGED")
        self.assertIsNone(result["profile"]["number"])


class BoundaryTest(unittest.TestCase):
    def run_main(self, argv, uid=1000, euid=1000, effect=None):
        output = io.StringIO()
        with patch.object(probe.sys, "argv", argv), patch.object(probe.os, "getuid", return_value=uid), \
                patch.object(probe.os, "geteuid", return_value=euid), patch.object(probe, "constrain") as limits, \
                patch.object(probe.signal, "setitimer"), patch.object(probe, "bounded_collect", side_effect=effect) as collect, \
                contextlib.redirect_stdout(output):
            result = probe.main()
        return result, json.loads(output.getvalue()), collect, limits

    def test_args_and_privilege_refused_before_observation(self):
        for argv, uid, euid, code in [(["probe", "--shell"], 1000, 1000, "UNSUPPORTED_ARGUMENTS"),
                                       (["probe"], 0, 0, "PRIVILEGED_EXECUTION"),
                                       (["probe"], 1000, 0, "PRIVILEGED_EXECUTION")]:
            with self.subTest(code=code):
                rc, output, collect, limits = self.run_main(argv, uid, euid)
                self.assertEqual((rc, output), (64, {"status": "refused", "code": code}))
                collect.assert_not_called()
                limits.assert_not_called()

    def test_errors_and_deadline_disclose_no_text(self):
        for error, code, rc in [(RuntimeError("SYNTHETIC_SECRET"), "OBSERVATION_FAILED", 70),
                                 (probe.Deadline(), "DEADLINE_EXCEEDED", 75)]:
            result, output, _collect, _limits = self.run_main(["probe"], effect=error)
            self.assertEqual((result, output), (rc, {"status": "refused", "code": code}))

    def test_limit_never_raises_preexisting_system_limit(self):
        with patch.object(probe.resource, "getrlimit", return_value=(32, 48)), \
                patch.object(probe.resource, "setrlimit") as update:
            probe._cap(probe.resource.RLIMIT_NOFILE, 64)
        update.assert_called_once_with(probe.resource.RLIMIT_NOFILE, (32, 32))

    def test_supervisor_returns_only_complete_synthetic_child_result(self):
        with patch.object(probe, "collect", return_value={"synthetic": True}):
            self.assertEqual(json.loads(probe.bounded_collect()), {"synthetic": True})

    def test_supervisor_kills_and_reaps_blocked_child(self):
        started = time.monotonic()
        with patch.object(probe, "MAX_SECONDS", 0.15), patch.object(probe, "collect", side_effect=lambda: time.sleep(20)):
            with self.assertRaises(probe.Deadline):
                probe.bounded_collect()
        self.assertLess(time.monotonic() - started, 1.0)
        with self.assertRaises(ChildProcessError):
            probe.os.waitpid(-1, probe.os.WNOHANG)

    def test_supervisor_refuses_failed_or_oversized_child(self):
        with patch.object(probe, "collect", side_effect=RuntimeError("PRIVATE_SYNTHETIC_MARKER")):
            with self.assertRaises(RuntimeError) as failure:
                probe.bounded_collect()
            self.assertNotIn("PRIVATE_SYNTHETIC_MARKER", str(failure.exception))
        with patch.object(probe, "collect", return_value={"oversized": "x" * probe.MAX_OUTPUT}):
            with self.assertRaises(probe.OutputLimit):
                probe.bounded_collect()


if __name__ == "__main__":
    unittest.main()
