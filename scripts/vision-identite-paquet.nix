# Construction du paquet réellement configuré par le module NixOS, sans
# construire de génération ni déclarer les préconditions d'activation remplies.
{ configuration ? ../hosts/hostinger/configuration.nix }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ configuration ({ ... }: {
      infrastructure.identite.enable = true;
    }) ];
  }).config;
  # Le module amont expose son keycloakBuild, avec confFile et les plugins
  # systemd, dans environment.systemPackages. Ne pas réécrire sa recette.
  paquets = builtins.filter (p: (p.pname or "") == "keycloak") c.environment.systemPackages;
  paquet = builtins.head paquets;
  settings = lib.filterAttrs (_: v: v != null && v != {}) c.services.keycloak.settings;
  public = v: builtins.isString v || builtins.isInt v || builtins.isBool v;
in
assert builtins.length paquets == 1;
assert paquet.version == "26.7.3";
assert !c.infrastructure.identite.preconditionsValidees;
assert !c.infrastructure.identite.inscriptionsOuvertes;
assert !c.services.postgresql.enableTCPIP;
assert c.services.postgresql.settings.listen_addresses == "";
assert c.services.keycloak.database.passwordFile == null;
assert builtins.all public (builtins.attrValues settings);
assert !(settings ? db-password);
{
  inherit paquet;
  resume = {
    version = paquet.version;
    source = toString paquet.src;
    paquet = toString paquet;
    plugins = map toString paquet.enabledPlugins;
    jdbc_unix = settings.db == "postgres" &&
      lib.hasInfix "socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory$FactoryArg" settings.db-url &&
      lib.hasInfix "socketFactoryArg=/run/postgresql/.s.PGSQL.5432" settings.db-url;
    preconditions_validees = c.infrastructure.identite.preconditionsValidees;
    inscriptions = c.infrastructure.identite.inscriptionsOuvertes;
    activation = false;
  };
}
