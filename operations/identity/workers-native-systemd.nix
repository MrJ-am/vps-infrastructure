# Synthetic integration, independently specified in workers-contract.json.
{ nixpkgs
, workers ? "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101"
, workerSource ? /nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source
, admissionAdoption
, journalAdoption ? "/nix/store/v93w5mxbphq8ziy8iyrnajgi5ahvg4hn-mrjam-vision-kanidm-workers-0.1.0-native-20261101-journalAdoption"
, broker ? "/nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0"
, tls ? /nix/store/qzbidvipgn2ip8mirxlcwry21mnvmvak-mrjam-identity-synthetic-tls
, acceleration ? "kvm"
}:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  lib = pkgs.lib;
  kanidm = (import ../hosts/mrjam-vps/preserved-packages.nix { }).kanidm;
  publicCA = builtins.unsafeDiscardStringContext "${tls}/ca.pem";
  nativeOptions = capability: {
    identityProtocol = "kanidm-native";
    kanidmCredentialFile = "/var/lib/synthetic-worker-credentials/${capability}.token";
    kanidmCaFile = publicCA;
    kanidmCaSha256 = builtins.hashFile "sha256" (tls + "/ca.pem");
  };
  ageFixture = pkgs.runCommand "synthetic-worker-archive-key" { nativeBuildInputs = [ pkgs.age ]; } ''
    mkdir -p "$out"
    age-keygen -o "$out/key" >/dev/null 2>&1
    age-keygen -y "$out/key" > "$out/recipient"
  '';
