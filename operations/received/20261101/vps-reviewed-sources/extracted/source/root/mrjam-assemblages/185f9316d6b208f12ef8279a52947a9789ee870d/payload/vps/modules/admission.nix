{ config, lib, pkgs, ... }:
let
  cfg = config.infrastructure.admission;
  python = pkgs.python3.withPackages (p: [ p.psycopg p.requests ]);
  source = pkgs.runCommand "mrjam-admission-source" {} ''
    mkdir -p "$out"
    cp ${../services/mrjam-admission/admission.py} "$out/admission.py"
    cp ${../services/mrjam-courriel/courriel.py} "$out/courriel.py"
  '';
  route = {
    proxyPass = "http://127.0.0.1:3027";
    extraConfig = ''
      proxy_set_header Host $host;
      proxy_set_header Origin $http_origin;
      proxy_set_header Authorization "";
      proxy_set_header Cookie "";
      proxy_set_header X-Mrj-User "";
      client_max_body_size 4k;
      limit_req zone=protected_api_per_ip burst=2 nodelay;
      limit_req_status 429;
      access_log off;
    '';
  };
in {
  options.infrastructure.admission = {
    enable = lib.mkEnableOption "admission commune contrôlée, sans inscription native";
    secretClient = lib.mkOption { type = lib.types.str; default = "/var/lib/mrjam-identite/admission-client.secret"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [{ assertion = config.infrastructure.visionMultiutilisateur.enable && config.infrastructure.courriel.enable;
      message = "L'admission exige l'identité commune, les migrations/ACL et les courriels qualifiés."; }];
    users.groups.vision_admission = {};
    users.users.vision_admission = { isSystemUser = true; group = "vision_admission"; };
    systemd.services.mrjam-admission = {
      description = "Admission MrJ.am avec invitation et vérifications préalables";
      wantedBy = [ "multi-user.target" ]; after = [ "postgresql.service" "keycloak.service" ];
      environment = {
        MRJ_ADMISSION_DSN = "dbname=vision user=vision_admission host=/run/postgresql";
        MRJ_ADMISSION_ETAT = "/var/lib/mrjam-admission";
        MRJ_SMTP_SECRET = "/run/credentials/mrjam-admission.service/smtp";
        MRJ_ADMISSION_SECRET = "/run/credentials/mrjam-admission.service/client";
      };
      serviceConfig = {
        ExecStart = "${python}/bin/python3 ${source}/admission.py";
        User = "vision_admission"; Group = "vision_admission";
        StateDirectory = "mrjam-admission"; StateDirectoryMode = "0700";
        LoadCredential = [ "smtp:${config.infrastructure.courriel.secret}" "client:${cfg.secretClient}" ];
        Restart = "on-failure"; RestartSec = 5; UMask = "0077";
        NoNewPrivileges = true; PrivateTmp = true; PrivateDevices = true;
        ProtectSystem = "strict"; ProtectHome = true; ProtectKernelTunables = true;
        ProtectKernelModules = true; ProtectControlGroups = true;
        RestrictSUIDSGID = true; CapabilityBoundingSet = "";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
        MemoryMax = "192M"; TasksMax = 32;
      };
    };
    services.nginx.virtualHosts."vision.mrj.am".locations = {
      "= /auth/admission" = route;
      "= /auth/admission/apercu" = route;
      "= /auth/admission/confirmer" = route;
    };
  };
}
