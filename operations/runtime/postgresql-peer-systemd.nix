# Local synthetic NixOS VM; no production generation, data or credential.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  rustSlot = {
    enable = true;
    artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-not-started-server";
    runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-not-started-runtime";
  };
in pkgs.testers.runNixOSTest {
  name = "mrjam-postgresql-peer-synthetic";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 900;
  nodes.machine = { pkgs, lib, ... }: {
    imports = [ ../nixos/mrjam-postgresql-access.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1024;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamRust = { enable = true; slots.blue = rustSlot; slots.green = rustSlot; };
    services.mrjamPostgresqlAccess = {
      enable = true;
      slots.blue = {
        mateval = { database = "synthetic_mateval"; role = "synthetic_mateval_app"; };
        vision = { database = "synthetic_vision"; role = "synthetic_vision_app"; };
      };
      slots.green.mateval = { database = "synthetic_mateval"; role = "synthetic_mateval_app"; };
    };
    users.groups.synthetic-outsider = { };
    users.users.synthetic-outsider = { isSystemUser = true; group = "synthetic-outsider"; };
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      ensureDatabases = [ "synthetic_mateval" "synthetic_vision" ];
      ensureUsers = [ { name = "synthetic_mateval_app"; } { name = "synthetic_vision_app"; } ];
      authentication = ''
        local all postgres peer
        local all all reject
        host all all 0.0.0.0/0 reject
        host all all ::/0 reject
      '';
    };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.util-linux ];
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql.service")
    machine.wait_for_unit("postgresql-setup.service")
    checks = []

    def query(user, role, database):
        return "runuser -u " + user + " -- psql -X -w --host=/run/postgresql --username=" + role + " --dbname=" + database + " --tuples-only --no-align --command='SELECT current_user'"

    with subtest("both slots authenticate as the same explicit role without a password"):
        for user in ("mrjam-rust-blue", "mrjam-rust-green"):
            assert machine.succeed(query(user, "synthetic_mateval_app", "synthetic_mateval")).strip() == "synthetic_mateval_app"
        checks.append("both-declared-uids-authenticate-with-peer")

    with subtest("a role declared only for blue remains inaccessible to green"):
        assert machine.succeed(query("mrjam-rust-blue", "synthetic_vision_app", "synthetic_vision")).strip() == "synthetic_vision_app"
        machine.fail(query("mrjam-rust-green", "synthetic_vision_app", "synthetic_vision"))
        checks.append("cross-slot-role-refused")

    with subtest("an undeclared Unix identity cannot select an application role"):
        for role, database in (("synthetic_mateval_app", "synthetic_mateval"), ("synthetic_vision_app", "synthetic_vision")):
            machine.fail(query("synthetic-outsider", role, database))
        checks.append("foreign-uid-refused")

    with subtest("no superuser role or foreign database is admitted by the map"):
        machine.fail(query("mrjam-rust-blue", "postgres", "postgres"))
        machine.fail(query("mrjam-rust-blue", "synthetic_mateval_app", "synthetic_vision"))
        checks.append("foreign-database-and-superuser-refused")

    with subtest("the Rust units remain unstarted and PostgreSQL remains private"):
        machine.fail("systemctl is-active --quiet mrjam-rust-blue.service")
        machine.fail("systemctl is-active --quiet mrjam-rust-green.service")
        machine.fail("psql -X -w --host=127.0.0.1 --username=synthetic_mateval_app --dbname=synthetic_mateval --command='SELECT current_user'")
        checks.append("no-implicit-rust-start-or-tcp-listener")

    Path(os.environ["out"], "peer-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "postgresql": "${pkgs.postgresql_17.version}", "production_qualification": False,
        "limitations": ["No application schema, real credential, installed VPS rule or resource reserve tested"]
    }, sort_keys=True) + "\n")
  '';
}
