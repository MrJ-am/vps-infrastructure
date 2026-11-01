# Local disposable VM only: real pinned Forgejo/PostgreSQL, synthetic state.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../forgejo/locked-toolchain.nix { };
  forgejo = locked.forgejo;
  checker = locked.callPackage ../forgejo/schema-check.nix { };
  observer = pkgs.callPackage ../bootstrap-services/package.nix { };
in pkgs.testers.runNixOSTest {
  name = "mrjam-forgejo-postgresql-adoption-synthetic";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-forgejo-host.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamForgejoHost = {
      enable = true; uid = 977; gid = 977;
      artifactStorePath = builtins.unsafeDiscardStringContext "${forgejo}";
    };
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "forgejo" ];
      ensureUsers = [ { name = "forgejo"; ensureDBOwnership = true; } ];
    };
    environment.systemPackages = [ forgejo checker observer pkgs.postgresql_17 pkgs.git pkgs.curl pkgs.util-linux ];
    # Only this disposable guest has bootstrap credentials/configuration.
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini { }).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = { SECRET_KEY = "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"; INTERNAL_TOKEN = "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"; };
        # Public all-zero 32-byte synthetic HMAC key in URL-safe raw base64.
        oauth2.JWT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."forgejo-adopt-runtime-role.sql".source = ../forgejo/adopt-runtime-role.sql;
    systemd.services.forgejo.serviceConfig.Restart = lib.mkForce "no";
    # Local synthetic diagnostics only; the deployed module keeps logs closed.
    systemd.services.forgejo.serviceConfig.StandardError = lib.mkForce "journal";
    systemd.services.forgejo.serviceConfig.StandardOutput = lib.mkForce "journal";
  };
  testScript = ''
    import hashlib
    import json
    import os
    import shlex
    from urllib.parse import urlsplit
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    checks = []

    def sql(statement):
        return machine.succeed("runuser -u forgejo -- psql -X -w -h /run/postgresql -d forgejo -At -v ON_ERROR_STOP=1 -c " + shlex.quote(statement)).strip()

    def refused():
        machine.succeed("systemctl cat forgejo.service >/dev/null")
        machine.succeed("systemctl reset-failed")
        machine.fail("systemctl start forgejo.service")
        machine.fail("systemctl is-active --quiet forgejo.service")

    def schema_hash():
        dump = machine.succeed("runuser -u forgejo -- pg_dump -h /run/postgresql --schema-only --no-owner --no-privileges forgejo")
        stable = "\n".join(x for x in dump.splitlines() if not x.startswith("\\restrict ") and not x.startswith("\\unrestrict "))
        return hashlib.sha256(stable.encode()).hexdigest()

    with subtest("installation is staged and cannot generate absent secrets"):
        machine.fail("systemctl is-active --quiet forgejo.service")
        refused()
        machine.fail("test -e /var/lib/forgejo/custom/conf/secret_key")
        assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'") == "0"
        checks.append("staged-and-no-implicit-secret-bootstrap")

    machine.succeed("install -d -m 0700 -o forgejo -g forgejo /var/lib/forgejo/custom/conf /var/lib/forgejo/repositories")
    machine.succeed("printf '%s' SYNTHETIC-SECRET-KEY-NOT-PRODUCTION > /var/lib/forgejo/custom/conf/secret_key")
    machine.succeed("printf '%s' SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION > /var/lib/forgejo/custom/conf/internal_token")
    machine.succeed("printf '%s' AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > /var/lib/forgejo/custom/conf/oauth2_jwt_secret")
    machine.succeed("chown forgejo:forgejo /var/lib/forgejo/custom/conf/*; chmod 0400 /var/lib/forgejo/custom/conf/*")

    with subtest("empty database is refused without creating migration tables"):
        refused()
        assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'") == "0"
        checks.append("empty-database-refused-without-schema-write")

    with subtest("explicit synthetic migration creates the exact three-part contract"):
        migration_status, migration_log = machine.execute("runuser -u forgejo -- env USER=forgejo HOME=/var/lib/forgejo FORGEJO_WORK_DIR=/var/lib/forgejo FORGEJO_CUSTOM=/var/lib/forgejo/custom forgejo migrate --config /etc/synthetic-forgejo.ini 2>&1")
        assert migration_status == 0, migration_log
        machine.fail("runuser -u forgejo -- mrjam-forgejo-check-schema")
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -f /etc/forgejo-adopt-runtime-role.sql")
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -f /etc/forgejo-adopt-runtime-role.sql")
        machine.succeed("runuser -u forgejo -- mrjam-forgejo-check-schema")
        machine.fail("runuser -u forgejo -- mrjam-forgejo-check-schema arbitrary-input")
        baseline = schema_hash()
        checks.append("explicit-migration-matches-source-derived-contract")

    with subtest("compatible schema still refuses a missing secret or substituted symlink"):
        machine.succeed("mv /var/lib/forgejo/custom/conf/internal_token /var/lib/forgejo/custom/conf/internal_token.saved")
        refused()
        machine.fail("test -e /var/lib/forgejo/custom/conf/internal_token")
        machine.succeed("ln -s internal_token.saved /var/lib/forgejo/custom/conf/internal_token")
        refused()
        machine.succeed("test -L /var/lib/forgejo/custom/conf/internal_token; rm /var/lib/forgejo/custom/conf/internal_token; mv /var/lib/forgejo/custom/conf/internal_token.saved /var/lib/forgejo/custom/conf/internal_token")
        checks.append("missing-or-symlink-secret-refused-with-compatible-schema")

    with subtest("runtime role cannot migrate, create tables or bypass the schema owner"):
        machine.fail("runuser -u forgejo -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -c 'CREATE TABLE forbidden(id int)'")
        machine.fail("runuser -u forgejo -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -c 'ALTER TABLE public.version ADD COLUMN forbidden int'")
        machine.fail("runuser -u forgejo -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -c 'SET ROLE mrjam_forgejo_schema'")
        checks.append("runtime-ddl-and-schema-owner-impersonation-refused")

    with subtest("adoption refuses an absent repository directory or a substituted link"):
        machine.succeed("mv /var/lib/forgejo/repositories /var/lib/forgejo/repositories.saved")
        refused()
        machine.fail("test -e /var/lib/forgejo/repositories")
        machine.succeed("ln -s repositories.saved /var/lib/forgejo/repositories")
        refused()
        machine.succeed("test -L /var/lib/forgejo/repositories; rm /var/lib/forgejo/repositories; mv /var/lib/forgejo/repositories.saved /var/lib/forgejo/repositories")
        checks.append("missing-or-symlink-repository-directory-refused")

    with subtest("DDL privileges in another schema and callable security-definer functions are refused"):
        def admin(statement):
            return machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d forgejo -v ON_ERROR_STOP=1 -c " + shlex.quote(statement))
        admin("CREATE SCHEMA synthetic_extra; GRANT USAGE,CREATE ON SCHEMA synthetic_extra TO forgejo")
        refused()
        admin("DROP SCHEMA synthetic_extra")
        admin("CREATE FUNCTION public.synthetic_definer() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'")
        refused()
        admin("DROP FUNCTION public.synthetic_definer()")
        machine.succeed("runuser -u forgejo -- mrjam-forgejo-check-schema")
        checks.append("cross-schema-ddl-and-security-definer-capabilities-refused")

    with subtest("incompatible legacy versions are refused unchanged"):
        for table, value in [("version", 305), ("forgejo_version", 44)]:
            for incompatible in [value - 1, value + 1]:
                sql("UPDATE " + table + " SET version=" + str(incompatible))
                refused()
                assert sql("SELECT version FROM " + table) == str(incompatible)
                sql("UPDATE " + table + " SET version=" + str(value))
        checks.append("older-and-newer-migration-levels-refused")

    with subtest("missing and extra migration identifiers are refused unchanged"):
        first = sql("SELECT id FROM forgejo_migration ORDER BY id LIMIT 1")
        sql("DELETE FROM forgejo_migration WHERE id='" + first + "'")
        refused()
        assert sql("SELECT count(*) FROM forgejo_migration WHERE id='" + first + "'") == "0"
        sql("INSERT INTO forgejo_migration(id,created_unix) VALUES ('" + first + "',0)")
        sql("INSERT INTO forgejo_migration(id,created_unix) VALUES ('synthetic-unknown-migration',0)")
        refused()
        assert sql("SELECT count(*) FROM forgejo_migration WHERE id='synthetic-unknown-migration'") == "1"
        sql("DELETE FROM forgejo_migration WHERE id='synthetic-unknown-migration'")
        checks.append("missing-and-extra-library-migrations-refused")

    with subtest("qualified schema starts the actual Forgejo service"):
        start_status, start_output = machine.execute("systemctl reset-failed forgejo.service; systemctl start forgejo.service")
        if start_status:
            raise AssertionError(machine.succeed("journalctl -u forgejo.service --no-pager -n 35"))
        machine.wait_for_unit("forgejo.service")
        machine.wait_for_open_port(3004)
        redirect = machine.succeed("curl -sS -H 'Host: forge.mrj.am' -o /dev/null -w '%{http_code} %{redirect_url}' http://127.0.0.1:3004/").strip()
        status, _, location = redirect.partition(" ")
        if status not in ("302", "303"):
            raise AssertionError({"http": redirect, "synthetic_journal": machine.succeed("journalctl -u forgejo.service --no-pager -n 35")})
        assert status in ("302", "303") and urlsplit(location).path == "/user/login", redirect
        assert schema_hash() == baseline
        machine.succeed("runuser -u forgejo -- mrjam-forgejo-check-schema")
        checks.append("real-forgejo-17-0-1-on-postgresql-17-with-stable-schema")

    with subtest("private runtime credentials and separate PostgreSQL permissions"):
        assert machine.succeed("stat -c '%u:%g:%a' /run/mrjam-forgejo/app.ini").strip() == "977:977:400"
        assert machine.succeed("id -G forgejo").strip() == "977"
        machine.fail("runuser -u nobody -- cat /run/mrjam-forgejo/app.ini")
        machine.fail("runuser -u forgejo -- psql -X -w -h /run/postgresql -d postgres -c 'SELECT 1'")
        machine.fail("runuser -u nobody -- psql -X -w -h /run/postgresql -U forgejo -d forgejo -c 'SELECT 1'")
        assert machine.succeed("systemctl show forgejo -p NoNewPrivileges --value").strip() == "yes"
        checks.append("private-credentials-and-closed-peer-identity")

    with subtest("immutable observation reports only the selected live code and Unix identities"):
        observed = json.loads(machine.succeed("mrjam-observe-services"))
        assert observed["authority"] == "unverified_observation"
        assert observed["accounts"]["forgejo"] == {"state": "observed", "uid": 977, "gid": 977}
        assert observed["services"]["forgejo"]["state"] == "active"
        assert observed["services"]["forgejo"]["store_path"] == "${forgejo}"
        # The pinned Nix package's public entrypoint is a PATH-setting shell
        # wrapper; /proc/exe must identify its real ELF, not the wrapper name.
        assert observed["services"]["forgejo"]["executable"] == "${forgejo}/bin/.forgejo-wrapped", observed
        assert observed["services"]["forgejo"]["nar_hash"] is not None
        assert observed["services"]["postgresql"]["executable"].endswith("/bin/postgres")
        assert observed["services"]["kanidm"]["state"] == "absent"
        machine.fail("runuser -u forgejo -- mrjam-observe-services > /tmp/observer-refusal.json")
        machine.fail("mrjam-observe-services arbitrary-command > /tmp/observer-refusal-argument.json")
        machine.succeed("test ! -s /tmp/observer-refusal.json; test ! -s /tmp/observer-refusal-argument.json")
        machine.fail("systemctl is-active --quiet mrjam-observe-services.service")
        checks.append("immutable-code-only-observation-and-entrypoint-refusals")

    with subtest("restart preserves schema, secrets and existing repository files"):
        machine.succeed("runuser -u forgejo -- sh -c 'printf SYNTHETIC-REPOSITORY > /var/lib/forgejo/repositories/adoption-sentinel'")
        machine.succeed("sha256sum /var/lib/forgejo/custom/conf/* > /tmp/synthetic-secret-hashes")
        machine.succeed("systemctl restart forgejo.service")
        machine.wait_for_unit("forgejo.service")
        assert schema_hash() == baseline
        machine.succeed("sha256sum -c /tmp/synthetic-secret-hashes")
        assert machine.succeed("cat /var/lib/forgejo/repositories/adoption-sentinel").strip() == "SYNTHETIC-REPOSITORY"
        machine.succeed("systemctl stop forgejo.service")
        machine.succeed("systemctl is-active --quiet postgresql.service")
        checks.append("restart-retains-state-and-stop-preserves-postgresql")

    Path(os.environ["out"], "forgejo-postgresql-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "forgejo": "${forgejo.version}", "postgresql": "${pkgs.postgresql_17.version}",
        "schema_sha256": baseline, "production_qualification": False,
        "limitations": ["No real credentials, installed schema or SSO identity adopted", "No data migration or production restore qualified", "Explicit schema migrations require a separate local operator; the runtime role has no DDL privilege"]
    }, sort_keys=True) + "\n")
  '';
}
