# Functional proof for an existing ELF; never converts its missing capability to ready.
{ nixpkgs
, server ? "/nix/store/hf08v9mbbr9hrjzp5j53691zv0b5dvq5-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a"
, assets ? "/nix/store/6gnyzs532bakw4lp5kr8apyd4i8pgla3-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-vision"
, workers ? "/nix/store/kbqmlal53czby17lpdycp8x2bhfiw7an-mrjam-vision-kanidm-workers-0.1.0-native-20261101"
, workerSource ? /nix/store/l7ckaann5dkj10bincrx635nsxkxhd01-source
, broker ? "/nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0"
, tls ? /nix/store/qzbidvipgn2ip8mirxlcwry21mnvmvak-mrjam-identity-synthetic-tls
, acceleration ? "kvm"
}:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  kanidm = (import ../hosts/mrjam-vps/preserved-packages.nix { }).kanidm;
  database = name: role: {
    transport = { kind = "unix"; directory = "/run/postgresql"; };
    database = name; username = role; password_file = null; schema = "public"; maximum_connections = 2;
  };
  configuration = capabilities: {
    schema_version = 1; public_hosts = [ "vision.mrj.am" ]; required_capabilities = capabilities;
    assets = [{ host = "vision.mrj.am"; mount = "/"; payload_prefix = ""; directory = assets;
      manifest_sha256 = "a0dfbd1c1674277adfe4606ba16f5919a731fc3c98d8d8672a8dce85a6d5815a"; }];
    identity = { protocol = "mrj-auth-v1"; endpoint = "127.0.0.1:3002"; };
    vision = { database = database "vision" "vision";
      public_mcp_url = "https://vision.mrj.am/mcp"; public_web_url = "https://vision.mrj.am";
      deletion_journal = database "vision_journal" "vision_journal_writer";
      embeddings = null; administration_database = null; admission_approval_credential_file = null;
    };
    mateval = null; audition = null; log = null;
  };
  runtime = capabilities: pkgs.runCommand "synthetic-deletion-runtime" {
    json = builtins.toJSON (configuration capabilities); passAsFile = [ "json" ];
  } ''
    mkdir -p "$out"
    cp "$jsonPath" "$out/runtime.json"
  '';
  baseRuntime = runtime [ "static-assets" ];
  requiredRuntime = runtime [ "static-assets" "vision-account-deletion" ];
  ageFixture = pkgs.runCommand "synthetic-http-deletion-key" { nativeBuildInputs = [ pkgs.age ]; } ''
    mkdir -p "$out"
    age-keygen -o "$out/key" >/dev/null 2>&1
    age-keygen -y "$out/key" > "$out/recipient"
  '';
