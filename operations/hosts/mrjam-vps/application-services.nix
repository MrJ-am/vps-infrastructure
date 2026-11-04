# Explicit host assembly. This module does not migrate state or promote units.
{ config, lib, ... }:
let
  cfg = config.mrjamVpsApplications;
  locked = (builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ./application-artifacts.json))).outputs;
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  domain = lib.types.strMatching "[a-z0-9]([a-z0-9.-]*[a-z0-9])?";
  privatePath = lib.types.strMatching "/(var/lib|run)/[A-Za-z0-9_./-]+";
  sqlName = lib.types.strMatching "[a-z][a-z0-9_]{0,62}";
  names = [ "audition" "log" "logique" "logo" "mateval" "style" "vision" ];
  requiredSites = [ "audition" "log" "logique" "mateval" "vision" ];
  workers = [ "archive" "replay" "cycle" "closure" "admission" ];
  nativeWorkers = cfg.workers.identityProtocol == "kanidm-native";
  workerIdentity = credentialFile: {
    inherit (cfg.workers) identityProtocol kanidmCaFile kanidmCaSha256;
  } // (if nativeWorkers then { kanidmCredentialFile = credentialFile; }
    else { keycloakCredentialFile = credentialFile; });
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
  gatewayNames = builtins.filter (name: builtins.hasAttr name cfg.sites)
    [ "audition" "logique" "logo" "style" "vision" ];
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
    allowIndependentVise = lib.mkOption { type = lib.types.bool; default = false;
      description = "Explicit separately qualified ViSe reintegration; never required by the main applications."; };
    activeSlot = lib.mkOption { type = lib.types.enum [ "blue" "green" ]; default = "blue"; };
    slots = lib.mkOption { type = lib.types.attrsOf storePath; default = { };
      description = "Installed blue/green runtime closures, each independently bound to the selected server and seven frontend manifests."; };
    identities = lib.mkOption { type = lib.types.attrsOf identityType; default = { };
      description = "Observed/reserved numeric identities for the exact installed units; never automatic UID allocation."; };
    sites = lib.mkOption { type = lib.types.attrsOf siteType; default = { };
      description = "Existing application hosts and retained certificates. Style/logo demos require an explicit additional host; their seven artifact roots are retained independently."; };
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
    principiiRoot = lib.mkOption { type = lib.types.nullOr (lib.types.strMatching "/srv/[A-Za-z0-9_./-]+");
      description = "Observed static root, or null for the existing root redirect to /matheval/."; };
    workers = {
      enable = lib.mkEnableOption "installation of all five qualified workers, without activation";
      identityProtocol = lib.mkOption { type = lib.types.enum [ "keycloak-legacy" "kanidm-native" ]; default = "keycloak-legacy"; };
      replayIdentityProtocol = lib.mkOption {
        type = lib.types.enum [ "inherit" "kanidm-delete-socket" ]; default = "inherit";
        description = "Separately qualified replay transport; inherited mode retains historical receipts.";
      };
      kanidmCaFile = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; };
      kanidmCaSha256 = lib.mkOption { type = lib.types.nullOr (lib.types.strMatching "[0-9a-f]{64}"); default = null; };
      artifacts = lib.genAttrs workers (name: lib.mkOption { type = storePath; default = locked."vision_${name}".store_path; });
      visionDatabase = lib.mkOption { type = sqlName; };
      journalDatabase = lib.mkOption { type = sqlName; };
      ageRecipient = lib.mkOption { type = lib.types.nullOr (lib.types.strMatching "age1[a-z0-9]{58}"); default = null; };
      archiveConfigurationCredentialFile = lib.mkOption { type = lib.types.nullOr privatePath; default = null; };
      archiveInitializeConfigurationCredentialFile = lib.mkOption { type = lib.types.nullOr privatePath; default = null; };
      credentials = lib.genAttrs [ "smtp" "archiveRecipient" "cycleIdentity" "replayIdentity" "admissionIdentity" "closure" "approval" ] (_: lib.mkOption { type = privatePath; });
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = slotNames != [ ] && lib.all (name: builtins.elem name [ "blue" "green" ]) slotNames
          && builtins.hasAttr cfg.activeSlot cfg.slots;
        message = "mrjamVpsApplications: install explicit blue/green runtime closures and select one declared slot."; }
      { assertion = lib.all (name: builtins.hasAttr name cfg.sites) requiredSites
          && lib.all (name: builtins.elem name names) (builtins.attrNames cfg.sites)
          && builtins.length (lib.unique (map (site: site.host) (builtins.attrValues cfg.sites))) == builtins.length (builtins.attrNames cfg.sites);
        message = "mrjamVpsApplications: existing application hosts must be explicit and distinct; demo hosts cannot be inferred from artifact names."; }
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
      { assertion = lib.all safePath ([ cfg.matevalActivationCredentialFile cfg.admissionApprovalCredentialFile cfg.logAliasesDatabase ]
          ++ lib.optional (cfg.principiiRoot != null) cfg.principiiRoot);
        message = "mrjamVpsApplications: existing state and credential references must be canonical."; }
      { assertion = cfg.logAliasesDatabase == "/run/mrjam-identity/aliases.sqlite"
          && builtins.hasAttr cfg.logReadersGroup config.users.groups
          && config.users.groups.${cfg.logReadersGroup}.gid != null;
        message = "mrjamVpsApplications: Log requires the dedicated alias-only projection and explicitly bound reader group, never session-state access."; }
      { assertion = if cfg.allowIndependentVise then
          (lib.attrByPath [ "services" "mrjamVise" "enable" ] false config) && (config.systemd.services ? vise)
        else !(config.systemd.services ? vise) && !(config.services.nginx.virtualHosts ? "vise.mrj.am");
        message = "mrjamVpsApplications: ViSe requires explicit independent reintegration; it remains excluded by default."; }
      # Historical artifacts remain available for reproducing their receipts.
      # Native protocol selection requires all five separately qualified outputs.
      { assertion = !cfg.workers.enable || !nativeWorkers || lib.all
          (name: cfg.workers.artifacts.${name} != locked."vision_${name}".store_path)
          workers;
        message = "mrjamVpsApplications: native identity requires all five adapted worker artifacts, including archival of both historical and native issuers."; }
      { assertion = cfg.workers.replayIdentityProtocol != "kanidm-delete-socket" || nativeWorkers;
        message = "mrjamVpsApplications: the bounded deletion adapter requires native admission and cycle protocols."; }
      { assertion = !cfg.workers.enable || nativeWorkers || (config.systemd.services.mrjam-vision-admission.wantedBy == [ ]
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
          "/" = if cfg.principiiRoot == null then { return = "404"; } else { tryFiles = "$uri $uri/ =404"; };
          "= /matheval".return = "308 /matheval/";
          "^~ /matheval/" = (rustLocation "principiipetit.io") // { extraConfig = forwarded "principiipetit.io" + "client_max_body_size 128k;"; };
          "= /healthz".return = "404";
          "= /readyz".return = "404";
        } // lib.optionalAttrs (cfg.principiiRoot == null) { "= /".return = "308 /matheval/"; };
      };
      "www.principiipetit.io" = (tls "www.principiipetit.io") // {
        locations."/".return = "308 https://principiipetit.io$request_uri";
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
      configurationCredentialFile = cfg.workers.archiveConfigurationCredentialFile;
      initializeConfigurationCredentialFile = cfg.workers.archiveInitializeConfigurationCredentialFile;
      smtpCredentialFile = cfg.workers.credentials.smtp;
      recipientCredentialFile = cfg.workers.credentials.archiveRecipient;
    };
    services.mrjamVisionCycle = lib.mkIf cfg.workers.enable ({
      enable = true; artifactStorePath = cfg.workers.artifacts.cycle;
      inherit (cfg.workers) visionDatabase journalDatabase;
      smtpCredentialFile = cfg.workers.credentials.smtp;
    } // workerIdentity cfg.workers.credentials.cycleIdentity);
    services.mrjamVisionReplay = lib.mkIf cfg.workers.enable ({
      enable = true; artifactStorePath = cfg.workers.artifacts.replay;
      inherit (cfg.workers) visionDatabase journalDatabase;
      admissionsCredentialFile = cfg.workers.credentials.closure;
    } // (if cfg.workers.replayIdentityProtocol == "kanidm-delete-socket"
      then { identityProtocol = "kanidm-delete-socket"; }
      else workerIdentity cfg.workers.credentials.replayIdentity));
    services.mrjamVisionClosure = lib.mkIf cfg.workers.enable {
      enable = true; artifactStorePath = cfg.workers.artifacts.closure;
      inherit (cfg.workers) visionDatabase journalDatabase;
      admissionsCredentialFile = cfg.workers.credentials.closure;
    };
    services.mrjamVisionAdmission = lib.mkIf cfg.workers.enable ({
      enable = true; artifactStorePath = cfg.workers.artifacts.admission;
      inherit (cfg.workers) visionDatabase;
      smtpCredentialFile = cfg.workers.credentials.smtp;
      closureCredentialFile = cfg.workers.credentials.closure;
      approvalCredentialFile = cfg.workers.credentials.approval;
    } // workerIdentity cfg.workers.credentials.admissionIdentity);
  };
}
