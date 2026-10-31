{ config, lib, ... }:

let
  cfg = config.services.mrjamRust;
  storePathType = lib.types.strMatching "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+";
  credentialNames = [
    "db-mateval" "db-mateval-admin" "mateval-activation-sha256"
    "db-vision" "db-vision-journal" "db-vision-admin" "db-audition"
    "admission-approval"
  ];
  credentialPathType = lib.types.strMatching "/(run/secrets|run/keys|var/lib/mrjam/secrets)/[A-Za-z0-9._/-]+";
  slotType = port: lib.types.submodule {
    options = {
      enable = lib.mkEnableOption "installation de l'unité privée, sans démarrage automatique";
      artifactStorePath = lib.mkOption {
        type = lib.types.nullOr storePathType;
        default = null;
        description = ''
          Chemin sans contexte Nix d'une fermeture préconstruite déjà installée
          par le futur déployeur. Le binaire est bin/mrjam-server. Ce chemin
          n'est ni une signature ni une preuve de qualification.
        '';
      };
      runtimeConfigStorePath = lib.mkOption {
        type = lib.types.nullOr storePathType;
        default = null;
        description = ''
          Fermeture préconstruite qualifiée contenant runtime.json, sans secret.
          Les mots de passe y désignent /run/credentials/mrjam-rust-SLOT.service/NOM.
          Le serveur valide strictement cette configuration et refuse une capacité
          exigée mais absente ; aucune migration n'est exécutée au démarrage.
        '';
      };
      credentials = lib.genAttrs credentialNames (_: lib.mkOption {
        type = lib.types.nullOr credentialPathType;
        default = null;
        description = "Référence d'un fichier secret existant hors store ; contenu jamais lu par Nix ou Cloud.";
      });
      port = lib.mkOption {
        type = lib.types.port;
        default = port;
        description = "Port TCP exclusivement sur 127.0.0.1 ; aucune publication Nginx.";
      };
    };
  };
  enabledSlots = lib.filterAttrs (_: slot: slot.enable) cfg.slots;
  enabledPorts = map (slot: slot.port) (builtins.attrValues enabledSlots);
  serviceName = name: "mrjam-rust-${name}";
