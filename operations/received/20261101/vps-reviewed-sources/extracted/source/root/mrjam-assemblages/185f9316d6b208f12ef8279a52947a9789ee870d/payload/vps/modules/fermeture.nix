{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.fermeture;
  python = pkgs.python3.withPackages (p: [ p.psycopg p.requests ]);
  source = pkgs.runCommand "mrjam-fermeture-source" {} ''
    mkdir -p "$out"
    cp ${../services/mrjam-fermeture/fermeture.py} "$out/fermeture.py"
    cp ${../services/mrjam-courriel/courriel.py} "$out/courriel.py"
  '';
in {
  options.infrastructure.fermeture = {
    enable = lib.mkEnableOption "fermeture autonome du compte commun après qualification";
    secretHook = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/fermeture-hook.secret"; };
    secretClient = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/fermeture-client.secret"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [{ assertion = config.infrastructure.admission.enable && config.infrastructure.visionCycle.enable;
      message = "La fermeture commune exige admission, cycle privé, registre externe et migrations qualifiés."; }];
    users.groups.vision_fermeture = {};
    users.users.vision_fermeture = { isSystemUser = true; group = "vision_fermeture"; };
    systemd.services.mrjam-fermeture = {
      description = "Fermeture commune sur intention personnelle avec registre chiffré";
      wantedBy = [ "multi-user.target" ]; after = [ "postgresql.service" "keycloak.service" "mrjam-admission.service" ];
      environment = {
        MRJ_FERMETURE_DSN = "dbname=vision user=vision_fermeture host=/run/postgresql";
        MRJ_SMTP_SECRET = "/run/credentials/mrjam-fermeture.service/smtp";
        MRJ_FERMETURE_CONFIG = "/run/credentials/mrjam-fermeture.service/config";
        MRJ_FERMETURE_CLIENT = "/run/credentials/mrjam-fermeture.service/client";
        MRJ_FERMETURE_HOOK = "/run/credentials/mrjam-fermeture.service/hook";
        AGE = "${pkgs.age}/bin/age";
      };
      serviceConfig = {
        ExecStart = "${python}/bin/python3 ${source}/fermeture.py";
        User = "vision_fermeture"; Group = "vision_fermeture";
        StateDirectory = "mrjam-fermeture"; StateDirectoryMode = "0700";
        LoadCredential = [ "smtp:${config.infrastructure.courriel.secret}" "config:${config.infrastructure.visionCycle.configPrivee}"
          "client:${cfg.secretClient}" "hook:${cfg.secretHook}" ];
        Restart = "on-failure"; RestartSec = 5; UMask = "0077";
        NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true; ProtectKernelTunables = true;
        ProtectKernelModules = true; ProtectControlGroups = true;
        RestrictSUIDSGID = true; CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        MemoryMax = "192M"; TasksMax = 32;
      };
    };
    systemd.services.keycloak = {
      environment.MRJ_FERMETURE_SECRET_FILE = "/run/credentials/keycloak.service/fermeture-hook";
      serviceConfig.LoadCredential = [ "fermeture-hook:${cfg.secretHook}" ];
    };
    systemd.services.mrjam-admission = {
      environment.MRJ_ADMISSION_FERMETURE_SECRET = "/run/credentials/mrjam-admission.service/fermeture-hook";
      serviceConfig.LoadCredential = [ "fermeture-hook:${cfg.secretHook}" ];
    };
    # Aucun endpoint de fermeture interne n'est routé par Nginx.
  };
}
