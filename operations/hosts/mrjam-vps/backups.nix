# Retain the public schedules, backup identities and historical destinations.
# Only explicit promotion enables timers; this module never restores data.
{ config, lib, pkgs, ... }:
let
  cfg = config.mrjamVpsBackups;
  native = import ../../backups/package.nix { inherit pkgs; };
  kanidm = config.services.mrjamKanidmHost.artifactStorePath;
  kanidmConfig = (pkgs.formats.toml { }).generate "mrjam-kanidm-backup.toml"
    (config.services.mrjamKanidmHost.settings // {
      tls_chain = "/run/credentials/mrjam-kanidm-backup.service/tls-chain";
      tls_key = "/run/credentials/mrjam-kanidm-backup.service/tls-key";
    });
  archiveConfiguration = "/var/lib/mrjam-worker-credentials/v1/archive.json";
  privateRecipient = unit: pkgs.writeScript "mrjam-private-backup-recipient-${unit}" ''
    #!${pkgs.python3}/bin/python3
    import sys
    sys.path.insert(0, "${native}/libexec")
    from native import recipient
    try:
        value = recipient("/run/credentials/${unit}.service/archive-configuration")
    except Exception:
        raise SystemExit(1)
    print(value)
  '';
  timer = calendar: jitter: {
    wantedBy = lib.optional cfg.promote "timers.target";
    timerConfig = { OnCalendar = calendar; RandomizedDelaySec = jitter; Persistent = true; };
  };
  rootService = {
    Type = "oneshot";
    User = "root";
    UMask = "0077";
    NoNewPrivileges = true;
    PrivateTmp = true;
    ProtectHome = true;
    StandardInput = "null";
    StandardOutput = "null";
    StandardError = "null";
    LimitCORE = 0;
    TimeoutStartSec = "30min";
  };
