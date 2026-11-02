# Independent synthetic guest: real native identity, peer SQL and projected aliases.
{ nixpkgs, artifact ? "/nix/store/1n0p3fn7nfdbwvpkbqlnk7y13057mivk-mrjam-identity-0.1.0", acceleration ? "tcg" }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  package = (import ../hosts/mrjam-vps/preserved-packages.nix { }).kanidm;
  tls = pkgs.runCommand "mrjam-identity-synthetic-tls" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    mkdir -p "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=MRJAM-INDEPENDENT-SYNTHETIC \
      -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign \
      -keyout ca-key.pem -out "$out/ca.pem" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -noenc -subj /CN=log.mrj.am \
      -keyout "$out/key.pem" -out request.pem >/dev/null 2>&1
    printf '%s\n' 'subjectAltName=DNS:log.mrj.am' 'basicConstraints=critical,CA:FALSE' \
      'keyUsage=critical,digitalSignature,keyEncipherment' 'extendedKeyUsage=serverAuth' > extensions
    openssl x509 -req -in request.pem -CA "$out/ca.pem" -CAkey ca-key.pem -CAcreateserial -days 3650 \
      -extfile extensions -out "$out/fullchain.pem" >/dev/null 2>&1
  '';
in assert builtins.elem acceleration [ "tcg" "kvm" ];
pkgs.testers.runNixOSTest {
  name = "mrjam-identity-native-systemd-synthetic";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-kanidm-host.nix ../nixos/mrjam-identity.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 2048;
    virtualisation.cores = 2;
    virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      settings.listen_addresses = lib.mkForce "127.0.0.1";
      authentication = lib.mkAfter ''
        local all all peer
        host all all 127.0.0.1/32 reject
        host all all ::1/128 reject
      '';
    };
    services.mrjamKanidmHost = {
      enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${package}";
    };
    services.mrjamIdentity = {
      enable = true; uid = 984; gid = 984; readersGid = 940; startAtBoot = false;
      artifactStorePath = builtins.unsafeDiscardStringContext artifact;
      principalRegistration = { uid = 947; gid = 947; };
    };
    users.groups.mrjam-vision-admission.gid = 947;
    users.groups.synthetic-outsider.gid = 949;
    users.users.mrjam-vision-admission = { uid = 947; group = "mrjam-vision-admission"; isSystemUser = true; };
    users.users.wrong-admission = { uid = 948; group = "mrjam-vision-admission"; isSystemUser = true; };
    users.users.alias-reader = { uid = 941; group = "mrjam-log-readers"; isSystemUser = true; };
    users.users.synthetic-outsider = { uid = 949; group = "synthetic-outsider"; isSystemUser = true; };
    security.pki.certificateFiles = [ "${tls}/ca.pem" ];
    environment.systemPackages = [ package pkgs.postgresql_17 pkgs.python3 pkgs.openssl pkgs.curl pkgs.util-linux ];
    environment.variables.SYNTHETIC_KANIDM_PACKAGE = "${package}";
    environment.etc."synthetic-identity-tls".source = tls;
    environment.etc."identity-runtime-fixture.py".source = ./runtime_fixture.py;
    environment.etc."identity-native-fixture/fixture.py".source = ./acceptance/fixture.py;
    environment.etc."identity-native-fixture/qualify.py".source = ./native-kanidm/qualify.py;
    environment.etc."identity-native-fixture/legacy-state.sql".source = ./acceptance/legacy-state.sql;
    environment.etc."identity-native-fixture/principals.sql".source = ./acceptance/principals.sql;
    environment.etc."synthetic-kanidm-init.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm-init.toml"
      (config.services.mrjamKanidmHost.settings // {
        tls_chain = "${tls}/fullchain.pem"; tls_key = "${tls}/key.pem";
        adminbindpath = "/run/synthetic-kanidm-init/admin.sock";
      });
    systemd.services.synthetic-kanidm-init.serviceConfig = {
      ExecStart = "${package}/bin/kanidmd server -c /etc/synthetic-kanidm-init.toml";
      User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm"; RuntimeDirectory = "synthetic-kanidm-init";
      UMask = "0077"; StandardOutput = "null"; StandardError = "null";
    };
    # Test assertions execute inside the unchanged production sandbox and identity.
    systemd.services.mrjam-identity.preStart = ''
      ${pkgs.python3}/bin/python3 -B /etc/identity-runtime-fixture.py prove-credential
    '';
    systemd.services.mrjam-identity-aliases.preStart = ''
      ${pkgs.python3}/bin/python3 -B /etc/identity-runtime-fixture.py prove-readonly
    '';
    systemd.services.synthetic-alias-reader = {
      serviceConfig = {
        Type = "oneshot"; User = "alias-reader"; Group = "mrjam-log-readers";
        ExecStart = "${pkgs.python3}/bin/python3 -B /etc/identity-runtime-fixture.py watch-projection";
        RuntimeDirectory = "synthetic-alias-reader"; RuntimeDirectoryPreserve = true;
        RuntimeDirectoryMode = "0700"; StandardOutput = "null"; StandardError = "null";
        TimeoutStartSec = 45;
      };
    };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("postgresql.service")
    helper = "python3 -B /etc/identity-runtime-fixture.py "
    peer = "runuser -u mrjam-metier -- psql -X -w -h /run/postgresql -U vision_identite "
    native_health = "curl --silent --fail --noproxy '*' --cacert /etc/synthetic-identity-tls/ca.pem --resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status"
    broker_health = "curl --silent --fail --noproxy '*' http://127.0.0.1:3002/readyz"
    checks = []

    with subtest("staged identity and projection have no boot activation or state bootstrap"):
        for unit in ["mrjam-identity.service", "mrjam-identity-aliases.service", "mrjam-identity-aliases.timer"]:
            machine.fail("systemctl is-active --quiet " + unit)
        machine.fail("systemctl start mrjam-identity.service")
        machine.fail("test -e /var/lib/mrjam-metier/log/sessions.sqlite")
        machine.succeed("systemctl stop kanidm.service")
        checks.append("staged-no-auto-start-or-sqlite-bootstrap")

    with subtest("explicit installation creates only invented PostgreSQL SQLite native state and credentials"):
        machine.succeed("runuser -u postgres -- createdb vision")
        machine.succeed(helper + "prepare-state")
        machine.succeed("systemctl reset-failed")
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
        checks.append("explicit-invented-state-and-real-native-provider")

    with subtest("LoadCredential uses retained UID without exposing the source secret or changing source state"):
        start_status, _start_output = machine.execute("systemctl start mrjam-identity.service")
        if start_status != 0:
            raise AssertionError(machine.succeed("cat /run/mrjam-identity/fixture-error-code /run/mrjam-identity/credential-metadata.json"))
        print(machine.succeed("cat /run/mrjam-identity/credential-metadata.json"))
        machine.wait_for_unit("mrjam-identity.service")
        machine.wait_until_succeeds(broker_health, timeout=60)
        machine.succeed("test -s /run/mrjam-identity/credential-proof")
        machine.succeed(helper + "check-adoption")
        assert machine.succeed("systemctl show mrjam-identity.service -p User --value").strip() == "mrjam-metier"
        assert machine.succeed("id -u mrjam-metier").strip() == "984"
        machine.fail("runuser -u mrjam-metier -- test -r /var/lib/mrjam-identite/kanidm-vision.secret")
        for unit in ["mrjam-identity.service", "mrjam-identity-aliases.service"]:
            assert machine.succeed("systemctl show " + unit + " -p StandardOutput --value").strip() == "null"
            assert machine.succeed("systemctl show " + unit + " -p StandardError --value").strip() == "null"
        checks.append("load-credential-retained-uid-no-ddl-no-bulk-chown")

    with subtest("SQL access is limited to the peer identity role and its fixed function"):
        assert machine.succeed(peer + "-d vision -Atc \"SELECT (vision_gestion.identifier('https://log.mrj.am/oauth2/openid/mrjam-vision','11111111-1111-4111-8111-111111111111')->>'actif')::boolean::int\"").strip() == "1"
        machine.fail(peer + "-d postgres -Atc 'SELECT 1'")
        machine.fail(peer + "-d vision -Atc 'SELECT * FROM public.synthetic_principals'")
        machine.fail("runuser -u alias-reader -- psql -X -w -h /run/postgresql -U vision_identite -d vision -Atc 'SELECT 1'")
        machine.fail("runuser -u mrjam-metier -- psql -X -w -h 127.0.0.1 -U vision_identite -d vision -Atc 'SELECT 1'")
        checks.append("postgresql-peer-only-exact-role-and-function")

    with subtest("projection reads a protected source and exposes only aliases to its reader group"):
        machine.succeed("systemctl start mrjam-identity-aliases.service")
        machine.succeed("runuser -u alias-reader -- " + helper + "check-projection-two")
        machine.succeed(helper + "check-adoption")
        assert machine.succeed("stat -c '%u:%g:%a' /run/mrjam-identity/aliases.sqlite").strip() == "984:940:640"
        for user in ["mrjam-vision-admission", "wrong-admission", "synthetic-outsider"]:
            machine.fail("runuser -u " + user + " -- test -r /run/mrjam-identity/aliases.sqlite")
        for user in ["alias-reader", "mrjam-vision-admission", "synthetic-outsider"]:
            machine.fail("runuser -u " + user + " -- test -r /var/lib/mrjam-metier/log/sessions.sqlite")
        checks.append("readonly-source-minimal-0640-projection-reader-group-only")

    with subtest("Unix registration rejects another UID even with the authorized socket group"):
        assert machine.succeed("stat -c '%u:%g:%a' /run/mrjam-identity/admission.sock").strip() == "984:947:660"
        machine.succeed("runuser -u wrong-admission -- " + helper + "wrong-registration")
        machine.succeed("runuser -u alias-reader -- " + helper + "check-projection-two")
        machine.succeed(helper + "check-adoption")
        checks.append("registration-exact-peer-uid-beyond-group-dac")

    with subtest("admission updates aliases while an existing reader keeps the same SQLite inode"):
        inode = machine.succeed("stat -c %i /run/mrjam-identity/aliases.sqlite").strip()
        machine.succeed("systemctl start --no-block synthetic-alias-reader.service")
        machine.wait_until_succeeds("test -s /run/synthetic-alias-reader/opened", timeout=20)
        machine.succeed("runuser -u mrjam-vision-admission -- " + helper + "register")
        machine.succeed(helper + "check-registration")
        machine.succeed("systemctl start mrjam-identity-aliases.service")
        machine.wait_until_succeeds("test -s /run/synthetic-alias-reader/observed", timeout=20)
        assert machine.succeed("stat -c %i /run/mrjam-identity/aliases.sqlite").strip() == inode
        machine.succeed("runuser -u alias-reader -- " + helper + "check-projection-three")
        machine.succeed(helper + "custom-policy")
        machine.succeed("runuser -u mrjam-vision-admission -- " + helper + "register")
        machine.succeed(helper + "check-custom-policy")
        checks.append("registration-idempotence-retained-policy-stable-inode-live-reader")

    with subtest("real native login and process restart retain session credentials privately"):
        machine.succeed(helper + "native-login")
        source_owners = machine.succeed("stat -c '%u:%g:%a' /var/lib/mrjam-metier/log/sessions.sqlite /var/lib/mrjam-metier/unrelated-owner-marker").strip()
        inode = machine.succeed("stat -c %i /run/mrjam-identity/aliases.sqlite").strip()
        machine.succeed("systemctl restart mrjam-identity.service")
        machine.wait_until_succeeds(broker_health, timeout=60)
        machine.succeed(helper + "after-restart")
        machine.succeed("systemctl start mrjam-identity-aliases.service")
        assert machine.succeed("stat -c %i /run/mrjam-identity/aliases.sqlite").strip() == inode
        assert machine.succeed("stat -c '%u:%g:%a' /var/lib/mrjam-metier/log/sessions.sqlite /var/lib/mrjam-metier/unrelated-owner-marker").strip() == source_owners
        machine.succeed(helper + "no-secret-journal")
        checks.append("native-session-and-projection-survive-restart-without-secret-diagnostics")

    with subtest("periodic projection activates only after an explicit timer start"):
        machine.fail("systemctl is-active --quiet mrjam-identity-aliases.timer")
        machine.succeed("systemctl start mrjam-identity-aliases.timer")
        machine.wait_for_unit("mrjam-identity-aliases.timer")
        machine.succeed("systemctl stop mrjam-identity-aliases.timer")
        machine.wait_until_succeeds("test \"$(systemctl show mrjam-identity-aliases.service -p ActiveState --value)\" = inactive", timeout=30)
        assert machine.succeed("systemctl show mrjam-identity-aliases.service -p ExecMainStatus --value").strip() == "0"
        machine.succeed("systemctl stop mrjam-identity.service")
        machine.succeed("systemctl stop kanidm.service")
        for unit in ["mrjam-identity.service", "mrjam-identity-aliases.service", "kanidm.service"]:
            assert machine.succeed("systemctl show " + unit + " -p ActiveState --value").strip() == "inactive"
            assert machine.succeed("systemctl show " + unit + " -p MainPID --value").strip() == "0"
        checks.append("explicit-start-and-stop-of-periodic-projection")

    Path(os.environ["out"], "identity-runtime-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-systemd-native-identity-peer-projection-registration",
        "checks": checks, "artifact": "${artifact}", "production_access": False,
        "artifact_sha256": machine.succeed("sha256sum ${artifact}/bin/mrjam-identity").split()[0],
        "module_sha256": "${builtins.hashFile "sha256" ../nixos/mrjam-identity.nix}",
        "fixture_sha256": "${builtins.hashFile "sha256" ./runtime_fixture.py}",
        "test_expression_sha256": "${builtins.hashFile "sha256" ./runtime-systemd.nix}",
        "production_sso_qualified": False, "human_mfa_qualified": False,
        "limits": ["Invented identity and SQL only", "No actual production owners or credentials adopted",
                   "No Nginx or application HTTP cutover", "No protected forge approval created"]
    }, sort_keys=True) + "\n")
  '';
}
