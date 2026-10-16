{ config, lib, pkgs, forgejoKanidmApi ? ../../scripts/kanidm-api-privee.py, ... }:
let
  cfg = config.infrastructure.forgejo;
  f = config.services.forgejo;
  lock = builtins.fromJSON (builtins.readFile ./versions.json);
  assets = import ./assets.nix { inherit pkgs; };
  render = pkgs.writeShellScript "forgejo-pandoc-org" ''
    set -eu
    ulimit -v 1048576
    exec ${pkgs.coreutils}/bin/timeout 20s ${pkgs.pandoc}/bin/pandoc \
      --sandbox --from=org --to=html5 --mathjax --wrap=none
  '';
  identityIni = pkgs.writeText "forgejo-identity.ini" (lib.generators.toINI {} {
    DEFAULT = { RUN_USER = "forgejo"; RUN_MODE = "prod"; WORK_PATH = f.stateDir; };
    database = { DB_TYPE = "postgres"; HOST = "/run/postgresql"; NAME = "forgejo"; USER = "forgejo"; SSL_MODE = "disable"; };
    security.INSTALL_LOCK = true;
    server.ROOT_URL = "https://${cfg.domain}/";
    repository.ROOT = "${f.stateDir}/repositories";
    log = { MODE = "console"; LEVEL = "Error"; };
  });
  identityCommand = phase: "${pkgs.python3}/bin/python3 ${./sso.py} ${phase} /var/lib/forgejo-identity ${config.services.postgresql.finalPackage} ${f.package}/bin/forgejo ${identityIni} ${config.services.kanidm.package} ${pkgs.curl}/bin/curl ${forgejoKanidmApi}";
  backupService = verify: {
      description = "Sauvegarde cohérente chiffrée Forgejo (données, dépôts, PostgreSQL)";
      after = [ "postgresql.service" ];
      path = [ pkgs.coreutils pkgs.diffutils pkgs.gnutar pkgs.age pkgs.util-linux pkgs.git config.services.postgresql.package ];
      serviceConfig = { Type = "oneshot"; UMask = "0077"; TimeoutStartSec = "5min"; };
      script = ''
        set -euo pipefail
        exec 9>/run/lock/forgejo-backup.lock
        flock 9
        tmp=$(mktemp -d /var/backup/forgejo/.snapshot-XXXXXX)
        active=0
        if ${pkgs.systemd}/bin/systemctl is-active --quiet forgejo; then active=1; fi
        cleanup() {
          if [ "$active" = 1 ]; then ${pkgs.systemd}/bin/systemctl start forgejo; fi
          rm -rf -- "$tmp"
        }
        trap cleanup EXIT
        ${pkgs.systemd}/bin/systemctl stop forgejo
        runuser -u forgejo -- pg_dump -h /run/postgresql --format=custom forgejo > "$tmp/forgejo.dump"
        tar -C /var/lib -cf "$tmp/data.tar" forgejo ${lib.optionalString cfg.sso.enable "forgejo-identity"}
        dest=/var/backup/forgejo/forgejo-$(date -u +%Y%m%dT%H%M%SZ).tar.age
        age-keygen -o "$tmp/key" 2>/dev/null
        public=$(age-keygen -y "$tmp/key")
        age -r '${cfg.backupRecipient}' "$tmp/key" > "$dest.key.age.tmp"
        tar -C "$tmp" -cf - forgejo.dump data.tar | age -r "$public" > "$dest.tmp"
        # Verify actual decryption and archive contents before accepting the pair.
        mkdir "$tmp/verified"
        age -d -i "$tmp/key" "$dest.tmp" | tar -xf - -C "$tmp/verified"
        cmp "$tmp/forgejo.dump" "$tmp/verified/forgejo.dump"
        cmp "$tmp/data.tar" "$tmp/verified/data.tar"
        pg_restore --list "$tmp/verified/forgejo.dump" >/dev/null
        ${lib.optionalString verify "${pkgs.python3}/bin/python3 ${./verify-backup.py} \"$tmp/verified\" ${config.services.postgresql.finalPackage}"}
        mv "$dest.key.age.tmp" "$dest.key.age"
        mv "$dest.tmp" "$dest"
      '';
    };
