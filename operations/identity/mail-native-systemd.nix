# Independent synthetic preservation test; no public networking or real state.
{ nixpkgs
, workers ? "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101"
, workerSource ? /nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source
, mailAdoption ? "/nix/store/7hmdar637aj6m80vrqma57g82pgqvbc1-mrjam-mail-native-adoption-2"
, tls ? /nix/store/qzbidvipgn2ip8mirxlcwry21mnvmvak-mrjam-identity-synthetic-tls
, acceleration ? "kvm"
}:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  ageFixture = pkgs.runCommand "synthetic-mail-archive-key" { nativeBuildInputs = [ pkgs.age ]; } ''
    mkdir -p "$out"
    age-keygen -o "$out/key" >/dev/null 2>&1
    age-keygen -y "$out/key" > "$out/recipient"
  '';
in assert builtins.elem acceleration [ "tcg" "kvm" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-native-mail-independent";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-vision-cycle.nix ../nixos/mrjam-vision-archive.nix
      ../hosts/mrjam-vps/state-adoption.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 2048;
    virtualisation.cores = 2;
    virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ];
    virtualisation.vlans = [ ];
    networking.useDHCP = lib.mkForce false;
    networking.dhcpcd.enable = false;
    networking.hosts."127.0.0.1" = [ "log.mrj.am" "smtp.protonmail.ch" ];
    system.extraDependencies = map builtins.storePath [ workers mailAdoption ];
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      extensions = ps: [ ps.pgvector ];
      settings.listen_addresses = lib.mkForce "127.0.0.1";
      authentication = lib.mkAfter ''
        local all all peer
        host all all 127.0.0.1/32 reject
        host all all ::1/128 reject
      '';
    };
    services.mrjamVisionCycle = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      smtpCredentialFile = "/var/lib/synthetic-mail-credentials/smtp.json";
      identityProtocol = "kanidm-native";
      kanidmCredentialFile = "/var/lib/synthetic-mail-credentials/cycle.token";
      kanidmCaFile = builtins.unsafeDiscardStringContext "${tls}/ca.pem";
      kanidmCaSha256 = builtins.hashFile "sha256" (tls + "/ca.pem");
    };
    services.mrjamVisionArchive = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      journalDatabase = "vision_journal"; ageRecipient = null;
      configurationCredentialFile = "/var/lib/synthetic-mail-credentials/archive.json";
      initializeConfigurationCredentialFile = "/var/lib/synthetic-mail-credentials/archive-initialize.json";
      smtpCredentialFile = "/var/lib/synthetic-mail-credentials/smtp.json";
      recipientCredentialFile = "/var/lib/synthetic-mail-credentials/recipient";
    };
    users.groups.mrjam-vision-archive.gid = 943;
    users.groups.mrjam-vision-cycle.gid = 945;
    users.users.mrjam-vision-archive.uid = 943;
    users.users.mrjam-vision-cycle.uid = 945;
    users.groups.mrjam-vision-admission.gid = 947;
    users.users.mrjam-vision-admission = { uid = 947; group = "mrjam-vision-admission"; isSystemUser = true; };
    users.groups.synthetic-legacy.gid = 984;
    users.users.synthetic-legacy = { uid = 984; group = "synthetic-legacy"; isSystemUser = true; };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.python3 pkgs.util-linux pkgs.age ];
    environment.variables.SYNTHETIC_AGE_PACKAGE = "${pkgs.age}";
    environment.etc."synthetic-age".source = ageFixture;
    environment.etc."mail-fixture.py".source = ./mail_fixture.py;
    environment.etc."workers_fixture.py".source = ./workers_fixture.py;
    environment.etc."identity-native-fixture/fixture.py".source = ./acceptance/fixture.py;
    environment.etc."identity-native-fixture/qualify.py".source = ./native-kanidm/qualify.py;
    environment.etc."native-adoption".source = ../migrations/admission-native;
    environment.etc."mail-adoption".source = ../migrations/mail-native;
    environment.etc."staging-helper/stage_adoption.py".source = ../deployment/stage_adoption.py;
    environment.etc."staging-helper/test_stage_adoption.py".source = ../deployment/test_stage_adoption.py;
    environment.etc."worker-sql/migrations".source = workerSource + "/migrations";
    environment.etc."worker-sql/journal".source = workerSource + "/journal";
    environment.etc."worker-sql/roles.sql".source = workerSource + "/scripts/roles.sql";
    systemd.services.synthetic-smtp-refusal.serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -B /etc/mail-fixture.py smtp-refuse";
      StandardOutput = "null"; StandardError = "journal";
    };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    helper = "python3 -B /etc/mail-fixture.py "
    units = ["mrjam-vision-cycle", "mrjam-vision-archive"]
    adopters = ["mrjam-cycle-mail-adopt", "mrjam-archive-mail-adopt"]
    checks = []

    with subtest("staging and adoption remain explicit"):
        for unit in units + adopters + ["mrjam-admission-native-adopt"]:
            machine.fail("systemctl is-active --quiet " + unit)
        machine.fail("test -e /var/lib/mrjam-vision-cycle/courriels.sqlite")
        machine.fail("test -e /var/lib/mrjam-vision-archive/courriels.sqlite")
        checks.append("no-implicit-initialization-or-start")

    with subtest("fixed source images include SQLite WAL commits and sealed metadata"):
        machine.succeed("python3 -I -S -m unittest discover -s /etc/staging-helper -p 'test_*.py'")
        machine.succeed("python3 -I -S -m unittest discover -s /etc/mail-adoption -p 'test_*.py'")
        machine.succeed(helper + "prepare")
        for unit in units:
            machine.succeed("systemctl stop " + unit)
        machine.succeed(helper + "stage")
        machine.succeed("systemctl start mrjam-admission-native-adopt.service")
        checks.append("stage-helper-six-tests-fixed-uid984-snapshots-and-mail29-tests")

    with subtest("actual sealed units preserve bytes proofs and optional markers"):
        for unit in adopters:
            machine.succeed("systemctl start " + unit)
        machine.succeed(helper + "check")
        machine.succeed(helper + "remember")
        for unit in adopters:
            machine.succeed("systemctl start " + unit)
        machine.succeed(helper + "unchanged")
        checks.append("real-systemd-publication-dedup-markers-stable-inode-and-idempotence")

    with subtest("new marker or colliding message refuses publication without effect"):
        machine.succeed(helper + "change-marker")
        machine.fail("systemctl start mrjam-cycle-mail-adopt.service")
        machine.succeed(helper + "unchanged")
        machine.succeed(helper + "restore")
        machine.succeed(helper + "change-collision")
        machine.fail("systemctl start mrjam-archive-mail-adopt.service")
        machine.succeed(helper + "unchanged")
        machine.succeed(helper + "restore")
        machine.succeed("systemctl reset-failed")
        checks.append("changed-marker-and-collision-atomic-refusal")

    with subtest("private archive initializer cannot truncate adopted state"):
        machine.succeed("systemctl start mrjam-vision-archive-initialize.service")
        machine.succeed(helper + "unchanged")
        machine.succeed("systemctl reset-failed")
        checks.append("private-initializer-preserves-adopted-state")

    with subtest("unchanged worker binaries drain old opaque queues without inventing erasure"):
        machine.succeed("systemctl start synthetic-smtp-refusal.service")
        for unit in units:
            machine.succeed("systemctl start " + unit)
        machine.succeed(helper + "retry")
        checks.append("actual-workers-resume-opaque-queues-on-smtp-refusal")

    with subtest("explicit invented mail receipt never acknowledges a SQL intention from its key alone"):
        machine.succeed(helper + "receive")
        for unit in units:
            machine.succeed("systemctl start " + unit)
        machine.succeed(helper + "received")
        checks.append("old-received-keys-and-markers-never-infer-sql-erasure")

    with subtest("private credential configuration and clean shutdown"):
        machine.succeed(helper + "no-leak")
        for unit in units + adopters + ["mrjam-admission-native-adopt", "synthetic-smtp-refusal"]:
            machine.succeed("systemctl stop " + unit)
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("private-archive-credential-no-diagnostic-leak-clean-shutdown")

    Path(os.environ["out"], "native-mail-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "independent-synthetic-native-mail", "checks": checks,
        "workers": "${workers}", "mail_adoption": "${mailAdoption}",
        "binaries": {name: machine.succeed("sha256sum ${workers}/bin/vision-" + name).split()[0] for name in ["cycle", "archive"]},
        "contract_sha256": "${builtins.hashFile "sha256" ./mail-contract.json}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./mail_fixture.py}",
        "test_sha256": "${builtins.hashFile "sha256" ./mail-native-systemd.nix}",
        "staging_sha256": "${builtins.hashFile "sha256" ../deployment/stage_adoption.py}",
        "state_adoption_module_sha256": "${builtins.hashFile "sha256" ../hosts/mrjam-vps/state-adoption.nix}",
        "archive_module_sha256": "${builtins.hashFile "sha256" ../nixos/mrjam-vision-archive.nix}",
        "cycle_module_sha256": "${builtins.hashFile "sha256" ../nixos/mrjam-vision-cycle.nix}",
        "production_access": False, "smtp_delivery_qualified": False, "offhost_archive_qualified": False,
        "limits": ["SMTP receipt explicitly simulated", "Markers are preserved without interpreting an unfinished production erasure"]
    }, sort_keys=True) + "\n")
  '';
}
