# Entirely synthetic common host: real Forgejo, Kanidm, Nextcloud and PostgreSQL.
{ nixpkgs, acceleration ? "tcg" }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  packages = import ../hosts/mrjam-vps/preserved-packages.nix { };
  locked = import ../forgejo/locked-toolchain.nix { };
  tls = pkgs.runCommand "mrjam-synthetic-core-tls" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    mkdir -p "$out"
    openssl req -x509 -newkey rsa:2048 -noenc -days 3650 -subj /CN=MRJAM-SYNTHETIC-ONLY \
      -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign \
      -keyout "$out/ca-key.pem" -out "$out/ca.pem" >/dev/null 2>&1
    for domain in forge.mrj.am log.mrj.am cloud.mrj.am; do
      mkdir "$out/$domain"
      openssl req -newkey rsa:2048 -noenc -subj "/CN=$domain" \
        -keyout "$out/$domain/key.pem" -out request.pem >/dev/null 2>&1
      printf 'subjectAltName=DNS:%s\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' "$domain" > extensions
      openssl x509 -req -in request.pem -CA "$out/ca.pem" -CAkey "$out/ca-key.pem" \
        -CAcreateserial -days 3650 -extfile extensions -out "$out/$domain/fullchain.pem" >/dev/null 2>&1
    done
  '';
