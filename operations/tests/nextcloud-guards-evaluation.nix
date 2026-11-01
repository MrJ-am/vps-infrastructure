{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-nextcloud-guards.nix ({ pkgs, ... }: {
      system.stateVersion = "26.05";
      boot.loader.grub.enable = false;
      fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
      services.nextcloud = {
        package = pkgs.nextcloud34;
        hostName = "nextcloud.synthetic.invalid";
        config.dbtype = "pgsql";
        config.dbhost = "/run/postgresql";
        config.adminpassFile = "/run/synthetic-not-created-admin-password";
        # A version-label fixture, never built and not evidence of patched PHP.
        phpPackage = pkgs.php84.overrideAttrs (_: { version = "8.4.27"; });
      };
    }) extra ];
  }).config;
  setup = { services.nextcloud.enable = true; services.mrjamNextcloudGuards.enable = true; };
  off = evaluate { };
  baseline = evaluate { services.nextcloud.enable = true; };
  enabled = evaluate setup;
  passes = config: !lib.any (a: !a.assertion && lib.hasPrefix "mrjamNextcloudGuards:" a.message) config.assertions;
  bad = extra: evaluate { imports = [ setup extra ]; };
  marker = "!/var/lib/nextcloud-php-security/blocked";
  result = {
    disabledDoesNotEnableNextcloud = !off.services.nextcloud.enable && !(off.systemd.services ? phpfpm-nextcloud);
    enabledGuardAssertionsPass = passes enabled;
    cliUploadProgressOff = enabled.services.nextcloud.phpOptions."session.upload_progress.enabled" == "Off";
    fpmAdminUploadProgressOff = enabled.services.phpfpm.pools.nextcloud.settings."php_admin_flag[session.upload_progress.enabled]" == false;
    globalUploadProgressOff = lib.hasInfix "session.upload_progress.enabled = Off" enabled.services.phpfpm.phpOptions;
    fpmMarkerRetained = enabled.systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists == marker;
    cronMarkerRetained = enabled.systemd.services.nextcloud-cron.unitConfig.ConditionPathExists == marker;
    phpPackageNotChanged = enabled.services.nextcloud.phpPackage.outPath == baseline.services.nextcloud.phpPackage.outPath;
    noAdditionalServices = builtins.attrNames enabled.systemd.services == builtins.attrNames baseline.systemd.services;
    noDatabaseChange = enabled.services.nextcloud.config.dbname == baseline.services.nextcloud.config.dbname;
    noStateOrSecretReferenceChange = enabled.services.nextcloud.home == baseline.services.nextcloud.home
      && enabled.services.nextcloud.config.adminpassFile == baseline.services.nextcloud.config.adminpassFile;
    missingNextcloudRejected = !passes (bad { services.nextcloud.enable = lib.mkForce false; });
    oldPhpRejected = !passes (bad ({ pkgs, ... }: { services.nextcloud.phpPackage = lib.mkForce (pkgs.php84.overrideAttrs (_: { version = "8.4.26"; })); }));
    differentBranchRejected = !passes (bad ({ pkgs, ... }: { services.nextcloud.phpPackage = lib.mkForce (pkgs.php84.overrideAttrs (_: { version = "8.5.1"; })); }));
    removedMarkerRejected = !passes (bad { systemd.services.phpfpm-nextcloud.unitConfig.ConditionPathExists = lib.mkForce ""; });
    fpmOverrideRejected = !passes (bad { services.phpfpm.pools.nextcloud.settings."php_admin_flag[session.upload_progress.enabled]" = lib.mkForce true; });
  };
in assert builtins.all (v: v) (builtins.attrValues result); result
