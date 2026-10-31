{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamForgejoPolicy;
  allowedRepositories = [ "Signature" "apprendre-a-demontrer" "etp-vie-affective" "matheval" "mrjam-plateforme" "mrjam-validation" "style-mrjam" "vision" "vps-infrastructure" ];
  policy = {
    schema_version = 2;
    owner = "MrJ-am";
    forgejo_version = "17.0.1";
    rules_revision = cfg.rulesRevision;
    controller_revision = cfg.controllerRevision;
    phase = cfg.phase;
    repositories = builtins.sort builtins.lessThan cfg.repositories;
  };
in {
  options.services.mrjamForgejoPolicy = {
    enable = lib.mkEnableOption "bounded local Forgejo repository-policy controller";
    mode = lib.mkOption { type = lib.types.enum [ "plan" "apply" ]; default = "plan"; };
    phase = lib.mkOption {
      type = lib.types.enum [ "bootstrap-repositories" "protect-main" "operate-validation" ];
      default = "bootstrap-repositories";
      description = "Create empty private repositories before exact source import; protect main only after import.";
    };
    rulesRevision = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{40}"; };
    controllerRevision = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{40}"; };
    repositories = lib.mkOption {
      type = lib.types.listOf (lib.types.enum allowedRepositories);
      default = [ "mrjam-plateforme" "mrjam-validation" "vps-infrastructure" ];
    };
    tokenFile = lib.mkOption {
      type = lib.types.strMatching "/(run|var/lib)/[A-Za-z0-9_./-]+";
      description = "Existing local credential reference; never a token value or a Nix store file.";
    };
    reviewedPlan = lib.mkOption {
      type = lib.types.nullOr lib.types.attrs;
      default = null;
      description = "Exact public metadata plan, bound to a recent observation and this policy. No approval boolean substitutes for it.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.repositories != [ ] && lib.length (lib.unique cfg.repositories) == lib.length cfg.repositories;
        message = "mrjamForgejoPolicy: unique non-empty managed repository list required."; }
      { assertion = !(lib.hasInfix "/../" cfg.tokenFile) && !(lib.hasSuffix "/.." cfg.tokenFile);
        message = "mrjamForgejoPolicy: credential reference must have no parent traversal."; }
      { assertion = cfg.mode != "apply" || cfg.reviewedPlan != null;
        message = "mrjamForgejoPolicy: apply requires a reviewed observation-bound plan."; }
      { assertion = pkgs.forgejo.version == "17.0.1";
        message = "mrjamForgejoPolicy: API profile is qualified only for Forgejo 17.0.1; requalify a different pin."; }
    ];
    environment.etc."mrjam-forgejo/policy.json" = {
      text = builtins.toJSON policy;
      mode = "0444";
    };
    environment.etc."mrjam-forgejo/reconcile-plan.json" = lib.mkIf (cfg.reviewedPlan != null) {
      text = builtins.toJSON cfg.reviewedPlan;
      mode = "0444";
    };
    systemd.services.mrjam-forgejo-policy = {
      description = "MRJ.am bounded Forgejo metadata reconciliation";
      # No WantedBy, timer or implicit invocation when the generation changes.
      restartIfChanged = false;
      stopIfChanged = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.python3}/bin/python3 -I -S ${../forgejo/reconcile.py} ${cfg.mode}";
        User = "mrjam-forgejo-policy";
        Group = "mrjam-forgejo-policy";
        DynamicUser = true;
        StateDirectory = "mrjam-forgejo-policy";
        StateDirectoryMode = "0700";
        WorkingDirectory = "/var/lib/mrjam-forgejo-policy";
        LoadCredential = [ "forgejo-token:${cfg.tokenFile}" ];
        UMask = "0077";
        NoNewPrivileges = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectProc = "invisible";
        ProcSubset = "pid";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        RestrictNamespaces = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        RestrictRealtime = true;
        SystemCallArchitectures = "native";
        SystemCallFilter = [ "@system-service" "~@privileged" "~@resources" ];
        RestrictAddressFamilies = [ "AF_INET" "AF_UNIX" ];
        IPAddressDeny = "any";
        IPAddressAllow = "localhost";
        SocketBindDeny = "any";
        InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm" "-/var/lib/nextcloud" "-/var/backup" "-/var/backups" ];
        ReadWritePaths = [ "/var/lib/mrjam-forgejo-policy" ];
        MemoryMax = "128M";
        TasksMax = 8;
        TimeoutStartSec = 185;
        StandardOutput = "journal"; # The program emits only closed receipts.
        StandardError = "null";
      };
    };
  };
}
