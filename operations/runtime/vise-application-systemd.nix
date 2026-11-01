# Real pinned application, entirely synthetic SQL, keys, sessions and backup.
{ nixpkgs, artifact, apiTests }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  tools = pkgs.callPackage ../builds/toolchains.nix { };
  checker = pkgs.callPackage ../vise/adoption-check.nix { };
  # A Nix path literal interpolated directly is copied into a new store root.
  # Keep the exact qualified outputs as store references for this runtime test.
  qualifiedArtifact = builtins.storePath (toString artifact);
  qualifiedTests = builtins.storePath (toString apiTests);
in pkgs.testers.runNixOSTest {
  name = "mrjam-vise-application-adoption-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 1500;
  nodes.machine = { lib, ... }: {
    imports = [ ../nixos/mrjam-vise.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536; virtualisation.cores = 2;
    virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamVise = { enable = true; adoption = { uid = 978; gid = 978; };
      artifactRoot = builtins.unsafeDiscardStringContext qualifiedArtifact; };
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "etp_carnet" ];
      ensureUsers = [ { name = "etp_carnet"; ensureDBOwnership = true; } ];
    };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.util-linux pkgs.curl tools.node checker qualifiedArtifact ];
    environment.etc."synthetic-vise-schema.sql".source = ../vise/schema-v1.sql;
    environment.etc."synthetic-vise-adopt-role.sql".source = ../vise/adopt-runtime-role.sql;
    environment.etc."synthetic-vise-api-tests.mjs".source = qualifiedTests + "/api-tests.mjs";
    # Diagnostics belong only to this disposable fixture.
    systemd.services.vise.serviceConfig = {
      Restart = lib.mkForce "no";
      StandardOutput = lib.mkForce "journal"; StandardError = lib.mkForce "journal";
    };
  };
  testScript = ''
    import hashlib
    import json
    import os
    import shlex
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    checks = []
    health = "curl --silent --show-error --fail --max-time 5 http://127.0.0.1:3017/api/health"

    def sql(statement, user="postgres"):
        return machine.succeed("runuser -u " + user + " -- psql -X -w -h /run/postgresql -d etp_carnet -At -v ON_ERROR_STOP=1 -c " + shlex.quote(statement)).strip()

    def refused():
        machine.succeed("systemctl reset-failed")
        machine.fail("systemctl start vise.service")
        machine.fail("systemctl is-active --quiet vise.service")
        machine.fail(health)

    def start():
        status, output = machine.execute("systemctl reset-failed; systemctl start vise.service")
        assert status == 0, output
        try:
            machine.wait_until_succeeds(health, timeout=60)
        except Exception as error:
            raise AssertionError(machine.succeed("journalctl -u vise --no-pager -n 30")) from error
        assert json.loads(machine.succeed(health)) == {"status": "ok", "prototype": True}

    def schema_hash():
        dump = machine.succeed("runuser -u etp_carnet -- pg_dump -h /run/postgresql --schema-only --no-owner --no-privileges etp_carnet")
        return hashlib.sha256("\n".join(line for line in dump.splitlines() if not line.startswith("\\restrict ") and not line.startswith("\\unrestrict ")).encode()).hexdigest()

    with subtest("empty persistent state is refused without schema or ledger creation"):
        machine.fail("systemctl is-active --quiet vise.service")
        refused()
        assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'") == "0"
        machine.fail("test -e /var/lib/etp-carnet/deletions.log")
        checks.append("empty-state-refused-without-bootstrap")

    with subtest("explicit synthetic initialization and role adoption are idempotent"):
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-vise-schema.sql")
        for _ in range(2):
            machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-vise-adopt-role.sql")
        machine.succeed("install -d -m 0700 -o etp_carnet -g etp_carnet /var/lib/etp-carnet; install -m 0600 -o etp_carnet -g etp_carnet /dev/null /var/lib/etp-carnet/deletions.log")
        machine.succeed("runuser -u etp_carnet -- mrjam-vise-check-adoption")
        machine.fail("runuser -u etp_carnet -- mrjam-vise-check-adoption arbitrary")
        baseline = schema_hash()
        checks.append("explicit-schema-initialization-and-idempotent-role-adoption")

    with subtest("missing, linked or over-permissive ledger is refused"):
        machine.succeed("mv /var/lib/etp-carnet/deletions.log /var/lib/etp-carnet/ledger.saved")
        refused()
        machine.fail("test -e /var/lib/etp-carnet/deletions.log")
        machine.succeed("ln -s ledger.saved /var/lib/etp-carnet/deletions.log")
        refused()
        machine.succeed("rm /var/lib/etp-carnet/deletions.log; mv /var/lib/etp-carnet/ledger.saved /var/lib/etp-carnet/deletions.log; chmod 0644 /var/lib/etp-carnet/deletions.log")
        refused()
        machine.succeed("chmod 0600 /var/lib/etp-carnet/deletions.log")
        checks.append("missing-symlink-and-public-ledger-refused")

    with subtest("incompatible schema and DDL privileges are refused unchanged"):
        sql("UPDATE schema_migrations SET version=2")
        refused()
        assert sql("SELECT version FROM schema_migrations") == "2"
        sql("UPDATE schema_migrations SET version=1")
        sql("ALTER TABLE comptes ADD COLUMN synthetic_extra integer")
        refused()
        sql("ALTER TABLE comptes DROP COLUMN synthetic_extra")
        sql("GRANT CREATE ON SCHEMA public TO etp_carnet")
        refused()
        sql("REVOKE CREATE ON SCHEMA public FROM etp_carnet")
        machine.succeed("runuser -u etp_carnet -- mrjam-vise-check-adoption")
        checks.append("schema-version-structure-and-runtime-ddl-refusals")

    with subtest("actual application starts without DDL and serves its pinned Elm site"):
        start()
        assert schema_hash() == baseline
        machine.fail("runuser -u etp_carnet -- psql -X -w -h /run/postgresql -d etp_carnet -c 'CREATE TABLE forbidden(id int)'")
        machine.fail("runuser -u etp_carnet -- psql -X -w -h /run/postgresql -d postgres -c 'SELECT 1'")
        machine.fail("runuser -u nobody -- psql -X -w -h /run/postgresql -U etp_carnet -d etp_carnet -c 'SELECT 1'")
        machine.succeed("curl -fsS http://127.0.0.1:3017/elm.js | cmp - ${qualifiedArtifact}/dist/elm.js")
        checks.append("real-rust-elm-http-and-closed-postgresql-role")

    with subtest("existing API suite exercises encrypted accounts, recovery, quotas and deletion"):
        status, output = machine.execute("env CARNET_API_TEST_URL=http://127.0.0.1:3017 CARNET_API_TEST_ORIGIN=https://vise.mrj.am node --test /etc/synthetic-vise-api-tests.mjs 2>&1", timeout=600)
        assert status == 0, output
        assert "pass 9" in output and "fail 0" in output, output
        assert schema_hash() == baseline
        machine.succeed("test -s /var/lib/etp-carnet/deletions.log")
        checks.append("nine-real-api-tests-with-encrypted-synthetic-fixtures")

    with subtest("SIGTERM drains and restart preserves state and the ledger"):
        machine.succeed("systemctl stop vise.service", timeout=60)
        assert machine.succeed("systemctl show vise -p ExecMainStatus --value").strip() == "0"
        machine.succeed("sha256sum /var/lib/etp-carnet/deletions.log > /tmp/synthetic-ledger-hash")
        start()
        machine.succeed("sha256sum -c /tmp/synthetic-ledger-hash")
        assert schema_hash() == baseline
        checks.append("sigterm-clean-exit-and-state-preserving-restart")

    with subtest("SQL restore keeps the newer deletion ledger and cannot resurrect its account"):
        machine.succeed("systemctl stop vise.service", timeout=60)
        # A deleted UUID comes from this run's invented accounts only. Recreate
        # its old SQL row in the disposable fixture to exercise real restoration.
        deleted = machine.succeed("head -1 /var/lib/etp-carnet/deletions.log").strip()
        import uuid
        assert str(uuid.UUID(deleted)) == deleted
        sql("DELETE FROM suppressions WHERE compte='" + deleted + "'::uuid")
        sql("INSERT INTO comptes(id,pseudonyme,password_hash,auth_recovery_hash) VALUES('" + deleted + "'::uuid,'synthetic_restored_deleted','synthetic','synthetic')")
        surviving_payload = sql("SELECT md5(string_agg(payload::text,',' ORDER BY compte::text)) FROM coffres")
        assert len(surviving_payload) == 32
        machine.succeed("runuser -u postgres -- pg_dump -h /run/postgresql -Fc --no-owner --no-privileges etp_carnet > /tmp/synthetic-vise-backup.dump")
        start()
        assert sql("SELECT count(*) FROM comptes WHERE id='" + deleted + "'::uuid") == "0"
        machine.succeed("systemctl stop vise.service", timeout=60)
        machine.succeed("runuser -u postgres -- pg_restore -h /run/postgresql -d etp_carnet --clean --if-exists --no-owner --no-privileges /tmp/synthetic-vise-backup.dump")
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-vise-adopt-role.sql")
        assert sql("SELECT count(*) FROM comptes WHERE id='" + deleted + "'::uuid") == "1"
        machine.succeed("sha256sum -c /tmp/synthetic-ledger-hash")
        start()
        assert sql("SELECT count(*) FROM comptes WHERE id='" + deleted + "'::uuid") == "0"
        assert sql("SELECT md5(string_agg(payload::text,',' ORDER BY compte::text)) FROM coffres") == surviving_payload
        assert schema_hash() == baseline
        checks.append("real-pg-dump-restore-with-current-ledger-and-no-account-resurrection")

    Path(os.environ["out"], "vise-application-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "artifact": "${qualifiedArtifact}", "api_tests": "${qualifiedTests}",
        "postgresql": "${pkgs.postgresql_17.version}", "schema_sha256": baseline,
        "production_qualification": False,
        "limitations": ["Entirely invented accounts, payloads, sessions and ledger", "No browser or production backup accessed", "Restore exercised only with this new binary; rollback to the old DDL-dependent binary is not qualified"]
    }, sort_keys=True) + "\n")
  '';
}
