{ nixpkgs, acceleration ? "kvm" }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../../forgejo/locked-toolchain.nix { };
  forgejo = locked.forgejo;
  package = pkgs.callPackage ./package.nix { forgejoUid = 982; forgejoGid = 982; };
in assert builtins.elem acceleration [ "kvm" "tcg" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-forgejo-closed-technical-bootstrap";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../../nixos/mrjam-forgejo-host.nix ./module.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536; virtualisation.cores = 2; virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ]; virtualisation.vlans = [ ];
    networking.useDHCP = lib.mkForce false; networking.dhcpcd.enable = false;
    services.mrjamForgejoHost = { enable = true; uid = 982; gid = 982;
      artifactStorePath = builtins.unsafeDiscardStringContext "${forgejo}"; };
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "forgejo" ];
      ensureUsers = [{ name = "forgejo"; ensureDBOwnership = true; }];
    };
    environment.systemPackages = [ package forgejo pkgs.postgresql_17 pkgs.git pkgs.python3 pkgs.curl pkgs.util-linux ];
    environment.variables.SYNTHETIC_BOOTSTRAP_PACKAGE = "${package}";
    environment.variables.SYNTHETIC_FORGEJO_PACKAGE = "${forgejo}";
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini { }).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = { SECRET_KEY = "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"; INTERNAL_TOKEN = "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"; };
        oauth2.JWT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."forgejo-adopt-runtime-role.sql".source = ../../forgejo/adopt-runtime-role.sql;
    environment.etc."synthetic-forgejo-policy/reconcile.py".source = ../../forgejo/reconcile.py;
    environment.etc."forgejo-bootstrap-fixture.py".source = ./fixture.py;
    environment.etc."forgejo-bootstrap-tests/core.py".source = ./core.py;
    environment.etc."forgejo-bootstrap-tests/test_core.py".source = ./test_core.py;
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    helper = "python3 -B /etc/forgejo-bootstrap-fixture.py "
    checks = []
    with subtest("explicit staging and closed unit tests"):
        machine.fail("systemctl is-active --quiet forgejo.service")
        machine.fail("systemctl is-active --quiet mrjam-forgejo-bootstrap.service")
        machine.fail("systemctl is-active --quiet mrjam-forgejo-probe.service")
        machine.succeed("python3 -I -S -B -m unittest discover -s /etc/forgejo-bootstrap-tests -p 'test_*.py'")
        setup_status, _ = machine.execute(helper + "prepare")
        if setup_status:
            raise AssertionError(machine.succeed("cat /var/lib/synthetic-forgejo-proof/migration-error"))
        machine.succeed("systemctl start forgejo.service")
        machine.wait_for_open_port(3004)
        checks.append("staged-real-forgejo17-postgresql17-and-19-closed-tests")

    with subtest("absent service account and old SSO identity remain unmodified"):
        machine.succeed(helper + "absent")
        checks.append("absence-reported-without-personal-fallback-or-created-token")

    with subtest("explicit technical bootstrap with no public password or token"):
        machine.succeed("systemctl start mrjam-forgejo-bootstrap.service")
        machine.succeed(helper + "bootstrap")
        machine.succeed("systemctl start mrjam-forgejo-probe.service")
        checks.append("real-systemd-bootstrap-and-read-probe-idempotence")

    with subtest("valid invented local passwords cannot log in through Basic or Web"):
        machine.succeed(helper + "password-routes")
        checks.append("real-valid-local-password-basic-and-web-login-refused")

    with subtest("scoped internal lease enables existing nine-repository reconciler"):
        machine.succeed(helper + "seed")
        checks.append("scoped-token-real-nine-repository-source-and-protection-controller")

    with subtest("closed probe preserves other repository and personal identities"):
        machine.succeed(helper + "populated")
        machine.succeed("systemctl start mrjam-forgejo-probe.service")
        checks.append("nine-closed-metadata-observations-and-other-state-preserved")

    with subtest("interrupted lease is revoked idempotently from a nonsecret journal"):
        machine.succeed(helper + "interrupted")
        checks.append("interrupted-token-recovery-and-actual-authentication-refusal")

    with subtest("closed invocation permissions diagnostics and clean shutdown"):
        machine.fail("mrjam-forgejo-probe arbitrary-input")
        machine.fail("runuser -u nobody -- mrjam-forgejo-probe")
        machine.succeed(helper + "no-leak")
        for unit in ["mrjam-forgejo-probe", "mrjam-forgejo-bootstrap", "forgejo"]:
            machine.succeed("systemctl stop " + unit)
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("root-only-noargs-no-private-diagnostics-and-shutdown")

    Path(os.environ["out"], "forgejo-bootstrap-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "isolated-invented-forgejo17-postgresql17", "checks": checks,
        "package": "${package}", "forgejo": "${forgejo}",
        "forgejo_uid": 982, "forgejo_gid": 982,
        "core_sha256": "${builtins.hashFile "sha256" ./core.py}",
        "test_sha256": "${builtins.hashFile "sha256" ./systemd-test.nix}",
        "unit_tests_sha256": "${builtins.hashFile "sha256" ./test_core.py}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./fixture.py}",
        "module_sha256": "${builtins.hashFile "sha256" ./module.nix}",
        "probe": json.loads(machine.succeed("cat /var/lib/synthetic-forgejo-proof/probe-result.json")),
        "production_access": False, "protected_governance_authority": False,
        "limits": ["No current production account or repository state inferred", "Source seed is invented public text, not production source adoption"]
    }, sort_keys=True) + "\n")
  '';
}
