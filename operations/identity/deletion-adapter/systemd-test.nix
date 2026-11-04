{ nixpkgs
, adapter ? "/nix/store/vxq44jamqwldh4q9j3xv50znz42lqg27-mrjam-identity-deletion-0.1.0-transport2"
, replay ? "/nix/store/cp5rsnp0iqyd4j1k815b40avhz5jgp6h-mrjam-vision-delete-replay-0.1.0"
, workers ? "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101"
, workerSource ? /nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source
, broker ? "/nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0"
, tls ? /nix/store/qzbidvipgn2ip8mirxlcwry21mnvmvak-mrjam-identity-synthetic-tls
, acceleration ? "kvm"
}:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  kanidm = (import ../../hosts/mrjam-vps/preserved-packages.nix { }).kanidm;
  ageFixture = pkgs.runCommand "synthetic-delete-adapter-age" { nativeBuildInputs = [ pkgs.age ]; } ''
    mkdir -p "$out"
    age-keygen -o "$out/key" >/dev/null 2>&1
    age-keygen -y "$out/key" > "$out/recipient"
  '';
  wrongCA = pkgs.runCommand "synthetic-delete-adapter-other-ca" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    mkdir -p "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=InventedOtherCA \
      -keyout key.pem -out "$out/ca.pem" >/dev/null 2>&1
  '';
