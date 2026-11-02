"""Invented rows, real PostgreSQL dumps/restore, SQLite WAL and age encryption."""
from datetime import datetime, timedelta, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("native", Path(__file__).with_name("native.py"))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = tempfile.TemporaryDirectory()
        cls.cluster_root = Path(cls.cluster.name)
        cls.socket = cls.cluster_root / "socket"
        cls.socket.mkdir()
        cls.data = cls.cluster_root / "postgresql"
        cls.environment = dict(os.environ, PGHOST=str(cls.socket), PGUSER="postgres")
        cls.commands = {name: shutil.which(binary) for name, binary in {
            "systemctl": "true", "runuser": "true", "pg_dump": "pg_dump", "pg_restore": "pg_restore",
            "age": "age", "age_keygen": "age-keygen", "tar": "tar"}.items()}
        cls.commands["systemctl"] = "synthetic-systemctl"
        cls.commands["runuser"] = "synthetic-runuser"
        cls.command(["initdb", "-D", str(cls.data), "-U", "postgres", "--no-locale", "--auth-local=trust"])
        cls.command(["pg_ctl", "-D", str(cls.data), "-l", str(cls.cluster_root / "postgresql.log"),
                     "-o", "-k " + str(cls.socket) + " -c listen_addresses=", "start"])
        for name in native.DATABASES:
            cls.command(["createdb", name])
            cls.command(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", name,
                         "-c", "CREATE TABLE fixture(value text); INSERT INTO fixture VALUES('invented-retained-row');"])

    @classmethod
    def tearDownClass(cls):
        cls.command(["pg_ctl", "-D", str(cls.data), "-m", "fast", "stop"])
        cls.cluster.cleanup()

    @classmethod
    def command(cls, arguments, output=None, data=None):
        result = subprocess.run(arguments, stdin=data or subprocess.DEVNULL,
                                stdout=output or subprocess.PIPE, stderr=subprocess.PIPE,
                                env=cls.environment, check=False, timeout=90)
        if result.returncode != 0:
            raise native.Refused("SYNTHETIC_COMMAND_FAILED")
        return result.stdout

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.state = self.base / "state"
        self.state.mkdir(mode=0o700)
        self.root = self.base / "backups"
        self.root.mkdir(mode=0o700)
        self.identity = {}
        self.connections = []
        for name, (relative, _, _) in native.SQLITES.items():
            path = self.state / relative
            path.parent.mkdir(parents=True)
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute("CREATE TABLE messages(value BLOB)")
            connection.execute("INSERT INTO messages VALUES(?)", (b"invented-opaque-MIME\r\n\x00",))
            connection.commit()
            path.chmod(0o600)
            self.connections.append(connection)
            self.identity[name] = (relative, os.getuid(), os.getgid())
        self.kanidm = self.base / "kanidm.json.gz"
        with gzip.open(self.kanidm, "wb") as stream:
            stream.write(b'{"synthetic_only":true}')
        self.kanidm.chmod(0o600)
        self.private_key = self.base / "invented-recipient-key"
        self.command(["age-keygen", "-o", str(self.private_key)])
        self.recipient = self.command(["age-keygen", "-y", str(self.private_key)]).decode().strip()
        self.inject = None
        self.called = []
        self.subject = native.NativeBackup(self.commands, self.state, self.root, self.kanidm,
            self.identity, os.getuid(), self.runner)

    def tearDown(self):
        for connection in self.connections:
            connection.close()
        self.temporary.cleanup()

    def runner(self, arguments, output=None, input_file=None):
        self.called.append(arguments[0])
        if arguments[0] == "synthetic-systemctl":
            self.assertEqual(arguments, ["synthetic-systemctl", "start", "mrjam-kanidm-backup.service"])
            if self.inject == "kanidm-unit":
                raise native.Refused("INVENTED_NATIVE_EXPORT_FAILURE")
            return
        if arguments[0] == "synthetic-runuser":
            self.assertEqual(arguments[1:4], ["-u", "postgres", "--"])
            arguments = [item for item in arguments[4:] if item != "--host=/run/postgresql"]
            if self.inject == "journal" and arguments[-1] == "vision_journal":
                raise native.Refused("INVENTED_JOURNAL_DUMP_FAILURE")
        self.command(arguments, output, input_file)
        if self.inject == "ciphertext" and arguments[0] == self.commands["age"] and "-d" not in arguments:
            output_path = Path(arguments[arguments.index("-o") + 1])
            if output_path.name == "components.tar.age":
                output_path.write_bytes(b"invented-corrupt-ciphertext")

    def published(self):
        return [path for path in self.root.iterdir() if native.STAMP.fullmatch(path.name)]

    def decrypt(self, output):
        key = self.base / "unwrapped-key"
        tar = self.base / "restored.tar"
        self.command(["age", "-d", "-i", str(self.private_key), "-o", str(key), str(output / "key.age")])
        self.command(["age", "-d", "-i", str(key), "-o", str(tar), str(output / "components.tar.age")])
        restored = self.base / "restored"
        restored.mkdir(mode=0o700)
        with tarfile.open(tar) as archive:
            self.assertEqual(archive.getnames(), list(native.FILES))
            archive.extractall(restored, filter="data")
        return restored

    def test_real_envelope_and_restoration_preserve_sql_rows_and_committed_wal(self):
        output = self.subject.publish(self.recipient)
        restored = self.decrypt(output)
        for name in native.SQLITES:
            with sqlite3.connect(restored / name) as connection:
                self.assertEqual(connection.execute("SELECT value FROM messages").fetchall(),
                                 [(b"invented-opaque-MIME\r\n\x00",)])
        for name in native.DATABASES:
            target = "restored_" + name
            self.command(["createdb", target])
            self.command(["pg_restore", "--exit-on-error", "--dbname=" + target, str(restored / (name + ".dump"))])
            result = self.command(["psql", "-XAt", "-d", target, "-c", "SELECT value FROM fixture"])
            self.assertEqual(result, b"invented-retained-row\n")
            self.command(["dropdb", target])
        self.assertEqual(gzip.decompress((restored / "kanidm.json.gz").read_bytes()), b'{"synthetic_only":true}')

    def test_publication_contains_only_ciphertext_and_non_atomic_manifest(self):
        output = self.subject.publish(self.recipient)
        self.assertEqual({path.name for path in output.iterdir()}, {"components.tar.age", "key.age", "manifest.json"})
        document = json.loads((output / "manifest.json").read_text())
        self.assertFalse(document["cross_component_atomic"])
        self.assertTrue(document["requires_current_erasure_journal"])
        self.assertNotIn(self.recipient, (output / "manifest.json").read_text())
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(any(path.name.startswith(".native-pending-") for path in self.root.iterdir()))

    def test_missing_native_export_never_publishes_partial_sql_set(self):
        self.inject = "kanidm-unit"
        with self.assertRaises(native.Refused):
            self.subject.publish(self.recipient)
        self.assertEqual(self.published(), [])

    def test_journal_dump_failure_never_publishes_partial_components(self):
        self.inject = "journal"
        with self.assertRaises(native.Refused):
            self.subject.publish(self.recipient)
        self.assertEqual(self.published(), [])

    def test_corrupt_encrypted_stream_is_not_published(self):
        self.inject = "ciphertext"
        with self.assertRaises(native.Refused):
            self.subject.publish(self.recipient)
        self.assertEqual(self.published(), [])

    def test_empty_or_invalid_native_export_refused(self):
        self.kanidm.write_bytes(b"not-a-gzip-stream")
        with self.assertRaises((OSError, native.Refused)):
            self.subject.publish(self.recipient)
        self.assertEqual(self.published(), [])

    def test_missing_sqlite_is_not_replaced_by_an_empty_image(self):
        (self.state / self.identity["archive.sqlite"][0]).unlink()
        with self.assertRaises(OSError):
            self.subject.publish(self.recipient)
        self.assertEqual(self.published(), [])

    def test_sqlite_permissions_and_symlinks_are_refused(self):
        path = self.state / self.identity["cycle.sqlite"][0]
        path.chmod(0o644)
        with self.assertRaises(native.Refused):
            native.sqlite_image(path, self.base / "permissive", os.getuid(), os.getgid())
        path.chmod(0o600)
        link = self.base / "link.sqlite"
        link.symlink_to(path)
        with self.assertRaises(OSError):
            native.sqlite_image(link, self.base / "linked", os.getuid(), os.getgid())

    def test_hardlinked_sqlite_refused(self):
        path = self.state / self.identity["cycle.sqlite"][0]
        os.link(path, self.base / "second-link")
        with self.assertRaises(native.Refused):
            native.sqlite_image(path, self.base / "hardlinked", os.getuid(), os.getgid())

    def test_invalid_recipient_refused_before_export(self):
        with self.assertRaises(native.Refused):
            self.subject.publish("invented-invalid-recipient")
        self.assertEqual(self.called, [])

    def test_retention_only_removes_verified_new_format_and_preserves_legacy(self):
        output = self.subject.publish(self.recipient)
        old_name = "20200101T000000Z-0123456789abcdef"
        old = self.root / old_name
        output.rename(old)
        manifest = old / "manifest.json"
        document = json.loads(manifest.read_text())
        document["created"] = old_name
        manifest.write_text(json.dumps(document))
        legacy = self.root / "vision-2020.age"
        legacy.write_bytes(b"invented-legacy-ciphertext")
        unknown = self.root / "20200102T000000Z-0123456789abcdef"
        unknown.mkdir()
        (unknown / "unexpected").write_text("invented")
        malformed = self.root / "20209999T999999Z-0123456789abcdef"
        malformed.mkdir()
        self.subject.prune(datetime.now(timezone.utc) - timedelta(days=30))
        self.assertFalse(old.exists())
        self.assertTrue(legacy.exists())
        self.assertTrue(unknown.exists())
        self.assertTrue(malformed.exists())

    def test_permissive_backup_directory_refused(self):
        self.root.chmod(0o750)
        with self.assertRaises(native.Refused):
            native.NativeBackup(self.commands, self.state, self.root, self.kanidm, self.identity, os.getuid())

    def test_retention_preserves_malformed_or_unrecognized_publications(self):
        output = self.subject.publish(self.recipient)
        old_name = "20200101T000000Z-abcdef0123456789"
        old = self.root / old_name
        output.rename(old)
        manifest = old / "manifest.json"
        document = json.loads(manifest.read_text())
        document["created"] = old_name
        for malformed in ([], dict(document, foreign_field=True)):
            manifest.write_text(json.dumps(malformed))
            self.subject.prune(datetime.now(timezone.utc) - timedelta(days=30))
            self.assertTrue(old.exists())
        manifest.write_text(json.dumps(document))
        (old / "components.tar.age").write_bytes(b"invented-damaged-ciphertext")
        self.subject.prune(datetime.now(timezone.utc) - timedelta(days=30))
        self.assertTrue(old.exists())

    def test_cli_has_no_caller_selected_paths_or_diagnostics(self):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("native.py")), "invented-argument"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b'{"error":"NATIVE_BACKUP_REFUSED"}\n')


if __name__ == "__main__":
    unittest.main()
