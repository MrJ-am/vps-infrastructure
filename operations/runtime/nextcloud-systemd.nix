# Disposable guest only. All SQL state, certificates and file contents are synthetic.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  packages = import ../hosts/mrjam-vps/preserved-packages.nix { };
in pkgs.testers.runNixOSTest {
  name = "mrjam-nextcloud-adoption-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 1800;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../nixos/mrjam-kanidm-host.nix ../nixos/mrjam-nextcloud-host.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536; virtualisation.cores = 2;
    virtualisation.diskSize = 4096;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamKanidmHost = { enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${packages.kanidm}"; };
    services.mrjamNextcloudHost = { enable = true; uid = 975; gid = 975; };
    # Explicit synthetic database initialization is outside the adoption module.
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "nextcloud" ];
      ensureUsers = [ { name = "nextcloud"; ensureDBOwnership = true; } ];
    };
    systemd.services.nextcloud-setup.serviceConfig.StandardError = lib.mkForce "journal";
    systemd.services.nextcloud-setup.serviceConfig.StandardOutput = lib.mkForce "journal";
    systemd.services.phpfpm-nextcloud.serviceConfig.StandardError = lib.mkForce "journal";
    systemd.services.phpfpm-nextcloud.serviceConfig.StandardOutput = lib.mkForce "journal";
    services.nginx.logError = "/var/log/nginx/error.log warn";
    environment.systemPackages = [ pkgs.openssl pkgs.curl pkgs.util-linux pkgs.postgresql_17 pkgs.python3 ];
    environment.etc."synthetic-nextcloud-package".text = "${config.services.nextcloud.finalPackage}";
  };
  testScript = ''
    import hashlib
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    checks = []
    occ = "runuser -u nextcloud -- nextcloud-occ "
    curl = "curl --silent --show-error --noproxy '*' --resolve cloud.mrj.am:443:127.0.0.1 --cacert /var/lib/acme/cloud.mrj.am/fullchain.pem "

    def schema_hash():
        dump = machine.succeed("runuser -u nextcloud -- pg_dump -h /run/postgresql --schema-only --no-owner --no-privileges nextcloud")
        stable = "\n".join(x for x in dump.splitlines() if not x.startswith("\\restrict ") and not x.startswith("\\unrestrict "))
        return hashlib.sha256(stable.encode()).hexdigest()

    with subtest("staged adoption refuses an empty instance without bootstrap"):
        machine.fail("systemctl is-active --quiet phpfpm-nextcloud.service")
        machine.fail("systemctl is-active --quiet nextcloud-cron.timer")
        machine.fail("systemctl start nextcloud-setup.service")
        machine.fail("test -e /var/lib/nextcloud/config/config.php")
        assert machine.succeed("runuser -u nextcloud -- psql -X -w -h /run/postgresql -d nextcloud -Atc \"SELECT count(*) FROM pg_tables WHERE schemaname='public'\"").strip() == "0"
        checks.append("empty-state-refused-without-account-or-schema-bootstrap")

    with subtest("explicit fixture initialization uses the locked real application"):
        status, output = machine.execute(occ + "maintenance:install --no-interaction --database=pgsql --database-host=/run/postgresql --database-name=nextcloud --database-user=nextcloud --database-pass= --disable-admin-user --data-dir=/var/lib/nextcloud/data </dev/null 2>&1", timeout=600)
        assert status == 0, output
        baseline = schema_hash()
        result = json.loads(machine.succeed(occ + "status --output=json"))
        assert result["installed"] is True and result["versionstring"] == "34.0.4", result
        assert result["needsDbUpgrade"] is False
        checks.append("nextcloud-34-0-4-explicit-synthetic-initialization")

    with subtest("adopted setup and FPM retain schema and local peer identity"):
        machine.succeed("systemctl reset-failed; systemctl start phpfpm-nextcloud.service")
        machine.wait_for_unit("phpfpm-nextcloud.service")
        machine.wait_for_unit("redis-nextcloud.service")
        assert schema_hash() == baseline
        machine.fail("runuser -u nextcloud -- psql -X -w -h /run/postgresql -d postgres -c 'SELECT 1'")
        machine.fail("runuser -u nobody -- psql -X -w -h /run/postgresql -U nextcloud -d nextcloud -c 'SELECT 1'")
        machine.fail("systemctl is-enabled --quiet nextcloud-update-db.service")
        assert machine.succeed("id -u nextcloud").strip() == "975"
        checks.append("real-fpm-and-redis-with-closed-peer-and-stable-schema")

    with subtest("TLS status works and local password routes remain refused"):
        machine.succeed("install -d -m 0750 -o root -g nginx /var/lib/acme/cloud.mrj.am")
        machine.succeed("openssl req -x509 -newkey rsa:2048 -noenc -days 1 -subj /CN=cloud.mrj.am -addext subjectAltName=DNS:cloud.mrj.am -keyout /var/lib/acme/cloud.mrj.am/key.pem -out /var/lib/acme/cloud.mrj.am/fullchain.pem >/dev/null 2>&1")
        machine.succeed("chown root:nginx /var/lib/acme/cloud.mrj.am/key.pem; chmod 0640 /var/lib/acme/cloud.mrj.am/key.pem; chmod 0444 /var/lib/acme/cloud.mrj.am/fullchain.pem")
        machine.succeed("systemctl reset-failed nginx.service; systemctl restart nginx.service")
        machine.wait_for_unit("nginx.service")
        machine.wait_for_open_port(443, timeout=60)
        status = json.loads(machine.succeed(curl + "--fail https://cloud.mrj.am/status.php"))
        assert status["installed"] is True and status["versionstring"] == "34.0.4", status
        assert status["needsDbUpgrade"] is False
        for path in ("/login", "/index.php/login", "/lostpassword/email"):
            assert machine.succeed(curl + "-X POST -o /dev/null -w '%{http_code}' https://cloud.mrj.am" + path).strip() == "403"
        checks.append("real-nextcloud-tls-status-and-local-password-refusals")

    with subtest("persistent PHP containment marker blocks FPM restart"):
        machine.succeed("systemctl stop phpfpm-nextcloud.service; install -d -m 0700 /var/lib/nextcloud-php-security; touch /var/lib/nextcloud-php-security/blocked")
        machine.succeed("systemctl start phpfpm-nextcloud.service")
        machine.fail("systemctl is-active --quiet phpfpm-nextcloud.service")
        machine.succeed("rm /var/lib/nextcloud-php-security/blocked; systemctl start phpfpm-nextcloud.service")
        machine.wait_for_unit("phpfpm-nextcloud.service")
        checks.append("persistent-containment-marker-enforced")

    with subtest("maintenance state is refused unchanged instead of implicitly upgraded"):
        machine.succeed("systemctl stop phpfpm-nextcloud.service")
        machine.succeed(occ + "maintenance:mode --on")
        machine.fail("systemctl start nextcloud-setup.service")
        assert json.loads(machine.succeed(occ + "status --output=json"))["maintenance"] is True
        assert schema_hash() == baseline
        machine.succeed(occ + "maintenance:mode --off")
        machine.succeed("systemctl reset-failed; systemctl start phpfpm-nextcloud.service")
        machine.wait_for_unit("phpfpm-nextcloud.service")
        assert schema_hash() == baseline
        checks.append("maintenance-refused-without-schema-or-flag-write")

    Path(os.environ["out"], "nextcloud-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-nixos-vm-tcg", "checks": checks,
        "nextcloud": "${packages.nextcloud.version}", "php": "${packages.php.version}",
        "postgresql": "${pkgs.postgresql_17.version}", "schema_sha256": baseline,
        "production_qualification": False,
        "limitations": ["No real account, file or OIDC client adopted", "No production backup or migration qualified", "TLS certificate and SQL state are entirely synthetic", "Kanidm is declared but not started in this suite"]
    }, sort_keys=True) + "\n")
  '';
}
