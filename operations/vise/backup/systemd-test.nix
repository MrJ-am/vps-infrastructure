{ nixpkgs, artifact }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  qualified = builtins.storePath (toString artifact);
in pkgs.testers.runNixOSTest {
  name = "mrjam-vise-coherent-backup-synthetic";
  requiredFeatures.kvm = false; qemu.forceAccel = false; globalTimeout = 1200;
  nodes.machine = { lib, ... }: {
    imports = [ ../../nixos/mrjam-vise.nix ./module.nix ];
    system.stateVersion = "26.05";
    # ViSe installs /server rather than /bin/server, so systemPackages does
    # not retain its root in buildEnv. Keep the exact artifact explicitly.
    system.extraDependencies = [ qualified ];
    virtualisation.memorySize = 1536; virtualisation.cores = 2;
    virtualisation.diskSize = 6144;
    virtualisation.qemu.options = [ "-machine accel=tcg" ];
    services.mrjamVise = { enable = true; adoption = { uid = 978; gid = 978; };
      artifactRoot = builtins.unsafeDiscardStringContext qualified; };
    services.mrjamViseCoherentBackup = {
      enable = true; promote = false; credentialFile = "/root/synthetic-recipient.json";
    };
    # Exercise the same boot activation as promote, without the daily capture
    # timer racing the fixture's initial provisioning of invented data.
    systemd.services.mrjam-vise-backup-recovery.wantedBy = lib.mkForce [ "multi-user.target" ];
    services.postgresql = {
      enable = true; package = pkgs.postgresql_17;
      ensureDatabases = [ "etp_carnet" ];
      # Never restore DDL ownership at boot after the explicit role adoption.
      ensureUsers = [{ name = "etp_carnet"; ensureDBOwnership = false; }];
    };
    environment.systemPackages = [ pkgs.postgresql_17 pkgs.util-linux pkgs.curl pkgs.age pkgs.python3 pkgs.gnutar ];
    environment.etc."synthetic-schema.sql".source = ../schema-v1.sql;
    environment.etc."synthetic-adopt.sql".source = ../adopt-runtime-role.sql;
    systemd.services.vise.serviceConfig.Restart = lib.mkForce "no";
    # Delay only the synthetic stop-interruption scenario; production gets
    # no delay or extra hook. The marker is in the service's private state.
    systemd.services.vise.preStop = ''
      if test -e /run/synthetic-vise-delay; then
        ${pkgs.coreutils}/bin/touch /var/lib/etp-carnet/synthetic-stopping
        ${pkgs.coreutils}/bin/sleep 15
        ${pkgs.coreutils}/bin/rm /var/lib/etp-carnet/synthetic-stopping
      fi
    '';

  };
  testScript = ''
    import json, os, shlex
    from pathlib import Path
    start_all()
    machine.wait_for_unit("postgresql-setup.service")
    machine.wait_until_succeeds("test \"$(systemctl show -p ActiveState --value mrjam-vise-backup-recovery.service)\" = failed", timeout=60)
    checks = []
    def sql(statement):
        return machine.succeed("runuser -u postgres -- psql -XwqAt -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -c " + shlex.quote(statement)).strip()
    def state():
        return json.loads(machine.succeed("cat /var/lib/mrjam-vise-backup/state.json"))
    def healthy():
        machine.wait_until_succeeds("curl -fsS --max-time 5 http://127.0.0.1:3017/api/health", timeout=60)
    def reset():
        machine.succeed("systemctl reset-failed mrjam-vise-backup.service")

    with subtest("initialize only invented SQL, ledger, recipient and lock"):
        machine.succeed("runuser -u postgres -- psql -Xw -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-schema.sql")
        machine.succeed("runuser -u postgres -- psql -Xw -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-adopt.sql")
        assert sql("SELECT has_database_privilege('etp_carnet','etp_carnet','CREATE')") == "f"
        machine.succeed("install -d -m 0700 -o etp_carnet -g etp_carnet /var/lib/etp-carnet")
        machine.succeed("install -m 0600 -o etp_carnet -g etp_carnet /dev/null /var/lib/etp-carnet/deletions.log")
        machine.succeed("install -d -m 0700 /var/lib/mrjam-cutover/first-deployment")
        machine.succeed("install -m 0600 /dev/null /var/lib/mrjam-cutover/first-deployment/transaction.lock")
        machine.succeed("age-keygen -o /root/synthetic-recipient.key 2>/dev/null")
        machine.succeed("python3 -c " + shlex.quote("import json,subprocess,os; r=subprocess.check_output(['age-keygen','-y','/root/synthetic-recipient.key'],text=True).strip(); p='/root/synthetic-recipient.json'; open(p,'w').write(json.dumps({'age_recipient':r})); os.chmod(p,0o600)"))
        account = "10000000-0000-4000-8000-000000000001"
        sql("INSERT INTO comptes(id,pseudonyme,password_hash,auth_recovery_hash) VALUES('" + account + "','synthetic_backup','invented','invented')")
        machine.succeed("systemctl start vise.service")
        healthy()

    with subtest("real offline paired encrypted backup restores service"):
        machine.succeed("systemctl start mrjam-vise-backup.service", timeout=300)
        healthy()
        journal = state()
        assert journal["phase"] == "complete" and journal["restart_required"] is True
        capture_id = journal["capture_id"]
        root = "/var/backup/mrjam/vise-v1/" + capture_id
        manifest = json.loads(machine.succeed("cat " + root + "/manifest.json"))
        assert manifest["offline_pair"] is True
        machine.succeed("age -d -i /root/synthetic-recipient.key -o /root/disposable.key " + root + "/key.age")
        machine.succeed("age -d -i /root/disposable.key -o /root/pair.tar " + root + "/components.tar.age")
        machine.succeed("install -d -m 0700 /root/pair")
        machine.succeed("tar -xf /root/pair.tar -C /root/pair")
        machine.succeed("cmp /root/pair/deletions.log /var/lib/etp-carnet/deletions.log")
        machine.succeed("pg_restore --list /root/pair/database.dump >/dev/null")
        checks.append("real-offline-pair-encryption-recipient-decryption-and-service-restart")

    with subtest("restore retains newer ledger and cannot resurrect an account"):
        machine.succeed("systemctl stop vise.service")
        machine.succeed("printf '%s\\n' " + account + " >> /var/lib/etp-carnet/deletions.log")
        sql("DELETE FROM comptes WHERE id='" + account + "'")
        machine.succeed("chmod 0644 /root/pair/database.dump; install -m 0644 /root/pair/database.dump /tmp/synthetic-restore.dump")
        machine.succeed("runuser -u postgres -- pg_restore -h /run/postgresql -d etp_carnet --clean --if-exists --no-owner --no-privileges /tmp/synthetic-restore.dump")
        machine.succeed("runuser -u postgres -- psql -Xw -h /run/postgresql -d etp_carnet -v ON_ERROR_STOP=1 -f /etc/synthetic-adopt.sql")
        assert sql("SELECT count(*) FROM comptes WHERE id='" + account + "'") == "1"
        machine.succeed("systemctl start vise.service")
        healthy()
        assert sql("SELECT count(*) FROM comptes WHERE id='" + account + "'") == "0"
        checks.append("real-restore-with-current-ledger-no-resurrection")

    with subtest("successful capture applies retention to verified old encrypted pairs"):
        # Clone only the invented encrypted fixture, then age its manifests.
        # Keep the original recent pair and require a second fresh capture
        # before the actual service may remove either old clone.
        parent = "/var/backup/mrjam/vise-v1/"
        for old_id in ["1" * 32, "2" * 32]:
            old_path = parent + old_id
            machine.succeed("test ! -e " + old_path)
            machine.succeed("cp -a " + root + " " + old_path)
            machine.succeed("python3 -c " + shlex.quote(
                "import json,time,pathlib; p=pathlib.Path(" + repr(old_path + "/manifest.json") + "); "
                "v=json.loads(p.read_text()); v.update(capture_id=" + repr(old_id) + ",created=int(time.time())-90*86400); "
                "p.write_text(json.dumps(v))"))
        machine.succeed("systemctl start mrjam-vise-backup.service", timeout=300)
        assert state()["phase"] == "complete" and state()["capture_id"] != capture_id
        healthy()
        machine.succeed("test -d " + root)
        machine.succeed("test -d " + parent + state()["capture_id"])
        for old_id in ["1" * 32, "2" * 32]:
            machine.succeed("test ! -e " + parent + old_id)
        checks.append("real-service-retention-removes-old-verified-pairs-and-keeps-two-recent-pairs")

    with subtest("systemd cgroup SIGKILL during graceful stop executes independent recovery"):
        machine.succeed("touch /run/synthetic-vise-delay")
        machine.succeed("systemctl start --no-block mrjam-vise-backup.service")
        machine.wait_until_succeeds("test -f /var/lib/etp-carnet/synthetic-stopping", timeout=60)
        assert state()["phase"] == "quiescing"
        machine.succeed("systemctl kill --kill-whom=all --signal=KILL mrjam-vise-backup.service")
        machine.wait_until_succeeds("python3 -c " + shlex.quote("import json; assert json.load(open('/var/lib/mrjam-vise-backup/state.json'))['phase']=='aborted'"), timeout=60)
        healthy()
        machine.succeed("rm /run/synthetic-vise-delay")
        checks.append("real-systemd-cgroup-kill-during-graceful-stop-independent-recovery-restarts-vise")

    with subtest("generation switch holding lock cannot deadlock recovery"):
        before = state()
        pid = machine.succeed("systemctl show vise.service -p MainPID --value").strip()
        machine.succeed("python3 -c " + shlex.quote(
            "import fcntl,subprocess; "
            "f=open('/var/lib/mrjam-cutover/first-deployment/transaction.lock','rb'); "
            "fcntl.flock(f,fcntl.LOCK_EX); "
            "subprocess.run(['systemctl','start','mrjam-vise-backup-recovery.service'],check=True,timeout=10)"))
        assert state() == before
        assert machine.succeed("systemctl show vise.service -p MainPID --value").strip() == pid
        machine.succeed("journalctl -u mrjam-vise-backup-recovery.service -o cat | grep -F VISE_BACKUP_RECOVERY_DEFERRED")
        machine.succeed("systemctl start mrjam-vise-backup-recovery.timer")
        machine.wait_until_succeeds("journalctl -u mrjam-vise-backup-recovery.service -o cat -g VISE_BACKUP | tail -n 1 | grep -F VISE_BACKUP_RECOVERY_COMPLETE", timeout=90)
        assert state() == before
        healthy()
        machine.succeed("systemctl stop mrjam-vise-backup-recovery.timer")
        checks.append("generation-lock-recovery-defers-without-effects-and-timer-retries")

    with subtest("sudden VM power failure preserves restart intent for boot recovery"):
        reset()
        machine.succeed("touch /run/synthetic-vise-delay")
        machine.succeed("systemctl start --no-block mrjam-vise-backup.service")
        machine.wait_until_succeeds("test -f /var/lib/etp-carnet/synthetic-stopping", timeout=60)
        interrupted = state()
        assert interrupted["phase"] == "quiescing" and interrupted["restart_required"] is True
        machine.crash()
        machine.start()
        machine.wait_for_unit("postgresql.service")
        machine.wait_until_succeeds("python3 -c " + shlex.quote("import json; assert json.load(open('/var/lib/mrjam-vise-backup/state.json'))['phase']=='aborted'"), timeout=90)
        assert state()["capture_id"] == interrupted["capture_id"]
        healthy()
        assert sql("SELECT count(*) FROM comptes WHERE id='" + account + "'") == "0"
        checks.append("vm-power-failure-durable-intent-boot-recovery-and-no-resurrection")
        assert sql("SELECT has_database_privilege('etp_carnet','etp_carnet','CREATE')") == "f"

    Path(os.environ['out'], 'vise-backup-result.json').write_text(json.dumps({
      'schema_version': 1, 'scope': 'synthetic-nixos-vm-tcg', 'checks': checks,
      'production_data_accessed': False, 'production_activated': False,
      'limitations': ['Offsite transfer remains unqualified', 'No production activation or production reboot']
    }, sort_keys=True))
  '';
}
