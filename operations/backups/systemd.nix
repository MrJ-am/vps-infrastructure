# Exact backup units on real systemd/PostgreSQL/Kanidm with invented state.
# Forgejo's writer and the Nextcloud maintenance CLI are explicit fixtures.
{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  kanidm = builtins.storePath "/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2";
  settings = {
    version = "2"; domain = "log.mrj.am"; origin = "https://log.mrj.am";
    bindaddress = "127.0.0.1:8443"; db_path = "/var/lib/kanidm/kanidm.db";
    tls_chain = "/run/credentials/kanidm.service/tls-chain";
    tls_key = "/run/credentials/kanidm.service/tls-key";
    adminbindpath = "/run/kanidmd/admin.sock"; log_level = "info";
    online_backup = { enabled = false; path = "/var/lib/kanidm/backups";
      schedule = "00 22 * * *"; versions = 1; compression = "gzip"; };
  };
  toml = (pkgs.formats.toml { }).generate "synthetic-backup-kanidm.toml" settings;
  occ = pkgs.writeShellScriptBin "nextcloud-occ" ''
    set -eu
    case "$*" in
      'maintenance:mode --on') printf on > /run/nextcloud-fixture/maintenance ;;
      'maintenance:mode --off') printf off > /run/nextcloud-fixture/maintenance ;;
      *) exit 1 ;;
    esac
  '';
  # This observer/fault injector exists only in the synthetic VM. Real age is
  # still used for encryption, authentication and decryption.
  backupAge = pkgs.writeShellScriptBin "age" ''
    set -euo pipefail
    ${pkgs.systemd}/bin/systemctl is-active --quiet forgejo.service
    touch /run/backup-fixture/forgejo-live-during-encryption
    if test "$1" = -d; then
      ${pkgs.python3}/bin/python3 - "$3" "''${@: -1}" <<'PY'
from pathlib import Path
import sys
root=Path('/run/backup-fixture')
if (root/'forgejo-change-capture').exists():
    path=Path(sys.argv[1]).parent/'data.tar'
    with path.open('r+b') as f:
        f.seek(600);value=f.read(1);assert value;f.seek(600);f.write(bytes([value[0]^1]))
if (root/'forgejo-corrupt-stream').exists():
    path=Path(sys.argv[2])
    with path.open('r+b') as f:
        f.seek(-1,2);value=f.read(1);assert value;f.seek(-1,2);f.write(bytes([value[0]^1]))