in assert builtins.elem acceleration [ "kvm" "tcg" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-native-delete-unix-independent";
  requiredFeatures.kvm = acceleration == "kvm"; qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../../nixos/mrjam-kanidm-host.nix ../../nixos/mrjam-identity.nix
      ../../nixos/mrjam-vision-admission.nix ../../nixos/mrjam-vision-closure.nix
      ../../nixos/mrjam-vision-archive.nix ../../nixos/mrjam-vision-replay.nix ../../nixos/mrjam-identity-deletion.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 2048; virtualisation.cores = 2; virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ]; virtualisation.vlans = [ ];
    networking.useDHCP = lib.mkForce false; networking.dhcpcd.enable = false;
    networking.hosts."127.0.0.1" = [ "log.mrj.am" "smtp.protonmail.ch" ];
    system.extraDependencies = map builtins.storePath [ adapter replay workers broker ];
    services.postgresql = { enable = true; package = pkgs.postgresql_17; extensions = ps: [ ps.pgvector ];
      authentication = lib.mkAfter "local all all peer\nhost all all 127.0.0.1/32 reject\nhost all all ::1/128 reject\n"; };
    services.mrjamKanidmHost = { enable = true; uid = 983; gid = 983;
      artifactStorePath = builtins.unsafeDiscardStringContext "${kanidm}"; };
    services.mrjamIdentity = { enable = true; uid = 984; gid = 984; readersGid = 940;
      artifactStorePath = builtins.unsafeDiscardStringContext broker; };
    services.mrjamVisionAdmission = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; admissionsOpen = false;
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
      closureCredentialFile = "/var/lib/synthetic-worker-credentials/closure";
      approvalCredentialFile = "/var/lib/synthetic-worker-credentials/approval";
      identityProtocol = "kanidm-native";
      kanidmCredentialFile = "/var/lib/synthetic-worker-credentials/admission.token";
      kanidmCaFile = builtins.unsafeDiscardStringContext "${tls}/ca.pem";
      kanidmCaSha256 = builtins.hashFile "sha256" (tls + "/ca.pem");
    };
    services.mrjamVisionClosure = { enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      admissionsCredentialFile = "/var/lib/synthetic-worker-credentials/closure"; };
    services.mrjamVisionArchive = { enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      journalDatabase = "vision_journal";
      ageRecipient = lib.removeSuffix "\n" (builtins.readFile "${ageFixture}/recipient");
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
      recipientCredentialFile = "/var/lib/synthetic-worker-credentials/archive-recipient"; };
    services.mrjamVisionReplay = { enable = true; artifactStorePath = builtins.unsafeDiscardStringContext replay;
      visionDatabase = "vision"; journalDatabase = "vision_journal"; identityProtocol = "kanidm-delete-socket";
      admissionsCredentialFile = "/var/lib/synthetic-worker-credentials/closure"; };
    services.mrjamIdentityDeletion = { enable = true; artifactStorePath = builtins.unsafeDiscardStringContext adapter;
      kanidmCaFile = builtins.unsafeDiscardStringContext "${tls}/ca.pem";
      kanidmCaSha256 = builtins.hashFile "sha256" (tls + "/ca.pem"); };
    users.groups.mrjam-vision-archive.gid = 943; users.users.mrjam-vision-archive.uid = 943;
    users.groups.mrjam-vision-replay.gid = 944; users.users.mrjam-vision-replay.uid = 944;
    users.groups.mrjam-vision-closure.gid = 946; users.users.mrjam-vision-closure.uid = 946;
    users.groups.mrjam-vision-admission.gid = 947; users.users.mrjam-vision-admission.uid = 947;
    users.users.synthetic-other = { uid = 949; group = "mrjam-vision-replay"; isSystemUser = true; };
    security.pki.certificateFiles = [ "${tls}/ca.pem" ];
    environment.systemPackages = [ kanidm pkgs.postgresql_17 pkgs.python3 pkgs.curl pkgs.util-linux pkgs.age pkgs.iproute2 ];
    environment.variables.SYNTHETIC_KANIDM_PACKAGE = "${kanidm}";
    environment.etc."synthetic-identity-tls".source = tls;
    environment.etc."synthetic-age".source = ageFixture;
    environment.etc."delete-adapter-fixture.py".source = ./fixture.py;
    environment.etc."workers_fixture.py".source = ../workers_fixture.py;
    environment.etc."workers-fixture.py".source = ../workers_fixture.py;
    environment.etc."identity-native-fixture/fixture.py".source = ../acceptance/fixture.py;
    environment.etc."identity-native-fixture/qualify.py".source = ../native-kanidm/qualify.py;
    environment.etc."identity-native-fixture/legacy-state.sql".source = ../acceptance/legacy-state.sql;
    environment.etc."native-adoption".source = ../../migrations/admission-native;
    environment.etc."worker-sql/migrations".source = workerSource + "/migrations";
    environment.etc."worker-sql/journal".source = workerSource + "/journal";
    environment.etc."worker-sql/roles.sql".source = workerSource + "/scripts/roles.sql";
    environment.etc."synthetic-kanidm-init.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm-init.toml"
      (config.services.mrjamKanidmHost.settings // { tls_chain = "${tls}/fullchain.pem"; tls_key = "${tls}/key.pem";
        adminbindpath = "/run/synthetic-kanidm-init/admin.sock"; });
    systemd.services.synthetic-kanidm-init.serviceConfig = {
      ExecStart = "${kanidm}/bin/kanidmd server -c /etc/synthetic-kanidm-init.toml";
      User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm"; RuntimeDirectory = "synthetic-kanidm-init";
      UMask = "0077"; StandardOutput = "null"; StandardError = "null"; };
    systemd.services.synthetic-smtp-refusal.serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -B /etc/workers-fixture.py smtp-refuse";
      StandardOutput = "null"; StandardError = "journal"; };
    specialisation.badDigest.configuration.services.mrjamIdentityDeletion.kanidmCaSha256 = lib.mkForce (lib.concatStrings (lib.replicate 64 "0"));
    specialisation.badCA.configuration.services.mrjamIdentityDeletion = {
      kanidmCaFile = lib.mkForce (builtins.unsafeDiscardStringContext "${wrongCA}/ca.pem");
      kanidmCaSha256 = lib.mkForce (builtins.hashFile "sha256" "${wrongCA}/ca.pem"); };
    specialisation.spy.configuration.systemd.services.kanidm.serviceConfig.ExecStart = lib.mkForce
      "${pkgs.python3}/bin/python3 -B /etc/delete-adapter-fixture.py spy";
  };
  testScript = ''
    import json, os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    base = machine.succeed("readlink -f /run/current-system").strip()
    helper = "python3 -B /etc/delete-adapter-fixture.py "
    worker = "python3 -B /etc/workers-fixture.py "
    health = "curl --silent --fail --noproxy '*' --cacert /etc/synthetic-identity-tls/ca.pem --resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status"
    checks = []
    def adapter_start():
        # An explicit-only unit may never have been loaded; reset-failed then
        # returns1. Its real start and socket readiness remain mandatory.
        reset_status, _ = machine.execute("systemctl reset-failed mrjam-identity-deletion")
        assert reset_status in (0, 1)
        machine.succeed("systemctl start mrjam-identity-deletion")
        machine.wait_until_succeeds("test -S /run/mrjam-identity-deletion/delete.sock", timeout=30)
        machine.wait_until_succeeds(helper + "ready", timeout=30)

    with subtest("staged modules and real invented provider"):
        for unit in ["mrjam-identity-deletion", "mrjam-vision-replay", "mrjam-vision-admission"]:
            machine.fail("systemctl is-active --quiet " + unit)
        machine.succeed(worker + "prepare-sql")
        machine.succeed("systemctl start synthetic-kanidm-init")
        machine.wait_until_succeeds(health, timeout=120)
        machine.succeed("systemctl stop synthetic-kanidm-init")
        machine.succeed("install -d -m0700 /var/lib/acme/log.mrj.am")
        machine.succeed("install -m0400 /etc/synthetic-identity-tls/key.pem /var/lib/acme/log.mrj.am/key.pem")
        machine.succeed("install -m0444 /etc/synthetic-identity-tls/fullchain.pem /var/lib/acme/log.mrj.am/fullchain.pem")
        machine.succeed("systemctl start kanidm")
        machine.wait_until_succeeds(health, timeout=120)
        machine.succeed(worker + "prepare-native")
        machine.succeed(helper + "prepare")
        adapter_start()
        machine.succeed(helper + "metadata")
        checks.append("real-native-provider-uid948-peer944-and-private-systemd-credential")

    with subtest("wrong peers and arbitrary commands cannot delete"):
        machine.succeed(helper + "negatives")
        machine.succeed(helper + "preserved")
        checks.append("root-other-peer-reset-list-group-token-path-framing-and-size-refusals")

    with subtest("actual network outage never claims deletion"):
        machine.succeed("ip link set lo down")
        machine.succeed(helper + "unavailable")
        machine.succeed("ip link set lo up")
        machine.wait_until_succeeds(health, timeout=30)
        machine.succeed(helper + "preserved")
        checks.append("provider-outage-unavailable-and-target-preserved")

    with subtest("CA fingerprint and chain are enforced"):
        machine.succeed("systemctl stop mrjam-identity-deletion")
        machine.succeed(base + "/specialisation/badDigest/bin/switch-to-configuration test")
        machine.execute("systemctl start mrjam-identity-deletion")
        machine.wait_until_fails("systemctl is-active --quiet mrjam-identity-deletion", timeout=15)
        assert machine.succeed("systemctl show mrjam-identity-deletion -p ExecMainStatus --value").strip() != "0"
        machine.succeed("systemctl stop mrjam-identity-deletion")
        machine.succeed(base + "/specialisation/badCA/bin/switch-to-configuration test")
        adapter_start()
        machine.succeed(helper + "unavailable")
        machine.succeed(helper + "preserved")
        machine.succeed("systemctl stop mrjam-identity-deletion")
        machine.succeed(base + "/bin/switch-to-configuration test")
        checks.append("wrong-ca-digest-start-refusal-and-untrusted-chain-no-deletion")

    with subtest("TLS wire exposes exactly the single validated DELETE"):
        machine.succeed("systemctl stop kanidm")
        machine.succeed(base + "/specialisation/spy/bin/switch-to-configuration test")
        machine.succeed("systemctl start kanidm")
        machine.wait_until_succeeds("test -f /var/lib/kanidm/adapter-spy.json", timeout=20)
        adapter_start()
        machine.succeed(helper + "spy-check")
        machine.succeed("systemctl stop mrjam-identity-deletion kanidm")
        machine.succeed(base + "/bin/switch-to-configuration test")
        machine.succeed("systemctl start kanidm")
        machine.wait_until_succeeds(health, timeout=30)
        adapter_start()
        machine.succeed(helper + "preserved")
        machine.succeed(helper + "deleted")
        checks.append("zero-upstream-calls-on-refusal-exact-delete-and-real-idempotent-person-erasure")

    with subtest("journal-gated replay holds only Unix deletion capability"):
        machine.succeed("systemctl start synthetic-smtp-refusal")
        machine.succeed("systemctl start mrjam-vision-admission-initialize mrjam-vision-archive-initialize")
        machine.succeed("systemctl start mrjam-vision-admission mrjam-vision-closure")
        machine.wait_until_succeeds(worker + "readiness", timeout=30)
        machine.succeed(helper + "closure-start")
        machine.succeed("systemctl start mrjam-vision-archive")
        machine.succeed(worker + "archive-pending")
        machine.succeed(worker + "closure-archive-receipt")
        machine.succeed("systemctl start mrjam-vision-archive")
        machine.succeed("systemctl stop mrjam-vision-admission")
        machine.succeed(helper + "closure-partial")
        machine.succeed("systemctl start mrjam-vision-admission")
        machine.wait_until_succeeds(worker + "readiness", timeout=30)
        machine.succeed("systemctl start mrjam-vision-replay")
        machine.succeed(helper + "replayed")
        machine.succeed("systemctl start mrjam-vision-replay")
        machine.succeed(helper + "replayed")
        checks.append("real-archive-gate-interrupted-purge-socket-replay-and-idempotent-journal-receipt")

    with subtest("no private diagnostics and explicit shutdown"):
        machine.succeed(helper + "no-leak")
        for unit in ["mrjam-vision-admission", "mrjam-vision-closure", "mrjam-vision-archive", "mrjam-vision-replay", "mrjam-identity-deletion", "synthetic-smtp-refusal", "kanidm"]:
            machine.succeed("systemctl stop " + unit)
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("no-private-diagnostics-no-provider-token-to-replay-clean-shutdown")

    Path(os.environ["out"], "delete-adapter-result.json").write_text(json.dumps({
        "schema_version": 1, "checks": checks, "adapter": "${adapter}", "replay": "${replay}", "kanidm": "${kanidm}",
        "adapter_sha256": machine.succeed("sha256sum ${adapter}/bin/mrjam-identity-deletion").split()[0],
        "replay_sha256": machine.succeed("sha256sum ${replay}/bin/vision-replay").split()[0],
        "contract_sha256": "${builtins.hashFile "sha256" ./contract.json}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./fixture.py}",
        "test_sha256": "${builtins.hashFile "sha256" ./systemd-test.nix}",
        "adapter_module_sha256": "${builtins.hashFile "sha256" ../../nixos/mrjam-identity-deletion.nix}",
        "replay_module_sha256": "${builtins.hashFile "sha256" ../../nixos/mrjam-vision-replay.nix}",
        "production_access": False, "smtp_delivery_qualified": False,
        "limits": ["Upstream people_admins credential broader than Unix capability", "SMTP archive receipt explicitly simulated", "No production or protected-governance authority"]
    }, sort_keys=True) + "\n")
  '';
}