in assert builtins.elem acceleration [ "tcg" "kvm" ];
pkgs.testers.runNixOSTest {
  name = "mrjam-core-services-coherent-return-synthetic";
  requiredFeatures.kvm = acceleration == "kvm";
  qemu.forceAccel = acceleration == "kvm";
  globalTimeout = 1800;
  nodes.machine = { config, lib, pkgs, ... }: {
    imports = [ ../hosts/mrjam-vps/core-services.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 3072;
    virtualisation.cores = 2;
    virtualisation.diskSize = 8192;
    virtualisation.qemu.options = [ "-machine accel=${acceleration}" ];
    security.pki.certificateFiles = [ "${tls}/ca.pem" ];
    environment.systemPackages = [ locked.forgejo packages.kanidm pkgs.postgresql_17
      pkgs.openssl pkgs.curl pkgs.util-linux pkgs.python3 pkgs.gnutar ];
    environment.etc."synthetic-core-tls".source = tls;
    environment.etc."forgejo-adopt-runtime-role.sql".source = ../forgejo/adopt-runtime-role.sql;
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini { }).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = { SECRET_KEY = "SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"; INTERNAL_TOKEN = "SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"; };
        oauth2.JWT_SECRET = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."synthetic-kanidm.toml".source = (pkgs.formats.toml { }).generate "synthetic-kanidm.toml"
      (config.services.mrjamKanidmHost.settings // {
        tls_chain = "${tls}/log.mrj.am/fullchain.pem";
        tls_key = "${tls}/log.mrj.am/key.pem";
        adminbindpath = "/run/synthetic-kanidm/admin.sock";
      });
    systemd.services.synthetic-kanidm-initialization.serviceConfig = {
      ExecStart = "${packages.kanidm}/bin/kanidmd server -c /etc/synthetic-kanidm.toml";
      User = "kanidm"; Group = "kanidm"; StateDirectory = "kanidm";
      RuntimeDirectory = "synthetic-kanidm"; UMask = "0077";
    };
    # Diagnostics are confined to this guest containing only invented data.
    systemd.services.forgejo.serviceConfig = { StandardOutput = lib.mkForce "journal"; StandardError = lib.mkForce "journal"; };
    systemd.services.kanidm.serviceConfig = { StandardOutput = lib.mkForce "journal"; StandardError = lib.mkForce "journal"; };
    systemd.services.nextcloud-setup.serviceConfig = { StandardOutput = lib.mkForce "journal"; StandardError = lib.mkForce "journal"; };
    systemd.services.phpfpm-nextcloud.serviceConfig = { StandardOutput = lib.mkForce "journal"; StandardError = lib.mkForce "journal"; };
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("multi-user.target")
    checks = []
    occ = "runuser -u nextcloud -- nextcloud-occ "
    sql = "runuser -u postgres -- psql -X -w -v ON_ERROR_STOP=1 -h /run/postgresql "
    forgejo = "runuser -u forgejo -- env USER=forgejo HOME=/var/lib/forgejo FORGEJO_WORK_DIR=/var/lib/forgejo FORGEJO_CUSTOM=/var/lib/forgejo/custom forgejo "
    curl = "curl --silent --show-error --fail --noproxy '*' --cacert /etc/synthetic-core-tls/ca.pem "

    def health():
        assert json.loads(machine.succeed(curl + "--resolve cloud.mrj.am:443:127.0.0.1 https://cloud.mrj.am/status.php"))["versionstring"] == "34.0.4"
        assert json.loads(machine.succeed(curl + "--resolve forge.mrj.am:443:127.0.0.1 https://forge.mrj.am/api/healthz"))["status"] == "pass"
        machine.succeed(curl + "--resolve log.mrj.am:443:127.0.0.1 https://log.mrj.am/status")

    def start_core():
        machine.succeed("systemctl reset-failed; systemctl start postgresql.service kanidm.service forgejo.service phpfpm-nextcloud.service nginx.service")
        for unit in ["postgresql", "kanidm", "forgejo", "phpfpm-nextcloud", "nginx"]:
            machine.wait_for_unit(unit + ".service")
        machine.wait_until_succeeds(curl + "--resolve log.mrj.am:443:127.0.0.1 https://log.mrj.am/status", timeout=120)
        health()

    def stop_core():
        machine.succeed("systemctl stop nginx.service nextcloud-cron.timer nextcloud-cron.service phpfpm-nextcloud.service forgejo.service kanidm.service redis-nextcloud.service")
        # Stopping the target alone returns before its PartOf services finish.
        # Wait for the server itself, including its final checkpoint, before tar.
        machine.succeed("systemctl stop postgresql.service postgresql.target", timeout=120)
        for unit in ["nginx", "nextcloud-cron", "phpfpm-nextcloud", "forgejo", "kanidm", "redis-nextcloud", "postgresql"]:
            assert machine.succeed("systemctl show -p ActiveState --value " + unit + ".service").strip() == "inactive"
            assert machine.succeed("systemctl show -p MainPID --value " + unit + ".service").strip() == "0"
        machine.fail("test -e /var/lib/postgresql/17/postmaster.pid")

    with subtest("existing-state composition refuses to initialize an absent PostgreSQL cluster"):
        machine.fail("systemctl is-active --quiet postgresql.service")
        machine.fail("test -e /var/lib/postgresql/17/PG_VERSION")
        for unit in ["forgejo", "kanidm", "phpfpm-nextcloud"]:
            machine.fail("systemctl is-active --quiet " + unit + ".service")
        checks.append("no-cluster-or-application-bootstrap")

    with subtest("explicit fixture installation creates only invented identities and databases"):
        machine.succeed("install -d -m 0700 -o postgres -g postgres /var/lib/postgresql/17")
        machine.succeed("runuser -u postgres -- initdb -D /var/lib/postgresql/17 --encoding=UTF8 --locale=C >/dev/null")
        machine.succeed("systemctl reset-failed; systemctl start postgresql.service")
        machine.wait_for_unit("postgresql-setup.service")
        machine.succeed(sql + "-d postgres -c 'CREATE ROLE forgejo LOGIN' -c 'CREATE DATABASE forgejo OWNER forgejo' -c 'CREATE ROLE nextcloud LOGIN' -c 'CREATE DATABASE nextcloud OWNER nextcloud'")
        machine.succeed("install -d -m 0700 -o forgejo -g forgejo /var/lib/forgejo /var/lib/forgejo/custom /var/lib/forgejo/custom/conf /var/lib/forgejo/repositories")
        machine.succeed("printf '%s' SYNTHETIC-SECRET-KEY-NOT-PRODUCTION > /var/lib/forgejo/custom/conf/secret_key; printf '%s' SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION > /var/lib/forgejo/custom/conf/internal_token; printf '%s' AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > /var/lib/forgejo/custom/conf/oauth2_jwt_secret; chown forgejo:forgejo /var/lib/forgejo/custom/conf/*; chmod 0400 /var/lib/forgejo/custom/conf/*")
        machine.succeed(forgejo + "migrate --config /etc/synthetic-forgejo.ini")
        machine.succeed(sql + "-d forgejo -f /etc/forgejo-adopt-runtime-role.sql")
        machine.succeed(occ + "maintenance:install --no-interaction --database=pgsql --database-host=/run/postgresql --database-name=nextcloud --database-user=nextcloud --database-pass= --disable-admin-user --data-dir=/var/lib/nextcloud/data", timeout=300)
        machine.succeed("systemctl start synthetic-kanidm-initialization.service")
        machine.wait_until_succeeds(curl + "--resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status", timeout=120)
        machine.succeed("systemctl stop synthetic-kanidm-initialization.service")
        for domain in ["forge.mrj.am", "log.mrj.am", "cloud.mrj.am"]:
            machine.succeed("install -d -m 0750 -o root -g nginx /var/lib/acme/" + domain)
            machine.succeed("install -m 0640 -o root -g nginx /etc/synthetic-core-tls/" + domain + "/key.pem /var/lib/acme/" + domain + "/key.pem")
            machine.succeed("install -m 0444 /etc/synthetic-core-tls/" + domain + "/fullchain.pem /var/lib/acme/" + domain + "/fullchain.pem")
        checks.append("explicit-fixtures-for-three-real-applications")

    with subtest("shared PostgreSQL and HTTPS proxy serve all three adopted services"):
        start_core()
        machine.succeed(curl + "--resolve forge.mrj.am:443:127.0.0.1 https://forge.mrj.am/assets/forgejo-org/config.js >/dev/null")
        machine.fail("runuser -u forgejo -- psql -X -w -h /run/postgresql -d nextcloud -c 'SELECT 1'")
        machine.fail("runuser -u nextcloud -- psql -X -w -h /run/postgresql -d forgejo -c 'SELECT 1'")
        machine.fail("runuser -u nobody -- psql -X -w -h /run/postgresql -U postgres -d postgres -c 'SELECT 1'")
        assert machine.succeed("curl --silent --noproxy '*' -o /dev/null -w '%{http_code}' -H 'Host: unknown.invalid' http://127.0.0.1/").strip() == "421"
        checks.append("three-https-services-shared-database-and-cross-role-refusals")

    with subtest("unknown TLS issuers and local password entry remain refused"):
        # No -k: the independent curl trust store must reject this synthetic CA.
        machine.fail("curl --silent --fail --noproxy '*' --cacert ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt --resolve cloud.mrj.am:443:127.0.0.1 https://cloud.mrj.am/status.php")
        assert machine.succeed("curl --silent --noproxy '*' --cacert /etc/synthetic-core-tls/ca.pem --resolve cloud.mrj.am:443:127.0.0.1 -X POST -o /dev/null -w '%{http_code}' https://cloud.mrj.am/login").strip() == "403"
        for path in ["/v1/raw/search", "/v1/oauth2/", "/v1/service_account/", "/scim/v1/Sync"]:
            assert machine.succeed("curl --silent --noproxy '*' --cacert /etc/synthetic-core-tls/ca.pem --resolve log.mrj.am:443:127.0.0.1 -o /dev/null -w '%{http_code}' https://log.mrj.am" + path).strip() == "404"
        checks.append("tls-verification-and-local-password-refusals")

    with subtest("quiescent backup captures the whole cluster and matching application files"):
        machine.succeed(sql + "-d postgres -c 'CREATE TABLE public.synthetic_return_marker(value text)' -c \"INSERT INTO public.synthetic_return_marker VALUES ('before-cutover')\"")
        machine.succeed("printf '%s' before-cutover > /var/lib/nextcloud/data/synthetic-return-marker")
        stop_core()
        machine.succeed("install -d -m 0700 /var/lib/synthetic-core-return")
        machine.succeed("tar --acls --xattrs --numeric-owner -C /var/lib -cpf /var/lib/synthetic-core-return/state.tar postgresql/17 forgejo kanidm nextcloud redis-nextcloud")
        checks.append("quiescent-cluster-and-files-capture")

    with subtest("paired return restores SQL and files before writes are reopened"):
        start_core()
        machine.succeed(sql + "-d postgres -c \"UPDATE public.synthetic_return_marker SET value='candidate-only'\"")
        machine.succeed("printf '%s' candidate-only > /var/lib/nextcloud/data/synthetic-return-marker")
        stop_core()
        for name in ["postgresql/17", "forgejo", "kanidm", "nextcloud", "redis-nextcloud"]:
            machine.succeed("mv /var/lib/" + name + " /var/lib/" + name + ".candidate-only")
        machine.succeed("tar --acls --xattrs --numeric-owner -C /var/lib -xpf /var/lib/synthetic-core-return/state.tar")
        start_core()
        assert machine.succeed(sql + "-d postgres -Atc 'SELECT value FROM public.synthetic_return_marker'").strip() == "before-cutover"
        assert machine.succeed("cat /var/lib/nextcloud/data/synthetic-return-marker").strip() == "before-cutover"
        machine.succeed("runuser -u postgres -- psql -X -w -h /run/postgresql -d forgejo -Atc 'SELECT count(*) > 0 FROM public.version'")
        checks.append("paired-offline-state-return-before-reopening-writes")

    Path(os.environ["out"], "core-services-result.json").write_text(json.dumps({
        "schema_version": 1, "scope": "synthetic-common-host-with-real-packages",
        "checks": checks, "vise_included": False, "production_access": False,
        "production_qualification": False,
        "limits": ["No full VPS machine or Rust application generation", "No positive SSO or real account adoption",
                   "Return is qualified only while production writes remain closed", "Certificates, SQL and files are invented"]
    }, sort_keys=True) + "\n")
  '';
}
