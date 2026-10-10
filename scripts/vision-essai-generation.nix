# Construction uniquement ; le programme opérateur vérifie les preuves avant cet appel.
{ configuration, source, fournisseur, sourceInterface }:
let
  e = import ./vision-bascule-evaluation.nix {
    inherit configuration source fournisseur sourceInterface; preconditionsValidees = true;
  };
  inherit (e) base c lib;
  normaliser = valeur: let essai = builtins.tryEval valeur;
    in if !essai.success then "__option_sans_valeur__"
    else if builtins.isAttrs valeur then lib.mapAttrs (_: normaliser) valeur
    else if builtins.isList valeur then map normaliser valeur else valeur;
  hote = cfg: normaliser (builtins.removeAttrs cfg.services.nginx.virtualHosts [ "log.mrj.am" "vision.mrj.am" ]);
  reseau = cfg: normaliser {
    inherit (cfg.networking) firewall interfaces useDHCP useNetworkd hostName nameservers
      defaultGateway defaultGateway6;
    systemd = cfg.systemd.network.networks;
    ssh = { inherit (cfg.services.openssh) enable ports settings openFirewall listenAddresses hostKeys; };
    cles = cfg.users.users.root.openssh.authorizedKeys.keys;
  };
  essentiels = [ "sshd" "matheval" "vision-embeddings" "postgresqlBackup-matheval" ];
  bootstrap = builtins.head (lib.splitString "/app/."
    (builtins.elemAt (lib.splitString "cp -R " c.systemd.services.vision-bootstrap.script) 1));
in
assert builtins.length e.gateway == 1 && builtins.length e.postgres == 1;
assert builtins.all (a: a.assertion) c.assertions;
assert builtins.toJSON (hote base) == builtins.toJSON (hote c);
assert builtins.all (n: toString base.systemd.units."${n}.service".unit == toString c.systemd.units."${n}.service".unit) essentiels;
assert builtins.toJSON (reseau base) == builtins.toJSON (reseau c);
assert base.services.postgresql.dataDir == c.services.postgresql.dataDir;
assert toString base.services.postgresql.finalPackage == toString c.services.postgresql.finalPackage;
assert !c.services.postgresql.enableTCPIP && c.services.postgresql.settings.listen_addresses == "";
assert c.services.keycloak.database.host == "/run/postgresql";
assert c.systemd.services.mrj-auth.environment.MRJ_AUTH_MODE == "oidc";
assert !c.infrastructure.identite.inscriptionsOuvertes;
{
  systeme = c.system.build.toplevel;
  resume = {
    version = 1;
    systeme_actif = toString base.system.build.toplevel;
    systeme_candidat = toString c.system.build.toplevel;
    postgres_paquet = toString c.services.postgresql.finalPackage;
    fournisseur_source = toString c.services.visionEmbeddings.source;
    backend_paquet = bootstrap;
    interface_store = c.systemd.services.vision.environment.VISION_DOCUMENT_ROOT;
    recipient_age = c.services.vision.backupRecipient;
    hors_vision_identite_conserve = true;
    preconditions_validees = true;
    inscriptions = false;
    activation = false;
    nginx_paquet = toString c.services.nginx.package;
    nginx_commande = c.systemd.services.nginx.serviceConfig.ExecStart;
    nginx_uid = c.users.users.nginx.uid;
    nginx_gid = c.users.groups.nginx.gid;
    nginx_confinement = builtins.intersectAttrs {
      User = null; Group = null; AmbientCapabilities = null;
      CapabilityBoundingSet = null; NoNewPrivileges = null;
    } c.systemd.services.nginx.serviceConfig;
  };
}
