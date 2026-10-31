{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamValidationStaging;
  worker = config.services.mrjamValidationWorker;
  package = pkgs.callPackage ../forgejo/staging-package.nix { };
  catalog = {
    schema_version = 1;
    rules_revision = worker.rulesRevision;
    proposals = map (entry: { sha256 = entry.sha256; source_store = toString entry.source; }) cfg.proposals;
  };
in {
  imports = [ ./mrjam-validation-worker.nix ];
  options.services.mrjamValidationStaging = {
    enable = lib.mkEnableOption "bounded publication of independently selected public sources";
    proposals = lib.mkOption {
      default = [ ];
      description = "One or two immutable public bundles selected outside candidate workflows. Each root contains the exact manifest and all declared files. Not an authority to fetch or activate them.";
      type = lib.types.listOf (lib.types.submodule {
        options = {
          sha256 = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{64}"; };
          source = lib.mkOption { type = lib.types.package; };
        };
      });
    };
    package = lib.mkOption { type = lib.types.package; readOnly = true; default = package; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = worker.enable; message = "mrjamValidationStaging requires the explicitly configured worker and its lock."; }
      { assertion = builtins.length cfg.proposals >= 1 && builtins.length cfg.proposals <= 2;
        message = "mrjamValidationStaging requires one or two pinned source bundles."; }
      { assertion = builtins.length (lib.unique (map (p: p.sha256) cfg.proposals)) == builtins.length cfg.proposals;
        message = "mrjamValidationStaging refuses duplicate proposals."; }
    ];
    environment.etc."mrjam-validation-staging/catalog.json" = {
      text = builtins.toJSON catalog;
      mode = "0444";
    };
    systemd.services.mrjam-validation-staging = {
      description = "MRJ.am bounded public source publication";
      after = [ "systemd-tmpfiles-setup.service" ];
      # Installation of the module does not publish or start validation jobs.
      restartIfChanged = false;
      stopIfChanged = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${package}/bin/mrjam-validation-stage-sources";
        User = "root";
        Group = "root";
        UMask = "0077";
        StandardInput = "null";
        StandardOutput = "journal"; # Fixed codes, counts and public content digests only.
        StandardError = "null";
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        ProtectSystem = "strict";
        ReadWritePaths = [ "/var/lib/mrjam-validation-input" ];
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        PrivateNetwork = true;
        RestrictAddressFamilies = [ "AF_UNIX" ];
        IPAddressDeny = "any";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        ProtectProc = "invisible";
        ProcSubset = "pid";
        RestrictNamespaces = true;
        RestrictSUIDSGID = true;
        RestrictRealtime = true;
        LockPersonality = true;
        InaccessiblePaths = [ "-/run/credentials" "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/lib/mrjam-validation-collector" "-/var/backup" "-/var/backups" "-/var/run/docker.sock" ];
        MemoryMax = "192M";
        CPUQuota = "20%";
        TasksMax = 16;
        TimeoutStartSec = 120;
        TimeoutStopSec = 5;
        KillMode = "control-group";
        LimitCORE = 0;
      };
    };
  };
}