in assert builtins.elem acceleration [ "tcg" "kvm" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-native-workers-independent";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1800;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-kanidm-host.nix ../nixos/mrjam-identity.nix
      ../nixos/mrjam-admission-adoption.nix ../nixos/mrjam-vision-cycle.nix
      ../nixos/mrjam-vision-closure.nix ../nixos/mrjam-vision-replay.nix ../nixos/mrjam-vision-archive.nix ];
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
    system.extraDependencies = map builtins.storePath [ workers admissionAdoption journalAdoption ];
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      extensions = ps: [ ps.pgvector ];
      settings.listen_addresses = lib.mkForce "127.0.0.1";
      authentication = lib.mkAfter ''
        local vision_journal vision_journal_import peer map=synthetic_journal_import
        local all all peer
        host all all 127.0.0.1/32 reject
        host all all ::1/128 reject
      '';
      identMap = lib.mkAfter "synthetic_journal_import synthetic-journal-import vision_journal_import\n";
    };
    services.mrjamKanidmHost = {
      enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${kanidm}";
    };
    services.mrjamIdentity = {
      enable = true; uid = 984; gid = 984; readersGid = 940; startAtBoot = false;
      artifactStorePath = builtins.unsafeDiscardStringContext broker;
      principalRegistration = { uid = 947; gid = 947; };
    };
    services.mrjamVisionAdmission = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; admissionsOpen = false;
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
      closureCredentialFile = "/var/lib/synthetic-worker-credentials/closure";
      approvalCredentialFile = "/var/lib/synthetic-worker-credentials/approval";
    } // nativeOptions "admission";
    services.mrjamAdmissionAdoption = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext admissionAdoption;
    };
    specialisation.open.configuration = {
      services.mrjamVisionAdmission.admissionsOpen = lib.mkForce true;
      services.mrjamAdmissionAdoption.enable = lib.mkForce false;
    };
    services.mrjamVisionCycle = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
    } // nativeOptions "cycle";
    services.mrjamVisionReplay = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      admissionsCredentialFile = "/var/lib/synthetic-worker-credentials/closure";
    } // nativeOptions "replay";
    services.mrjamVisionClosure = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      admissionsCredentialFile = "/var/lib/synthetic-worker-credentials/closure";
    };
    services.mrjamVisionArchive = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      journalDatabase = "vision_journal";
      ageRecipient = lib.removeSuffix "\n" (builtins.readFile "${ageFixture}/recipient");
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
      recipientCredentialFile = "/var/lib/synthetic-worker-credentials/archive-recipient";
    };
    users.groups.mrjam-vision-archive.gid = 943;
    users.groups.mrjam-vision-replay.gid = 944;
    users.groups.mrjam-vision-cycle.gid = 945;
    users.groups.mrjam-vision-closure.gid = 946;
    users.groups.mrjam-vision-admission.gid = 947;
    users.users.mrjam-vision-archive.uid = 943;
    users.users.mrjam-vision-replay.uid = 944;
    users.users.mrjam-vision-cycle.uid = 945;
    users.users.mrjam-vision-closure.uid = 946;
    users.users.mrjam-vision-admission.uid = 947;
    users.groups.synthetic-journal-import.gid = 948;
    users.users.synthetic-journal-import = { uid = 948; group = "synthetic-journal-import"; isSystemUser = true; };
    security.pki.certificateFiles = [ "${tls}/ca.pem" ];
    environment.systemPackages = [ kanidm pkgs.postgresql_17 pkgs.python3 pkgs.curl pkgs.util-linux pkgs.age ];
    environment.variables.SYNTHETIC_KANIDM_PACKAGE = "${kanidm}";
    environment.etc."synthetic-identity-tls".source = tls;
    environment.etc."synthetic-age".source = ageFixture;
    environment.etc."workers-fixture.py".source = ./workers_fixture.py;
    environment.etc."workers-journal-fixture.py".source = ./workers_journal_fixture.py;
    environment.etc."workers_fixture.py".source = ./workers_fixture.py;
    environment.etc."identity-native-fixture/fixture.py".source = ./acceptance/fixture.py;
    environment.etc."identity-native-fixture/qualify.py".source = ./native-kanidm/qualify.py;
    environment.etc."identity-native-fixture/legacy-state.sql".source = ./acceptance/legacy-state.sql;
    environment.etc."native-adoption".source = ../migrations/admission-native;
    environment.etc."worker-sql/migrations".source = workerSource + "/migrations";
    environment.etc."worker-sql/journal".source = workerSource + "/journal";
    environment.etc."worker-sql/roles.sql".source = workerSource + "/scripts/roles.sql";
    environment.etc."synthetic-kanidm-init.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm-init.toml"
      (config.services.mrjamKanidmHost.settings // {
        tls_chain = "${tls}/fullchain.pem"; tls_key = "${tls}/key.pem";
        adminbindpath = "/run/synthetic-kanidm-init/admin.sock";
      });
    systemd.services.synthetic-kanidm-init.serviceConfig = {
      ExecStart = "${kanidm}/bin/kanidmd server -c /etc/synthetic-kanidm-init.toml";
      User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm"; RuntimeDirectory = "synthetic-kanidm-init";
      UMask = "0077"; StandardOutput = "null"; StandardError = "null";
    };
    systemd.services.synthetic-smtp-refusal.serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -B /etc/workers-fixture.py smtp-refuse";
      StandardOutput = "null"; StandardError = "journal";
    };
    systemd.services.vision-journal-adoption.serviceConfig = {
      Type = "oneshot"; User = "synthetic-journal-import"; Group = "synthetic-journal-import";
      ExecStart = "${journalAdoption}/bin/vision-journal-adoption";
      LoadCredential = map (name: "${name}:/var/lib/synthetic-worker-credentials/"
        + (if name == "sources" then "journal-sources" else if name == "configuration" then "journal-configuration" else name))
        [ "sources" "configuration" "journal-lisp" "journal-cycle" "journal-fermeture" ];
      NoNewPrivileges = true; ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true;
      PrivateNetwork = true; RestrictAddressFamilies = [ "AF_UNIX" ];
      StandardOutput = "journal"; StandardError = "journal"; UMask = "0077";
    };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    helper = "python3 -B /etc/workers-fixture.py "
    journal = "python3 -B /etc/workers-journal-fixture.py "
    native_health = "curl --silent --fail --noproxy '*' --cacert /etc/synthetic-identity-tls/ca.pem --resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status"
    broker_health = "curl --silent --fail --noproxy '*' http://127.0.0.1:3002/readyz"
    checks = []
    units = ["mrjam-vision-" + name for name in ["admission", "cycle", "closure", "replay", "archive"]]

    with subtest("staged workers and native adoption have no automatic start"):
        for unit in units + ["mrjam-admission-adoption", "mrjam-identity", "vision-journal-adoption"]:
            machine.fail("systemctl is-active --quiet " + unit)
        machine.succeed("systemctl stop kanidm.service")
        machine.fail("test -e /var/lib/mrjam-vision-admission/admissions.sqlite")
        checks.append("staged-without-auto-start")

    with subtest("fresh SQL and real provider contain only invented state"):
        machine.succeed(helper + "prepare-sql")
        machine.succeed("systemctl start synthetic-kanidm-init.service")
        machine.wait_until_succeeds(native_health, timeout=120)
        machine.succeed("systemctl stop synthetic-kanidm-init.service")
        machine.succeed("install -d -m 0700 /var/lib/acme/log.mrj.am")
        machine.succeed("install -m 0400 /etc/synthetic-identity-tls/key.pem /var/lib/acme/log.mrj.am/key.pem")
        machine.succeed("install -m 0444 /etc/synthetic-identity-tls/fullchain.pem /var/lib/acme/log.mrj.am/fullchain.pem")
        machine.succeed("systemctl reset-failed")
        machine.succeed("systemctl start kanidm.service")
        machine.wait_until_succeeds(native_health, timeout=120)
        machine.succeed(helper + "prepare-native")
        machine.succeed(helper + "capabilities")
        machine.succeed("systemctl start synthetic-smtp-refusal.service")
        checks.append("real-native-provider-distinct-disposable-worker-tokens")

    with subtest("native adoption preserves enrolment and opaque mail proofs"):
        machine.succeed("python3 -I -S -m unittest discover -s /etc/native-adoption -p 'test_*.py'")
        machine.succeed(helper + "prepare-adoption")
        machine.succeed("systemctl start mrjam-admission-adoption.service")
        machine.succeed(helper + "check-adoption")
        machine.succeed("systemctl start mrjam-admission-adoption.service")
        machine.succeed(helper + "check-adoption")
        machine.succeed("systemctl start mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "readiness", timeout=30)
        machine.succeed(helper + "closed")
        checks.append("native-adoption-24-tests-and-sealed-systemd-publication")

    with subtest("confirmed admission resumes one person and one invitation through broker peer registration"):
        machine.succeed("systemctl stop mrjam-vision-admission.service")
        machine.succeed("/run/current-system/specialisation/open/bin/switch-to-configuration test")
        machine.succeed("systemctl start mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "readiness", timeout=30)
        machine.succeed(helper + "request-admission")
        machine.succeed("systemctl restart mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "partial", timeout=45)
        machine.succeed("systemctl stop mrjam-vision-admission.service")
        machine.succeed("systemctl start mrjam-identity.service")
        machine.wait_until_succeeds(broker_health, timeout=30)
        machine.succeed("systemctl start mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "completed", timeout=45)
        machine.succeed("systemctl restart mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "readiness", timeout=30)
        machine.succeed(helper + "completed")
        machine.succeed(helper + "enrolment")
        checks.append("real-person-mail-enrolment-resume-with-exact-uid947-and-single-invitation")

    with subtest("native cycle mail refusal cannot start a deadline or erase content"):
        machine.succeed("systemctl start mrjam-vision-cycle-initialize.service")
        machine.succeed(helper + "cycle-begin")
        machine.succeed("systemctl start mrjam-vision-cycle.service")
        machine.succeed(helper + "cycle-pending")
        machine.succeed(helper + "cycle-receipt")
        machine.succeed("systemctl start mrjam-vision-cycle.service")
        machine.succeed(helper + "cycle-due")
        machine.succeed("systemctl start mrjam-vision-cycle.service")
        machine.succeed(helper + "cycle-archive-pending")
        machine.succeed("systemctl start mrjam-vision-archive-initialize.service")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed(helper + "archive-pending")
        checks.append("native-mail-smtp-refusal-deadline-and-archive-gates")

    with subtest("explicit invented archive receipt permits only the due account erasure"):
        machine.succeed(helper + "cycle-archive-receipt")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed("systemctl start mrjam-vision-cycle.service")
        machine.succeed(helper + "cycle-erased")
        machine.succeed("systemctl start mrjam-vision-cycle.service")
        machine.succeed(helper + "cycle-erased")
        checks.append("cycle-scoped-idempotent-erasure-after-explicit-synthetic-receipt")

    with subtest("native closure survives purge interruption and replay removes only its native person"):
        machine.succeed("systemctl start mrjam-vision-closure.service")
        machine.wait_for_unit("mrjam-vision-closure.service")
        machine.succeed(helper + "closure-request")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed(helper + "archive-pending")
        machine.succeed(helper + "closure-archive-receipt")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed("systemctl stop mrjam-vision-admission.service")
        machine.succeed(helper + "closure-partial")
        machine.succeed("systemctl restart mrjam-vision-closure.service")
        machine.succeed("systemctl start mrjam-vision-admission.service")
        machine.wait_until_succeeds(helper + "readiness", timeout=30)
        machine.succeed("systemctl start mrjam-vision-replay.service")
        machine.succeed(helper + "closure-erased")
        machine.succeed("systemctl start mrjam-vision-replay.service")
        machine.succeed(helper + "closure-erased")
        checks.append("closure-partial-effect-and-native-replay-idempotence")

    with subtest("sealed journal adoption preserves both issuers, epochs and receipts"):
        machine.succeed(journal + "prepare")
        machine.succeed("systemctl start vision-journal-adoption.service")
        machine.succeed(journal + "imported")
        machine.succeed("systemctl start vision-journal-adoption.service")
        machine.succeed(journal + "imported")
        machine.succeed(journal + "collision")
        machine.fail("systemctl start vision-journal-adoption.service")
        machine.succeed(journal + "refused")
        machine.succeed(journal + "ambiguous")
        machine.fail("systemctl start vision-journal-adoption.service")
        machine.succeed(journal + "refused")
        checks.append("journal-native-legacy-epoch-idempotence-and-atomic-collision-refusal")

    with subtest("closed diagnostics and explicit service shutdown"):
        machine.succeed(helper + "no-secret-journal")
        for unit in units + ["mrjam-identity", "kanidm", "synthetic-smtp-refusal", "vision-journal-adoption"]:
            machine.succeed("systemctl stop " + unit)
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("no-private-diagnostics-clean-shutdown")

    Path(os.environ["out"], "native-workers-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "independent-synthetic-native-workers", "checks": checks,
        "workers": "${workers}", "broker": "${broker}", "worker_source": "${workerSource}",
        "binaries": {name: machine.succeed("sha256sum ${workers}/bin/vision-" + name).split()[0]
                     for name in ["admission", "cycle", "closure", "replay", "archive"]},
        "contract_sha256": "${builtins.hashFile "sha256" ./workers-contract.json}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./workers_fixture.py}",
        "test_sha256": "${builtins.hashFile "sha256" ./workers-native-systemd.nix}",
        "journal_fixture_sha256": "${builtins.hashFile "sha256" ./workers_journal_fixture.py}",
        "journal_adoption_sha256": machine.succeed("sha256sum ${journalAdoption}/bin/vision-journal-adoption").split()[0],
        "production_access": False, "smtp_delivery_qualified": False, "offhost_archive_qualified": False,
        "limits": ["SMTP and archive receipts explicitly simulated", "No production state or human MFA"]
    }, sort_keys=True) + "\n")
  '';
}
