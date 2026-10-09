# Construire les unités et leurs dépendances sans lever l'assertion qui
# empêche une génération activable. Les credentials restent des chemins.
{ configuration ? ../hosts/hostinger/vision-semantique.nix, fournisseur ? null }:
let
  pkgs = import <nixpkgs> { system = "x86_64-linux"; };
  lib = pkgs.lib;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ configuration ({ lib, ... }: {
      infrastructure.identite.enable = true;
      infrastructure.visionMultiutilisateur.enable = true;
      infrastructure.courriel.enable = true;
      infrastructure.visionCycle.enable = true;
      infrastructure.admission.enable = true;
      infrastructure.fermeture.enable = true;
    }) ] ++ lib.optional (fournisseur != null) ({ lib, ... }: {
      services.visionEmbeddings.source = lib.mkForce (builtins.storePath fournisseur);
    });
  }).config;
  noms = [ "keycloak" "mrj-auth" "vision-gestion" "vision-cycle"
    "mrjam-admission" "mrjam-fermeture" "mrjam-courriel" ];
  refus = builtins.filter (a: !a.assertion) c.assertions;
  generation = builtins.tryEval (toString c.system.build.toplevel);
  paquets = builtins.filter (p: (p.pname or "") == "keycloak") c.environment.systemPackages;
  keycloak = builtins.head paquets;
  jdbc = c.services.keycloak.settings.db == "postgres" &&
    lib.hasInfix "socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory$FactoryArg" c.services.keycloak.settings.db-url &&
    lib.hasInfix "socketFactoryArg=/run/postgresql/.s.PGSQL.5432" c.services.keycloak.settings.db-url;
  sources = import ../services/sources-mrjam.nix { inherit pkgs; };
  unites = lib.genAttrs noms (nom: {
    chemin = toString c.systemd.units."${nom}.service".unit;
    utilisateur = c.systemd.services.${nom}.serviceConfig.User;
    executable = c.systemd.services.${nom}.serviceConfig.ExecStart;
  });
  lot = pkgs.linkFarm "vision-mrjam-composants" (
    (map (nom: { name = "unites/${nom}.service";
      path = c.systemd.units."${nom}.service".unit; }) noms) ++ [
      { name = "sources"; path = sources; }
      { name = "keycloak"; path = keycloak; }
    ]);
in
assert !c.infrastructure.identite.preconditionsValidees;
assert !c.infrastructure.identite.inscriptionsOuvertes;
assert builtins.length refus == 1;
assert (builtins.head refus).message == "Identité : fournir la preuve de migration/restauration avant activation.";
assert !generation.success;
assert builtins.length paquets == 1 && keycloak.version == "26.7.3";
assert !c.services.postgresql.enableTCPIP && c.services.postgresql.settings.listen_addresses == "";
assert c.services.keycloak.database.passwordFile == null;
assert jdbc;
assert c.systemd.services.mrj-auth.environment.MRJ_AUTH_MODE == "oidc";
assert c.services.nginx.virtualHosts."log.mrj.am".locations."/".return == "404";
{
  inherit lot;
  resume = {
    version = 1;
    lot = toString lot;
    inherit unites;
    keycloak = toString keycloak;
    keycloak_version = keycloak.version;
    jdbc_unix = jdbc;
    sources = toString sources;
    fournisseur_epingle = fournisseur != null;
    fournisseur_source = if fournisseur != null then toString c.services.visionEmbeddings.source else null;
    garde_activation = true;
    generation_constructible = generation.success;
    preconditions_validees = c.infrastructure.identite.preconditionsValidees;
    inscriptions = c.infrastructure.identite.inscriptionsOuvertes;
    postgres_tcp = c.services.postgresql.enableTCPIP;
    activation = false;
  };
}
