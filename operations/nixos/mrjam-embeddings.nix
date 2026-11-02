# Retain the installed provider's exact model, Python environment and algorithm.
{ config, lib, ... }:
let
  cfg = config.services.mrjamEmbeddings;
  store = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  script = ../embeddings/embeddings.py;
in {
  options.services.mrjamEmbeddings = {
    enable = lib.mkEnableOption "qualified unchanged local Vision embedding provider";
    pythonStorePath = lib.mkOption { type = store; };
    modelStorePath = lib.mkOption { type = store; };
    promote = lib.mkEnableOption "provider startup after the explicit application cutover";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = cfg.pythonStorePath == "/nix/store/dbnsh65c9fir9psk7waq3swb3mdh18cr-python3-3.13.15-env"
          && cfg.modelStorePath == "/nix/store/mwwjyy4vlrwp59a7srjy53x24viksa6z-vision-modele-multilingue-e8f8c211226b"
          && !(builtins.hasContext cfg.pythonStorePath) && !(builtins.hasContext cfg.modelStorePath);
        message = "Vision embeddings must preserve the separately reproduced and qualified installed Python/model outputs."; }
    ];
    system.extraDependencies = map builtins.storePath [ cfg.pythonStorePath cfg.modelStorePath ];
    systemd.services.vision-embeddings = {
      description = "Vision preserved multilingual local embeddings";
      wantedBy = lib.optionals cfg.promote [ "multi-user.target" ];
      before = [ "mrjam-rust-blue.service" "mrjam-rust-green.service" ];
      restartIfChanged = false;
      environment = {
        HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1";
        HF_HOME = "/var/cache/vision-embeddings";
        OMP_NUM_THREADS = "2"; TOKENIZERS_PARALLELISM = "false";
      };
      serviceConfig = {
        ExecStart = "${cfg.pythonStorePath}/bin/python ${script} --modele ${cfg.modelStorePath} --port 39004";
        DynamicUser = true; CacheDirectory = "vision-embeddings";
        Restart = "on-failure"; RestartSec = 5;
        NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
        PrivateTmp = true; PrivateDevices = true; ProtectSystem = "strict"; ProtectHome = true;
        RestrictAddressFamilies = [ "AF_INET" ]; IPAddressDeny = "any"; IPAddressAllow = [ "127.0.0.0/8" ];
        ProtectKernelTunables = true; ProtectKernelModules = true; ProtectKernelLogs = true;
        ProtectControlGroups = true; RestrictSUIDSGID = true; RestrictRealtime = true;
        LockPersonality = true; RestrictNamespaces = true;
        MemoryMax = "2G"; CPUQuota = "200%"; TasksMax = 64;
        TimeoutStartSec = 120; TimeoutStopSec = 30; KillMode = "control-group";
        UMask = "0077"; LimitCORE = 0;
        StandardInput = "null"; StandardOutput = "null"; StandardError = "null";
      };
    };
  };
}
