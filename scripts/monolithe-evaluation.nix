# Superposer uniquement l'assemblage aux déclarations réellement installées.
# Aucune reconstruction d'un ancien hosts/hostinger ni mise à jour Nixpkgs.
{ configuration, paquet, documentVision, ressourcesMatheval, bankVersion }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  modules = [ (builtins.toPath configuration) ];
  evaluationBase = import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; inherit modules;
  };
  base = evaluationBase.config;
  gateway = builtins.head evaluationBase.options.infrastructure.gateway.projects.declarations;
  postgres = builtins.head evaluationBase.options.infrastructure.postgresql.projects.declarations;
  matheval = builtins.head evaluationBase.options.services.matheval.enable.declarations;
  locaux = [ "gateway.nix" "mrj-auth.nix" "journal-http.nix" "identite.nix"
    "vision-gestion.nix" "courriel.nix" "vision-cycle.nix" "admission.nix"
    "fermeture.nix" "metier.nix" ];
  remplacerGateway = toString gateway != toString ../modules/gateway.nix;
  remplacerPostgres = toString postgres != toString ../modules/postgresql.nix;
  remplacerMatheval = toString matheval != toString ../modules/matheval.nix;
  moduleCandidate = { lib, ... }: {
    disabledModules = lib.optionals remplacerGateway
      (map (n: builtins.dirOf (toString gateway) + "/" + n) locaux)
      ++ lib.optional remplacerPostgres (toString postgres)
      ++ lib.optional remplacerMatheval (toString matheval);
    imports = lib.optional remplacerGateway ../modules/gateway.nix
      ++ lib.optional remplacerPostgres ../modules/postgresql.nix
      ++ lib.optional remplacerMatheval ../modules/matheval.nix;
    infrastructure.gateway.projects = lib.mkForce base.infrastructure.gateway.projects;
    infrastructure.postgresql.projects = lib.mkForce base.infrastructure.postgresql.projects;
    services.dbus.packages = lib.mkForce base.services.dbus.packages;
    infrastructure.metier = {
      enable = true;
      paquet = lib.mkForce (builtins.storePath paquet);
      documentVision = lib.mkForce documentVision;
      ressourcesMatheval = lib.mkForce ressourcesMatheval;
      bankVersion = lib.mkForce bankVersion;
    };
    # Les secrets, clients, SMTP, IdP et embeddings viennent des options actives.
    infrastructure.identite.preconditionsValidees = lib.mkForce true;
  };
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = modules ++ [ moduleCandidate ];
  }).config;
  invariant = cfg: {
    kernel = toString cfg.boot.kernelPackages.kernel;
    kernelParams = cfg.boot.kernelParams;
    grub = cfg.boot.loader.grub.device;
    networking = lib.mapAttrs (_: f: toString f.source)
      (lib.filterAttrs (n: _: lib.hasPrefix "systemd/network" n) cfg.environment.etc);
    firewall = cfg.networking.firewall.allowedTCPPorts;
    rootKeys = cfg.users.users.root.openssh.authorizedKeys.keys;
    postgres = {
      package = toString cfg.services.postgresql.finalPackage;
      dataDir = cfg.services.postgresql.dataDir;
      # Seuls ces deux chemins générés changent pour le peer du compte commun.
      # Leur contenu est contrôlé séparément, avec ajouts exacts et ancien ordre.
      settings = builtins.removeAttrs cfg.services.postgresql.settings [ "hba_file" "ident_file" ];
      databases = cfg.services.postgresql.ensureDatabases;
      backups = cfg.services.postgresqlBackup.databases;
    };
    domaines = builtins.filter (n: n != "mrjam-fermeture-interne")
      (builtins.attrNames cfg.services.nginx.virtualHosts);
    units = lib.genAttrs [ "sshd" "mrj-auth" "keycloak" "vision-embeddings"
      "phpfpm-nextcloud" "redis-nextcloud" "nextcloud-setup" "nextcloud-cron"
      "nextcloud-backup" ] (n: cfg.systemd.units."${n}.service".text);
  };
  rapport = {
    avant = toString base.system.build.toplevel;
    apres = toString c.system.build.toplevel;
    invariantAvant = invariant base;
    invariantApres = invariant c;
    assertions = builtins.all (a: a.assertion) c.assertions;
    postgres = toString c.services.postgresql.finalPackage;
    nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
    paquet = toString c.infrastructure.metier.paquet;
    backupRecipient = c.services.vision.backupRecipient;
    postgresAccesAvant = { authentication = base.services.postgresql.authentication;
      identMap = base.services.postgresql.identMap; };
    postgresAccesApres = { authentication = c.services.postgresql.authentication;
      identMap = c.services.postgresql.identMap; };
  };
in { inherit base c moduleCandidate rapport; }
