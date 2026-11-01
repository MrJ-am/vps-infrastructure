# Explicit host assembly. This module does not migrate state or promote units.
{ config, lib, ... }:
let
  cfg = config.mrjamVpsApplications;
  locked = (builtins.fromJSON (builtins.readFile ./application-artifacts.json)).outputs;
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  domain = lib.types.strMatching "[a-z0-9]([a-z0-9.-]*[a-z0-9])?";
  privatePath = lib.types.strMatching "/(var/lib|run)/[A-Za-z0-9_./-]+";
  sqlName = lib.types.strMatching "[a-z][a-z0-9_]{0,62}";
  names = [ "audition" "log" "logique" "logo" "mateval" "style" "vision" ];
  workers = [ "archive" "replay" "cycle" "closure" "admission" ];
  slotNames = builtins.attrNames cfg.slots;
  units = map (slot: "mrjam-rust-${slot}") slotNames
    ++ lib.optionals cfg.workers.enable (map (name: "mrjam-vision-${name}") workers);
  port = config.services.mrjamRust.slots.${cfg.activeSlot}.port;
  siteType = lib.types.submodule { options = {
    host = lib.mkOption { type = domain; };
    certificateName = lib.mkOption { type = domain; };
  }; };
  identityType = lib.types.submodule { options = {
    uid = lib.mkOption { type = lib.types.ints.between 1 65533; };
    gid = lib.mkOption { type = lib.types.ints.between 1 65533; };
  }; };
  connectionType = lib.types.submodule { options = {
    database = lib.mkOption { type = sqlName; };
    role = lib.mkOption { type = sqlName; };
  }; };
  safePath = path: !(lib.hasInfix "//" path) && !(lib.hasSuffix "/" path)
    && lib.all (part: part != "." && part != "..") (lib.splitString "/" path);
  forwarded = host: ''
    proxy_http_version 1.1;
    proxy_set_header Host ${host};
    proxy_set_header X-Forwarded-Host ${host};
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Origin $http_origin;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-CSRF-Token $http_x_csrf_token;
    proxy_set_header X-Mrj-User "";
    proxy_set_header X-User-Id "";
    proxy_set_header X-Authenticated-User "";
    proxy_set_header X-Forwarded-User "";
    proxy_set_header X-Vision-Authenticated "";
    proxy_set_header X-Vision-Browser "";
    proxy_set_header X-Original-Method "";
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_connect_timeout 5s;
  '';
  rustLocation = host: { proxyPass = "http://127.0.0.1:${toString port}"; extraConfig = forwarded host; };
  nativeLog = {
    proxyPass = "https://127.0.0.1:8443";
    extraConfig = ''
      client_max_body_size 64k;
      proxy_set_header Host log.mrj.am;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header Connection "";
      proxy_ssl_server_name on;
      proxy_ssl_name log.mrj.am;
      proxy_ssl_verify on;
      proxy_ssl_verify_depth 2;
      proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
    '';
  };
  tls = name: {
    forceSSL = true; enableACME = false;
    sslCertificate = "/var/lib/acme/${name}/fullchain.pem";
    sslCertificateKey = "/var/lib/acme/${name}/key.pem";
  };
  gatewayNames = [ "audition" "logique" "logo" "style" "vision" ];
  roots = [ cfg.serverStorePath ] ++ map (name: cfg.frontendStorePaths.${name}) names
    ++ map (slot: cfg.slots.${slot}) slotNames
    ++ lib.optionals cfg.workers.enable (map (name: cfg.workers.artifacts.${name}) workers);