PY
    fi
    exec ${pkgs.age}/bin/age "$@"
  '';
  fixture = pkgs.writeText "backup-systemd-fixture.py" ''
    import gzip
    import json
    import os
    from pathlib import Path
    import re
    import sqlite3
    import subprocess
    import sys
    import tarfile

    ROOT = Path("/run/backup-fixture")
    STAMP = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}")

    def require(value, code):
        if not value:
            raise RuntimeError(code)

    def command(args, input_file=None):
        result = subprocess.run(args, stdin=input_file or subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=120)
        require(result.returncode == 0, "SYNTHETIC_COMMAND_FAILED")
        return result.stdout

    def private_file(path, value, uid=0, gid=0):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(value)
        path.chmod(0o600)
        os.chown(path, uid, gid)

    def setup():
        ROOT.mkdir(mode=0o700)
        command(["${pkgs.openssl}/bin/openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt",
                 "ec_paramgen_curve:prime256v1", "-nodes", "-subj", "/CN=log.mrj.am", "-addext",
                 "subjectAltName=DNS:log.mrj.am", "-keyout", str(ROOT/"tls.key"), "-out", str(ROOT/"tls.pem"), "-days", "1"])
        cert = Path("/var/lib/acme/log.mrj.am")
        cert.mkdir(mode=0o700, parents=True)
        private_file(cert/"fullchain.pem", (ROOT/"tls.pem").read_bytes())
        private_file(cert/"key.pem", (ROOT/"tls.key").read_bytes())
        command(["${pkgs.age}/bin/age-keygen", "-o", str(ROOT/"recipient-key")])
        recipient = command(["${pkgs.age}/bin/age-keygen", "-y", str(ROOT/"recipient-key")]).decode().strip()
        private_file(Path("/var/lib/mrjam-worker-credentials/v1/archive.json"), json.dumps({"age_recipient":recipient}).encode())
        for path, uid in (("mrjam-metier/log/sessions.sqlite",984), ("mrjam-vision-admission/admissions.sqlite",947),
                          ("mrjam-vision-cycle/courriels.sqlite",945), ("mrjam-vision-archive/courriels.sqlite",943)):
            file=Path("/var/lib")/path
            file.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.chown(file.parent,uid,uid)
            with sqlite3.connect(file) as connection:
                connection.execute("CREATE TABLE fixture(value BLOB)")
                connection.execute("INSERT INTO fixture VALUES(?)", (b"invented-preserved-bytes\x00\r\n",))
            file.chmod(0o600)
            os.chown(file,uid,uid)
        private_file(Path("/var/lib/forgejo/repositories/fixture.git/marker"),b"invented-forgejo-repository",982,982)
        private_file(Path("/var/lib/forgejo-identity/client.json"),b'{"synthetic":true}')
        private_file(Path("/var/lib/nextcloud/config/config.php"),b"invented-nextcloud-config",990,990)
        private_file(Path("/var/lib/nextcloud/data/marker"),b"invented-nextcloud-data",990,990)
        Path("/run/nextcloud-fixture").mkdir(mode=0o700)
        os.chown("/run/nextcloud-fixture",990,990)

    def restore_dump(path, expected):
        name="synthetic_restore_"+expected
        prefix=["${pkgs.util-linux}/bin/runuser","-u","postgres","--"]
        command(prefix+["${pkgs.postgresql_17}/bin/createdb",name])
        with path.open("rb") as source:
            command(prefix+["${pkgs.postgresql_17}/bin/pg_restore","--exit-on-error","--dbname="+name],source)
        value=command(prefix+["${pkgs.postgresql_17}/bin/psql","-XAt","-d",name,"-c","SELECT value FROM fixture"])
        require(value==(expected+"\n").encode(),"RESTORED_SQL_MISMATCH")
        command(prefix+["${pkgs.postgresql_17}/bin/dropdb",name])

    def decrypt(key_path,data_path,name):
        key=ROOT/(name+".key")
        result=ROOT/(name+".tar")
        command(["${pkgs.age}/bin/age","-d","-i",str(ROOT/"recipient-key"),"-o",str(key),str(key_path)])
        command(["${pkgs.age}/bin/age","-d","-i",str(key),"-o",str(result),str(data_path)])
        return result

    def verify_native():
        base=Path("/var/backup/mrjam/native-v1")
        published=[path for path in base.iterdir() if STAMP.fullmatch(path.name)]
        require(len(published)==1,"NATIVE_PUBLICATION_COUNT")
        path=published[0]
        require(path.stat().st_mode&0o777==0o700,"NATIVE_DIRECTORY_MODE")
        require({item.name for item in path.iterdir()}=={"components.tar.age","key.age","manifest.json"},"NATIVE_PRIVATE_FILES_EXPORTED")
        for item in path.iterdir():
            require(item.stat().st_mode&0o777==0o600,"NATIVE_FILE_MODE")
        document=json.loads((path/"manifest.json").read_text())
        require(document["cross_component_atomic"] is False,"NATIVE_ATOMICITY_FALSE_CLAIM")
        unpacked=ROOT/"native-restored"
        unpacked.mkdir(mode=0o700)
        bundle=decrypt(path/"key.age",path/"components.tar.age","native")
        with tarfile.open(bundle) as archive:
            archive.extractall(unpacked,filter="data")
        for name in ("vision","vision_journal","matheval"):
            restore_dump(unpacked/(name+".dump"),name)
        for name in ("sessions.sqlite","admissions.sqlite","cycle.sqlite","archive.sqlite"):
            with sqlite3.connect(unpacked/name) as connection:
                require(connection.execute("SELECT value FROM fixture").fetchall()==[(b"invented-preserved-bytes\x00\r\n",)],"RESTORED_SQLITE_MISMATCH")
        with gzip.open(unpacked/"kanidm.json.gz","rb") as stream:
            require(bool(json.load(stream)),"RESTORED_NATIVE_EXPORT_EMPTY")
        result=subprocess.run(["${pkgs.util-linux}/bin/runuser","-u","forgejo","--","${pkgs.coreutils}/bin/test","-r",str(path/"manifest.json")],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        require(result.returncode!=0,"NATIVE_PUBLICATION_NOT_PRIVATE")

    def verify_forgejo():
        paths=list(Path("/var/backup/forgejo").glob("forgejo-*.tar.age"))
        require(len(paths)==1,"FORGEJO_PUBLICATION_COUNT")
        path=paths[0]
        bundle=decrypt(Path(str(path)+".key.age"),path,"forgejo")
        unpacked=ROOT/"forgejo-restored"
        unpacked.mkdir(mode=0o700)
        with tarfile.open(bundle) as archive:
            require(set(archive.getnames())=={"forgejo.dump","data.tar"},"FORGEJO_BUNDLE_MEMBERS")
            archive.extractall(unpacked,filter="data")
        restore_dump(unpacked/"forgejo.dump","forgejo")
        with tarfile.open(unpacked/"data.tar") as archive:
            require(archive.extractfile("forgejo/repositories/fixture.git/marker").read()==b"invented-forgejo-repository","FORGEJO_FILES_CHANGED")
            require(archive.extractfile("forgejo-identity/client.json").read()==b'{"synthetic":true}',"FORGEJO_SSO_FILE_MISSING")

    def verify_forgejo_refusal():
        root=Path('/var/backup/forgejo')
        require(len(list(root.glob('forgejo-*.tar.age')))==1,'FORGEJO_REFUSAL_PUBLISHED')
        require(not list(root.glob('*.tmp')) and not list(root.glob('.snapshot-*')),
                'FORGEJO_REFUSAL_LEFT_TEMPORARIES')

    def verify_nextcloud():
        paths=[path for path in Path("/var/backup/nextcloud").iterdir() if path.name.endswith("Z")]
        require(len(paths)==1,"NEXTCLOUD_PUBLICATION_COUNT")
        path=paths[0]
        require((Path("/run/nextcloud-fixture/maintenance")).read_text()=="off","NEXTCLOUD_LEFT_IN_MAINTENANCE")
        restore_dump(path/"base.dump","nextcloud")
        with tarfile.open(path/"fichiers.tar") as archive:
            require(archive.extractfile("config/config.php").read()==b"invented-nextcloud-config","NEXTCLOUD_CONFIG_CHANGED")
            require(archive.extractfile("data/marker").read()==b"invented-nextcloud-data","NEXTCLOUD_DATA_CHANGED")
        require((path/"SHA256SUMS").is_file(),"NEXTCLOUD_CHECKSUMS_MISSING")

    def corrupt_source():
        path=Path("/var/lib/mrjam-vision-archive/courriels.sqlite")
        path.rename(path.with_suffix(".retained"))
        path.symlink_to(path.with_suffix(".retained"))

    def verify_refusal():
        published=[path for path in Path("/var/backup/mrjam/native-v1").iterdir() if STAMP.fullmatch(path.name)]
        require(len(published)==1,"REFUSAL_PUBLISHED_PARTIAL_BACKUP")

    CASES={"setup":setup,"native":verify_native,"forgejo":verify_forgejo,"nextcloud":verify_nextcloud,
           "corrupt-source":corrupt_source,"refusal":verify_refusal,"forgejo-refusal":verify_forgejo_refusal}
    try:
        require(len(sys.argv)==2 and sys.argv[1] in CASES,"SYNTHETIC_CASE_REFUSED")
        CASES[sys.argv[1]]()
    except Exception:
        print('{"status":"failed"}')
        raise SystemExit(1)
    print('{"status":"ok"}')
  '';
in pkgs.testers.runNixOSTest {
  name = "mrjam-native-backups-systemd-synthetic";
  requiredFeatures.kvm = false;
  qemu.forceAccel = false;
  globalTimeout = 1200;
  nodes.machine = { lib, ... }: {
    imports = [ ../hosts/mrjam-vps/backups.nix ({ lib, ... }: {
      options.services.mrjamForgejoHost.enable = lib.mkOption { type = lib.types.bool; };
      options.services.mrjamNextcloudHost.enable = lib.mkOption { type = lib.types.bool; };
      options.services.mrjamKanidmHost = {
        enable = lib.mkOption { type = lib.types.bool; };
        artifactStorePath = lib.mkOption { type = lib.types.str; };
        settings = lib.mkOption { type = lib.types.attrs; };
      };
      options.mrjamVpsApplications.workers.archiveConfigurationCredentialFile = lib.mkOption { type = lib.types.str; };
    }) ];
    system.stateVersion = "26.05";
    virtualisation.memorySize = 1536;
    virtualisation.cores = 2;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamForgejoHost.enable = true;
    services.mrjamNextcloudHost.enable = true;
    services.mrjamKanidmHost = { enable = true; artifactStorePath = toString kanidm; inherit settings; };
    mrjamVpsApplications.workers.archiveConfigurationCredentialFile = "/var/lib/mrjam-worker-credentials/v1/archive.json";
    mrjamVpsBackups.enable = true;
    users.groups = lib.genAttrs [ "forgejo" "kanidm" "mrjam-metier" "mrjam-vision-archive" "mrjam-vision-cycle" "mrjam-vision-admission" "nextcloud" ]
      (name: { gid = { forgejo = 982; kanidm = 983; mrjam-metier = 984; mrjam-vision-archive = 943;
        mrjam-vision-cycle = 945; mrjam-vision-admission = 947; nextcloud = 990; }.${name}; });
    users.users = lib.genAttrs [ "forgejo" "kanidm" "mrjam-metier" "mrjam-vision-archive" "mrjam-vision-cycle" "mrjam-vision-admission" "nextcloud" ]
      (name: { isSystemUser = true; group = name; uid = { forgejo = 982; kanidm = 983; mrjam-metier = 984;
        mrjam-vision-archive = 943; mrjam-vision-cycle = 945; mrjam-vision-admission = 947; nextcloud = 990; }.${name}; });
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17; enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      authentication = ''
        local all postgres peer
        local forgejo forgejo peer
        local all all reject
      '';
      initialScript = pkgs.writeText "synthetic-backup-databases.sql" ''
        CREATE ROLE forgejo LOGIN;
        CREATE DATABASE vision;
        CREATE DATABASE vision_journal;
        CREATE DATABASE matheval;
        CREATE DATABASE nextcloud;
        CREATE DATABASE forgejo OWNER forgejo;
        \connect vision
        CREATE TABLE fixture(value text);
        INSERT INTO fixture VALUES('vision');
        \connect vision_journal
        CREATE TABLE fixture(value text);
        INSERT INTO fixture VALUES('vision_journal');
        \connect matheval
        CREATE TABLE fixture(value text);
        INSERT INTO fixture VALUES('matheval');
        \connect nextcloud
        CREATE TABLE fixture(value text);
        INSERT INTO fixture VALUES('nextcloud');
        \connect forgejo
        SET ROLE forgejo;
        CREATE TABLE fixture(value text);
        INSERT INTO fixture VALUES('forgejo');
      '';
    };
    systemd.services.kanidm = {
      serviceConfig = {
        User = "kanidm"; Group = "kanidm"; Type = "simple";
        ExecStart = "${kanidm}/bin/kanidmd server -c ${toml}";
        StateDirectory = "kanidm"; StateDirectoryMode = "0700";
        RuntimeDirectory = "kanidmd"; RuntimeDirectoryMode = "0700";
        LoadCredential = [ "tls-chain:/var/lib/acme/log.mrj.am/fullchain.pem" "tls-key:/var/lib/acme/log.mrj.am/key.pem" ];
        StandardOutput = "null"; StandardError = "null";
      };
    };
    systemd.services.forgejo.serviceConfig = { User = "forgejo"; Type = "simple"; ExecStart = "${pkgs.coreutils}/bin/sleep infinity"; };
    systemd.services.mrjam-forgejo-runner = {
      requires = [ "forgejo.service" ]; after = [ "forgejo.service" ];
      wantedBy = [ "forgejo.service" ];
      serviceConfig = { Type = "simple"; ExecStart = "${pkgs.coreutils}/bin/sleep infinity"; Restart = "no"; };
    };
    systemd.services.forgejo-backup.path = lib.mkBefore [ backupAge ];
    systemd.services.nextcloud-setup.serviceConfig = { Type = "oneshot"; ExecStart = "${pkgs.coreutils}/bin/true"; };
    systemd.services.nextcloud-backup.path = lib.mkForce [ pkgs.coreutils pkgs.util-linux pkgs.gnutar pkgs.findutils pkgs.postgresql_17 occ ];
    environment.systemPackages = [ pkgs.python3 pkgs.postgresql_17 pkgs.curl pkgs.util-linux ];
  };
  testScript = ''
    import json
    import os
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql.service")
    machine.wait_for_unit("postgresql-setup.service")
    checks = []
    def fixture_case(case):
        value = json.loads(machine.succeed("${pkgs.python3}/bin/python3 ${fixture} " + case, timeout=240))
        assert value == {"status": "ok"}
    with subtest("no-backup-timer-autostarts"):
        for name in ("mrjam-sauvegarde", "forgejo-backup", "nextcloud-backup", "postgresqlBackup-matheval", "postgresqlBackup-nextcloud"):
            machine.fail("systemctl is-active --quiet " + name + ".timer")
        fixture_case("setup")
        machine.succeed("systemctl start kanidm.service")
        machine.wait_until_succeeds("curl --silent --fail --noproxy '*' --cacert /run/backup-fixture/tls.pem --resolve log.mrj.am:8443:127.0.0.1 https://log.mrj.am:8443/status >/dev/null", timeout=120)
        checks.append("staged-timers-inactive-with-real-native-provider")
    with subtest("native-backup-exact-unit-and-credentials"):
        machine.succeed("systemctl start mrjam-sauvegarde.service", timeout=300)
        fixture_case("native")
        checks.append("real-unit-private-credentials-sql-sqlite-and-native-export")
    with subtest("retained-forgejo-backup-format-and-writer-lifecycle"):
        machine.succeed("systemctl start forgejo.service")
        machine.succeed("systemctl start forgejo-backup.service", timeout=240)
        machine.succeed("systemctl is-active --quiet forgejo.service")
        fixture_case("forgejo")
        checks.append("forgejo-stop-copy-verified-envelope-and-restart")
        machine.succeed("test -f /run/backup-fixture/forgejo-live-during-encryption")
        machine.wait_for_unit("mrjam-forgejo-runner.service")
        checks.append("forgejo-and-coordinator-resume-before-encryption-finishes")
    with subtest("forgejo-stream-and-capture-corruption-refused"):
        for mode in ("forgejo-change-capture", "forgejo-corrupt-stream"):
            machine.succeed("sleep 1; touch /run/backup-fixture/" + mode)
            machine.fail("systemctl start forgejo-backup.service", timeout=240)
            machine.succeed("systemctl is-active --quiet forgejo.service mrjam-forgejo-runner.service")
            fixture_case("forgejo-refusal")
            machine.succeed("rm /run/backup-fixture/" + mode)
        checks.append("forgejo-stream-compare-and-age-authentication-failures-preserve-backup-and-availability")
    with subtest("retained-nextcloud-backup-format"):
        machine.succeed("systemctl start nextcloud-backup.service", timeout=240)
        fixture_case("nextcloud")
        checks.append("nextcloud-maintenance-contract-and-real-sql-files")
    with subtest("plain-postgresql-backups-preserved"):
        machine.succeed("systemctl start postgresqlBackup-matheval.service postgresqlBackup-nextcloud.service", timeout=180)
        machine.succeed("test -s /var/backup/postgresql/matheval.sql.gz && test -s /var/backup/postgresql/nextcloud.sql.gz")
        checks.append("retained-postgresql-dump-units")
    with subtest("refusal-preserves-previous-backup"):
        fixture_case("corrupt-source")
        machine.fail("systemctl start mrjam-sauvegarde.service", timeout=240)
        fixture_case("refusal")
        checks.append("symlink-source-refused-without-partial-publication")
    Path(os.environ["out"], "result.json").write_text(json.dumps({
        "schema_version": 1, "checks": checks, "passed": True, "synthetic_only": True,
        "production_access": False, "native_source_sha256": "${builtins.hashFile "sha256" ./native.py}",
        "module_sha256": "${builtins.hashFile "sha256" ../hosts/mrjam-vps/backups.nix}",
        "limitations": ["Forgejo writer process and Nextcloud maintenance CLI are fixtures",
                        "PostgreSQL, native Kanidm, systemd credentials, tar and age are real",
                        "No production recipient, disk reserve, external backup or whole-platform restore tested"]
    }, sort_keys=True) + "\n")
  '';
}
