# Construire une phase d'identité indépendante sur la configuration active.
{ configuration, fournisseur ? null }:
let
  lib = import <nixpkgs/lib>;
  pkgs = import <nixpkgs> {};
  modules = [ (builtins.toPath configuration) ] ++
    lib.optional (fournisseur != null) ({ lib, ... }: {
      services.visionEmbeddings.source = lib.mkForce (builtins.storePath fournisseur);
    });
  evaluer = additions: (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux"; modules = modules ++ additions;
  }).config;
  base = evaluer [];
  c = evaluer [ ../modules/identite-amorcage.nix {
    infrastructure.amorcageIdentite.enable = true;
  } ];
  essentiels = [ "sshd" "postgresql" "vision" "matheval" "mrj-auth" ];
  unites = configuration: lib.genAttrs essentiels
    (nom: toString configuration.systemd.units."${nom}.service".unit);
  # Certaines options Nginx sans défaut (certificat fourni par ACME) restent
  # présentes mais sans valeur. Comparer chaque valeur définie, sans forcer
  # celles que le générateur Nginx n'utilise pas.
  normaliser = valeur:
    let tentative = builtins.tryEval valeur;
    in if !tentative.success then "__option_sans_valeur__"
    else if builtins.isAttrs valeur then lib.mapAttrs (_: normaliser) valeur
    else if builtins.isList valeur then map normaliser valeur
    else valeur;
  hote = configuration: normaliser (builtins.removeAttrs configuration.services.nginx.virtualHosts [ "log.mrj.am" ]);
  pg = configuration: with configuration.services.postgresql; {
    paquet = toString finalPackage; inherit authentication identMap ensureDatabases ensureUsers;
    tcp = enableTCPIP; ecoute = settings.listen_addresses; repertoire = dataDir;
  };
  keycloak = import ../lib/keycloak-optimise.nix { pkgs = import <nixpkgs> {}; };
  executables = lib.splitString " " c.systemd.services.mrjam-amorcage-identite.serviceConfig.ExecStart;
  lot = (import <nixpkgs> {}).linkFarm "mrjam-amorcage-composants" [
    { name = "identite"; path = c.systemd.units."mrjam-amorcage-identite.service".unit; }
    { name = "cluster"; path = c.systemd.units."mrjam-amorcage-postgresql.service".unit; }
    { name = "sauvegarde"; path = c.systemd.units."mrjam-amorcage-sauvegarde.service".unit; }
  ];
  ordinaireFerme = configuration:
    !(configuration.infrastructure.identite.enable or false) &&
    !(configuration.infrastructure.identite.preconditionsValidees or false) &&
    !(configuration.infrastructure.identite.inscriptionsOuvertes or false) &&
    !(configuration.infrastructure.visionMultiutilisateur.enable or false) &&
    !(configuration.infrastructure.admission.enable or false) &&
    !(configuration.infrastructure.fermeture.enable or false);
in
assert ordinaireFerme base && ordinaireFerme c;
assert !(base.services.keycloak.enable or false);
assert !(base.services.nginx.virtualHosts ? "log.mrj.am");
assert (unites base) == (unites c);
assert builtins.toJSON (hote base) == builtins.toJSON (hote c);
assert (pg base) == (pg c);
assert base.networking.firewall.allowedTCPPorts == c.networking.firewall.allowedTCPPorts;
assert !c.services.postgresql.enableTCPIP && c.services.postgresql.settings.listen_addresses == "";
assert !(c.services.keycloak.enable or false);
assert c.systemd.services.mrjam-amorcage-identite.serviceConfig.DynamicUser;
assert c.systemd.services.mrjam-amorcage-postgresql.serviceConfig.RestrictAddressFamilies == [ "AF_UNIX" ];
assert c.services.nginx.virtualHosts."log.mrj.am".locations."/".return == "404";
assert c.services.nginx.virtualHosts."log.mrj.am".locations."/realms/mrjam/clients-registrations/".return == "404";
assert lib.hasInfix "proxy_set_header X-Forwarded-Port 443;" c.services.nginx.virtualHosts."log.mrj.am".locations."/realms/mrjam/".extraConfig;
assert keycloak.version == "26.7.3";
{
  generation = c.system.build.toplevel;
  composants = lot;
  resume = {
    version = 1; systeme_actif = toString base.system.build.toplevel;
    systeme_amorcage = toString c.system.build.toplevel;
    paquet = toString keycloak; keycloak_version = keycloak.version;
    postgres_paquet = toString c.services.postgresql.finalPackage;
    nginx_paquet = toString c.services.nginx.package;
    nginx_commande = c.systemd.services.nginx.serviceConfig.ExecStart;
    nginx_confinement = lib.getAttrs [ "User" "Group" "AmbientCapabilities"
      "CapabilityBoundingSet" "NoNewPrivileges" ] c.systemd.services.nginx.serviceConfig;
    nginx_uid = c.users.users.nginx.uid;
    nginx_gid = c.users.groups.nginx.gid;
    runuser_paquet = toString (lib.getBin pkgs.util-linux);
    age_paquet = toString (lib.getBin pkgs.age);
    tar_paquet = toString (lib.getBin pkgs.gnutar);
    fournisseur_source = if fournisseur == null then null else toString c.services.visionEmbeddings.source;
    unites_essentielles = unites c;
    unite_identite = toString c.systemd.units."mrjam-amorcage-identite.service".unit;
    unite_cluster = toString c.systemd.units."mrjam-amorcage-postgresql.service".unit;
    themes = builtins.elemAt executables 5;
    lanceur_identite = builtins.elemAt executables 1;
    lanceur_cluster = "${../scripts/identite-amorcage-postgresql.sh}";
    unites_conservees = true; hotes_conserves = true; postgres_production_conserve = true;
    parefeu_conserve = true; cluster_independant = true; postgres_tcp = false;
    inscriptions = false; mode_vision_oidc = false; preconditions_validees = false;
    activation = false; identite_humaine = false;
  };
}
