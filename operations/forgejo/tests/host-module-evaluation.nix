{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-forgejo-host.nix ({ pkgs, ... }: {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
      services.postgresql.package = pkgs.postgresql_17;
    }) extra ];
  }).config;
  setup = { services.postgresql.enable = true; services.mrjamForgejoHost = {
    enable = true; uid = 977; gid = 977;
    artifactStorePath = "/nix/store/qcrq6ngi273hak8l7ldv1k9zqq0cqg2h-forgejo-17.0.1";
  }; };
  off = evaluate { };
  on = evaluate setup;
  unit = on.systemd.services.forgejo;
  valid = c: lib.all (a: a.assertion) c.assertions;
  bad = extra: evaluate { imports = [ setup extra ]; };
  settings = on.services.mrjamForgejoHost.settings;
  result = {
    disabledInert = valid off && !(off.systemd.services ? forgejo) && !(off.users.users ? forgejo);
    enabledValid = valid on;
    noUpstreamBootstrap = !on.services.forgejo.enable && !(on.systemd.services ? forgejo-secrets);
    noSsoOrAccountCreation = !(on.systemd.services ? forgejo-identity) && !(on.systemd.services ? forgejo-account)
      && !(on.systemd.services ? forgejo-bootstrap);
    explicitSchemaPreflight = !settings.database.AUTO_MIGRATION && !(lib.hasInfix " migrate" unit.preStart)
      && lib.hasInfix "mrjam-forgejo-check-schema" unit.preStart;
    peerClosed = lib.hasPrefix on.services.mrjamPostgresqlPolicy.blocks.forgejo on.services.postgresql.authentication;
    noDatabaseProvisioning = on.services.postgresql.ensureUsers == [ ] && on.services.postgresql.ensureDatabases == [ ];
    stagedByDefault = unit.wantedBy == [ ] && !unit.restartIfChanged && !unit.stopIfChanged;
    explicitBootStart = (bad { services.mrjamForgejoHost.startAtBoot = true; }).systemd.services.forgejo.wantedBy == [ "multi-user.target" ];
    exactIdentity = on.users.users.forgejo.uid == 977 && on.users.groups.forgejo.gid == 977;
    noPasswordOrGroups = on.users.users.forgejo.hashedPassword == "!" && on.users.users.forgejo.extraGroups == [ ];
    persistentPathsPreserved = unit.serviceConfig.WorkingDirectory == "/var/lib/forgejo"
      && settings.repository.ROOT == "/var/lib/forgejo/repositories";
    credentialsOutsideStore = unit.environment.FORGEJO__SECURITY__SECRET_KEY__FILE == "/var/lib/forgejo/custom/conf/secret_key"
      && !(unit.serviceConfig ? LoadCredential) && unit.serviceConfig.User == "forgejo";
    runtimeConfigPrivate = unit.serviceConfig.RuntimeDirectoryMode == "0700" && lib.hasInfix "chmod 0400" unit.preStart;
    ssoOnly = !settings.service.ENABLE_INTERNAL_SIGNIN && !settings.service.ENABLE_BASIC_AUTHENTICATION;
    loginLandingInServerSection = settings.server.LANDING_PAGE == "login" && !(settings.DEFAULT ? LANDING_PAGE);
    noActionsUntilAdoption = !settings.actions.ENABLED;
    rendererRetained = settings."markup.orgmode".RENDER_CONTENT_MODE == "sanitized";
    noImplicitRoute = !on.services.nginx.enable;
    logsClosed = unit.serviceConfig.StandardOutput == "null" && unit.serviceConfig.StandardError == "null";
    missingArtifactRejected = !valid (bad { services.mrjamForgejoHost.artifactStorePath = lib.mkForce null; });
    mutableArtifactRejected = !valid (bad { services.mrjamForgejoHost.artifactStorePath = lib.mkForce "/tmp/forgejo"; });
    otherBuildRejected = !valid (bad { services.mrjamForgejoHost.artifactStorePath = lib.mkForce "/nix/store/00000000000000000000000000000000-forgejo-other"; });
    extendedHbaRejected = !valid (bad { services.mrjamPostgresqlPolicy.blocks.forgejo = lib.mkAfter "local all all trust\n"; });
    missingUidRejected = !valid (bad { services.mrjamForgejoHost.uid = lib.mkForce null; });
    missingGidRejected = !valid (bad { services.mrjamForgejoHost.gid = lib.mkForce null; });
    missingDatabaseRejected = !valid (bad { services.postgresql.enable = lib.mkForce false; });
    addedGroupRejected = !valid (bad { users.users.forgejo.extraGroups = [ "wheel" ]; });
  };
in assert lib.all (x: x) (builtins.attrValues result); result
