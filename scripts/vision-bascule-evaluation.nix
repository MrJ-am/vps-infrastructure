# Même assemblage pour qualification fermée et essai explicitement préparé.
{ configuration, source, fournisseur, preconditionsValidees ? false, sourceInterface ? null }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  modules = [ (builtins.toPath configuration) ];
  evaluationBase = import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; inherit modules;
  };
  base = evaluationBase.config;
  # Les modules de l'entrée enregistrée appartiennent à une ancienne copie.
  # Remplacer leurs déclarations, sans redéclarer les mêmes options deux fois.
  gateway = evaluationBase.options.infrastructure.gateway.projects.declarations;
  postgres = evaluationBase.options.infrastructure.postgresql.projects.declarations;
  passerelleActuelle = toString ../modules/gateway.nix;
  postgresActuel = toString ../modules/postgresql.nix;
  anciennePasserelle = toString (builtins.head gateway);
  ancienPostgres = toString (builtins.head postgres);
  remplacerPasserelle = anciennePasserelle != passerelleActuelle;
  remplacerPostgres = ancienPostgres != postgresActuel;
  locaux = [ "gateway.nix" "mrj-auth.nix" "journal-http.nix" "identite.nix"
    "vision-gestion.nix" "courriel.nix" "vision-cycle.nix" "admission.nix" "fermeture.nix" ];
  # toPath garde une chaîne absolue hors store : le constructeur ne voit pas
  # le dossier root privé. Copier uniquement l'archive publique déjà vérifiée.
  sourceVision = builtins.path {
    path = source; name = "vision-source-a9c51acac81510d7dc896f5daf4e6fb28a36b979";
  };
  interfaceStore = if sourceInterface == null then "" else builtins.path {
    path = sourceInterface; name = "vision-interface-a9c51acac81510d7dc896f5daf4e6fb28a36b979";
  };
  moduleCandidate = { lib, ... }: {
      disabledModules = lib.optionals remplacerPasserelle
        (map (nom: builtins.dirOf anciennePasserelle + "/" + nom) locaux)
        ++ lib.optional remplacerPostgres ancienPostgres;
      imports = lib.optional remplacerPasserelle ../modules/gateway.nix
        ++ lib.optional remplacerPostgres ../modules/postgresql.nix;
      # Les registres effectifs du VPS sont conservés, pas leurs défauts récents.
      infrastructure.gateway.projects = lib.mkForce base.infrastructure.gateway.projects;
      infrastructure.postgresql.projects = lib.mkForce base.infrastructure.postgresql.projects;
      infrastructure.amorcageIdentite.enable = lib.mkForce false;
      infrastructure.identite.enable = true;
      infrastructure.identite.preconditionsValidees = lib.mkForce preconditionsValidees;
      infrastructure.identite.inscriptionsOuvertes = lib.mkForce false;
      infrastructure.visionMultiutilisateur.enable = true;
      infrastructure.courriel.enable = true;
      infrastructure.visionCycle.enable = true;
      infrastructure.admission.enable = true;
      infrastructure.fermeture.enable = true;
      services.vision.bootstrapSource = lib.mkForce sourceVision;
      services.vision.bootstrapCommit = lib.mkForce "a9c51acac81510d7dc896f5daf4e6fb28a36b979";
      services.vision.backupRecipient = lib.mkIf preconditionsValidees (lib.mkForce "age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc");
      assertions = lib.optional preconditionsValidees {
        assertion = sourceInterface != null;
        message = "Essai Vision : artefact d’interface exact requis.";
      };
      systemd.services.vision.environment.VISION_DOCUMENT_ROOT =
        lib.mkIf preconditionsValidees (lib.mkForce (toString interfaceStore));
      services.nginx.virtualHosts."vision.mrj.am".locations = lib.mkIf preconditionsValidees
        (lib.genAttrs [ "= /" "= /app.js" "= /app.css" "= /interface-manifest.json" "^~ /assets/mrjam/" ]
          (_: { root = lib.mkForce (toString interfaceStore); }));
      services.visionEmbeddings.source = lib.mkForce (builtins.storePath fournisseur);
      # Conserver les protections déjà actives de l'hôte d'identité.
      services.nginx.virtualHosts."log.mrj.am" = {
        extraConfig = lib.mkForce base.services.nginx.virtualHosts."log.mrj.am".extraConfig;
        locations = {
          "= /realms/mrjam/clients-registrations".return = "404";
          "/realms/mrjam/clients-registrations/".return = "404";
          "/realms/mrjam/".extraConfig = lib.mkForce base.services.nginx.virtualHosts."log.mrj.am".locations."/realms/mrjam/".extraConfig;
          "/resources/".extraConfig = lib.mkForce base.services.nginx.virtualHosts."log.mrj.am".locations."/resources/".extraConfig;
        };
      };
  };
  configurationCandidate = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = modules ++ [ moduleCandidate ];
  }).config;
in { inherit base lib pkgs gateway postgres anciennePasserelle ancienPostgres
  remplacerPasserelle remplacerPostgres moduleCandidate; c = configurationCandidate; }
