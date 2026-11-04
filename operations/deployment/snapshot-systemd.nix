# Independent synthetic qualification: real PostgreSQL 17, systemd and tar.
# This VM never receives a production path, credential, archive or generation.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  fixture = pkgs.writeText "snapshot-systemd-fixture.py" ''
    import hashlib
    import json
    import os
    from pathlib import Path
    import pwd
    import shutil
    import sqlite3
    import stat
    import subprocess
    import sys

    sys.path.insert(0, "/etc/snapshot-qualification")
    from cutover import Checkpoint, Cutover, Phase, Refused
    from snapshot import FrozenSnapshot, ROOTS, REQUIRED, SnapshotRefused

    STATE = Path("/var/lib")
    PRIVATE = STATE / "snapshot-qualification"
    PGDATA = STATE / "postgresql/17"
    WORKERS = tuple(name for name in ROOTS if name not in REQUIRED)
    APPS = tuple(name for name in ROOTS if name in REQUIRED and name != "postgresql/17")
    WRITERS = ("snapshot-fixture-writes.target", "snapshot-fixture-writer.timer", "snapshot-fixture-writer.service")
    SYSTEMCTL = "${pkgs.systemd}/bin/systemctl"
    RUNUSER = "${pkgs.util-linux}/bin/runuser"
    TAR = "${pkgs.gnutar}/bin/tar"
    PSQL = "${pkgs.postgresql_17}/bin/psql"

    class FixtureRefused(RuntimeError):
        pass

    def require(condition, code):
        if not condition:
            raise FixtureRefused(code)

    def run(arguments, data=None, checked=True):
        result = subprocess.run(arguments, input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=180, check=False)
        if checked:
            require(result.returncode == 0, "FIXTURE_COMMAND_FAILED")
        return result

    def service(*arguments):
        return run([SYSTEMCTL, *arguments]).stdout.strip()

    def sql(statement):
        return run([RUNUSER, "-u", "postgres", "--", PSQL, "-X", "-w", "-qAt",
                    "--host=/run/postgresql", "--dbname=snapshot_fixture",
                    "--set=ON_ERROR_STOP=1"], statement).stdout.strip()

    def active(unit):
        return service("show", unit, "--property=ActiveState", "--value")

    def freeze():
        service("stop", *WRITERS)
        service("stop", "postgresql.target", "postgresql.service", "postgresql-setup.service")

    def verify_quiescent():
        for unit in (*WRITERS, "postgresql.target", "postgresql.service", "postgresql-setup.service"):
            require(active(unit) == "inactive", "WRITER_NOT_STOPPED")
        require(service("show", "postgresql.service", "--property=MainPID", "--value") == "0",
                "POSTGRESQL_PROCESS_NOT_STOPPED")
        require(not (PGDATA / "postmaster.pid").exists(), "POSTGRESQL_PIDFILE_REMAINS")

    def start_postgres():
        service("start", "postgresql.target")
        require(active("postgresql.service") == "active", "POSTGRESQL_NOT_STARTED")
        require(service("show", "postgresql.service", "--property=MainPID", "--value") != "0",
                "POSTGRESQL_PROCESS_MISSING")

    def fixture_guard():
        require(Path("/etc/snapshot-qualification/synthetic-only").read_text() == "INVENTED_VM_ONLY\n",
                "SYNTHETIC_VM_MARKER_MISSING")
        require(os.geteuid() == 0, "SYNTHETIC_ROOT_REQUIRED")
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        require(stat.S_IMODE(PRIVATE.stat().st_mode) == 0o700, "FIXTURE_DIRECTORY_NOT_PRIVATE")

    def marker(name, generation):
        path = STATE / name / "paired-marker"
        path.write_text(generation + "\n")

    def baseline():
        fixture_guard()
        freeze()
        verify_quiescent()
        # Each case starts a distinct invented transaction. Clear only the
        # rate counter left by earlier cases, preserving normal unit limits.
        service("reset-failed", "postgresql.service", "postgresql-setup.service")
        for name in WORKERS:
            path = STATE / name
            if path.exists():
                shutil.rmtree(path)
        for name in APPS:
            path = STATE / name
            path.mkdir(mode=0o700, exist_ok=True)
            marker(name, "synthetic-old")
        # The source is readable by this invented observer; private retention
        # must still deny the same UID access through its new ancestor.
        cloud = STATE / "nextcloud"
        cloud.chmod(0o755)
        file = cloud / "paired-marker"
        identity = pwd.getpwnam("snapshot-file-owner")
        os.chown(file, identity.pw_uid, identity.pw_gid)
        file.chmod(0o640)
        run(["${pkgs.acl}/bin/setfacl", "-m", "u:snapshot-outsider:r--", str(file)])
        os.setxattr(file, "user.snapshot-fixture", b"invented-xattr")
        require(run([RUNUSER, "-u", "snapshot-outsider", "--", "${pkgs.coreutils}/bin/test", "-r", str(file)],
                    checked=False).returncode == 0, "BASELINE_ACL_NOT_EFFECTIVE")
        start_postgres()
        sql("CREATE TABLE IF NOT EXISTS paired_state(id integer PRIMARY KEY, generation text NOT NULL);"
            "INSERT INTO paired_state VALUES(1,'synthetic-old') "
            "ON CONFLICT(id) DO UPDATE SET generation=EXCLUDED.generation;")
        service("start", "snapshot-fixture-writes.target")
        require(all(not (STATE / name).exists() for name in WORKERS), "WORKER_ALREADY_PRESENT")

    def pair_is(generation):
        require(sql("SELECT generation FROM paired_state WHERE id=1;") == generation,
                "SQL_GENERATION_MISMATCH")
        require(all((STATE / name / "paired-marker").read_text() == generation + "\n" for name in APPS),
                "FILE_GENERATION_MISMATCH")

    def tree_identity(path):
        # Compare exact offline candidate files internally; never export them.
        result = {}
        for base, folders, files in os.walk(path, followlinks=False):
            for name in sorted(folders + files):
                child = Path(base) / name
                metadata = child.lstat()
                key = str(child.relative_to(path))
                value = [stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid]
                if child.is_symlink():
                    value += ["link", os.readlink(child)]
                elif child.is_file():
                    value += ["file", hashlib.sha256(child.read_bytes()).hexdigest()]
                elif child.is_dir():
                    value += ["directory"]
                else:
                    raise FixtureRefused("UNEXPECTED_SYNTHETIC_FILE_TYPE")
                result[key] = value
        return result

    def snapshot_folder(case):
        root = PRIVATE / case
        root.mkdir(mode=0o700)
        return root

    class Backend:
        def __init__(self, case, fail=None):
            self.root = snapshot_folder(case)
            self.snapshot_root = self.root / "snapshot"
            self.snapshot_root.mkdir(mode=0o700)
            self.checkpoint_root = self.root / "checkpoint"
            self.checkpoint_root.mkdir(mode=0o700)
            self.checkpoint = Checkpoint(self.checkpoint_root)
            self.saved = FrozenSnapshot(STATE, self.snapshot_root, TAR)
            self.fail = fail
            self.calls = []
            self.metadata = None

        def called(self, name):
            self.calls.append(name)

        def preflight(self):
            self.called("preflight")
            pair_is("synthetic-old")
            require(all(not (STATE / name).exists() for name in WORKERS), "WORKER_ALREADY_PRESENT")
            file = STATE / "nextcloud/paired-marker"
            metadata = file.stat()
            self.metadata = (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode),
                             os.getxattr(file, "user.snapshot-fixture"),
                             run(["${pkgs.acl}/bin/getfacl", "-cpn", str(file)]).stdout)

        def freeze(self):
            self.called("freeze")
            freeze()

        def verify_quiescent(self):
            self.called("verify_quiescent")
            verify_quiescent()

        def snapshot(self):
            self.called("snapshot")
            verify_quiescent()
            self.saved.create()

        def verify_snapshot(self):
            self.called("verify_snapshot")
            require(set(self.saved.verify()["roots"]) == REQUIRED, "SNAPSHOT_ROOT_SET_MISMATCH")

        def install_candidate(self):
            self.called("install_candidate")
            # This marker models sequencing only; no NixOS generation is switched.
            (self.root / "generation-model").write_text("synthetic-candidate")

        def adopt_private_state(self):
            self.called("adopt_private_state")
            verify_quiescent()
            for name in APPS:
                marker(name, "synthetic-candidate")
            for name in WORKERS:
                path = STATE / name
                path.mkdir(mode=0o700)
                with sqlite3.connect(path / "queue.sqlite") as database:
                    database.execute("CREATE TABLE queue(value TEXT NOT NULL)")
                    database.execute("INSERT INTO queue VALUES('synthetic-candidate-queue')")
                (path / "queue.sqlite").chmod(0o600)
            start_postgres()
            sql("UPDATE paired_state SET generation='synthetic-candidate' WHERE id=1;")

        def start_private_services(self):
            self.called("start_private_services")
            require(active("postgresql.service") == "active", "PRIVATE_POSTGRESQL_UNAVAILABLE")
            require(all(active(unit) == "inactive" for unit in WRITERS), "PUBLIC_WRITER_OPEN_TOO_EARLY")

        def verify_private_services(self):
            self.called("verify_private_services")
            pair_is("synthetic-candidate")
            if self.fail == "private":
                raise FixtureRefused("INJECTED_PRIVATE_FAILURE")

        def open_public_writes(self):
            self.called("open_public_writes")
            require(self.checkpoint.read() == Phase.OPENING, "DURABLE_OPENING_MARKER_MISSING")
            service("start", "snapshot-fixture-writes.target")
            sql("UPDATE paired_state SET generation='synthetic-public-write' WHERE id=1;")
            for name in APPS:
                marker(name, "synthetic-public-write")
            if self.fail == "opening":
                raise FixtureRefused("INJECTED_OPENING_FAILURE")

        def verify_public_services(self):
            self.called("verify_public_services")
            pair_is("synthetic-public-write")
            if self.fail == "public":
                raise FixtureRefused("INJECTED_PUBLIC_VERIFICATION_FAILURE")

        def restore_snapshot(self):
            self.called("restore_snapshot")
            verify_quiescent()
            identities = {name: tree_identity(STATE / name) for name in ROOTS}
            self.saved.restore()
            retained = self.snapshot_root / "candidate-state-retained"
            require(stat.S_IMODE(retained.stat().st_mode) == 0o700, "CANDIDATE_RETENTION_NOT_PRIVATE")
            require(all(tree_identity(retained / name) == identities[name] for name in ROOTS),
                    "OFFLINE_CANDIDATE_RETENTION_CHANGED")
            require(all(not (STATE / name).exists() for name in WORKERS), "NEW_WORKER_SURVIVED_RETURN")
            file = STATE / "nextcloud/paired-marker"
            metadata = file.stat()
            restored = (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode),
                        os.getxattr(file, "user.snapshot-fixture"),
                        run(["${pkgs.acl}/bin/getfacl", "-cpn", str(file)]).stdout)
            require(restored == self.metadata, "FILE_METADATA_NOT_RESTORED")
            for name in WORKERS:
                with sqlite3.connect(retained / name / "queue.sqlite") as database:
                    require(database.execute("SELECT value FROM queue").fetchall() == [("synthetic-candidate-queue",)],
                            "CANDIDATE_QUEUE_NOT_RETAINED")
            for file in (self.saved.archive, self.saved.manifest, retained / "nextcloud/paired-marker"):
                require(run([RUNUSER, "-u", "snapshot-outsider", "--", "${pkgs.coreutils}/bin/test", "-r", str(file)],
                            checked=False).returncode != 0, "PRIVATE_RETURN_CONTENT_READABLE")

        def restore_previous_generation(self):
            self.called("restore_previous_generation")
            (self.root / "generation-model").write_text("synthetic-old")

        def verify_previous_private_services(self):
            self.called("verify_previous_private_services")
            require(all(active(unit) == "inactive" for unit in WRITERS), "REOPENED_BEFORE_RETURN_VERIFICATION")
            start_postgres()
            pair_is("synthetic-old")

        def reopen_previous_services(self):
            self.called("reopen_previous_services")
            pair_is("synthetic-old")
            service("start", "snapshot-fixture-writes.target")

        def hold_current_state(self):
            self.called("hold_current_state")
            freeze()
            verify_quiescent()

    def expect_refused(operation, error, code=None):
        try:
            operation()
        except error as exception:
            require(code is None or str(exception) == code, "UNEXPECTED_CLOSED_REFUSAL")
        else:
            raise FixtureRefused("EXPECTED_REFUSAL_MISSING")

    def quiescence_case():
        baseline()
        expect_refused(verify_quiescent, FixtureRefused, "WRITER_NOT_STOPPED")
        service("stop", *WRITERS)
        expect_refused(verify_quiescent, FixtureRefused, "WRITER_NOT_STOPPED")
        freeze()
        verify_quiescent()
        service("--job-mode=ignore-dependencies", "start", "postgresql.target")
        require(active("postgresql.service") == "inactive", "GUARD_FIXTURE_STARTED_POSTGRESQL")
        expect_refused(verify_quiescent, FixtureRefused, "WRITER_NOT_STOPPED")
        service("stop", "postgresql.target")
        pidfile = PGDATA / "postmaster.pid"
        pidfile.write_text("invented-stale-pid\n")
        try:
            expect_refused(verify_quiescent, FixtureRefused, "POSTGRESQL_PIDFILE_REMAINS")
        finally:
            pidfile.unlink()
        verify_quiescent()

    def paired_return_case():
        baseline()
        backend = Backend("paired-return", "private")
        cutover = Cutover(backend, backend.checkpoint)
        expect_refused(cutover.execute, Refused, "CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED")
        require(backend.checkpoint.read() == Phase.RETURNED, "RETURN_CHECKPOINT_MISSING")
        pair_is("synthetic-old")
        require("open_public_writes" not in backend.calls, "PUBLIC_WRITE_BEFORE_FAILED_RETURN")
        require(backend.calls.count("restore_snapshot") == 1, "PAIR_NOT_RESTORED_EXACTLY_ONCE")
        require(backend.calls.index("restore_snapshot") < backend.calls.index("restore_previous_generation")
                < backend.calls.index("verify_previous_private_services") < backend.calls.index("reopen_previous_services"),
                "RETURN_ORDER_INVALID")

    def after_open_case(failure):
        baseline()
        backend = Backend("after-open-" + str(failure), failure)
        cutover = Cutover(backend, backend.checkpoint)
        if failure is None:
            require(cutover.execute()["code"] == "CUTOVER_VERIFIED", "OPEN_VERIFICATION_FAILED")
            require(backend.checkpoint.read() == Phase.OPEN, "OPEN_CHECKPOINT_MISSING")
        else:
            expect_refused(cutover.execute, Refused, "OPENING_FAILED_CURRENT_STATE_PRESERVED")
            require(backend.checkpoint.read() == Phase.HELD, "HELD_CHECKPOINT_MISSING")
            verify_quiescent()
            start_postgres()
        pair_is("synthetic-public-write")
        require("restore_snapshot" not in backend.calls and "restore_previous_generation" not in backend.calls,
                "OLD_STATE_RESTORED_AFTER_WRITE")
        require(not (backend.snapshot_root / "candidate-state-retained").exists(), "CANDIDATE_MOVED_AFTER_WRITE")
        before = list(backend.calls)
        expect_refused(cutover.return_before_opening, Refused, "RESTORE_AFTER_PUBLIC_WRITES_REFUSED")
        expect_refused(Cutover(backend, backend.checkpoint).return_before_opening, Refused,
                       "RESTORE_AFTER_PUBLIC_WRITES_REFUSED")
        require(backend.calls == before, "REJECTED_RETURN_MUTATED_STATE")
        pair_is("synthetic-public-write")

    def storage_case():
        baseline()
        freeze()
        verify_quiescent()
        destination = STATE / "nextcloud/nested-mount"
        destination.mkdir()
        source = PRIVATE / "synthetic-bind-source"
        source.mkdir(mode=0o700)
        (source / "marker").write_text("invented-mounted-data")
        run(["${pkgs.util-linux}/bin/mount", "--bind", str(source), str(destination)])
        try:
            saved = FrozenSnapshot(STATE, snapshot_folder("nested-mount"), TAR)
            expect_refused(saved.create, SnapshotRefused, "NESTED_STATE_MOUNT_REFUSED")
            require(not saved.archive.exists(), "SNAPSHOT_CREATED_WITH_OMITTED_MOUNT")
        finally:
            run(["${pkgs.util-linux}/bin/umount", str(destination)])
            destination.rmdir()
        tablespace = STATE / "snapshot-external-tablespace"
        tablespace.mkdir(mode=0o700)
        postgres = pwd.getpwnam("postgres")
        os.chown(tablespace, postgres.pw_uid, postgres.pw_gid)
        start_postgres()
        sql("CREATE TABLESPACE snapshot_external LOCATION '/var/lib/snapshot-external-tablespace';")
        freeze()
        saved = FrozenSnapshot(STATE, snapshot_folder("external-tablespace"), TAR)
        expect_refused(saved.create, SnapshotRefused, "EXTERNAL_TABLESPACE_REFUSED")
        require(not saved.archive.exists(), "SNAPSHOT_CREATED_WITH_OMITTED_TABLESPACE")
        start_postgres()
        sql("DROP TABLESPACE snapshot_external;")
        freeze()
        wal = PGDATA / "pg_wal"
        external_wal = PRIVATE / "synthetic-external-wal"
        wal.rename(external_wal)
        wal.symlink_to(external_wal, target_is_directory=True)
        try:
            saved = FrozenSnapshot(STATE, snapshot_folder("external-wal"), TAR)
            expect_refused(saved.create, SnapshotRefused, "EXTERNAL_WAL_REFUSED")
            require(not saved.archive.exists(), "SNAPSHOT_CREATED_WITH_OMITTED_WAL")
        finally:
            wal.unlink()
            external_wal.rename(wal)

    def integrity_case():
        baseline()
        freeze()
        verify_quiescent()
        saved = FrozenSnapshot(STATE, snapshot_folder("corrupt-archive"), TAR)
        saved.create()
        original = {name: tree_identity(STATE / name) for name in REQUIRED}
        with saved.archive.open("ab") as stream:
            stream.write(b"invented-corruption")
        expect_refused(saved.restore, SnapshotRefused, "SNAPSHOT_INTEGRITY_REFUSED")
        require(not (saved.root / "candidate-state-retained").exists(), "CORRUPT_ARCHIVE_MOVED_STATE")
        require(all(tree_identity(STATE / name) == original[name] for name in REQUIRED),
                "CORRUPT_ARCHIVE_CHANGED_STATE")
        start_postgres()
        pair_is("synthetic-old")

    CASES = {"quiescence": quiescence_case, "paired-return": paired_return_case,
             "opening-failure": lambda: after_open_case("opening"),
             "public-verification-failure": lambda: after_open_case("public"),
             "successful-open": lambda: after_open_case(None),
             "storage-boundaries": storage_case, "corrupt-archive": integrity_case}

    if __name__ == "__main__":
        name = sys.argv[1] if len(sys.argv) == 2 else "invalid"
        try:
            require(name in CASES, "UNKNOWN_SYNTHETIC_CASE")
            CASES[name]()
        except Exception as failure:
            # No SQL, file, archive, command output or arbitrary diagnostics.
            code = str(failure) if isinstance(failure, FixtureRefused) else "SYNTHETIC_CASE_FAILED"
            print(json.dumps({"status": "failed", "case": name, "code": code}, sort_keys=True))
            raise SystemExit(1)
        print(json.dumps({"status": "ok", "case": name}, sort_keys=True))
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-paired-offline-snapshot-synthetic";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 1200;
  nodes.machine = { lib, ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    users.groups.snapshot-file-owner.gid = 1230;
    users.users.snapshot-file-owner = { isSystemUser = true; uid = 1230; group = "snapshot-file-owner"; };
    users.groups.snapshot-outsider.gid = 1231;
    users.users.snapshot-outsider = { isSystemUser = true; uid = 1231; group = "snapshot-outsider"; };
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      dataDir = "/var/lib/postgresql/17";
      enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      ensureDatabases = [ "snapshot_fixture" ];
      authentication = ''
        local all postgres peer
        local all all reject
        host all all 0.0.0.0/0 reject
        host all all ::/0 reject
      '';
    };
    # Only this invented tablespace is writable for the negative omission test.
    # PostgreSQL's normal strict sandbox and all remaining paths are preserved.
    systemd.services.postgresql.serviceConfig.ReadWritePaths = [ "-/var/lib/snapshot-external-tablespace" ];
    systemd.targets.snapshot-fixture-writes = {
      description = "Invented writer inventory for offline snapshot qualification";
      requires = [ "snapshot-fixture-writer.service" "snapshot-fixture-writer.timer" ];
    };
    systemd.services.snapshot-fixture-writer = {
      partOf = [ "snapshot-fixture-writes.target" ];
      serviceConfig = { Type = "simple"; ExecStart = "${pkgs.coreutils}/bin/sleep infinity"; };
    };
    systemd.timers.snapshot-fixture-writer = {
      partOf = [ "snapshot-fixture-writes.target" ];
      timerConfig = { OnActiveSec = "1h"; Unit = "snapshot-fixture-writer.service"; };
    };
    environment.etc = {
      "snapshot-qualification/cutover.py".source = ./cutover.py;
      "snapshot-qualification/snapshot.py".source = ./snapshot.py;
      "snapshot-qualification/synthetic-only".text = "INVENTED_VM_ONLY\n";
    };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.python3 pkgs.util-linux pkgs.acl pkgs.gnutar ];
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql.service")
    machine.wait_for_unit("postgresql-setup.service")
    checks = []
    for case in ("quiescence", "paired-return", "opening-failure", "public-verification-failure",
                 "successful-open", "storage-boundaries", "corrupt-archive"):
        with subtest(case):
            result = json.loads(machine.succeed("${pkgs.python3}/bin/python3 ${fixture} " + case, timeout=240))
            assert result == {"status": "ok", "case": case}, "closed synthetic case failed"
            checks.append(case)
    Path(os.environ["out"], "snapshot-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "postgresql": "${pkgs.postgresql_17.version}", "production_qualification": False,
        "cutover_sha256": "${builtins.hashFile "sha256" ./cutover.py}",
        "snapshot_sha256": "${builtins.hashFile "sha256" ./snapshot.py}",
        "limitations": ["No VPS data, credentials, storage capacity or maintenance-window duration tested",
                        "Generation switching is a sequencing model; the sealed production backend is separate",
                        "No snapshot, SQL row, application file or command diagnostics exported"]
    }, sort_keys=True) + "\n")
  '';
}
