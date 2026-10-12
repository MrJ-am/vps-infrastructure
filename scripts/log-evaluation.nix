{ configuration, paquet, documentVision, ressourcesMatheval, bankVersion, kanidm }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  paquetKanidm = import ../assemblage/kanidm/artefact.nix { inherit pkgs; artefact = kanidm; };
  commun = import ./monolithe-evaluation.nix {
    inherit configuration paquet documentVision ressourcesMatheval bankVersion;
  };
  base = commun.base;
  moduleLog = { lib, ... }: {
    imports = [ commun.moduleCandidate ];
    infrastructure.log = { enable = true; paquet = paquetKanidm; };
  };
  moduleAmorcage = { lib, ... }: {
    imports = [ commun.moduleCandidate ];
    # Conserver exactement le processus métier et ses ressources pendant la
    # préparation du nouvel IdP loopback. Aucun client n'utilise encore Kanidm.
    infrastructure.metier.paquet = lib.mkForce base.infrastructure.metier.paquet;
    infrastructure.metier.documentVision = lib.mkForce base.infrastructure.metier.documentVision;
    infrastructure.metier.ressourcesMatheval = lib.mkForce base.infrastructure.metier.ressourcesMatheval;
    services.kanidm.server.enable = lib.mkOverride 20 true;
    services.kanidm.package = lib.mkOverride 20 paquetKanidm;
    services.kanidm.server.settings.adminbindpath = "/run/kanidmd/admin.sock";
    services.kanidm.server.settings.online_backup.versions = lib.mkOverride 20 0;
    systemd.services.kanidm.enable = lib.mkOverride 20 true;
    systemd.services.kanidm.serviceConfig.AmbientCapabilities = lib.mkForce [];
  };
  eval = m: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = [ (builtins.toPath configuration) m ];
  }).config;
  c = eval moduleLog;
  a = eval moduleAmorcage;
  protege = cfg: {
    kernel = toString cfg.boot.kernelPackages.kernel;
    kernelParams = cfg.boot.kernelParams;
    reseau = lib.mapAttrs (_: f: toString f.source)
      (lib.filterAttrs (n: _: lib.hasPrefix "systemd/network" n) cfg.environment.etc);
    firewall = cfg.networking.firewall.allowedTCPPorts;
    ssh = cfg.users.users.root.openssh.authorizedKeys.keys;
    postgres = { package = toString cfg.services.postgresql.finalPackage;
      dataDir = cfg.services.postgresql.dataDir;
      settings = builtins.removeAttrs cfg.services.postgresql.settings [ "hba_file" "ident_file" ];
      databases = cfg.services.postgresql.ensureDatabases;
      backups = cfg.services.postgresqlBackup.databases; };
    units = lib.genAttrs [ "sshd" "vision-embeddings" "phpfpm-nextcloud" "redis-nextcloud"
      "nextcloud-setup" "nextcloud-cron" "nextcloud-backup" ] (n: cfg.systemd.units."${n}.service".text);
    domaines = builtins.attrNames cfg.services.nginx.virtualHosts;
  };
in {
  inherit moduleLog moduleAmorcage;
  rapport = {
    avant = toString base.system.build.toplevel;
    amorcage = toString a.system.build.toplevel;
    apres = toString c.system.build.toplevel;
    assertions = builtins.all (x: x.assertion) c.assertions && builtins.all (x: x.assertion) a.assertions;
    protegeAvant = protege base; protegeAmorcage = protege a; protegeApres = protege c;
    postgresAccesAvant = { authentication = base.services.postgresql.authentication; identMap = base.services.postgresql.identMap; };
    postgresAccesApres = { authentication = c.services.postgresql.authentication; identMap = c.services.postgresql.identMap; };
    inscriptionsOuvertes = base.infrastructure.identite.inscriptionsOuvertes;
    paquet = toString c.infrastructure.metier.paquet;
    nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
    kanidmConfig = c.systemd.services.kanidm.serviceConfig.ExecStart;
    backupRecipient = c.services.vision.backupRecipient;
  };
}
