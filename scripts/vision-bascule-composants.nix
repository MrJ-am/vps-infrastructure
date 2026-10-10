# Construire les composants sur le socle actuel sans lever le garde d'activation.
{ configuration, source, fournisseur }:
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
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = modules ++ [ ({ lib, ... }: {
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
      infrastructure.identite.preconditionsValidees = lib.mkForce false;
      infrastructure.identite.inscriptionsOuvertes = lib.mkForce false;
      infrastructure.visionMultiutilisateur.enable = true;
      infrastructure.courriel.enable = true;
      infrastructure.visionCycle.enable = true;
      infrastructure.admission.enable = true;
      infrastructure.fermeture.enable = true;
      services.vision.bootstrapSource = lib.mkForce (builtins.toPath source);
      services.vision.bootstrapCommit = lib.mkForce "a9c51acac81510d7dc896f5daf4e6fb28a36b979";
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
    }) ];
  }).config;
  noms = [ "keycloak" "mrj-auth" "vision" "vision-bootstrap" "vision-migrate"
    "vision-gestion" "vision-cycle" "mrjam-admission" "mrjam-fermeture" "mrjam-courriel" ];
  unites = lib.genAttrs noms (nom: toString c.systemd.units."${nom}.service".unit);
  lot = pkgs.linkFarm "vision-bascule-composants" (map (nom: {
    name = "${nom}.service"; path = c.systemd.units."${nom}.service".unit;
  }) noms);
  refus = builtins.filter (a: !a.assertion) c.assertions;
  generation = builtins.tryEval (toString c.system.build.toplevel);
  # Les options sans valeur (certificats ACME) ne doivent pas être forcées.
  normaliser = valeur: let essai = builtins.tryEval valeur;
    in if !essai.success then "__option_sans_valeur__"
    else if builtins.isAttrs valeur then lib.mapAttrs (_: normaliser) valeur
    else if builtins.isList valeur then map normaliser valeur else valeur;
  hote = cfg: normaliser (builtins.removeAttrs cfg.services.nginx.virtualHosts [ "log.mrj.am" "vision.mrj.am" ]);
in
assert builtins.length gateway == 1 && builtins.length postgres == 1;
assert lib.hasSuffix "/gateway.nix" anciennePasserelle;
assert lib.hasSuffix "/postgresql.nix" ancienPostgres;
assert builtins.length refus == 1 && (builtins.head refus).message == "Identité : fournir la preuve de migration/restauration avant activation.";
assert !generation.success;
assert builtins.toJSON (hote base) == builtins.toJSON (hote c);
assert base.networking.firewall.allowedTCPPorts == c.networking.firewall.allowedTCPPorts;
assert base.services.postgresql.dataDir == c.services.postgresql.dataDir;
assert toString base.services.postgresql.finalPackage == toString c.services.postgresql.finalPackage;
assert !c.services.postgresql.enableTCPIP && c.services.postgresql.settings.listen_addresses == "";
assert c.services.keycloak.database.host == "/run/postgresql";
assert c.systemd.services.mrj-auth.environment.MRJ_AUTH_MODE == "oidc";
{
  inherit lot;
  resume = {
    version = 1; systeme_actif = toString base.system.build.toplevel;
    lot = toString lot; inherit unites;
    postgres_paquet = toString c.services.postgresql.finalPackage;
    fournisseur_source = toString c.services.visionEmbeddings.source;
    preconditions_validees = false; garde_activation = true;
    generation_constructible = generation.success;
    hors_vision_identite_conserve = true; inscriptions = false; activation = false;
    modules_passerelle_actualises = remplacerPasserelle;
    module_postgresql_actualise = remplacerPostgres;
  };
}
