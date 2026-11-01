{ nixpkgs, diagnose ? false }:
let
  lib = import (nixpkgs + "/lib");
  packages = import ../hosts/mrjam-vps/preserved-packages.nix { };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-kanidm-host.nix ../nixos/mrjam-nextcloud-host.nix
      ({ pkgs, ... }: {
        system.stateVersion = "26.05";
        boot.loader.grub.enable = false;
        fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
        services.postgresql.package = pkgs.postgresql_17;
      }) extra ];
  }).config;
  setup = {
    services.postgresql.enable = true;
    services.mrjamKanidmHost = { enable = true; uid = 976; gid = 976;
      artifactStorePath = builtins.unsafeDiscardStringContext "${packages.kanidm}"; };
    services.mrjamNextcloudHost = { enable = true; uid = 975; gid = 975; };
  };
  off = evaluate { };
  on = evaluate setup;
  variant = extra: evaluate { imports = [ setup extra ]; };
  valid = c: lib.all (a: a.assertion) c.assertions;
  kani = on.systemd.services.kanidm;
  nc = on.services.nextcloud;
  result = {
    disabledInert = valid off && !(off.systemd.services ? kanidm) && !off.services.nextcloud.enable;
    configuredValid = valid on;
    versionsPreserved = packages.kanidm.version == "1.11.2" && nc.package.version == "34.0.4" && nc.phpPackage.version == "8.4.27";
    oidcPreserved = nc.extraApps.user_oidc.name == "nextcloud-app-user_oidc-8.10.1" && !nc.settings.user_oidc.auto_provision && nc.settings.user_oidc.use_pkce;
    noNativeIdpProvisioning = !on.services.kanidm.server.enable && !on.services.kanidm.provision.enable && !on.services.kanidm.unix.enable;
    noAutomaticDomainRename = !(lib.hasInfix "domain rename" kani.preStart)
      && !(lib.hasInfix "domain rename" (builtins.toJSON kani.serviceConfig.ExecStartPre));
    existingIdpRequired = lib.hasInfix "test -s /var/lib/kanidm/kanidm.db" kani.preStart;
    tlsOutsideStore = kani.serviceConfig.LoadCredential == [ "tls-chain:/var/lib/acme/log.mrj.am/fullchain.pem" "tls-key:/var/lib/acme/log.mrj.am/key.pem" ];
    identitiesExplicit = on.users.users.kanidm.uid == 976 && on.users.groups.kanidm.gid == 976
      && on.users.users.nextcloud.uid == 975 && on.users.groups.nextcloud.gid == 975;
    kanidmPrivate = kani.serviceConfig.StateDirectoryMode == "0700" && kani.serviceConfig.RuntimeDirectoryMode == "0700" && kani.serviceConfig.CapabilityBoundingSet == [ ];
    kanidmStaged = kani.wantedBy == [ ] && !kani.restartIfChanged && !kani.stopIfChanged;
    kanidmScheduledBackupExplicitlyOff = !on.services.mrjamKanidmHost.settings.online_backup.enabled
      && on.services.mrjamKanidmHost.settings.online_backup.compression == "gzip";
    nextcloudStaged = on.systemd.services.nextcloud-setup.wantedBy == [ ]
      && on.systemd.services.phpfpm-nextcloud.wantedBy == [ ] && on.systemd.timers.nextcloud-cron.wantedBy == [ ]
      && on.systemd.services.redis-nextcloud.wantedBy == [ ] && !on.systemd.services.redis-nextcloud.restartIfChanged;
    noImplicitNcUpgrade = lib.hasInfix "status --exit-code" on.systemd.services.nextcloud-setup.script
      && !(lib.hasInfix " upgrade" on.systemd.services.nextcloud-setup.script)
      && !(lib.hasInfix "maintenance:install" on.systemd.services.nextcloud-setup.script)
      && !on.systemd.services.nextcloud-update-db.enable;
    setupBeforePhp = lib.elem "nextcloud-setup.service" on.systemd.services.phpfpm-nextcloud.requires;
    noDatabaseBootstrap = !nc.database.createLocally && on.services.postgresql.ensureDatabases == [ ] && on.services.postgresql.ensureUsers == [ ];
    noAccountBootstrap = nc.config.adminuser == null && nc.config.adminpassFile == null;
    noAppAutoUpdate = !nc.appstoreEnable && !nc.autoUpdateApps.enable && !nc.extraAppsEnable;
    containmentKept = on.services.mrjamNextcloudGuards.enable
      && on.systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists == "!/var/lib/nextcloud-php-security/blocked";
    passwordsBlocked = lib.hasInfix "$nextcloud_local_password" on.services.nginx.virtualHosts."cloud.mrj.am".extraConfig;
    peerClosed = lib.hasPrefix on.services.mrjamPostgresqlPolicy.blocks.nextcloud on.services.postgresql.authentication;
    missingKanidmUidRejected = !valid (variant { services.mrjamKanidmHost.uid = lib.mkForce null; });
    missingNextcloudGidRejected = !valid (variant { services.mrjamNextcloudHost.gid = lib.mkForce null; });
    otherKanidmBuildRejected = !valid (variant { services.mrjamKanidmHost.artifactStorePath = lib.mkForce "/nix/store/00000000000000000000000000000000-other"; });
    addedIdpGroupRejected = !valid (variant { users.users.kanidm.extraGroups = [ "wheel" ]; });
    addedHbaRejected = !valid (variant { services.mrjamPostgresqlPolicy.blocks.nextcloud = lib.mkAfter "local all all trust\n"; });
  };
in if diagnose then {
  inherit result;
  failedAssertions = map (a: a.message) (lib.filter (a: !a.assertion) on.assertions);
} else assert lib.all (x: x) (builtins.attrValues result); result