in {
  options.infrastructure.forgejo = {
    enable = lib.mkEnableOption "Forgejo privé avec Pandoc et MathJax locaux";
    sso.enable = lib.mkEnableOption "Kanidm comme unique connexion Web";
    quotas = {
      maxRepositories = lib.mkOption { type = lib.types.int; default = -1; description = "Nombre de dépôts par personne, -1 sans limite ; surchargeable par compte."; };
      totalStorage = lib.mkOption { type = lib.types.str; default = "-1"; description = "Stockage total par défaut (ex. 5 GiB), -1 sans limite ; groupes via API."; };
    };
    domain = lib.mkOption { type = lib.types.str; default = "forge.mrj.am"; };
    backupRecipient = lib.mkOption { type = lib.types.str;
      default = config.services.vision.backupRecipient; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !cfg.sso.enable || config.services.kanidm.server.enable;
        message = "Le raccordement Forgejo exige le Kanidm existant."; }
      { assertion = builtins.match "(-1|[0-9]+( ?(B|KiB|MiB|GiB|TiB))?)" cfg.quotas.totalStorage != null; message = "Quota de stockage invalide."; }
      { assertion = cfg.quotas.maxRepositories >= -1; message = "Quota du nombre de dépôts invalide."; }
      { assertion = pkgs.forgejo.version == lock.forgejo && pkgs.pandoc.version == lock.pandoc;
        message = "Requalifier Forgejo/Pandoc et actualiser versions.json avant mise à jour."; }
      { assertion = builtins.match "[a-z0-9.-]+" cfg.domain != null;
        message = "Domaine Forgejo invalide."; }
    ];
    services.forgejo = {
      enable = true;
      package = pkgs.forgejo;
      database = { type = "postgres"; name = "forgejo"; user = "forgejo";
        socket = "/run/postgresql"; createDatabase = true; };
      settings = {
        DEFAULT.APP_NAME = "Forgejo";
        server = {
          DOMAIN = cfg.domain; ROOT_URL = "https://${cfg.domain}/";
          HTTP_ADDR = "127.0.0.1"; HTTP_PORT = 3004;
          START_SSH_SERVER = true; SSH_DOMAIN = cfg.domain;
          SSH_PORT = 2222; SSH_LISTEN_HOST = "0.0.0.0"; SSH_LISTEN_PORT = 2222;
          DISABLE_SSH = false; OFFLINE_MODE = true;
        };
        service = { DISABLE_REGISTRATION = true; REQUIRE_SIGNIN_VIEW = true;
          ENABLE_INTERNAL_SIGNIN = !cfg.sso.enable;
          ENABLE_BASIC_AUTHENTICATION = !cfg.sso.enable;
          ALLOW_ONLY_EXTERNAL_REGISTRATION = cfg.sso.enable;
          DEFAULT_ALLOW_CREATE_ORGANIZATION = false;
          DEFAULT_KEEP_EMAIL_PRIVATE = true; ENABLE_NOTIFY_MAIL = false; };
        repository = { DEFAULT_PRIVATE = "private"; FORCE_PRIVATE = true;
          MAX_CREATION_LIMIT = cfg.quotas.maxRepositories;
          DISABLE_HTTP_GIT = false; ENABLE_PUSH_CREATE_USER = false;
          ENABLE_PUSH_CREATE_ORG = false; };
        "repository.upload".ENABLED = false;
        "repository.signing".SIGNING_KEY = "none";
        security = { INSTALL_LOCK = true; PASSWORD_HASH_ALGO = "argon2";
          REVERSE_PROXY_LIMIT = 1; REVERSE_PROXY_TRUSTED_PROXIES = "127.0.0.1/32"; };
        session.COOKIE_SECURE = true;
        openid = { ENABLE_OPENID_SIGNIN = false; ENABLE_OPENID_SIGNUP = false; };
        oauth2_client = {
          ENABLE_AUTO_REGISTRATION = cfg.sso.enable;
          ACCOUNT_LINKING = "disabled";
          USERNAME = "nickname";
          OPENID_CONNECT_SCOPES = "openid profile email";
        };
        admin = { DISABLE_REGULAR_ORG_CREATION = true;
          EXTERNAL_USER_DISABLE_FEATURES = "manage_password"; };
        quota.ENABLED = true;
        "quota.default".TOTAL = cfg.quotas.totalStorage;
        actions.ENABLED = false;
        packages.ENABLED = false;
        federation.ENABLED = false;
        mailer.ENABLED = false;
        "markup.orgmode" = {
          ENABLED = true; FILE_EXTENSIONS = ".org";
          RENDER_COMMAND = toString render; IS_INPUT_FILE = false;
          NEED_POSTPROCESS = true; RENDER_CONTENT_MODE = "sanitized";
        };
        "markup.sanitizer.orgmode.math" = {
          ELEMENT = "span"; ALLOW_ATTR = "class"; REGEXP = "^math (inline|display)$";
        };
        log.LEVEL = "Warn";
      };
    };
    # Restrict even the database's default PUBLIC grants to its dedicated owner.
    systemd.services.postgresql-setup.postStart = lib.mkAfter ''
      ${config.services.postgresql.finalPackage}/bin/psql -X --set=ON_ERROR_STOP=1 \
        --host=/run/postgresql --dbname=forgejo <<'SQL'
      REVOKE ALL PRIVILEGES ON DATABASE forgejo FROM PUBLIC;
      REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC;
      GRANT USAGE, CREATE ON SCHEMA public TO forgejo;
      SQL
    '';
    # The stock module provisions persistent runtime secrets outside the store.
    systemd.tmpfiles.rules = [
      "d ${f.customDir}/templates 0750 forgejo forgejo - -"
      "d ${f.customDir}/templates/custom 0750 forgejo forgejo - -"
      "L+ ${f.customDir}/templates/custom/footer.tmpl - - - - ${./assets/footer.tmpl}"
      "d /var/backup/forgejo 0700 root root 30d -"
    ];
    services.nginx.enable = true;
    services.nginx.virtualHosts.${cfg.domain} = {
      forceSSL = true; enableACME = true;
      locations."/" = { proxyPass = "http://127.0.0.1:3004"; proxyWebsockets = true;
        extraConfig = ''
          client_max_body_size 256m;
          proxy_read_timeout 300s;
        ''; };
      locations."^~ /assets/forgejo-org/" = {
        alias = "${assets}/";
        # expires sets caching without replacing inherited security headers.
        extraConfig = "expires 1h;";
      };
      extraConfig = ''
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy same-origin always;
        add_header X-Frame-Options SAMEORIGIN always;
      '';
    };
    networking.firewall.allowedTCPPorts = [ 2222 ];
    # Bootstrap only on an empty installation, with no password in argv or journal.
    systemd.services.forgejo-bootstrap = lib.mkIf (!cfg.sso.enable) {
      description = "Créer le premier administrateur Forgejo hors store et journaux";
      wantedBy = [ "multi-user.target" ];
      requires = [ "forgejo.service" ]; after = [ "forgejo.service" ];
      serviceConfig = { Type = "oneshot"; UMask = "0077"; StateDirectory = "forgejo-bootstrap";
        StateDirectoryMode = "0700"; StandardOutput = "null"; StandardError = "null"; };
      path = [ pkgs.util-linux config.services.postgresql.package ];
      script = ''
        set -eu
        count=$(runuser -u forgejo -- psql -XAtq -h /run/postgresql -d forgejo -c 'SELECT count(*) FROM "user"')
        if [ "$count" = 0 ]; then
          runuser -u forgejo -- env FORGEJO_WORK_DIR=${f.stateDir} FORGEJO_CUSTOM=${f.customDir} \
            ${f.package}/bin/forgejo admin user create --username mrjam-admin \
            --email forgejo-admin@mrj.am --admin --random-password --random-password-length 40 \
            --must-change-password=true > /var/lib/forgejo-bootstrap/initial-admin.txt
        fi
      '';
    };
    systemd.services.forgejo = lib.mkIf cfg.sso.enable {
      requires = [ "forgejo-identity.service" ]; after = [ "forgejo-identity.service" ];
    };
    systemd.services.forgejo-identity = lib.mkIf cfg.sso.enable {
      description = "Client Kanidm et rattachement Forgejo par UUID natif";
      requires = [ "postgresql-setup.service" "kanidm.service" ];
      after = [ "postgresql-setup.service" "kanidm.service" ]; before = [ "forgejo.service" ];
      path = [ pkgs.util-linux pkgs.coreutils ];
      serviceConfig = { Type = "oneshot"; UMask = "0077"; StateDirectory = "forgejo-identity";
        StateDirectoryMode = "0700"; TimeoutStartSec = "3min"; RemainAfterExit = true; };
      script = identityCommand "prepare";
    };
    systemd.services.forgejo-account = lib.mkIf cfg.sso.enable {
      description = "Conserver le compte administrateur sous le nom MrJam";
      wantedBy = [ "multi-user.target" ]; requires = [ "forgejo.service" ]; after = [ "forgejo.service" ];
      path = [ pkgs.util-linux pkgs.coreutils ];
      serviceConfig = { Type = "oneshot"; UMask = "0077"; TimeoutStartSec = "2min"; };
      script = identityCommand "account";
    };
    systemd.services.forgejo-backup = backupService false;
    systemd.services.forgejo-backup-qualification = backupService true;
    systemd.timers.forgejo-backup = {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnCalendar = "*-*-* 04:45:00"; Persistent = true; RandomizedDelaySec = "10min"; };
    };
  };
}
