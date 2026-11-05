import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import deploy as D
import migrations as M
import system_delivery as S


class SystemDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.old = self.root / "old.conf"
        self.old.write_text("proxy_pass http://127.0.0.1:38102;")
        self.configuration = self.root / "nginx-current.conf"
        self.configuration.symlink_to(self.old)
        for obj, key, value in [(D, "STATE", self.state), (D, "NGINX_CONF", self.configuration),
                                (S, "PRIMARY", self.root / "primary.conf")]:
            item = patch.object(obj, key, value)
            item.start()
            self.addCleanup(item.stop)
        self.previous = {"revision": "b" * 40, "slot": "green", "previous_slot": "blue"}
        D.atomic_json(self.state / "current.json", self.previous)
        self.executable = "/nix/store/" + "a" * 32 + "-server/bin/mrjam-server serve --config /nix/store/" + "a" * 32 + "-runtime/runtime.json"

    def test_failed_third_candidate_restores_the_previous_fallback_contents(self):
        slots = {"blue": "A", "green": "B"}
        def failing_prepare(build):
            slots["blue"] = "C"
            raise RuntimeError("candidate rejected")
        def restore(slot, executable):
            self.assertEqual(executable, self.executable)
            slots[slot] = "A"
        with patch.object(D, "slot_command", return_value=self.executable), \
                patch.object(S, "retain"), patch.object(D, "promote_server", side_effect=failing_prepare), \
                patch.object(D, "configure_slot", side_effect=restore), patch.object(D, "command"):
            with self.assertRaises(RuntimeError):
                D.promote({"revision": "c" * 40})
        self.assertEqual(slots, {"blue": "A", "green": "B"})
        self.assertEqual(json.loads((self.state / "current.json").read_text()), self.previous)
        self.assertFalse((self.state / "preparation.json").exists())

    def test_interrupted_preparation_is_restored_without_starting_services_at_boot(self):
        D.atomic_json(self.state / "preparation.json", {"revision": "c" * 40,
                      "slot": "blue", "command": self.executable})
        with patch.object(D, "configure_slot") as configure, patch.object(D, "command") as command:
            D.recover(reload=False)
        configure.assert_called_once_with("blue", self.executable)
        command.assert_not_called()

    def test_later_rollback_restores_the_displaced_slot_as_well_as_the_route(self):
        candidate = self.root / "candidate.conf"
        candidate.write_text("proxy_pass http://127.0.0.1:38101;")
        D.symlink(candidate, self.configuration)
        transaction = {"revision": "c" * 40, "old_configuration": str(self.old),
                       "old_state": self.previous,
                       "replaced_slot": {"slot": "blue", "command": self.executable}}
        with patch.object(D, "reload_nginx"), patch.object(D, "configure_slot") as configure, patch.object(D, "command"):
            D.rollback(transaction)
        configure.assert_called_once_with("blue", self.executable)
        self.assertEqual(self.configuration.resolve(), self.old)
        self.assertEqual(json.loads((self.state / "current.json").read_text()), self.previous)

    def test_system_rollback_routes_before_restoring_the_generation(self):
        candidate = self.root / "candidate.conf"
        candidate.write_text("proxy_pass http://127.0.0.1:38101;")
        D.symlink(candidate, self.configuration)
        order = []
        def restore(*args, **kwargs):
            self.assertEqual(self.configuration.resolve(), self.old)
            order.append("system")
        transaction = {"format": 2, "revision": "c" * 40,
                       "old_configuration": str(self.old), "old_state": self.previous}
        D.atomic_json(self.state / "transaction.json", transaction)
        with patch.object(D, "reload_nginx", side_effect=lambda: order.append("route")), \
                patch.object(D, "command"), \
                patch.object(S, "restore_system", side_effect=restore):
            D.rollback(transaction)
        self.assertEqual(order, ["route", "system", "route"])
        self.assertFalse((self.state / "transaction.json").exists())
        self.assertEqual(json.loads((self.state / "current.json").read_text()), self.previous)

    def test_boot_recovery_selects_the_old_generation_without_starting_applications(self):
        transaction = {"format": 2, "revision": "c" * 40, "old_system": "/old-system",
                       "old_configuration": str(self.old), "old_state": self.previous}
        D.atomic_json(self.state / "transaction.json", transaction)
        with patch.object(S, "current_system", return_value="/new-system"), \
                patch.object(S, "restore_system") as restore, patch.object(D, "command") as command:
            with self.assertRaises(RuntimeError):
                S.rollback(transaction, reload=False)
        restore.assert_called_once_with(transaction, restart=False)
        command.assert_called_once_with(["systemctl", "reboot", "--no-block"])
        self.assertTrue((self.state / "transaction.json").exists())
        self.assertEqual(self.configuration.resolve(), self.old)

    def test_failure_after_incompatible_writes_preserves_data_and_never_restores_old_system(self):
        transaction = {"revision": "c" * 40, "compatible": False, "writes_resumed": True}
        with patch.object(S, "park") as park, patch.object(S, "restore_system") as restore, \
                patch.object(M, "recover") as recover:
            with self.assertRaises(RuntimeError):
                S.rollback(transaction)
        park.assert_called_once_with(transaction, "writes-may-have-resumed")
        restore.assert_not_called()
        recover.assert_not_called()

    def test_changed_schema_requires_its_own_migration_scope(self):
        D.atomic_json(self.state / "baseline.json", {"schema_digest": "a", "schema_digests": {"server": "a", "vise": "v"}})
        build = {"schema_digests": {"server": "b", "vise": "v"}}
        with self.assertRaises(RuntimeError):
            S.validate_transition(build, {"stateful_versions": {}}, {"steps": [{"scope": "vise"}]}, None)
        S.validate_transition(build, {"stateful_versions": {}}, {"steps": [{"scope": "server"}]}, None)

    def test_postgresql_major_upgrade_requires_a_migration_but_minor_does_not(self):
        D.atomic_json(self.state / "baseline.json", {"schema_digest": "a", "stateful_versions": {"postgresql": "17.11"}})
        build = {"schema_digests": {"server": "a"}}
        S.validate_transition(build, {"stateful_versions": {"postgresql": "17.12"}}, {"steps": []}, None)
        with self.assertRaises(RuntimeError):
            S.validate_transition(build, {"stateful_versions": {"postgresql": "18.0"}}, {"steps": []}, None)

    def test_template_moves_only_shared_server_and_exact_revision_marker(self):
        revision = "a" * 40
        text = 'proxy_pass http://127.0.0.1:38101;\nproxy_pass http://127.0.0.1:3017;\nadd_header X-Mrjam-Deployment "' + revision + ':blue" always;'
        result = S.template(text, "green", revision)
        self.assertIn("127.0.0.1:38102", result)
        self.assertIn("127.0.0.1:3017", result)
        self.assertIn(revision + ":green", result)

    def test_boot_wrapper_references_durable_routing_instead_of_a_generation(self):
        S.ensure_gateway_entry()
        self.assertEqual(S.PRIMARY.read_text(), "include " + str(self.configuration) + ";\n")
        self.assertEqual(self.configuration.resolve(), self.old)

    def test_unsafe_artifact_path_is_rejected(self):
        for path in ["/tmp/release", "/nix/store/../../etc", "/nix/store/" + "a" * 32 + "-x/bin"]:
            with self.assertRaises(ValueError):
                S.store_path(path)