in
{
  options.services.mrjamRust = {
    enable = lib.mkEnableOption "unités privées du monolithe Rust à qualifier";
    slots = {
      blue = lib.mkOption { type = slotType 38101; default = { }; };
      green = lib.mkOption { type = slotType 38102; default = { }; };
    };
    limits = {
      aggregateCpuPercent = lib.mkOption {
        type = lib.types.ints.positive;
        default = 100;
        description = "Plafond CPU cumulé des deux unités ; 100 = un cœur.";
      };
      instanceMemoryMiB = lib.mkOption {
        type = lib.types.ints.positive;
        default = 512;
        description = "Plafond proposé après mesure synthétique transport/JSON ; à qualifier avec assets, crypto et SQL, sans présumer la réserve du VPS.";
      };
      aggregateMemoryMiB = lib.mkOption {
        type = lib.types.ints.positive;
        default = 1024;
        description = "Plafond mémoire partagé ; ne prouve pas la marge du VPS.";
      };
      instanceTasks = lib.mkOption {
        type = lib.types.ints.positive;
        default = 128;
        description = "Nombre maximal de tâches par unité.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = enabledSlots != { };
        message = "mrjam-rust: sélectionner au moins un slot à installer.";
      }
      {
        assertion = builtins.length enabledPorts == builtins.length (lib.unique enabledPorts);
        message = "mrjam-rust: les ports des slots installés doivent être distincts.";
      }
      {
        assertion = cfg.limits.aggregateMemoryMiB >= cfg.limits.instanceMemoryMiB;
        message = "mrjam-rust: le plafond mémoire cumulé doit couvrir au moins une instance.";
      }
    ] ++ lib.mapAttrsToList (_: slot: {
      assertion = slot.artifactStorePath != null
        && !(builtins.hasContext slot.artifactStorePath);
      message = "mrjam-rust: chaque slot installé exige un chemin de fermeture préconstruite sans contexte dérivation.";
    }) enabledSlots ++ lib.mapAttrsToList (_: slot: {
      assertion = slot.runtimeConfigStorePath != null
        && !(builtins.hasContext slot.runtimeConfigStorePath);
      message = "mrjam-rust: chaque slot exige sa configuration runtime préconstruite, sans contenu secret ni contexte dérivation.";
    }) enabledSlots ++ lib.mapAttrsToList (_: slot: {
      assertion = lib.all (path: path == null || (
        !(builtins.hasContext path)
        && !(lib.hasInfix "//" path)
        && !(builtins.elem ".." (lib.splitString "/" path))
        && !(builtins.elem "." (lib.splitString "/" path))
        && !(lib.hasSuffix "/" path)
      )) (builtins.attrValues slot.credentials);
      message = "mrjam-rust: les références de credentials doivent être absolues, canoniques, hors store et sans contexte Nix.";
    }) enabledSlots;

    users.groups = lib.mapAttrs' (name: _: lib.nameValuePair (serviceName name) { }) enabledSlots;
    users.users = lib.mapAttrs' (name: _: lib.nameValuePair (serviceName name) {
      isSystemUser = true;
      group = serviceName name;
      createHome = false;
    }) enabledSlots;

    systemd.slices.mrjam-rust = {
      description = "Budget cumulé des instances Rust privées";
      sliceConfig = {
        CPUAccounting = true;
        CPUQuota = "${toString cfg.limits.aggregateCpuPercent}%";
        MemoryAccounting = true;
        MemoryMax = "${toString cfg.limits.aggregateMemoryMiB}M";
        TasksAccounting = true;
        TasksMax = cfg.limits.instanceTasks * 2;
        IOAccounting = true;
        IOWeight = 100;
      };
    };

    systemd.services = lib.mapAttrs' (name: slot:
      let
        unit = serviceName name;
        # Empty only while reporting an invalid configuration assertion.
        artifact = if slot.artifactStorePath == null then "/unconfigured" else slot.artifactStorePath;
        runtime = if slot.runtimeConfigStorePath == null then "/unconfigured" else slot.runtimeConfigStorePath;
        executable = "${artifact}/bin/mrjam-server";
      in lib.nameValuePair unit {
        description = "Monolithe Rust privé ${name}, non promu automatiquement";
        # Installing a unit must neither start it nor restart its active sibling.
        wantedBy = [ ];
        restartIfChanged = false;
        stopIfChanged = false;
        after = [ "network.target" ];
        unitConfig = {
          AssertFileIsExecutable = executable;
          AssertPathExists = "${runtime}/runtime.json";
          StartLimitIntervalSec = 60;
          StartLimitBurst = 3;
        };
        environment = {
          MRJAM_LISTEN_ADDR = "127.0.0.1:${toString slot.port}";
          MRJAM_INSTANCE = name;
          MRJAM_WORKERS_ENABLED = "false";
        };
        serviceConfig = {
          Type = "simple";
          User = unit;
          Group = unit;
          ExecStart = "${executable} serve --config ${runtime}/runtime.json";
          LoadCredential = lib.mapAttrsToList (name: path: "${name}:${path}")
            (lib.filterAttrs (_: path: path != null) slot.credentials);
          WorkingDirectory = "/";
          Slice = "mrjam-rust.slice";
          Restart = "on-failure";
          RestartSec = 5;
          KillSignal = "SIGTERM";
          KillMode = "control-group";
          TimeoutStopSec = "infinity";
          SendSIGKILL = false;
          UMask = "0077";
          # A qualified, closed logging contract must precede diagnostic export.
          StandardOutput = "null";
          StandardError = "null";
          NoNewPrivileges = true;
          PrivateTmp = true;
          PrivateDevices = true;
          PrivateIPC = true;
          ProtectSystem = "strict";
          ProtectHome = true;
          ProtectKernelTunables = true;
          ProtectKernelModules = true;
          ProtectKernelLogs = true;
          ProtectControlGroups = true;
          ProtectClock = true;
          ProtectHostname = true;
          ProtectProc = "invisible";
          ProcSubset = "pid";
          RestrictSUIDSGID = true;
          RestrictRealtime = true;
          RestrictNamespaces = true;
          LockPersonality = true;
          MemoryDenyWriteExecute = true;
          CapabilityBoundingSet = "";
          AmbientCapabilities = "";
          RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" ];
          SocketBindDeny = "any";
          SocketBindAllow = "ipv4:tcp:${toString slot.port}";
          IPAddressDeny = "any";
          IPAddressAllow = "localhost";
          SystemCallArchitectures = "native";
          SystemCallFilter = [ "@system-service" "~@privileged" "~@resources" ];
          SystemCallErrorNumber = "EPERM";
          InaccessiblePaths = [
            "-/run/docker.sock" "-/var/run/docker.sock" "-/run/podman"
            "-/run/libvirt" "-/run/secrets" "-/var/backup" "-/var/backups"
          ];
          MemoryAccounting = true;
          MemoryHigh = "${toString (cfg.limits.instanceMemoryMiB * 3 / 4)}M";
          MemoryMax = "${toString cfg.limits.instanceMemoryMiB}M";
          TasksAccounting = true;
          TasksMax = cfg.limits.instanceTasks;
          LimitNOFILE = 4096;
        };
      }) enabledSlots;
  };
}
