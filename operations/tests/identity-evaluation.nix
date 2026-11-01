{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../hosts/mrjam-vps/core-services.nix ../nixos/mrjam-identity.nix
      ({ pkgs, ... }: {
        system.stateVersion = "26.05";
        fileSystems."/" = { device = "/dev/synthetic"; fsType = "ext4"; };
        boot.loader.grub.enable = false;
        services.mrjamIdentity = {
          enable = true; uid = 984; gid = 984; readersGid = 940;
          # Evaluation placeholder only; no candidate process is launched.
          artifactStorePath = builtins.unsafeDiscardStringContext "${pkgs.coreutils}";
        };
      }) extra ];
  }).config;
  cfg = evaluate { };
  svc = cfg.systemd.services.mrjam-identity;
  aliases = cfg.systemd.services.mrjam-identity-aliases;
  timer = cfg.systemd.timers.mrjam-identity-aliases;
  badMap = evaluate { services.postgresql.identMap = lib.mkAfter "mrjam_native_identity nobody vision_identite\n"; };
  badGroup = evaluate { services.mrjamIdentity.readersGid = lib.mkForce 984; };
  enabled = evaluate { services.mrjamIdentity.startAtBoot = true; };
  refused = prefix: candidate: lib.any (a: !a.assertion && lib.hasPrefix prefix a.message) candidate.assertions;
  result = {
    validComposition = lib.all (a: a.assertion) cfg.assertions;
    stateOwnerRetained = cfg.users.users.mrjam-metier.uid == 984 && cfg.users.groups.mrjam-metier.gid == 984;
    noImplicitPromotion = svc.wantedBy == [ ] && aliases.wantedBy == [ ] && timer.wantedBy == [ ];
    explicitPromotion = enabled.systemd.services.mrjam-identity.wantedBy == [ "multi-user.target" ]
      && enabled.systemd.timers.mrjam-identity-aliases.wantedBy == [ "timers.target" ];
    noStateDirectoryChown = !(svc.serviceConfig ? StateDirectory);
    existingStateRequired = svc.unitConfig.AssertPathExists == "/var/lib/mrjam-metier/log/sessions.sqlite";
    credentialOnlyByReference = svc.serviceConfig.LoadCredential == [ "kanidm-vision:/var/lib/mrjam-identite/kanidm-vision.secret" ];
    nativeDependencies = svc.requires == [ "postgresql.service" "kanidm.service" ];
    reservedPeerMap = lib.hasInfix "local vision vision_identite peer map=mrjam_native_identity" cfg.services.postgresql.authentication;
    additionalPeerRefused = refused "mrjamIdentity: no additional peer" badMap;
    sharedAliasGroupRefused = refused "mrjamIdentity: retained state identity" badGroup;
    privateLoopback = svc.serviceConfig.IPAddressDeny == "any" && svc.serviceConfig.IPAddressAllow == "localhost"
      && svc.serviceConfig.SocketBindAllow == "ipv4:tcp:3002";
    noCapability = svc.serviceConfig.CapabilityBoundingSet == "" && svc.serviceConfig.NoNewPrivileges;
    noPrivateDiagnostics = svc.serviceConfig.StandardOutput == "null" && svc.serviceConfig.StandardError == "null";
    aliasesCannotModifySessions = aliases.serviceConfig.ReadWritePaths == [ "/run/mrjam-identity" ]
      && aliases.serviceConfig.ReadOnlyPaths == [ "/var/lib/mrjam-metier/log" ];
    aliasesNoNetwork = aliases.serviceConfig.PrivateNetwork && aliases.serviceConfig.RestrictAddressFamilies == [ "AF_UNIX" ];
    projectionSeparate = lib.hasInfix "project-aliases --source /var/lib/mrjam-metier/log/sessions.sqlite --destination /run/mrjam-identity/aliases.sqlite" aliases.serviceConfig.ExecStart;
    aliasReaderGroup = svc.serviceConfig.Group == "mrjam-log-readers" && svc.serviceConfig.RuntimeDirectoryMode == "2750";
  };
in assert lib.assertMsg (lib.all (value: value) (builtins.attrValues result))
  (builtins.toJSON result + builtins.toJSON (map (a: a.message) (builtins.filter (a: !a.assertion) cfg.assertions))); result
