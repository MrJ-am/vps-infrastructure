# A single Unix-peer capability: delete one native person UUID. The provider
# credential is confined to this service, never passed to the replay worker.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.mrjamIdentityDeletion;
  unit = "mrjam-identity-deletion";
  storePath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  caPath = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+(/[A-Za-z0-9+._?=-]+)*";
  runtime = pkgs.writeText "mrjam-identity-deletion.json" (builtins.toJSON {
    schema_version = 1;
    kanidm_ca_file = cfg.kanidmCaFile;
    kanidm_ca_sha256 = cfg.kanidmCaSha256;
  });
in {
  options.services.mrjamIdentityDeletion = {
    enable = lib.mkEnableOption "native person deletion through the exact replay Unix peer";
    startAtBoot = lib.mkEnableOption "explicit promotion of the bounded deletion adapter";
    artifactStorePath = lib.mkOption { type = storePath;
      description = "Previously built and independently qualified bin/mrjam-identity-deletion."; };
    kanidmCaFile = lib.mkOption { type = caPath; };
    kanidmCaSha256 = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{64}"; };
    credentialFile = lib.mkOption { type = lib.types.str;
      default = "/var/lib/mrjam-identite/kanidm-replay.token"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = !(builtins.hasContext cfg.artifactStorePath) && !(builtins.hasContext cfg.kanidmCaFile)
          && lib.all (part: part != "." && part != "..") (lib.splitString "/" cfg.kanidmCaFile);
        message = "mrjamIdentityDeletion: qualified context-free artifact and immutable canonical public CA required."; }
      { assertion = cfg.credentialFile == "/var/lib/mrjam-identite/kanidm-replay.token";
        message = "mrjamIdentityDeletion: preserve the explicit private provider credential reference."; }
      { assertion = (config.users.users.mrjam-vision-replay.uid or null) == 944
          && (config.users.groups.mrjam-vision-replay.gid or null) == 944
          && (config.services.mrjamVisionReplay.identityProtocol or null) == "kanidm-delete-socket";
        message = "mrjamIdentityDeletion: the only client must be the declared replay peer UID/GID 944 with the socket protocol."; }
      { assertion = lib.all (entry: entry.name == unit || entry.value.uid != 948)
          (lib.mapAttrsToList (name: value: { inherit name value; }) config.users.users);
        message = "mrjamIdentityDeletion: UID 948 is reserved for this adapter alone."; }
    ];
    system.extraDependencies = [ (builtins.storePath cfg.artifactStorePath)
      (builtins.storePath (lib.concatStringsSep "/" (lib.take 4 (lib.splitString "/" cfg.kanidmCaFile)))) ];
    users.users.${unit} = {
      uid = 948; group = "mrjam-vision-replay"; isSystemUser = true;
      extraGroups = [ ]; createHome = false; home = "/var/empty"; hashedPassword = "!";
    };
    systemd.services.${unit} = {
      description = "MRJ.am bounded native person deletion for the replay peer";
      wantedBy = lib.optional cfg.startAtBoot "multi-user.target";
      requires = [ "kanidm.service" ]; after = [ "kanidm.service" ];
      restartIfChanged = false; stopIfChanged = false;
      serviceConfig = {
        Type = "simple";
        ExecStart = "${cfg.artifactStorePath}/bin/mrjam-identity-deletion --config ${runtime}";
        User = unit; Group = "mrjam-vision-replay";
        LoadCredential = [ "kanidm:${cfg.credentialFile}" ];
        RuntimeDirectory = unit; RuntimeDirectoryMode = "0750";
        RuntimeDirectoryPreserve = true;
        ReadWritePaths = [ "/run/${unit}" ];
        UMask = "0077"; LimitCORE = 0;
        StandardInput = "null"; StandardOutput = "null"; StandardError = "null";
        NoNewPrivileges = true; CapabilityBoundingSet = ""; AmbientCapabilities = "";
        ProtectSystem = "strict"; ProtectHome = true; PrivateTmp = true; PrivateDevices = true;
        PrivateIPC = true; ProtectKernelTunables = true; ProtectKernelModules = true;
        ProtectKernelLogs = true; ProtectControlGroups = true; ProtectProc = "invisible";
        ProcSubset = "pid"; ProtectClock = true; RestrictSUIDSGID = true; RestrictRealtime = true;
        RestrictNamespaces = true; LockPersonality = true; MemoryDenyWriteExecute = true;
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
        IPAddressDeny = "any"; IPAddressAllow = "127.0.0.1/32";
        RestrictNetworkInterfaces = [ "lo" ]; SocketBindDeny = "any";
        InaccessiblePaths = [ "-/var/lib/forgejo" "-/var/lib/postgresql" "-/var/lib/kanidm"
          "-/var/lib/nextcloud" "-/var/lib/mrjam-identite" "-/var/lib/mrjam-metier"
          "-/var/lib/mrjam-worker-credentials" "-/var/backup" "-/var/backups"
          "-/run/postgresql" "-/run/mrjam-identity" "-/run/nix" "-/run/docker.sock" ];
        MemoryAccounting = true; MemoryMax = "128M"; CPUQuota = "20%"; TasksMax = 32;
        TimeoutStartSec = 30; TimeoutStopSec = 30; KillMode = "control-group";
        Restart = "on-failure"; RestartSec = 3;
      };
    };
  };
}
