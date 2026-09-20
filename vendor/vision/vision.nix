{ config, lib, pkgs, ... }:
let
  cfg = config.services.vision;

  bootstrapPackage = pkgs.stdenv.mkDerivation {
    pname = "vision-bootstrap";
    version = cfg.version;
    src = cfg.bootstrapSource;
    nativeBuildInputs = [ pkgs.sbcl ];
    dontStrip = true;
    buildPhase = ''
      runHook preBuild
      export HOME="$TMPDIR"
      export XDG_CACHE_HOME="$TMPDIR/.cache"
      mkdir -p "$XDG_CACHE_HOME"
      sh build.sh
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      mkdir -p "$out/app"
      cp -R vision.asd src docs migrations scripts build.sh "$out/app/"
      install -m 0550 vision "$out/app/vision"
      printf '%s\n' ${lib.escapeShellArg cfg.bootstrapCommit} > "$out/app/RELEASE"
      runHook postInstall
    '';
  };

  release = pkgs.writeShellApplication {
    name = "vision-release";
    runtimeInputs = [ pkgs.coreutils pkgs.gnutar pkgs.gzip pkgs.sbcl pkgs.curl pkgs.util-linux ];
    text = ''
      id="''${1:-}"
      if [[ ! "$id" =~ ^[0-9a-f]{40}$ ]]; then
        echo "Identifiant de version invalide" >&2
        exit 2
      fi

      exec 9>/srv/vision/deploy.lock
      flock 9
      archive="/srv/vision/incoming/$id.tar.gz"
      target="/srv/vision/releases/$id"
      test -f "$archive"

      if [[ ! -d "$target" ]]; then
        staging="$(mktemp -d "/srv/vision/releases/.prepare-$id.XXXXXX")"
        trap 'rm -rf -- "$staging"' EXIT
        tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$staging"
        test "$(cat "$staging/RELEASE")" = "$id"
        (cd "$staging" && sh build.sh)
        chmod 0550 "$staging/vision"
        chmod 0750 "$staging"
        mv "$staging" "$target"
        trap - EXIT
      fi

      previous=""
      if [[ -L /srv/vision/current && -d /srv/vision/current ]]; then
        previous="$(readlink -f /srv/vision/current)"
      fi
      ln -sfn "$target" /srv/vision/next
      mv -Tf /srv/vision/next /srv/vision/current

      if ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart vision-migrate.service \
          && ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart vision.service; then
        for _attempt in $(seq 1 30); do
          if curl --fail --silent --max-time 2 http://127.0.0.1:${toString cfg.port}/healthz >/dev/null; then
            rm -f -- "$archive"
            echo "Version $id active"
            exit 0
          fi
          sleep 1
        done
      fi

      if [[ -n "$previous" && -d "$previous" && "$previous" != "$target" ]]; then
        ln -sfn "$previous" /srv/vision/next
        mv -Tf /srv/vision/next /srv/vision/current
        ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart vision-migrate.service || true
        ${config.security.wrapperDir}/sudo -n ${pkgs.systemd}/bin/systemctl restart vision.service || true
      fi
      echo "La version ne repond pas ; retour a la version precedente tente." >&2
      exit 1
    '';
  };

  setCredentials = pkgs.writeShellApplication {
    name = "vision-set-credentials";
    runtimeInputs = [ pkgs.openssl pkgs.coreutils ];
    text = ''
      if (( EUID != 0 )); then
        echo "vision-set-credentials doit etre execute par root" >&2
        exit 1
      fi
      : "''${VISION_API_USERNAME:?VISION_API_USERNAME absent}"
      : "''${VISION_API_PASSWORD:?VISION_API_PASSWORD absent}"
      if [[ ! "$VISION_API_USERNAME" =~ ^[A-Za-z0-9_.-]{1,64}$ ]]; then
        echo "Identifiant Vision invalide" >&2
        exit 2
      fi
      if (( ''${#VISION_API_PASSWORD} < 24 )); then
        echo "Le mot de passe Vision doit contenir au moins 24 caracteres" >&2
        exit 2
      fi

      temporary="$(mktemp /var/lib/vision/auth/.htpasswd.XXXXXX)"
      trap 'rm -f -- "$temporary"; unset VISION_API_USERNAME VISION_API_PASSWORD password_hash' EXIT
      password_hash="$(printf '%s\n' "$VISION_API_PASSWORD" | openssl passwd -6 -stdin)"
      printf '%s:%s\n' "$VISION_API_USERNAME" "$password_hash" > "$temporary"
      chown root:vision-auth "$temporary"
      chmod 0640 "$temporary"
      mv -f -- "$temporary" /var/lib/vision/auth/htpasswd
    '';
  };

  backup = pkgs.writeShellApplication {
    name = "vision-backup";
    runtimeInputs = [ config.services.postgresql.package pkgs.age pkgs.util-linux ];
    text = ''
      runuser -u postgres -- pg_dump --format=custom vision \
        | age -r ${lib.escapeShellArg cfg.backupRecipient}
    '';
  };
in {
  options.services.vision = {
    enable = lib.mkEnableOption "Vision API";
    domain = lib.mkOption { type = lib.types.str; default = "vision.mrj.am"; };
    port = lib.mkOption { type = lib.types.port; default = 3001; };
    version = lib.mkOption { type = lib.types.str; default = "1.0.0"; };
    bootstrapSource = lib.mkOption {
      type = lib.types.path;
      description = "Source Vision revue et epinglee par l'infrastructure.";
    };
    bootstrapCommit = lib.mkOption {
      type = lib.types.str;
      description = "Commit Git exact de bootstrap, sur quarante caracteres hexadecimaux.";
    };
    deploymentPublicKeys = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [];
    };
    backupRecipient = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Cle publique age ; la cle privee reste hors du VPS et de Git.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = builtins.match "[0-9a-f]{40}" cfg.bootstrapCommit != null;
        message = "Vision exige le SHA Git complet de son bootstrap.";
      }
      {
        assertion = cfg.backupRecipient == "" || builtins.match "age1[0-9a-z]+" cfg.backupRecipient != null;
        message = "La cle de sauvegarde Vision doit etre un destinataire age public.";
      }
    ];

    users.groups.vision = {};
    users.groups.vision-auth = {};
    users.users.vision = {
      isSystemUser = true;
      group = "vision";
    };
    users.users.vision-deploy = {
      isSystemUser = true;
      group = "vision";
      home = "/var/lib/vision-deploy";
      createHome = true;
      shell = pkgs.bashInteractive;
      openssh.authorizedKeys.keys = map (key: "restrict " + key) cfg.deploymentPublicKeys;
    };
    users.users.nginx.extraGroups = [ "vision-auth" ];

    systemd.tmpfiles.rules = [
      "d /srv/vision 0750 vision-deploy vision -"
      "d /srv/vision/releases 0750 vision-deploy vision -"
      "d /srv/vision/incoming 0700 vision-deploy vision -"
      "d /var/lib/vision 0710 root vision-auth -"
      "d /var/lib/vision/auth 0750 root vision-auth -"
      "f /var/lib/vision/auth/htpasswd 0640 root vision-auth - vision-disabled:!"
    ];

    environment.systemPackages = [ pkgs.sbcl pkgs.rsync release setCredentials ]
      ++ lib.optional (cfg.backupRecipient != "") backup;

    security.sudo.extraRules = [{
      users = [ "vision-deploy" ];
      commands = [
        { command = "${pkgs.systemd}/bin/systemctl restart vision-migrate.service"; options = [ "NOPASSWD" ]; }
        { command = "${pkgs.systemd}/bin/systemctl restart vision.service"; options = [ "NOPASSWD" ]; }
      ] ++ lib.optional (cfg.backupRecipient != "") {
        command = "${backup}/bin/vision-backup";
        options = [ "NOPASSWD" ];
      };
    }];

    systemd.services.vision-bootstrap = {
      description = "Installer le bootstrap epingle de Vision si necessaire";
      requiredBy = [ "vision-migrate.service" ];
      before = [ "vision-migrate.service" ];
      after = [ "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        UMask = "0077";
        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        ReadWritePaths = [ "/srv/vision" ];
        RestrictAddressFamilies = [ "AF_UNIX" ];
      };
      script = ''
        set -eu
        target=/srv/vision/releases/${cfg.bootstrapCommit}
        if ! test -d "$target"; then
          staging="$(mktemp -d /srv/vision/releases/.bootstrap.XXXXXX)"
          cp -R ${bootstrapPackage}/app/. "$staging/"
          chown -R vision-deploy:vision "$staging"
          chmod -R u=rwX,g=rX,o= "$staging"
          chmod 0550 "$staging/vision"
          mv "$staging" "$target"
        fi
        if ! test -L /srv/vision/current; then
          ln -s "$target" /srv/vision/current
        fi
      '';
    };

    systemd.services.vision-migrate = {
      description = "Appliquer les migrations PostgreSQL de Vision";
      after = [ "vision-bootstrap.service" "postgresql.service" "postgresql-setup.service" ];
      requires = [ "vision-bootstrap.service" "postgresql.service" "postgresql-setup.service" ];
      before = [ "vision.service" ];
      serviceConfig = {
        Type = "oneshot";
        User = "vision";
        Group = "vision";
        WorkingDirectory = "/srv/vision/current";
        ExecStart = "${pkgs.dash}/bin/dash /srv/vision/current/scripts/migrate.sh";
        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        ProtectProc = "invisible";
        ProcSubset = "pid";
        RestrictSUIDSGID = true;
        RestrictRealtime = true;
        LockPersonality = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_UNIX" ];
        UMask = "0077";
      };
      path = [ config.services.postgresql.package ];
      environment = {
        PGHOST = "/run/postgresql";
        PGDATABASE = "vision";
        PGUSER = "vision";
      };
    };

    systemd.services.vision = {
      description = "API Vision";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" "vision-migrate.service" ];
      requires = [ "vision-migrate.service" ];
      environment = {
        IP = "127.0.0.1";
        PORT = toString cfg.port;
        VISION_VERSION = cfg.version;
        VISION_DOCUMENT_ROOT = "/srv/vision/current/docs";
        PGHOST = "/run/postgresql";
        PGDATABASE = "vision";
        PGUSER = "vision";
        PGOPTIONS = "-c statement_timeout=5000";
      };
      path = [ config.services.postgresql.package ];
      serviceConfig = {
        Type = "simple";
        User = "vision";
        Group = "vision";
        WorkingDirectory = "/srv/vision/current";
        ExecStart = "/srv/vision/current/vision";
        Restart = "on-failure";
        RestartSec = 3;
        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        ProtectProc = "invisible";
        ProcSubset = "pid";
        RestrictSUIDSGID = true;
        RestrictRealtime = true;
        LockPersonality = true;
        CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
        IPAddressDeny = "any";
        IPAddressAllow = [ "127.0.0.0/8" ];
        TasksMax = 64;
        MemoryMax = "256M";
        UMask = "0077";
      };
    };
  };
}