in assert builtins.elem acceleration [ "tcg" "kvm" ]; pkgs.testers.runNixOSTest {
  name = "mrjam-existing-server-native-deletion";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-kanidm-host.nix ../nixos/mrjam-identity.nix
      ../nixos/mrjam-vision-replay.nix ../nixos/mrjam-vision-archive.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 2048; virtualisation.cores = 2; virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    virtualisation.qemu.networkingOptions = lib.mkForce [ ]; virtualisation.vlans = [ ];
    networking.useDHCP = lib.mkForce false; networking.dhcpcd.enable = false;
    networking.hosts."127.0.0.1" = [ "log.mrj.am" "smtp.protonmail.ch" ];
    system.extraDependencies = map builtins.storePath [ server assets workers broker ] ++ [ baseRuntime requiredRuntime ];
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17; extensions = ps: [ ps.pgvector ];
      settings.listen_addresses = lib.mkForce "127.0.0.1";
      authentication = lib.mkAfter ''
        local all all peer
        host all all 127.0.0.1/32 reject
        host all all ::1/128 reject
      '';
    };
    services.mrjamKanidmHost = { enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${kanidm}"; };
    services.mrjamIdentity = { enable = true; uid = 984; gid = 984; readersGid = 940;
      artifactStorePath = builtins.unsafeDiscardStringContext broker; startAtBoot = false; };
    services.mrjamRust = { enable = true; slots.blue = { enable = true;
      artifactStorePath = builtins.unsafeDiscardStringContext server;
      runtimeConfigStorePath = builtins.unsafeDiscardStringContext "${baseRuntime}"; }; };
    services.mrjamPostgresqlAccess.slots.blue = {
      vision = { database = "vision"; role = "vision"; };
      visionJournal = { database = "vision_journal"; role = "vision_journal_writer"; };
    };
    services.mrjamVisionReplay = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      visionDatabase = "vision"; journalDatabase = "vision_journal";
      admissionsCredentialFile = "/var/lib/synthetic-worker-credentials/closure";
      identityProtocol = "kanidm-native";
      kanidmCredentialFile = "/var/lib/synthetic-worker-credentials/replay.token";
      kanidmCaFile = builtins.unsafeDiscardStringContext "${tls}/ca.pem";
      kanidmCaSha256 = builtins.hashFile "sha256" (tls + "/ca.pem");
    };
    services.mrjamVisionArchive = {
      enable = true; artifactStorePath = builtins.unsafeDiscardStringContext workers;
      journalDatabase = "vision_journal";
      ageRecipient = lib.removeSuffix "\n" (builtins.readFile "${ageFixture}/recipient");
      smtpCredentialFile = "/var/lib/synthetic-worker-credentials/smtp.json";
      recipientCredentialFile = "/var/lib/synthetic-worker-credentials/archive-recipient";
    };
    users.groups.mrjam-rust-blue.gid = 941; users.users.mrjam-rust-blue.uid = 941;
    users.groups.mrjam-vision-archive.gid = 943; users.users.mrjam-vision-archive.uid = 943;
    users.groups.mrjam-vision-replay.gid = 944; users.users.mrjam-vision-replay.uid = 944;
    security.pki.certificateFiles = [ "${tls}/ca.pem" ];
    environment.systemPackages = [ kanidm pkgs.postgresql_17 pkgs.python3 pkgs.curl pkgs.util-linux pkgs.age ];
    environment.variables.SYNTHETIC_KANIDM_PACKAGE = "${kanidm}";
    environment.variables.SYNTHETIC_SERVER = "${server}/bin/mrjam-server";
    environment.variables.SYNTHETIC_REQUIRED_CONFIG = "${requiredRuntime}/runtime.json";
    environment.etc."synthetic-identity-tls".source = tls;
    environment.etc."synthetic-age".source = ageFixture;
    environment.etc."deletion-required".source = requiredRuntime;
    environment.etc."deletion-fixture.py".source = ./deletion_fixture.py;
    environment.etc."workers_fixture.py".source = ./workers_fixture.py;
    environment.etc."workers-fixture.py".source = ./workers_fixture.py;
    environment.etc."identity-native-fixture/fixture.py".source = ./acceptance/fixture.py;
    environment.etc."identity-native-fixture/qualify.py".source = ./native-kanidm/qualify.py;
    environment.etc."identity-native-fixture/legacy-state.sql".source = ./acceptance/legacy-state.sql;
    environment.etc."native-adoption".source = ../migrations/admission-native;
    environment.etc."worker-sql/migrations".source = workerSource + "/migrations";
    environment.etc."worker-sql/journal".source = workerSource + "/journal";
    environment.etc."worker-sql/roles.sql".source = workerSource + "/scripts/roles.sql";
    environment.etc."synthetic-kanidm-init.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm-init.toml"
      (config.services.mrjamKanidmHost.settings // { tls_chain = "${tls}/fullchain.pem"; tls_key = "${tls}/key.pem";
        adminbindpath = "/run/synthetic-kanidm-init/admin.sock"; });
    systemd.services.synthetic-kanidm-init.serviceConfig = {
      ExecStart = "${kanidm}/bin/kanidmd server -c /etc/synthetic-kanidm-init.toml";
      User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm"; RuntimeDirectory = "synthetic-kanidm-init";
      UMask = "0077"; StandardOutput = "null"; StandardError = "null";
    };
    systemd.services.synthetic-smtp-refusal.serviceConfig = {
      ExecStart = "${pkgs.python3}/bin/python3 -B /etc/workers-fixture.py smtp-refuse";
      StandardOutput = "null"; StandardError = "journal";
    };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    helper = "python3 -B /etc/deletion-fixture.py "
    worker = "python3 -B /etc/workers-fixture.py "
    native_health = "curl --silent --fail --noproxy '*' --cacert /etc/synthetic-identity-tls/ca.pem --resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status"
    ready = "curl --silent --fail --noproxy '*' -H 'Host: vision.mrj.am' http://127.0.0.1:38101/readyz"
    checks = []

    with subtest("native provider and unchanged server are staged explicitly"):
        for unit in ["mrjam-rust-blue", "mrjam-identity", "mrjam-vision-archive", "mrjam-vision-replay"]:
            machine.fail("systemctl is-active --quiet " + unit)
        machine.succeed("systemctl stop kanidm.service")
        machine.succeed(worker + "prepare-sql")
        machine.succeed("systemctl start synthetic-kanidm-init.service")
        machine.wait_until_succeeds(native_health, timeout=120)
        machine.succeed("systemctl stop synthetic-kanidm-init.service")
        machine.succeed("install -d -m 0700 /var/lib/acme/log.mrj.am")
        machine.succeed("install -m 0400 /etc/synthetic-identity-tls/key.pem /var/lib/acme/log.mrj.am/key.pem")
        machine.succeed("install -m 0444 /etc/synthetic-identity-tls/fullchain.pem /var/lib/acme/log.mrj.am/fullchain.pem")
        machine.succeed("systemctl reset-failed")
        machine.succeed("systemctl start kanidm.service")
        machine.wait_until_succeeds(native_health, timeout=120)
        machine.succeed(worker + "prepare-native")
        print(machine.succeed(helper + "provider-self"))
        machine.succeed(helper + "prepare")
        machine.succeed("systemctl start mrjam-identity.service")
        machine.wait_until_succeeds("curl --silent --fail http://127.0.0.1:3002/readyz", timeout=30)
        machine.succeed("systemctl start mrjam-rust-blue.service")
        machine.wait_until_succeeds(ready, timeout=30)
        checks.append("real-native-provider-and-received-server-elf")

    with subtest("missing readiness capability remains observable and unchanged"):
        machine.succeed(helper + "readiness-limitation")
        checks.append("required-deletion-capability-still-refused")

    with subtest("real native session enforces public deletion guards"):
        machine.succeed(helper + "login")
        machine.succeed(helper + "guards")
        checks.append("real-native-session-origin-csrf-confirmation-and-owner-guards")

    with subtest("durable pending intention preserves content across restart"):
        machine.succeed(helper + "pending")
        machine.succeed("systemctl restart mrjam-rust-blue.service")
        machine.wait_until_succeeds(ready, timeout=30)
        machine.succeed(helper + "pending")
        checks.append("public-http202-durable-intention-no-early-erasure")

    with subtest("actual encrypted archive remains pending on SMTP refusal"):
        machine.succeed("systemctl start synthetic-smtp-refusal.service")
        machine.succeed("systemctl start mrjam-vision-archive-initialize.service")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed(helper + "archive-pending")
        checks.append("actual-age-archive-smtp-refusal-cannot-acknowledge")

    with subtest("actual archiver receipt permits scoped HTTP deletion"):
        machine.succeed(worker + "cycle-archive-receipt")
        machine.succeed("systemctl start mrjam-vision-archive.service")
        machine.succeed(helper + "deleted")
        checks.append("http200-after-explicit-synthetic-receipt-only-own-vision-account-erased")

    with subtest("native replay records exact receipt and retains common identity"):
        machine.succeed("systemctl start mrjam-vision-replay.service")
        machine.succeed(helper + "replayed")
        machine.succeed("systemctl start mrjam-vision-replay.service")
        machine.succeed(helper + "replayed")
        machine.succeed(helper + "readiness-limitation")
        checks.append("real-replay-idempotent-receipt-common-identity-and-survivor-preserved")

    with subtest("private diagnostics and explicit shutdown"):
        machine.succeed(helper + "no-leak")
        for unit in ["mrjam-rust-blue", "mrjam-identity", "mrjam-vision-archive", "mrjam-vision-replay", "synthetic-smtp-refusal", "kanidm"]:
            machine.succeed("systemctl stop " + unit)
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("no-private-diagnostics-and-clean-shutdown")

    Path(os.environ["out"], "native-deletion-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "unchanged-server-native-http-deletion", "checks": checks,
        "server": "${server}", "server_sha256": machine.succeed("sha256sum ${server}/bin/mrjam-server").split()[0],
        "broker": "${broker}", "workers": "${workers}",
        "contract_sha256": "${builtins.hashFile "sha256" ./deletion-contract.json}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./deletion_fixture.py}",
        "test_sha256": "${builtins.hashFile "sha256" ./deletion-native-systemd.nix}",
        "native_self_shape": json.loads(machine.succeed("cat /run/native-self-shape.json")),
        "production_access": False, "smtp_delivery_qualified": False, "offhost_archive_qualified": False,
        "deletion_required_capability_accepted": False,
        "limits": ["Existing ELF still rejects required vision-account-deletion", "Synthetic SMTP receipt only", "No complete deployment readiness or protected authority"]
    }, sort_keys=True) + "\n")
  '';
}
