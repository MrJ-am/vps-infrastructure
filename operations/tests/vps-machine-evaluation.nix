{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  facts = builtins.fromJSON (builtins.readFile ../hosts/mrjam-vps/received-profile.json);
  servicesReport = builtins.fromJSON (builtins.readFile ../received/20261101/services-v1.json);
  eval = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../hosts/mrjam-vps/configuration.nix extra ];
  }).config;
  cfg = eval { };
  network = cfg.systemd.network.networks."05-matheval-eth0";
  changed = eval { system.stateVersion = lib.mkForce "24.11"; };
  stateRefused = lib.any (a: !a.assertion && lib.hasPrefix "mrjamVpsMachine: stateVersion" a.message) changed.assertions;
  activationBlocked = lib.any (a: !a.assertion && lib.hasPrefix "mrjamVpsMachine: complete host activation blocked." a.message) cfg.assertions;
  unexpectedFailures = builtins.filter (a: !a.assertion && !(lib.hasPrefix "mrjamVpsMachine: complete host activation blocked." a.message)) cfg.assertions;
  result = {
    sourceBytesMatch = builtins.hashFile "sha256" ../received/20261101/vps-reviewed-sources/sources-vps-revues.tar == facts.archive_sha256;
    preserveDeclaredStateVersion = cfg.system.stateVersion == "26.05";
    noCompatibilityIncrease = stateRefused;
    completeHostActivationRefused = activationBlocked
      && !(builtins.tryEval cfg.system.build.toplevel.drvPath).success;
    noOtherFailedAssertion = unexpectedFailures == [ ];
    x86Platform = cfg.nixpkgs.hostPlatform.system == "x86_64-linux";
    rootDeviceFromVps = cfg.fileSystems."/".device == "/dev/disk/by-uuid/f222513b-ded1-49fa-b591-20ce86a2fe7f";
    rootFilesystemAndGrowthPreserved = cfg.fileSystems."/".fsType == "ext4" && cfg.fileSystems."/".autoResize && cfg.boot.growPartition;
    bootDevicePreserved = cfg.boot.loader.grub.enable && cfg.boot.loader.grub.device == "/dev/sda";
    noSwapInvented = cfg.swapDevices == [ ];
    qemuProfileFromPinnedNixpkgs = cfg.services.qemuGuest.enable && builtins.elem "virtio_pci" cfg.boot.initrd.availableKernelModules;
    networkUsesReceivedInterface = network.matchConfig.Name == "eth0" && network.matchConfig.MACAddress == facts.mac_address;
    bothAddressesPreserved = network.address == facts.addresses;
    bothRoutesPreserved = map (r: r.Gateway) network.routes == facts.gateways;
    resolverPreserved = network.dns == facts.dns && cfg.services.resolved.enable;
    noDhcpIntroduced = !cfg.networking.useDHCP && cfg.networking.useNetworkd && network.networkConfig.DHCP == "no";
    cloudInitDoesNotRestartOnChange = lib.all (name: !cfg.systemd.services.${name}.restartIfChanged)
      [ "cloud-init-local" "cloud-init" "cloud-config" "cloud-final" ];
    cloudInitDoesNotEmitKeys = !cfg.services.cloud-init.settings.ssh.emit_keys_to_console;
    rootPublicIdentityPreserved = cfg.users.users.root.openssh.authorizedKeys.keys == [ facts.root_public_key ];
    passwordSshStillDenied = !cfg.services.openssh.settings.PasswordAuthentication
      && !cfg.services.openssh.settings.KbdInteractiveAuthentication
      && cfg.services.openssh.settings.PermitRootLogin == "prohibit-password";
    inventoryStillStaged = !cfg.services.mrjamInventory.enable;
    observedServiceIdentitiesUsed = builtins.all (pair:
      pair.candidate.uid == servicesReport.accounts.${pair.account}.uid
      && pair.candidate.gid == servicesReport.accounts.${pair.account}.gid
    ) [
      { candidate = cfg.services.mrjamForgejoHost; account = "forgejo"; }
      { candidate = cfg.services.mrjamKanidmHost; account = "kanidm"; }
      { candidate = cfg.services.mrjamNextcloudHost; account = "nextcloud"; }
      { candidate = cfg.services.mrjamVise.adoption; account = "etp_carnet"; }
    ];
    observedIdentitiesDoNotActivateServices = !cfg.services.mrjamForgejoHost.enable
      && !cfg.services.mrjamKanidmHost.enable && !cfg.services.mrjamNextcloudHost.enable;
    observedIdentitiesDoNotCreateAccounts = builtins.all (name: !(builtins.hasAttr name cfg.users.users))
      [ "forgejo" "kanidm" "nextcloud" "etp_carnet" ];
    observedBuildsAreNotQualifiedArtifacts = cfg.services.mrjamForgejoHost.artifactStorePath == null
      && cfg.services.mrjamKanidmHost.artifactStorePath == null && cfg.services.mrjamVise.artifactRoot == null;
    rustForgejoAndViseStillStaged = !cfg.services.mrjamRust.enable && !cfg.services.mrjamForgejo.enable && !cfg.services.mrjamVise.enable;
    noDatabaseProvisioning = !cfg.services.postgresql.enable && cfg.services.postgresql.ensureDatabases == [ ];
    noWebServerOrViseBackupEnabled = !cfg.services.nginx.enable && !(cfg.systemd.services ? vise-backup);
    noRunningGenerationClaim = facts.generation_binding == "unverified" && !facts.hardware_correspondence_verified
      && !facts.network_correspondence_verified && !facts.code_directory_ids_are_authenticated_git_commits;
  };
in assert builtins.all (v: v) (builtins.attrValues result); result
