{ nixpkgs, matevalSource }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  locked = import ../forgejo/locked-toolchain.nix { };
  previous = (import (import ../compatibility/nixpkgs-vps-observed.nix) { system="x86_64-linux"; }).forgejo;
in
assert previous.version == "16.0.3" && locked.forgejo.version == "17.0.1";
pkgs.testers.runNixOSTest {
  name = "mrjam-explicit-database-adoption-units";
  requiredFeatures.kvm = true;
  globalTimeout = 900;
  nodes.machine = { config, lib, ... }: {
    imports = [ ../nixos/mrjam-forgejo-host.nix ./database-adoption.nix ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    virtualisation.vlans = [ ];
    services.mrjamForgejoHost = {
      enable = true; uid=982;gid=982;
      artifactStorePath = builtins.unsafeDiscardStringContext (toString locked.forgejo);
    };
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      authentication = ''
        local all postgres peer
        local all all reject
      '';
    };
    environment.systemPackages = [ pkgs.util-linux pkgs.postgresql_17 pkgs.curl ];
    # The real host retains this context-free artifact in core-services.nix.
    system.extraDependencies = [ locked.forgejo ];
    environment.etc."synthetic-forgejo.ini".source = (pkgs.formats.ini { }).generate "synthetic-forgejo.ini"
      (lib.recursiveUpdate config.services.mrjamForgejoHost.settings {
        security = {SECRET_KEY="SYNTHETIC-SECRET-KEY-NOT-PRODUCTION";INTERNAL_TOKEN="SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION";};
        oauth2.JWT_SECRET="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
      });
    environment.etc."synthetic-matheval/001.sql".source = matevalSource + "/migrations/001-collecte.sql";
    environment.etc."synthetic-matheval/002.sql".source = matevalSource + "/migrations/002-sessions-administrateur.sql";
    environment.etc."synthetic-bootstrap.sql".text = ''
      CREATE ROLE forgejo LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
      CREATE DATABASE forgejo OWNER forgejo;
      CREATE ROLE matheval_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
      CREATE DATABASE matheval OWNER matheval_app;
    '';
    # Invented fixture diagnostics only, never changed production service output.
    systemd.services.forgejo.serviceConfig.Restart = lib.mkForce "no";
  };
  testScript = ''
    import json,os,shlex
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    checks=[]
    sql="runuser -u postgres -- psql -X -w -qAt -v ON_ERROR_STOP=1 -h /run/postgresql "
    old="runuser -u forgejo -- env USER=forgejo HOME=/var/lib/forgejo FORGEJO_WORK_DIR=/var/lib/forgejo FORGEJO_CUSTOM=/var/lib/forgejo/custom ${previous}/bin/forgejo --config /etc/synthetic-forgejo.ini "
    units=["mrjam-adopt-matheval","mrjam-bootstrap-journal","mrjam-adopt-forgejo-role","mrjam-upgrade-forgejo-schema"]
    with subtest("all real migration units remain explicit and have closed diagnostics"):
        for unit in units:
            machine.fail("systemctl is-active --quiet "+unit)
            assert machine.succeed("systemctl show --value -p StandardOutput "+unit).strip()=="null"
        machine.succeed(sql+"-d postgres -f /etc/synthetic-bootstrap.sql")
        machine.succeed(sql+"-d matheval -f /etc/synthetic-matheval/001.sql -f /etc/synthetic-matheval/002.sql")
        machine.succeed(sql+"-d matheval -c "+shlex.quote("INSERT INTO corpus(version,digest,bank,codebook) VALUES('invented','invented','{}','{}')"))
        machine.succeed("install -d -m 0700 -o forgejo -g forgejo /var/lib/forgejo /var/lib/forgejo/repositories /var/lib/forgejo/custom /var/lib/forgejo/custom/conf")
        for name,value in [("secret_key","SYNTHETIC-SECRET-KEY-NOT-PRODUCTION"),("internal_token","SYNTHETIC-INTERNAL-TOKEN-NOT-PRODUCTION"),("oauth2_jwt_secret","AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")]:
            path="/var/lib/forgejo/custom/conf/"+name
            machine.succeed("printf %s "+shlex.quote(value)+" > "+path+"; chown forgejo:forgejo "+path+"; chmod 0400 "+path)
        machine.succeed(old+"migrate",timeout=180)
        machine.succeed(old+"admin user create --username synthetic-preserved --password invented-fixture-only-password --email synthetic@invalid.example --must-change-password=false")
        machine.fail("systemctl start forgejo.service")
        checks.append("explicit-only-existing-schema-refused")
    with subtest("bounded journal bootstrap creates isolated schema without application events"):
        machine.succeed("systemctl start mrjam-bootstrap-journal.service")
        assert machine.succeed(sql+"-d postgres -c \"SELECT rolcanlogin::text FROM pg_roles WHERE rolname='vision_journal_import'\"").strip()=="false"
        assert machine.succeed(sql+"-d vision_journal -c \"SELECT has_database_privilege('matheval_app','vision_journal','CONNECT')::text\"").strip()=="false"
        machine.fail("systemctl start mrjam-bootstrap-journal.service")
        checks.append("journal-explicit-and-repeat-refused")
    with subtest("bounded MatEval adoption preserves invented rows and rejects repeating"):
        machine.succeed("systemctl start mrjam-adopt-matheval.service")
        assert machine.succeed(sql+"-d matheval -c \"SELECT version FROM corpus\"").strip()=="invented"
        assert machine.succeed(sql+"-d matheval -c \"SELECT has_table_privilege('matheval_app','public.administrators','SELECT')::text\"").strip()=="false"
        machine.fail("systemctl start mrjam-adopt-matheval.service")
        checks.append("matheval-preserved-and-repeat-refused")
    with subtest("Forgejo16 migrates through its explicit unit before removing schema privileges"):
        code,_=machine.execute("systemctl start mrjam-upgrade-forgejo-schema.service",timeout=180)
        if code!=0:
            # Diagnostics are confined to this invented VM and never shipped in
            # the production unit. Replay only this failed fixture operation.
            machine.succeed("mkdir -p /run/systemd/system/mrjam-upgrade-forgejo-schema.service.d; printf '[Service]\\nStandardOutput=journal\\nStandardError=journal\\n' > /run/systemd/system/mrjam-upgrade-forgejo-schema.service.d/synthetic-diagnostic.conf; systemctl daemon-reload")
            machine.execute("systemctl start mrjam-upgrade-forgejo-schema.service",timeout=180)
            raise RuntimeError(machine.succeed("journalctl -u mrjam-upgrade-forgejo-schema.service --no-pager -n 50"))
        machine.succeed("systemctl start mrjam-adopt-forgejo-role.service")
        assert machine.succeed(sql+"-d forgejo -c \"SELECT count(*) FROM public.user WHERE lower_name='synthetic-preserved'\"").strip()=="1"
        assert machine.succeed(sql+"-d forgejo -c \"SELECT has_schema_privilege('forgejo','public','CREATE')::text\"").strip()=="false"
        machine.succeed("systemctl reset-failed forgejo.service; systemctl start forgejo.service")
        machine.wait_for_open_port(3004)
        machine.succeed("curl --fail --silent --output /dev/null http://127.0.0.1:3004/api/healthz")
        checks.append("forgejo16-to17-explicit-unit-restricted-role")
    with subtest("migration state stays private after services stop"):
        machine.succeed("systemctl stop forgejo.service")
        machine.succeed("systemctl stop postgresql.service postgresql.target")
        for unit in ["forgejo.service","postgresql.service"]:
            assert machine.succeed("systemctl show --value -p MainPID "+unit).strip()=="0"
        checks.append("clean-shutdown")
    Path(os.environ["out"],"result.json").write_text(json.dumps({
      "schema_version":1,"checks":checks,"production_access":False,
      "module_sha256":"${builtins.hashFile "sha256" ./database-adoption.nix}",
      "test_sha256":"${builtins.hashFile "sha256" ./database-adoption-systemd.nix}",
      "limits":["Synthetic database state only", "No generation switch or external SMTP"]
    },sort_keys=True)+"\n")
  '';
}
