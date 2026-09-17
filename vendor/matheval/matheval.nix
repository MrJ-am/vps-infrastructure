{ config, lib, pkgs, ... }:
let
  cfg = config.services.matheval;
  release = pkgs.writeShellApplication {
    name = "matheval-release";
    runtimeInputs = [ pkgs.coreutils pkgs.gnutar pkgs.gzip pkgs.nodejs_22 pkgs.curl pkgs.util-linux ];
    text = ''
      id="''${1:-}"
      if [[ ! "$id" =~ ^[0-9a-f]{40}$ ]]; then echo "Identifiant de version invalide" >&2; exit 2; fi
      exec 9>/srv/matheval/deploy.lock
      flock 9
      archive="/srv/matheval/incoming/$id.tar.gz"
      target="/srv/matheval/releases/$id"
      if [[ ! -d "$target" ]]; then
        staging="$(mktemp -d "/srv/matheval/releases/.prepare-$id.XXXXXX")"
        trap 'rm -rf -- "$staging"' EXIT
        tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$staging"
        test "$(cat "$staging/RELEASE")" = "$id"
        npm --prefix "$staging/server" ci --omit=dev --ignore-scripts
        chmod 0755 "$staging"
        mv "$staging" "$target"
        trap - EXIT
      fi
      previous=""
      if [[ -L /srv/matheval/current && -d /srv/matheval/current ]]; then
        previous="$(readlink -f /srv/matheval/current)"
      fi
      ln -sfn "$target" /srv/matheval/next
      mv -Tf /srv/matheval/next /srv/matheval/current
      ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart matheval.service
      for _attempt in $(seq 1 30); do
        if curl --fail --silent --max-time 2 http://127.0.0.1:3000/matheval/api/health >/dev/null; then
          echo "Version $id active"
          exit 0
        fi
        sleep 1
      done
      if [[ -n "$previous" && -d "$previous" && "$previous" != "$target" ]]; then
        ln -sfn "$previous" /srv/matheval/next
        mv -Tf /srv/matheval/next /srv/matheval/current
        ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart matheval.service
      fi
      echo "La version ne répond pas ; retour à la version précédente tenté." >&2
      exit 1
    '';
  };
  backup = pkgs.writeShellApplication {
    name = "matheval-backup";
    runtimeInputs = [ pkgs.postgresql_17 pkgs.age pkgs.util-linux ];
    text = ''
      runuser -u postgres -- pg_dump --format=custom matheval | age -r ${lib.escapeShellArg cfg.backupRecipient}
    '';
  };
in {
  options.services.matheval = {
    enable = lib.mkEnableOption "Matheval";
    domain = lib.mkOption { type = lib.types.str; default = "principiipetit.io"; };
    deploymentPublicKeys = lib.mkOption { type = lib.types.listOf lib.types.str; default = []; };
    backupRecipient = lib.mkOption { type = lib.types.str; default = ""; description = "Clé publique age ; la clé privée est conservée hors du VPS."; };
  };
  config = lib.mkIf cfg.enable {
    services.postgresql = {
      enable = true;
      package = pkgs.postgresql_17;
      enableTCPIP = false;
      settings.listen_addresses = lib.mkForce "";
      ensureDatabases = [ "matheval" ];
      ensureUsers = [{ name = "matheval"; ensureDBOwnership = true; }];
    };
    services.postgresqlBackup = {
      enable = true;
      databases = [ "matheval" ];
      startAt = "daily";
      location = "/var/backup/postgresql";
    };
    users.groups.matheval = {};
    users.users.matheval = { isSystemUser = true; group = "matheval"; };
    users.users.matheval-deploy = {
      isSystemUser = true;
      group = "matheval";
      home = "/var/lib/matheval-deploy";
      createHome = true;
      shell = pkgs.bashInteractive;
      openssh.authorizedKeys.keys = map (key: "restrict " + key) cfg.deploymentPublicKeys;
    };
    systemd.tmpfiles.rules = [
      "d /srv/matheval 0755 matheval-deploy matheval -"
      "d /srv/matheval/releases 0755 matheval-deploy matheval -"
      "d /srv/matheval/incoming 0700 matheval-deploy matheval -"
      "d /var/lib/matheval 0700 matheval matheval -"
    ];
    environment.systemPackages = [ pkgs.nodejs_22 pkgs.rsync release ] ++ lib.optional (cfg.backupRecipient != "") backup;
    security.sudo.extraRules = [{
      users = [ "matheval-deploy" ];
      commands = [
        { command = "${pkgs.systemd}/bin/systemctl restart matheval.service"; options = [ "NOPASSWD" ]; }
      ] ++ lib.optional (cfg.backupRecipient != "") { command = "${backup}/bin/matheval-backup"; options = [ "NOPASSWD" ]; };
    }];
    systemd.services.matheval = {
      description = "Collecte et administration Matheval";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" "postgresql.service" ];
      requires = [ "postgresql.service" ];
      environment = {
        NODE_ENV = "production";
        HOST = "127.0.0.1";
        PORT = "3000";
        BASE_PATH = "/matheval";
        PUBLIC_ORIGIN = "https://${cfg.domain}";
      };
      serviceConfig = {
        Type = "simple";
        User = "matheval";
        Group = "matheval";
        WorkingDirectory = "/srv/matheval/current";
        ExecStart = "${pkgs.nodejs_22}/bin/node /srv/matheval/current/server/src/index.mjs";
        EnvironmentFile = "/var/lib/matheval/secrets.env";
        Restart = "on-failure";
        RestartSec = 3;
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        UMask = "0077";
      };
    };
  };
}