in {
  options.mrjamVpsBackups = {
    enable = lib.mkEnableOption "retained service backups and native component backup";
    promote = lib.mkEnableOption "backup schedules after explicit cutover";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.mrjamForgejoHost.enable && config.services.mrjamKanidmHost.enable
          && config.services.mrjamNextcloudHost.enable && config.services.postgresql.enable;
        message = "mrjamVpsBackups: require all separately adopted services."; }
      { assertion = config.mrjamVpsApplications.workers.archiveConfigurationCredentialFile == archiveConfiguration;
        message = "mrjamVpsBackups: preserve the qualified private recipient reference, never a recipient copied to the store."; }
    ];
    systemd.tmpfiles.rules = [
      "d /var/backup/mrjam 0700 root root -"
      "d /var/backup/mrjam/native-v1 0700 root root -"
      "d /var/backup/forgejo 0700 root root -"
      "d /var/backup/nextcloud 0700 root root -"
    ];
    services.postgresqlBackup = {
      enable = true;
      databases = [ "matheval" "nextcloud" ];
      backupAll = false;
      location = "/var/backup/postgresql";
      startAt = [ ];
    };
    systemd.services.postgresqlBackup-matheval.serviceConfig = { StandardOutput = "null"; StandardError = "null"; };
    systemd.services.postgresqlBackup-nextcloud.serviceConfig = { StandardOutput = "null"; StandardError = "null"; };
    systemd.timers = {
      postgresqlBackup-matheval = timer "daily" "0";
      postgresqlBackup-nextcloud = timer "daily" "0";
      nextcloud-backup = timer "*-*-* 03:30:00 UTC" "0";
      forgejo-backup = timer "*-*-* 04:45:00" "10min";
      mrjam-sauvegarde = timer "daily" "30m";
    };

    systemd.services.mrjam-kanidm-backup = {
      description = "Private native Kanidm export for the encrypted component backup";
      after = [ "kanidm.service" ];
      requires = [ "kanidm.service" ];
      restartIfChanged = false;
      stopIfChanged = false;
      path = [ pkgs.coreutils pkgs.gzip ];
      script = ''
        set -euo pipefail
        umask 0077
        test -s /var/lib/kanidm/kanidm.db
        test ! -L /var/lib/kanidm/kanidm.db
        temporary=/run/mrjam-kanidm-backup/kanidm.partial
        test ! -e "$temporary"
        test ! -L "$temporary"
        (set -C; ${kanidm}/bin/kanidmd -c ${kanidmConfig} scripting backup > "$temporary")
        test -s "$temporary"
        gzip -t "$temporary"
        chmod 0600 "$temporary"
        mv -f "$temporary" /run/mrjam-kanidm-backup/kanidm.json.gz
      '';
      serviceConfig = {
        Type = "oneshot";
        User = "kanidm";
        Group = "kanidm";
        RuntimeDirectory = "mrjam-kanidm-backup";
        RuntimeDirectoryMode = "0700";
        RuntimeDirectoryPreserve = true;
        LoadCredential = [ "tls-chain:/var/lib/acme/log.mrj.am/fullchain.pem" "tls-key:/var/lib/acme/log.mrj.am/key.pem" ];
        ReadWritePaths = [ "/var/lib/kanidm" "/run/mrjam-kanidm-backup" ];
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        PrivateNetwork = true;
        RestrictAddressFamilies = [ "AF_UNIX" ];
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        UMask = "0077";
        StandardInput = "null";
        StandardOutput = "null";
        StandardError = "null";
        LimitCORE = 0;
        TimeoutStartSec = "10min";
        MemoryMax = "768M";
        TasksMax = 64;
      };
    };
    systemd.services.mrjam-sauvegarde = {
      description = "Encrypted native Vision, journal, session, mail and identity component backups";
      after = [ "postgresql.service" "kanidm.service" ];
      requires = [ "postgresql.service" "kanidm.service" ];
      restartIfChanged = false;
      stopIfChanged = false;
      serviceConfig = rootService // {
        ExecStart = "${native}/bin/mrjam-native-backup";
        LoadCredential = [ "archive-configuration:${archiveConfiguration}" ];
        ProtectSystem = "strict";
        ReadWritePaths = [ "/var/backup/mrjam/native-v1" ];
        MemoryMax = "512M";
        TasksMax = 64;
      };
    };

    # Preserve the historical local Nextcloud format and seven-day retention.
    # No upgrade, configuration repair or creation of an application database.
    systemd.services.nextcloud-backup = {
      description = "Retained local Nextcloud database and file backup";
      after = [ "nextcloud-setup.service" "postgresql.service" ];
      requires = [ "nextcloud-setup.service" "postgresql.service" ];
      restartIfChanged = false;
      stopIfChanged = false;
      path = [ pkgs.coreutils pkgs.util-linux pkgs.gnutar pkgs.findutils
        config.services.postgresql.package config.services.nextcloud.occ ];
      serviceConfig = rootService;
      script = ''
        set -euo pipefail
        umask 0077
        exec 9>/run/lock/nextcloud-backup.lock
        flock -x 9
        destination=/var/backup/nextcloud
        test -d "$destination"
        test ! -L "$destination"
        horodatage=$(date -u +%Y%m%dT%H%M%SZ)
        temporaire="$destination/$horodatage.tmp"
        final="$destination/$horodatage"
        test ! -e "$final"
        mkdir "$temporaire"
        maintenance=0
        restaurer_service() {
          if test "$maintenance" -eq 1; then
            runuser -u nextcloud -- nextcloud-occ maintenance:mode --off || true
          fi
        }
        trap restaurer_service EXIT
        trap 'exit 1' HUP INT TERM
        runuser -u nextcloud -- nextcloud-occ maintenance:mode --on
        maintenance=1
        runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl nextcloud > "$temporaire/base.dump"
        tar --acls --xattrs -C /var/lib/nextcloud -cpf "$temporaire/fichiers.tar" config data
        (cd "$temporaire" && sha256sum base.dump fichiers.tar > SHA256SUMS)
        pg_restore --list "$temporaire/base.dump" >/dev/null
        tar -tf "$temporaire/fichiers.tar" >/dev/null
        runuser -u nextcloud -- nextcloud-occ maintenance:mode --off
        maintenance=0
        mv -T "$temporaire" "$final"
        find "$destination" -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime +7 -exec rm -rf -- {} +
      '';
    };

    # Preserve the disposable-key envelope and verification used by Forgejo.
    # The recipient is read only inside this private unit, from the existing
    # archive configuration, instead of embedding it in a new Nix derivation.
    systemd.services.forgejo-backup = {
      description = "Retained encrypted Forgejo database and repository backup";
      after = [ "postgresql.service" ];
      requires = [ "postgresql.service" ];
      restartIfChanged = false;
      stopIfChanged = false;
      path = [ pkgs.coreutils pkgs.diffutils pkgs.gnutar pkgs.age pkgs.util-linux pkgs.git
        config.services.postgresql.package ];
      serviceConfig = rootService // { LoadCredential = [ "archive-configuration:${archiveConfiguration}" ]; };
      script = ''
        set -euo pipefail
        umask 0077
        exec 9>/run/lock/forgejo-backup.lock
        flock -x 9
        recipient=$(${privateRecipient "forgejo-backup"})
        tmp=$(mktemp -d /var/backup/forgejo/.snapshot-XXXXXX)
        active=0
        if ${pkgs.systemd}/bin/systemctl is-active --quiet forgejo.service; then active=1; fi
        cleanup() {
          if test "$active" = 1; then ${pkgs.systemd}/bin/systemctl start forgejo.service; fi
          rm -rf -- "$tmp"
        }
        trap cleanup EXIT
        trap 'exit 1' HUP INT TERM
        ${pkgs.systemd}/bin/systemctl stop forgejo.service
        runuser -u forgejo -- pg_dump -h /run/postgresql --format=custom forgejo > "$tmp/forgejo.dump"
        roots=(forgejo)
        if test -d /var/lib/forgejo-identity; then
          test ! -L /var/lib/forgejo-identity
          roots+=(forgejo-identity)
        fi
        tar --acls --xattrs -C /var/lib -cf "$tmp/data.tar" "''${roots[@]}"
        dest=/var/backup/forgejo/forgejo-$(date -u +%Y%m%dT%H%M%SZ).tar.age
        test ! -e "$dest"
        test ! -e "$dest.key.age"
        age-keygen -o "$tmp/key" 2>/dev/null
        public=$(age-keygen -y "$tmp/key")
        age -r "$recipient" "$tmp/key" > "$dest.key.age.tmp"
        tar -C "$tmp" -cf - forgejo.dump data.tar | age -r "$public" > "$dest.tmp"
        mkdir "$tmp/verified"
        age -d -i "$tmp/key" "$dest.tmp" | tar -xf - -C "$tmp/verified"
        cmp "$tmp/forgejo.dump" "$tmp/verified/forgejo.dump"
        cmp "$tmp/data.tar" "$tmp/verified/data.tar"
        pg_restore --list "$tmp/verified/forgejo.dump" >/dev/null
        mv "$dest.key.age.tmp" "$dest.key.age"
        mv "$dest.tmp" "$dest"
      '';
    };
  };
}
