# Independent regression: exact failed production closure unit, invented SQL/data.
{ nixpkgs ? /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  source = /nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source;
  closureUnit = /nix/store/l0gfw9rfbiqf6b7avagaki5ym8jl238z-unit-mrjam-vision-closure.service/mrjam-vision-closure.service;
  closureConfig = builtins.storePath "/nix/store/lrmqxvywhy6m61p5rayfmbxmbjk0i8h9-mrjam-vision-closure.json";
  workers = builtins.storePath "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101";
in pkgs.testers.runNixOSTest {
  name = "mrjam-journal-namespace-closure-regression";
  requiredFeatures.kvm = true;
  globalTimeout = 900;
  nodes.machine = { lib, ... }: {
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    virtualisation.diskSize = 4096;
    virtualisation.vlans = [ ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ];
    networking.useDHCP = lib.mkForce false;
    networking.dhcpcd.enable = false;
    users.groups.mrjam-vision-closure.gid = 946;
    users.users.mrjam-vision-closure = { uid = 946; group = "mrjam-vision-closure"; isSystemUser = true; };
    users.groups.synthetic-journal-writer.gid = 941;
    users.users.synthetic-journal-writer = { uid = 941; group = "synthetic-journal-writer"; isSystemUser = true; };
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      extensions = ps: [ ps.pgvector ];
      enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      authentication = lib.mkForce ''
        local all postgres peer
        local vision vision_fermeture peer map=synthetic_closure
        local vision_journal vision_journal_fermeture peer map=synthetic_closure
        local vision_journal vision_journal_writer peer map=synthetic_writer
        local all all reject
      '';
      identMap = ''
        synthetic_closure mrjam-vision-closure vision_fermeture
        synthetic_closure mrjam-vision-closure vision_journal_fermeture
        synthetic_writer synthetic-journal-writer vision_journal_writer
      '';
    };
    # Literal immutable unit, including ExecStartPre, sandbox and LoadCredential.
    systemd.units."mrjam-vision-closure.service".text = builtins.readFile closureUnit;
    system.extraDependencies = [ workers closureConfig ];
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.python3 pkgs.util-linux pkgs.curl ];
    environment.etc."journal-closure-fixture.py".source = ./journal_closure_fixture.py;
    environment.etc."synthetic-worker-source".source = source;
    environment.etc."synthetic-journal-bootstrap".source = ./journal-bootstrap;
    environment.etc."synthetic-journal-correction.sql".source = ./journal-public-schema-usage.sql;
  };
  testScript = ''
    import json, os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql.service")
    helper = "python3 -I /etc/journal-closure-fixture.py "
    checks = []
    with subtest("literal closure unit and config are retained without startup"):
        machine.fail("systemctl is-active --quiet mrjam-vision-closure.service")
        machine.succeed("cmp /etc/systemd/system/mrjam-vision-closure.service ${closureUnit}")
        machine.succeed(helper + "prepare")
        checks.append("exact-production-unit-config-credential-path")
    with subtest("historical bootstrap reproduces the pre-start failure"):
        machine.fail("systemctl start mrjam-vision-closure.service")
        machine.succeed(helper + "old-failure")
        checks.append("historical-bootstrap-execstartpre-exit1-no-server")
    with subtest("minimal grant allows exact check-local and serve"):
        machine.succeed(helper + "correct")
        machine.succeed("systemctl reset-failed mrjam-vision-closure.service")
        machine.succeed("systemctl start mrjam-vision-closure.service")
        machine.wait_for_open_port(3028)
        machine.succeed(helper + "running")
        checks.append("corrected-bootstrap-check-local-serve-loopback")
    with subtest("namespace permission does not grant table or function access"):
        machine.succeed(helper + "boundaries")
        checks.append("no-create-no-direct-tables-no-importer-or-public-expansion")
    with subtest("grant is idempotent and only addresses the dedicated journal"):
        machine.succeed(helper + "repeat-and-wrong-database")
        machine.succeed("systemctl restart mrjam-vision-closure.service")
        machine.wait_for_open_port(3028)
        machine.succeed(helper + "running")
        checks.append("idempotent-correction-wrong-database-refused")
    with subtest("exact writer catalogue predicate passes under peer identity"):
        machine.succeed(helper + "writer")
        checks.append("actual-writer-predicate-peer-no-broad-table-rights")
    machine.succeed("systemctl stop mrjam-vision-closure.service")
    machine.succeed(helper + "no-events")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"checks":checks,"production_access":False,
      "closure_unit_sha256":"${builtins.hashFile "sha256" closureUnit}",
      "closure_config_sha256":"${builtins.hashFile "sha256" closureConfig}",
      "correction_sha256":"${builtins.hashFile "sha256" ./journal-public-schema-usage.sql}",
      "fixture_sha256":"${builtins.hashFile "sha256" ./journal_closure_fixture.py}",
      "test_sha256":"${builtins.hashFile "sha256" ./journal-closure-systemd.nix}",
      "limits":["Invented database and credential only", "Exact writer SQL predicate, not full Rust readiness or SSO", "No external SMTP or generation switch"]
    },sort_keys=True)+"\n")
  '';
}
