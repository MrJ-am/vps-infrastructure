"""Synthetic fixed metadata and real local files; no VPS or production probe."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).parents[1] / "preflight-capacity-after-release-004-20261102.py"
spec = importlib.util.spec_from_file_location("capacity_probe", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PRIVATE = "PRIVATE_SYNTHETIC_IDENTITY_DO_NOT_EXPORT"


def unit_row(name):
    return {"Id": name, "LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
            "MainPID": "0", "ExecMainCode": "0", "ExecMainStatus": "0", "ControlGroup": "",
            "MemoryMax": "infinity", "MemoryHigh": "infinity", "MemorySwapMax": "infinity",
            "TasksMax": "512", "CPUWeight": "[not set]"}


class Capacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = m.contract()

    def setUp(self):
        self.units = {name: unit_row(name) for name in (m.CONTROLLER_UNIT, *m.UNITS)}
        self.units[m.CONTROLLER_UNIT].update(ActiveState="active", SubState="exited", ExecMainCode="1")
        self.phase = self.contract.Phase.OPEN
        self.result = {"schema_version": 1, "code": "CUTOVER_VERIFIED", "phase": self.phase.value}
        self.backend = SimpleNamespace(Phase=self.contract.Phase, private_directory=lambda *_: None,
            private_read=lambda *_: self.result, Checkpoint=lambda *_: SimpleNamespace(read=lambda: self.phase))

    def test_fixed_unit_projection_accepts_kernel_format_and_refuses_extra_units_fields(self):
        raw = "\n\n".join("\n".join(k + "=" + v for k, v in row.items()) for row in self.units.values())
        self.assertEqual(m.parse_units(raw), self.units)
        for malformed in (raw + "\nPrivate=" + PRIVATE, raw + "\n\n" + raw.split("\n\n")[0],
                          raw.replace(m.UNITS[0], "arbitrary.service", 1),
                          raw.replace("MainPID=0", "MainPID=" + PRIVATE, 1)):
            with self.assertRaises(m.Refused):
                m.parse_units(malformed)

    def test_success_gate_rejects_old_generation_phase_result_and_running_controller(self):
        with patch.object(m.os.path, "realpath", return_value=m.PROMOTED):
            m.successful_release(self.backend, self.units)
            with patch.object(m.os.path, "realpath", return_value="/invented/old"):
                with self.assertRaises(m.Refused):
                    m.successful_release(self.backend, self.units)
            self.phase = self.contract.Phase.RETURNED
            with self.assertRaises(m.Refused):
                m.successful_release(self.backend, self.units)
            self.phase = self.contract.Phase.OPEN
            self.result["schema_version"] = True
            with self.assertRaises(m.Refused):
                m.successful_release(self.backend, self.units)
            self.result["schema_version"] = 1
            self.units[m.CONTROLLER_UNIT]["MainPID"] = "100"
            with self.assertRaises(m.Refused):
                m.successful_release(self.backend, self.units)

    def test_failed_gate_precedes_identity_memory_disk_or_cgroup_read(self):
        with patch.object(m.os.path, "realpath", return_value="/invented/old"), \
             patch.object(m, "identities", side_effect=AssertionError("must not read")), \
             patch.object(m, "public_read", side_effect=AssertionError("must not read")):
            with self.assertRaises(m.Refused):
                m.observe(self.backend, self.units)

    def test_only_fixed_nss_queries_and_numeric_technical_ids_are_exported(self):
        seen = []
        def numeric(value):
            seen.append(value)
            if value % 2:
                raise KeyError()
            return SimpleNamespace(pw_name=PRIVATE, gr_name=PRIVATE)
        def account(name):
            self.assertIn(name, m.ACCOUNTS)
            return SimpleNamespace(pw_uid=950, pw_gid=951, pw_name=PRIVATE, pw_gecos=PRIVATE)
        def group(name):
            self.assertIn(name, m.GROUPS)
            return SimpleNamespace(gr_gid=951, gr_name=PRIVATE, gr_mem=[PRIVATE])
        with patch.object(m.pwd, "getpwuid", side_effect=numeric), patch.object(m.grp, "getgrgid", side_effect=numeric), \
             patch.object(m.pwd, "getpwnam", side_effect=account), patch.object(m.grp, "getgrnam", side_effect=group):
            value = m.identities()
        self.assertEqual(seen, [n for n in range(949, 960) for _ in range(2)])
        self.assertNotIn(PRIVATE, json.dumps(value))
        self.assertEqual(set(value["technical_accounts"]), set(m.ACCOUNTS))
        self.assertFalse(value["reserved_ids"]["950"]["uid_free"])

    def test_memory_projection_and_duplicate_units_bounds(self):
        raw = "MemTotal: 8000000 kB\nMemAvailable: 2000000 kB\nSwapTotal: 4000000 kB\nSwapFree: 3000000 kB\nIgnored: 5 kB"
        value = m.memory(raw)
        self.assertEqual(len(value), 4)
        self.assertEqual(value["MemAvailable_bytes"], 2048000000)
        for malformed in (raw + "\nMemTotal: 1 kB", raw.replace("2000000", "9000000"),
                          raw.replace("kB", "B", 1), raw.replace("MemAvailable", "Missing")):
            with self.assertRaises(m.Refused):
                m.memory(malformed)

    def test_numeric_sentinels_are_not_zero_or_unlimited_claims(self):
        self.assertIsNone(m.number("[not set]", unavailable=True))
        self.assertEqual(m.number("infinity", limit=True), "max")
        for value in ("-1", "true", PRIVATE, str(2**64), "1ms"):
            with self.assertRaises(m.Refused):
                m.number(value, limit=True, unavailable=True)
        with self.assertRaises(m.Refused):
            m.number("max")

    def test_absent_or_arbitrary_cgroup_path_is_never_followed(self):
        with patch.object(m, "public_read", side_effect=AssertionError("must not read")):
            self.assertEqual(m.cgroup(m.UNITS[0], {"ControlGroup": ""}), {"observed": False, "reason": "absent"})
            self.assertEqual(m.cgroup(m.UNITS[0], {"ControlGroup": "/private/" + PRIVATE}),
                             {"observed": False, "reason": "unexpected-location"})
        with self.assertRaises(m.Refused):
            m.cgroup("unknown.service", {"ControlGroup": ""})

    def test_real_cgroup_fixture_fields_are_projected_and_not_modified(self):
        with tempfile.TemporaryDirectory(dir=Path(".local").resolve()) as temporary:
            root = Path(temporary)
            unit = m.UNITS[0]
            folder = root / "system.slice" / unit
            folder.mkdir(parents=True)
            values = {name: "64\n" for name in m.CGROUP_FILES}
            values.update({"memory.max": "max\n", "pids.max": "256\n", "cpu.max": "25000 100000\n",
                "memory.events": "low 0\nhigh 2\nmax 3\noom 0\noom_kill 0\noom_group_kill 0\nsock_throttled 1\n",
                "cpu.stat": "usage_usec 5000\nuser_usec 3000\nsystem_usec 2000\nnr_throttled 2\ncore_sched.force_idle_usec 9\n"})
            for name, content in values.items():
                (folder / name).write_text(content)
            before = {name: ((folder/name).stat().st_ino, (folder/name).read_bytes()) for name in values}
            with patch.object(m, "CGROUP_ROOT", root):
                value = m.cgroup(unit, {"ControlGroup": "/system.slice/" + unit})
            self.assertTrue(value["observed"])
            self.assertEqual(value["counters_and_limits"]["cpu.max"], {"quota_usec": 25000, "period_usec": 100000})
            self.assertNotIn("sock_throttled", value["counters_and_limits"]["memory.events"])
            self.assertNotIn("core_sched.force_idle_usec", value["counters_and_limits"]["cpu.stat"])
            self.assertEqual(before, {name: ((folder/name).stat().st_ino, (folder/name).read_bytes()) for name in values})
            (folder / "cpu.stat").unlink()
            with patch.object(m, "CGROUP_ROOT", root):
                self.assertFalse(m.cgroup(unit, {"ControlGroup": "/system.slice/" + unit})["observed"])

    def test_cgroup_directory_symlink_is_refused(self):
        with tempfile.TemporaryDirectory(dir=Path(".local").resolve()) as temporary:
            root = Path(temporary);(root / "system.slice").mkdir()
            (root / "system.slice" / m.UNITS[0]).symlink_to(root)
            with patch.object(m, "CGROUP_ROOT", root), self.assertRaises(m.Refused):
                m.cgroup(m.UNITS[0], {"ControlGroup": "/system.slice/" + m.UNITS[0]})

    def test_custom_slice_paths_match_qualified_generation(self):
        self.assertEqual(set(m.CGROUP_PATHS), set(m.UNITS))
        base = Path(m.PROMOTED) / "etc/systemd/system"
        for unit in m.UNITS:
            lines = (base/unit).read_text().splitlines()
            slices = [line[6:] for line in lines if line.startswith("Slice=")]
            self.assertLessEqual(len(slices), 1)
            value = slices[0] if slices else "system.slice"
            parts = value[:-6].split("-")
            expected = "/" + "/".join("-".join(parts[:i]) + ".slice" for i in range(1, len(parts)+1)) + "/" + unit
            self.assertEqual(m.CGROUP_PATHS[unit], expected)
        for unit in ("mrjam-rust-blue.service", "mrjam-rust-green.service", "phpfpm-nextcloud.service"):
            with patch.object(m, "public_read", side_effect=AssertionError("must not read wrong slice")):
                self.assertEqual(m.cgroup(unit, {"ControlGroup": "/system.slice/" + unit}),
                                 {"observed": False, "reason": "unexpected-location"})

    def test_unknown_or_duplicate_stat_fields_never_enter_selected_output(self):
        self.assertEqual(m.selected_counters("usage_usec 5\nprivate 9", ("usage_usec",)), {"usage_usec": 5})
        for raw in ("usage_usec 5\nusage_usec 6", "usage_usec " + PRIVATE, "usage_usec -1"):
            with self.assertRaises(m.Refused):
                m.selected_counters(raw, ("usage_usec",))

    def test_arguments_are_refused_before_any_command_or_read(self):
        output = io.StringIO()
        with patch.object(m.sys, "argv", ["probe", "arbitrary"]), \
             patch.object(m, "contract", side_effect=AssertionError("must not read")), \
             patch.object(m, "show_units", side_effect=AssertionError("must not execute")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {"schema_version": 1, "code": "CI_CAPACITY_METADATA_REFUSED"})


if __name__ == "__main__":
    unittest.main()