in {
  imports = [
    ../../nixos/mrjam-gateway.nix
    ../../nixos/mrjam-postgresql-access.nix
    ../../nixos/mrjam-vision-archive.nix
    ../../nixos/mrjam-vision-replay.nix
    ../../nixos/mrjam-vision-cycle.nix
    ../../nixos/mrjam-vision-closure.nix
    ../../nixos/mrjam-vision-admission.nix
  ];
  options.mrjamVpsApplications = {
    enable = lib.mkEnableOption "explicit Rust/Elm host composition without ViSe";
    activeSlot = lib.mkOption { type = lib.types.enum [ "blue" "green" ]; default = "blue"; };
    slots = lib.mkOption { type = lib.types.attrsOf storePath; default = { };
      description = "Installed blue/green runtime closures, each independently bound to the selected server and seven frontend manifests."; };
    identities = lib.mkOption { type = lib.types.attrsOf identityType; default = { };
      description = "Observed/reserved numeric identities for the exact installed units; never automatic UID allocation."; };
    sites = lib.mkOption { type = lib.types.attrsOf siteType; default = { };
      description = "Seven explicit frontend names, public hostnames and retained certificate directories."; };
    serverStorePath = lib.mkOption { type = storePath; default = locked.server.store_path; };
    frontendStorePaths = lib.genAttrs names (name: lib.mkOption {
      type = storePath; default = locked."frontend_${name}".store_path;
    });
    databaseAccess = lib.genAttrs [ "mateval" "matevalAdministration" "vision" "visionAdministration" "visionJournal" "audition" ] (_: lib.mkOption {
      type = connectionType;
      description = "Explicit existing database/role pair, matched to runtime.json; absence is never SQL bootstrap.";
    });
    matevalActivationCredentialFile = lib.mkOption { type = privatePath;
      default = "/var/lib/mrjam-metier/secrets/matheval-setup-hash"; };
    admissionApprovalCredentialFile = lib.mkOption { type = privatePath; };
    logAliasesDatabase = lib.mkOption { type = privatePath;
      default = "/run/mrjam-identity/aliases.sqlite"; };
    logReadersGroup = lib.mkOption { type = lib.types.strMatching "[a-z][a-z0-9-]+";
      default = "mrjam-log-readers"; };
    principiiRoot = lib.mkOption { type = lib.types.strMatching "/srv/[A-Za-z0-9_./-]+";
      description = "Observed static root for the existing site outside /matheval/, preserved verbatim."; };
    workers = {
      enable = lib.mkEnableOption "installation of all five qualified workers, without activation";
      artifacts = lib.genAttrs workers (name: lib.mkOption { type = storePath; default = locked."vision_${name}".store_path; });
      visionDatabase = lib.mkOption { type = sqlName; };
      journalDatabase = lib.mkOption { type = sqlName; };
      ageRecipient = lib.mkOption { type = lib.types.strMatching "age1[a-z0-9]{58}"; };
      credentials = lib.genAttrs [ "smtp" "archiveRecipient" "cycleIdentity" "replayIdentity" "admissionIdentity" "closure" "approval" ] (_: lib.mkOption { type = privatePath; });
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = slotNames != [ ] && lib.all (name: builtins.elem name [ "blue" "green" ]) slotNames
          && builtins.hasAttr cfg.activeSlot cfg.slots;
        message = "mrjamVpsApplications: install explicit blue/green runtime closures and select one declared slot."; }
      { assertion = builtins.attrNames cfg.sites == names
          && builtins.length (lib.unique (map (site: site.host) (builtins.attrValues cfg.sites))) == 7;
        message = "mrjamVpsApplications: all seven distinct frontend hosts are required."; }
      { assertion = cfg.sites.vision.host == "vision.mrj.am" && cfg.sites.audition.host == "audition.mrj.am"
          && cfg.sites.log.host == "log.mrj.am" && cfg.sites.mateval.host == "principiipetit.io";
        message = "mrjamVpsApplications: Rust's fixed application origins and MatEval mount must be preserved."; }
      { assertion = lib.sort builtins.lessThan (builtins.attrNames cfg.identities) == lib.sort builtins.lessThan units;
        message = "mrjamVpsApplications: every installed application identity requires an explicit UID/GID binding."; }
      { assertion = builtins.length (lib.unique (map (identity: identity.uid) (builtins.attrValues cfg.identities))) == builtins.length units
          && builtins.length (lib.unique (map (identity: identity.gid) (builtins.attrValues cfg.identities))) == builtins.length units
          && lib.all (identity: !(builtins.elem identity.uid [ 60 71 982 983 984 990 991 993 995 996 ])
            && !(builtins.elem identity.gid [ 60 71 982 983 984 990 991 993 994 995 ])) (builtins.attrValues cfg.identities);
        message = "mrjamVpsApplications: dedicated numeric identities cannot collide with each other or retained VPS identities."; }
      { assertion = lib.all (path: !(builtins.hasContext path)) roots;
        message = "mrjamVpsApplications: runtime references must select already-built context-free immutable roots."; }
      { assertion = lib.all safePath [ cfg.matevalActivationCredentialFile cfg.admissionApprovalCredentialFile cfg.logAliasesDatabase cfg.principiiRoot ];
        message = "mrjamVpsApplications: existing state and credential references must be canonical."; }
      { assertion = cfg.logAliasesDatabase == "/run/mrjam-identity/aliases.sqlite"
          && builtins.hasAttr cfg.logReadersGroup config.users.groups
          && config.users.groups.${cfg.logReadersGroup}.gid != null;
        message = "mrjamVpsApplications: Log requires the dedicated alias-only projection and explicitly bound reader group, never session-state access."; }
      { assertion = !(config.systemd.services ? vise) && !(config.services.nginx.virtualHosts ? "vise.mrj.am");
        message = "mrjamVpsApplications: the first composition deliberately excludes ViSe."; }
      # These three unchanged executables implement a fixed Keycloak protocol on
      # 8085 and its historical issuer. A session broker on 3002 is not a substitute.
      { assertion = !cfg.workers.enable || (config.systemd.services.mrjam-vision-admission.wantedBy == [ ]
          && !config.services.mrjamVisionAdmission.admissionsOpen
          && !config.services.mrjamVisionCycle.timer.enable && !config.services.mrjamVisionReplay.timer.enable);
        message = "mrjamVpsApplications: legacy-protocol workers require a separately reviewed native identity adaptation before promotion."; }
    ];
    system.extraDependencies = map builtins.storePath roots;
    users.users = lib.mapAttrs (_: identity: { inherit (identity) uid; }) cfg.identities;
    users.groups = lib.mapAttrs (_: identity: { inherit (identity) gid; }) cfg.identities;
    services.mrjamRust = {
      enable = true;
      slots = lib.mapAttrs (_: runtime: { enable = true; artifactStorePath = cfg.serverStorePath; runtimeConfigStorePath = runtime; }) cfg.slots;
    };
    services.mrjamPostgresqlAccess = {
      enable = true;
      slots = lib.genAttrs slotNames (_: cfg.databaseAccess);
    };
    systemd.services = lib.genAttrs (map (slot: "mrjam-rust-${slot}") slotNames) (_: {
      after = [ "postgresql.service" "mrjam-identity.service" "mrjam-identity-aliases.service" ];
      requires = [ "postgresql.service" ];
      serviceConfig = {
        LoadCredential = [ "mateval-activation-sha256:${cfg.matevalActivationCredentialFile}"
          "admission-approval:${cfg.admissionApprovalCredentialFile}" ];
        SupplementaryGroups = [ cfg.logReadersGroup ];
        BindReadOnlyPaths = [ (builtins.dirOf cfg.logAliasesDatabase) ];
      };
    }) // lib.optionalAttrs cfg.workers.enable (lib.genAttrs (map (name: "mrjam-vision-${name}") workers) (_: {
      stopIfChanged = false;
    }));
    services.mrjamGateway = {
      enable = true; inherit (cfg) activeSlot;
      sites = builtins.listToAttrs (map (name: lib.nameValuePair cfg.sites.${name}.host {
        inherit (cfg.sites.${name}) certificateName;
        authenticationBridge = builtins.elem name [ "audition" "vision" ];
        mcpOAuthBridge = builtins.elem name [ "audition" "vision" ];
      }) gatewayNames);
    };
    services.nginx.virtualHosts = {
      "principiipetit.io" = (tls cfg.sites.mateval.certificateName) // {
        root = cfg.principiiRoot;
        locations = {
          "/".tryFiles = "$uri $uri/ =404";
          "= /matheval".return = "308 /matheval/";
          "^~ /matheval/" = (rustLocation "principiipetit.io") // { extraConfig = forwarded "principiipetit.io" + "client_max_body_size 128k;"; };
          "= /healthz".return = "404";
          "= /readyz".return = "404";
        };
      };
      "log.mrj.am" = {
        # Exact overrides of core's native fallback; native API/OIDC boundaries
        # and the more-specific administrative denials remain explicit.
        locations = {
          "/" = { proxyPass = lib.mkForce "http://127.0.0.1:${toString port}"; extraConfig = lib.mkForce (forwarded "log.mrj.am"); };
          "^~ /v1/" = nativeLog;
          "^~ /oauth2/" = nativeLog;
          "= /status" = nativeLog;
          "= /healthz".return = "404";
          "= /readyz".return = "404";
        } // lib.genAttrs [ "= /ui" "= /ui/" "= /ui/login" "= /ui/oauth2" "= /ui/reset" "= /ui/profile" ] (_: {
          proxyPass = "http://127.0.0.1:${toString port}/index.html";
          extraConfig = forwarded "log.mrj.am" + "limit_except GET HEAD { deny all; }";
        });
      };
    } // lib.genAttrs [ "vision.mrj.am" "audition.mrj.am" ] (host: {
      locations."= /oauth/revoke" = { proxyPass = "http://127.0.0.1:3002";
        extraConfig = forwarded host + "client_max_body_size 64k;"; };
    });
    services.mrjamVisionArchive = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.archive;
      inherit (cfg.workers) journalDatabase ageRecipient;
      smtpCredentialFile = cfg.workers.credentials.smtp;
      recipientCredentialFile = cfg.workers.credentials.archiveRecipient;
    };
    services.mrjamVisionCycle = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.cycle;
      inherit (cfg.workers) visionDatabase journalDatabase;
      smtpCredentialFile = cfg.workers.credentials.smtp;
      keycloakCredentialFile = cfg.workers.credentials.cycleIdentity;
    };
    services.mrjamVisionReplay = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.replay;
      inherit (cfg.workers) visionDatabase journalDatabase;
      keycloakCredentialFile = cfg.workers.credentials.replayIdentity;
      admissionsCredentialFile = cfg.workers.credentials.closure;
    };
    services.mrjamVisionClosure = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.closure;
      inherit (cfg.workers) visionDatabase journalDatabase;
      admissionsCredentialFile = cfg.workers.credentials.closure;
    };
    services.mrjamVisionAdmission = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.admission;
      inherit (cfg.workers) visionDatabase;
      smtpCredentialFile = cfg.workers.credentials.smtp;
      keycloakCredentialFile = cfg.workers.credentials.admissionIdentity;
      closureCredentialFile = cfg.workers.credentials.closure;
      approvalCredentialFile = cfg.workers.credentials.approval;
    };
  };
}
