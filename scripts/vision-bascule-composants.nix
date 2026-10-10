# Construire les composants sur le socle actuel sans lever le garde d'activation.
{ configuration, source, fournisseur }:
let
  evaluation = import ./vision-bascule-evaluation.nix { inherit configuration source fournisseur; };
  inherit (evaluation) base lib pkgs gateway postgres anciennePasserelle ancienPostgres
    remplacerPasserelle remplacerPostgres c;
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
    source_vision_store = lib.hasPrefix "/nix/store/" (toString c.services.vision.bootstrapSource);
    preconditions_validees = false; garde_activation = true;
    generation_constructible = generation.success;
    hors_vision_identite_conserve = true; inscriptions = false; activation = false;
    modules_passerelle_actualises = remplacerPasserelle;
    module_postgresql_actualise = remplacerPostgres;
  };
}
