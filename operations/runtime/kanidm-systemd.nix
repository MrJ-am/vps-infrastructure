# Entirely synthetic state, certificates and backup. No production data.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  package = (import ../hosts/mrjam-vps/preserved-packages.nix { }).kanidm;
in pkgs.testers.runNixOSTest {
  name = "mrjam-kanidm-adoption-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 1200;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-kanidm-host.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536; virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamKanidmHost = { enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${package}"; };
    systemd.services.kanidm.serviceConfig.Restart = lib.mkForce "no";
    # Local synthetic diagnostics; production defaults remain closed.
    systemd.services.kanidm.serviceConfig.StandardOutput = lib.mkForce "journal";
    systemd.services.kanidm.serviceConfig.StandardError = lib.mkForce "journal";
    environment.systemPackages = [ package pkgs.openssl pkgs.curl pkgs.util-linux pkgs.python3 ];
    environment.etc."synthetic-kanidm.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm.toml"
      (config.services.mrjamKanidmHost.settings // {
        tls_chain = "/var/lib/kanidm/synthetic-cert.pem";
        tls_key = "/var/lib/kanidm/synthetic-key.pem";
        adminbindpath = "/run/synthetic-kanidm/admin.sock";
      });
    environment.etc."synthetic-kanidm-restored.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm-restored.toml"
      (config.services.mrjamKanidmHost.settings // {
        db_path = "/var/lib/kanidm-restored/kanidm.db";
        tls_chain = "/var/lib/kanidm/synthetic-cert.pem";
        tls_key = "/var/lib/kanidm/synthetic-key.pem";
        adminbindpath = "/run/synthetic-kanidm-restored/admin.sock";
      });
    # Explicit fixture initialization is separate from the adoption module.
    systemd.services.synthetic-kanidm-initialization = {
      serviceConfig = {
        ExecStart = "${package}/bin/kanidmd server -c /etc/synthetic-kanidm.toml";
        User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm";
        RuntimeDirectory = "synthetic-kanidm"; UMask = "0077";
      };
    };
    systemd.services.synthetic-kanidm-restored = {
      serviceConfig = {
        ExecStart = "${package}/bin/kanidmd server -c /etc/synthetic-kanidm-restored.toml";
        User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm-restored";
        RuntimeDirectory = "synthetic-kanidm-restored"; UMask = "0077";
      };
    };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    checks = []
    health = "curl --silent --show-error --fail --noproxy '*' --resolve log.mrj.am:8443:127.0.0.1 --cacert /var/lib/kanidm/synthetic-cert.pem https://log.mrj.am:8443/status"

    def healthy(unit, timeout):
        try:
            machine.wait_until_succeeds("systemctl is-active --quiet " + unit + " && " + health, timeout=timeout)
        except Exception as error:
            raise AssertionError(machine.succeed("journalctl -u " + unit + " --no-pager -n 45")) from error

    with subtest("adoption refuses missing credentials and never creates an identity database"):
        machine.fail("systemctl is-active --quiet kanidm.service")
        machine.fail("systemctl start kanidm.service")
        machine.fail("test -e /var/lib/kanidm/kanidm.db")
        checks.append("staged-and-no-identity-bootstrap")

    machine.succeed("install -d -m 0700 -o kanidm -g kanidm /var/lib/kanidm")
    machine.succeed("runuser -u kanidm -- openssl req -x509 -newkey rsa:2048 -noenc -days 1 -subj /CN=log.mrj.am -addext subjectAltName=DNS:log.mrj.am -keyout /var/lib/kanidm/synthetic-key.pem -out /var/lib/kanidm/synthetic-cert.pem >/dev/null 2>&1")
    machine.succeed("install -d -m 0700 /var/lib/acme/log.mrj.am")
    machine.succeed("install -m 0400 /var/lib/kanidm/synthetic-key.pem /var/lib/acme/log.mrj.am/key.pem")
    machine.succeed("install -m 0444 /var/lib/kanidm/synthetic-cert.pem /var/lib/acme/log.mrj.am/fullchain.pem")

    with subtest("credentials alone do not allow an empty database to be initialized"):
        machine.succeed("systemctl reset-failed")
        machine.fail("systemctl start kanidm.service")
        machine.fail("test -e /var/lib/kanidm/kanidm.db")
        checks.append("empty-state-refused-after-tls-credentials")

    with subtest("explicit fixture initialization prepares independent synthetic identity state"):
        machine.succeed("systemctl start synthetic-kanidm-initialization.service")
        healthy("synthetic-kanidm-initialization.service", 180)
        machine.succeed("systemctl stop synthetic-kanidm-initialization.service")
        machine.succeed("test -s /var/lib/kanidm/kanidm.db")
        checks.append("explicit-synthetic-identity-initialization")

    with subtest("adopted unit serves TLS under the preserved Unix identity"):
        machine.succeed("systemctl reset-failed; systemctl start kanidm.service")
        machine.wait_for_unit("kanidm.service")
        healthy("kanidm.service", 120)
        assert machine.succeed("id -G kanidm").strip() == "976"
        assert machine.succeed("stat -c '%u:%g:%a' /var/lib/kanidm").strip() == "976:976:700"
        assert machine.succeed("stat -c '%u:%g:%a' /run/kanidmd").strip() == "976:976:700"
        machine.fail("runuser -u nobody -- cat /var/lib/kanidm/kanidm.db")
        machine.fail("runuser -u kanidm -- cat /var/lib/acme/log.mrj.am/key.pem")
        assert machine.succeed("systemctl show kanidm -p NoNewPrivileges --value").strip() == "yes"
        assert machine.succeed("systemctl show kanidm -p AmbientCapabilities --value").strip() == ""
        checks.append("real-service-tls-isolation-and-identity")

    with subtest("restart retains TLS and database without domain rename or recovery"):
        machine.succeed("sha256sum /var/lib/acme/log.mrj.am/* > /tmp/synthetic-tls-hashes")
        machine.succeed("systemctl restart kanidm.service")
        healthy("kanidm.service", 120)
        machine.succeed("sha256sum -c /tmp/synthetic-tls-hashes")
        machine.succeed("systemctl stop kanidm.service")
        machine.succeed("runuser -u kanidm -- kanidmd database verify -c /etc/synthetic-kanidm.toml >/dev/null 2>&1")
        checks.append("restart-and-offline-consistency-check")

    with subtest("offline backup restores into a separate database and serves TLS"):
        # 1.11.2 writes gzip according to the config, while restore selects the
        # decoder from the filename suffix. A .json suffix is not valid here.
        machine.succeed("runuser -u kanidm -- kanidmd database backup -c /etc/synthetic-kanidm.toml /var/lib/kanidm/synthetic-backup.json.gz >/dev/null 2>&1")
        machine.succeed("test -s /var/lib/kanidm/synthetic-backup.json.gz; install -d -m 0700 -o kanidm -g kanidm /var/lib/kanidm-restored")
        machine.succeed("python3 -c \"import gzip,json; json.load(gzip.open('/var/lib/kanidm/synthetic-backup.json.gz'))\"")
        restore_status, restore_output = machine.execute("runuser -u kanidm -- kanidmd database restore -c /etc/synthetic-kanidm-restored.toml /var/lib/kanidm/synthetic-backup.json.gz </dev/null 2>&1", timeout=120)
        assert restore_status == 0, restore_output
        machine.succeed("runuser -u kanidm -- kanidmd database verify -c /etc/synthetic-kanidm-restored.toml >/dev/null 2>&1")
        machine.succeed("systemctl start synthetic-kanidm-restored.service")
        healthy("synthetic-kanidm-restored.service", 120)
        machine.succeed("systemctl stop synthetic-kanidm-restored.service")
        # The original remains separate and restartable after the restore trial.
        machine.succeed("systemctl start kanidm.service")
        healthy("kanidm.service", 120)
        machine.succeed("systemctl stop kanidm.service; sha256sum -c /tmp/synthetic-tls-hashes")
        checks.append("offline-backup-separate-restore-and-original-restart")

    Path(os.environ["out"], "kanidm-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "kanidm": "${package.version}", "production_qualification": False,
        "limitations": ["Synthetic identity database only", "No real client, account, certificate or installed schema adopted", "No full OIDC integration or production backup/restore qualified"]
    }, sort_keys=True) + "\n")
  '';
}