class MigrationPlanTests(unittest.TestCase):
    def test_destructive_migration_needs_exact_release_and_recovery_authorization(self):
        plan = {"steps": [{"id": "remove_old", "destructive": True}]}
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError):
                M.authorize(plan, "a" * 40, root)
            Path(root, "a" * 40 + ".json").write_text(json.dumps({"revision": "a" * 40,
                 "migrations": ["remove_old"], "recovery_tested": True}))
            M.authorize(plan, "a" * 40, root)
            with self.assertRaises(RuntimeError):
                M.authorize(plan, "b" * 40, root)

    def test_migration_cannot_read_a_file_outside_its_release(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root, "plan")
            directory.mkdir()
            Path(root, "outside.sql").write_text("SELECT 1;")
            with self.assertRaises(ValueError):
                M.source_file(directory, "../outside.sql")

    def test_incompatible_sql_requires_a_program_with_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "plan.json")
            path.write_text(json.dumps({"version": 1, "steps": [{"id": "change", "driver": "sql",
                               "database": "invented", "compatibility": "maintenance"}]}))
            with self.assertRaises(ValueError):
                M.load(path)


@unittest.skipUnless(os.environ.get("MRJAM_SYNTHETIC_DATABASE_URL") and shutil.which("psql"),
                     "Run inside the disposable PostgreSQL release fixture")
class RealPostgresqlMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.psql = shutil.which("psql")
        self.url = os.environ["MRJAM_SYNTHETIC_DATABASE_URL"]
        self.step = {"id": "synthetic_change", "driver": "sql", "database": "synthetic",
                     "compatibility": "both", "sql": "change.sql", "checks": "checks.sql", "fixture": "fixture.sql"}
        self.execute("DROP SCHEMA IF EXISTS mrjam_delivery CASCADE; DROP TABLE IF EXISTS synthetic_delivery_records; CREATE TABLE synthetic_delivery_records(id integer PRIMARY KEY);")
        (self.root / "change.sql").write_text("INSERT INTO synthetic_delivery_records VALUES (1);")
        (self.root / "checks.sql").write_text("DO $$ BEGIN IF (SELECT count(*) FROM synthetic_delivery_records) <> 1 THEN RAISE EXCEPTION 'Synthetic row count mismatch'; END IF; END $$;")

    def execute(self, text):
        M.psql("synthetic", text, self.psql, test_url=self.url)

    def apply(self):
        self.execute(M.sql_transaction(self.step, self.root))

    def test_replay_is_recorded_once_and_does_not_repeat_the_data_change(self):
        self.apply()
        self.apply()
        self.execute("DO $$ BEGIN IF (SELECT count(*) FROM synthetic_delivery_records) <> 1 OR (SELECT count(*) FROM mrjam_delivery.migrations) <> 1 THEN RAISE EXCEPTION 'Replay changed synthetic data'; END IF; END $$;")

    def test_failed_check_rolls_back_both_data_and_migration_ledger(self):
        (self.root / "checks.sql").write_text("SELECT 1/0;")
        with self.assertRaises(subprocess.CalledProcessError):
            self.apply()
        self.execute("DO $$ BEGIN IF (SELECT count(*) FROM synthetic_delivery_records) <> 0 OR to_regnamespace('mrjam_delivery') IS NOT NULL THEN RAISE EXCEPTION 'Partial migration persisted'; END IF; END $$;")

    def test_an_applied_script_cannot_be_rewritten_and_reexecuted(self):
        self.apply()
        (self.root / "change.sql").write_text("INSERT INTO synthetic_delivery_records VALUES (2);")
        with self.assertRaises(subprocess.CalledProcessError):
            self.apply()
        self.execute("DO $$ BEGIN IF (SELECT count(*) FROM synthetic_delivery_records) <> 1 THEN RAISE EXCEPTION 'Changed migration ran'; END IF; END $$;")

    def test_two_executors_serialize_the_same_migration(self):
        (self.root / "change.sql").write_text("SELECT pg_sleep(0.2); INSERT INTO synthetic_delivery_records VALUES (1);")
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(self.apply) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
        self.execute("DO $$ BEGIN IF (SELECT count(*) FROM synthetic_delivery_records) <> 1 THEN RAISE EXCEPTION 'Concurrent migration ran twice'; END IF; END $$;")


@unittest.skipUnless(os.environ.get("MRJAM_TEST_MIGRATION_PROGRAM"), "Run with the Nix migration-program fixture")
class RealMigrationProgramTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".synthetic").touch()
        self.path = self.root / "plan.json"
        self.step = {"id": "synthetic_vendor", "driver": "program", "scope": "server",
                     "package": os.environ["MRJAM_TEST_MIGRATION_PROGRAM"], "compatibility": "maintenance"}
        self.write_plan()
        for item in [patch.object(M, "LEDGER", self.root / "ledger.json"),
                     patch.dict(os.environ, MRJAM_MIGRATION_FIXTURE=str(self.root))]:
            item.start()
            self.addCleanup(item.stop)

    def write_plan(self):
        self.path.write_text(json.dumps({"version": 1, "steps": [self.step]}))

    def apply(self, revision="a" * 40):
        return M.apply(self.path, "/unused/psql", revision, self.root)

    def calls(self):
        return (self.root / "calls").read_text().splitlines()

    def test_completed_migration_does_not_pause_every_subsequent_delivery(self):
        self.step["hold_units"] = ["postgresql"]
        self.write_plan()
        self.assertEqual(S.migration_holds(M.load(self.path), self.root), ["postgresql"])
        self.apply()
        self.assertTrue((self.root / "paused").exists())
        M.resume(self.path)
        self.apply(revision="b" * 40)
        M.resume(self.path)
        self.assertEqual(self.calls(), ["quiesce", "apply", "verify", "resume"])
        self.assertTrue(M.compatible(M.load(self.path), root=self.root))
        self.assertEqual(S.migration_holds(M.load(self.path), self.root), [])

    def test_after_system_program_waits_for_the_new_system_but_quiesces_before_it(self):
        self.step["phase"] = "after-system"
        self.write_plan()
        M.prepare(self.path, "a" * 40, self.root)
        M.apply(self.path, "/unused/psql", "a" * 40, self.root, phase="before-system")
        self.assertEqual(self.calls(), ["quiesce"])
        M.apply(self.path, "/unused/psql", "a" * 40, self.root, phase="after-system")
        M.resume(self.path)
        self.assertEqual(self.calls(), ["quiesce", "apply", "verify", "resume"])

    def test_failure_before_reopening_writes_runs_recovery(self):
        (self.root / "fail_verify").touch()
        with self.assertRaises(subprocess.CalledProcessError):
            self.apply()
        self.assertTrue((self.root / "paused").exists())
        M.recover(self.path)
        self.assertFalse((self.root / "changed").exists())
        self.assertFalse((self.root / "paused").exists())
        self.assertEqual(M.receipt(self.step, self.root)["phase"], "recovered")

    def test_changed_completed_program_is_rejected_before_any_action(self):
        self.apply()
        M.resume(self.path)
        before = self.calls()
        self.step["scope"] = "other"
        self.write_plan()
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(self.calls(), before)

    def test_destructive_authorization_is_not_required_again_for_completed_history(self):
        self.step["destructive"] = True
        self.write_plan()
        with self.assertRaises(RuntimeError):
            self.apply()
        (self.root / ("a" * 40 + ".json")).write_text(json.dumps({"revision": "a" * 40,
             "migrations": [self.step["id"]], "recovery_tested": True}))
        self.apply()
        M.resume(self.path)
        self.apply(revision="b" * 40)
        self.assertEqual(self.calls(), ["quiesce", "apply", "verify", "resume"])


if __name__ == "__main__":
    unittest.main()
