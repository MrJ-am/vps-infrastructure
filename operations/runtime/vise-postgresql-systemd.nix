# Local synthetic NixOS/TCG test. The shell fixture is not the ViSe application.
# No VPS data, real database, backup, credential or production capacity claim.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  syntheticVise = pkgs.runCommand "mrjam-vise-synthetic-unit-fixture" { } ''
    mkdir -p "$out/dist"
    cat > "$out/server" <<'SCRIPT'
    #!${pkgs.runtimeShell}
    set -eu
    printf '%s\n' 'SYNTHETIC-LEDGER-NOT-APPLICATION-DATA' > "$CARNET_DELETION_LEDGER"
    exec ${pkgs.coreutils}/bin/sleep infinity
    SCRIPT
    chmod 0555 "$out/server"
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-vise-postgresql-composition-synthetic";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 900;
  nodes.machine = { pkgs, lib, ... }: {
    imports = [ ../nixos/mrjam-vise.nix ../nixos/mrjam-postgresql-access.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamVise = {
      enable = true; adoption = { uid = 978; gid = 978; };
      # Fixture closure explicitly installed below; never a production approval.
      artifactRoot = builtins.unsafeDiscardStringContext "${syntheticVise}";
    };
    services.mrjamRust = {
      enable = true;
      slots.blue = { enable = true;
        artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-not-started-server";
        runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-not-started-runtime";
      };
    };
    services.mrjamPostgresqlAccess = {
      enable = true;
      slots.blue.mateval = { database = "synthetic_mateval"; role = "synthetic_mateval_app"; };
    };
    users.groups.synthetic-outsider = { };
    users.users.synthetic-outsider = { isSystemUser = true; group = "synthetic-outsider"; };
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      enableTCPIP = true; settings.listen_addresses = lib.mkForce "127.0.0.1";
      ensureDatabases = [ "etp_carnet" "synthetic_mateval" ];
      ensureUsers = [ { name = "etp_carnet"; } { name = "synthetic_mateval_app"; } { name = "synthetic-outsider"; } ];
      # Intentionally permissive fallback: tests prove dedicated denials win.
      # These rules belong only to this disposable guest, not the host module.
      authentication = ''
        local all postgres peer
        local all all peer
        host all all 127.0.0.1/32 trust
      '';
    };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.util-linux syntheticVise ];
    environment.etc."synthetic-vise-schema.sql".source = ../vise/schema-v1.sql;
    environment.etc."synthetic-vise-adopt-role.sql".source = ../vise/adopt-runtime-role.sql;
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql.service")
    machine.wait_for_unit("postgresql-setup.service")
    checks = []

    def query(user, role, database, host="/run/postgresql"):
        return "runuser -u " + user + " -- psql -X -w --host=" + host + " --username=" + role + " --dbname=" + database + " --tuples-only --no-align --command='SELECT current_user'"

    with subtest("both independent applications authenticate through their own peer rule"):
        assert machine.succeed(query("etp_carnet", "etp_carnet", "etp_carnet")).strip() == "etp_carnet"
        assert machine.succeed(query("mrjam-rust-blue", "synthetic_mateval_app", "synthetic_mateval")).strip() == "synthetic_mateval_app"
        checks.append("vise-and-rust-peer-authenticate")

    with subtest("ViSe cannot open another database despite the permissive fallback"):
        machine.fail(query("etp_carnet", "etp_carnet", "synthetic_mateval"))
        machine.fail(query("etp_carnet", "etp_carnet", "postgres"))
        checks.append("vise-other-databases-refused")

    with subtest("neither application may impersonate the other or PostgreSQL"):
        machine.fail(query("mrjam-rust-blue", "etp_carnet", "etp_carnet"))
        machine.fail(query("etp_carnet", "synthetic_mateval_app", "synthetic_mateval"))
        machine.fail(query("etp_carnet", "postgres", "postgres"))
        checks.append("cross-application-and-superuser-roles-refused")

    with subtest("the unrelated Unix identity cannot acquire either role"):
        machine.fail(query("synthetic-outsider", "etp_carnet", "etp_carnet"))
        machine.fail(query("synthetic-outsider", "synthetic_mateval_app", "synthetic_mateval"))
        checks.append("undeclared-unix-identity-refused")

    with subtest("ViSe TCP is rejected before a working trust fallback"):
        assert machine.succeed(query("synthetic-outsider", "synthetic-outsider", "postgres", "127.0.0.1")).strip() == "synthetic-outsider"
        machine.fail(query("etp_carnet", "etp_carnet", "etp_carnet", "127.0.0.1"))
        checks.append("vise-tcp-refused-with-live-listener-and-trust-fallback")

    with subtest("staged units and backup remain unstarted"):
        machine.fail("systemctl is-active --quiet vise.service")
        machine.fail("systemctl is-active --quiet mrjam-rust-blue.service")
        machine.fail("systemctl cat vise-backup.service")
        machine.fail("systemctl cat vise-backup.timer")
        checks.append("no-automatic-application-start-or-vise-backup")

    with subtest("explicit fixture start exercises the declared identity and private state"):
        machine.fail("systemctl start vise.service")
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-vise-schema.sql")
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-vise-adopt-role.sql")
        machine.succeed("install -d -m 0700 -o etp_carnet -g etp_carnet /var/lib/etp-carnet; install -m 0600 -o etp_carnet -g etp_carnet /dev/null /var/lib/etp-carnet/deletions.log; systemctl reset-failed")
        machine.succeed("systemctl start vise.service")
        machine.wait_for_unit("vise.service")
        machine.wait_until_succeeds("test -f /var/lib/etp-carnet/deletions.log")
        assert machine.succeed("stat -c '%u:%g:%a' /var/lib/etp-carnet").strip() == "978:978:700"
        assert machine.succeed("stat -c '%u:%g:%a' /var/lib/etp-carnet/deletions.log").strip() == "978:978:600"
        assert machine.succeed("id -G etp_carnet").strip() == "978"
        machine.fail("runuser -u synthetic-outsider -- cat /var/lib/etp-carnet/deletions.log")
        assert machine.succeed("systemctl show vise.service -p NoNewPrivileges --value").strip() == "yes"
        checks.append("real-systemd-identity-private-state-and-no-new-privileges")

    with subtest("stopping the fixture leaves unrelated PostgreSQL operational"):
        machine.succeed("systemctl stop vise.service")
        machine.succeed(query("mrjam-rust-blue", "synthetic_mateval_app", "synthetic_mateval"))
        checks.append("vise-stop-preserves-shared-postgresql")

    Path(os.environ["out"], "vise-peer-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "postgresql": "${pkgs.postgresql_17.version}", "production_qualification": False,
        "limitations": ["Shell unit fixture, not the ViSe application", "No real schema, crypto format, backup/restore, installed VPS state or resource reserve tested"]
    }, sort_keys=True) + "\n")
  '';
}
