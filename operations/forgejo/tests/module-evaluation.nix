{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-forgejo.nix {
      system.stateVersion = "26.05"; # Synthetic fixture only, never a VPS value.
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
    } extra ];
  }).config;
  disabled = evaluate { };
  forgejoEnabled = evaluate { services.mrjamForgejo.enable = true; };
  runnerEnabled = evaluate { services.mrjamForgejo.runner.enable = true; };
  # NixOS assertion messages may reference failure-only fields lazily. Never
  # force the message of a passing assertion merely to select our contract.
  passes = c: !(builtins.any (a: (!a.assertion)
    && lib.hasPrefix "mrjamForgejo:" a.message) c.assertions);
  settings = disabled.services.mrjamForgejo.preparation.settings;
  results = {
    disabledPasses = passes disabled;
    noForgejoService = !disabled.services.forgejo.enable;
    noRunnerService = disabled.services.gitea-actions-runner.instances == { };
    noForgejoIdentity = !(builtins.hasAttr "forgejo" disabled.users.users);
    noSSOOrBackupUnits = !(builtins.hasAttr "forgejo-identity" disabled.systemd.services)
      && !(builtins.hasAttr "forgejo-backup" disabled.systemd.services);
    noPostgresProvisioning = !disabled.services.postgresql.enable;
    noNginxProvisioning = !disabled.services.nginx.enable;
    noRuntimeInstalled = !(builtins.elem (toString disabled.services.mrjamForgejo.preparation)
      (map toString disabled.environment.systemPackages));
    forgejoEnableRejected = !(passes forgejoEnabled);
    runnerEnableRejected = !(passes runnerEnabled);
    actionsFrozen = !settings.actions.ENABLED;
    noLocalAuthenticationFallback = !settings.service.ENABLE_INTERNAL_SIGNIN && !settings.service.ENABLE_BASIC_AUTHENTICATION;
    privateRepositoryDefault = settings.repository.FORCE_PRIVATE && settings.repository.DEFAULT_PRIVATE == "private";
    privateHTTP = settings.server.HTTP_ADDR == "127.0.0.1";
    sanitizedOrg = settings."markup.orgmode".RENDER_CONTENT_MODE == "sanitized";
  };
in
assert builtins.all (value: value) (builtins.attrValues results);
results
