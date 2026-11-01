{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../hosts/mrjam-vps/core-services.nix {
      system.stateVersion = "26.05";
      fileSystems."/" = { device = "/dev/synthetic"; fsType = "ext4"; };
      boot.loader.grub.enable = false;
    } extra ];
  }).config;
  cfg = evaluate { };
  hba = cfg.services.postgresql.authentication;
  bad = evaluate { services.postgresql.ensureDatabases = [ "unrequested" ]; };
  result = {
    validComposition = builtins.all (a: a.assertion) cfg.assertions;
    retainedForgejoIdentity = cfg.users.users.forgejo.uid == 982 && cfg.users.groups.forgejo.gid == 982;
    retainedKanidmIdentity = cfg.users.users.kanidm.uid == 983 && cfg.users.groups.kanidm.gid == 983;
    retainedNextcloudIdentity = cfg.users.users.nextcloud.uid == 990 && cfg.users.groups.nextcloud.gid == 990;
    retainedPostgresIdentity = cfg.users.users.postgres.uid == 71 && cfg.users.groups.postgres.gid == 71;
    exactPostgresqlMajorAndDirectory = lib.versions.major cfg.services.postgresql.package.version == "17"
      && cfg.services.postgresql.dataDir == "/var/lib/postgresql/17";
    postgresCannotInitializeEmptyState = lib.hasPrefix "test -d /var/lib/postgresql/17" cfg.systemd.services.postgresql.preStart;
    noImplicitSqlProvisioning = cfg.services.postgresql.ensureDatabases == [ ] && cfg.services.postgresql.ensureUsers == [ ];
    sqlBootstrapRefused = lib.any (a: !a.assertion && lib.hasPrefix "mrjamCoreServices: SQL bootstrap" a.message) bad.assertions;
    localOnlyPostgres = cfg.services.postgresql.settings.listen_addresses == "" && !cfg.services.postgresql.enableTCPIP;
    postgresTerminalReject = lib.hasInfix "local all postgres peer\nlocal all all reject\n" hba;
    dedicatedPeerBlocksPresent = lib.hasInfix "local forgejo forgejo peer" hba && lib.hasInfix "local nextcloud nextcloud peer" hba;
    noVise = !(cfg.systemd.services ? vise) && !(cfg.services.nginx.virtualHosts ? "vise.mrj.am");
    exactCoreRoutes = builtins.attrNames cfg.services.nginx.virtualHosts == [ "cloud.mrj.am" "forge.mrj.am" "log.mrj.am" ];
    forgejoProxy = cfg.services.nginx.virtualHosts."forge.mrj.am".locations."/".proxyPass == "http://127.0.0.1:3004";
    forgejoAssetsRetained = lib.hasSuffix "/share/forgejo-org/" cfg.services.nginx.virtualHosts."forge.mrj.am".locations."^~ /assets/forgejo-org/".alias;
    identityTlsVerified = lib.hasInfix "proxy_ssl_verify on;" cfg.services.nginx.virtualHosts."log.mrj.am".locations."/".extraConfig;
    identityAdministrationNotPublished = builtins.all (prefix:
      cfg.services.nginx.virtualHosts."log.mrj.am".locations."^~ ${prefix}".return == "404")
      [ "/v1/raw/" "/v1/oauth2/" "/v1/service_account/" "/scim/" ];
    unknownHostRefused = lib.hasInfix "return 421;" cfg.services.nginx.appendHttpConfig && lib.hasInfix "ssl_reject_handshake on;" cfg.services.nginx.appendHttpConfig;
    existingCertificatesReferenced = builtins.all (name: cfg.services.nginx.virtualHosts.${name}.sslCertificateKey == "/var/lib/acme/${name}/key.pem") [ "cloud.mrj.am" "forge.mrj.am" "log.mrj.am" ];
    executableClosuresRetained = builtins.length cfg.system.extraDependencies >= 2;
    nextcloudUpgradeRemainsExplicit = !cfg.systemd.services.nextcloud-update-db.enable;
    noImplicitServicePromotion = cfg.systemd.services.forgejo.wantedBy == [ ] && cfg.systemd.services.kanidm.wantedBy == [ ]
      && cfg.systemd.services.phpfpm-nextcloud.wantedBy == [ ];
  };
in assert builtins.all (value: value) (builtins.attrValues result); result
