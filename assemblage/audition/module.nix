{ site, paquetMetier, authentication, timers, units, moduleAudition ? ../../modules/audition.nix }:
{ config, lib, pkgs, ... }:
let
  # Le module PostgreSQL verrouillé change son preStart quand hba/ident changent.
  # Reprendre sa ligne exacte de sélection du fichier, sans initdb ni arrêt.
  liens = builtins.filter (l: lib.hasInfix "ln -sfn" l && lib.hasInfix "/postgresql.conf\"" l)
    (lib.splitString "\n" config.systemd.services.postgresql.preStart);
  recharger = pkgs.writeShellScript "mrjam-postgresql-recharger" ''
    set -eu
    ${builtins.head liens}
    ${pkgs.coreutils}/bin/kill -HUP "$1"
  '';
in {
  imports = [ moduleAudition ];
  infrastructure.audition = {
    enable = true;
    inherit site;
    paquet = paquetMetier;
    # Ce module est une entrée du promoteur central après ses préconditions.
    # Cette valeur seule ne constitue jamais une attestation de qualification.
    preconditions = true;
  };
  # La génération publiée force son ancienne liste peer. Ajouter cette seule
  # ligne en conservant intégralement les règles déjà installées.
  services.postgresql.authentication = lib.mkOverride 20
    (lib.optionalString (!(lib.hasInfix "local vision audition_app peer map=mrjam_metier" authentication))
      "local vision audition_app peer map=mrjam_metier\n" + authentication);
  assertions = [ { assertion = builtins.length liens == 1;
    message = "Rechargement PostgreSQL : sélection unique du fichier verrouillé requise."; } ];
  # Le promoteur exige que tous les paramètres hors hba/ident, le paquet et
  # l'unité hors preStart/ExecReload restent identiques. Ces seuls fichiers
  # sont rechargeables par SIGHUP ; ne jamais appliquer cette politique à une
  # mise à jour de paquet ou à une autre modification PostgreSQL.
  systemd.services.postgresql = {
    reloadIfChanged = lib.mkOverride 20 true;
    serviceConfig.ExecReload = lib.mkOverride 20 "${recharger} $MAINPID";
  };
  # Ajouter un certificat ne reprogramme pas les renouvellements existants.
  systemd.timers = lib.mapAttrs (_: t: {
    timerConfig.OnCalendar = lib.mkOverride 20 t.timerConfig.OnCalendar;
  }) (lib.filterAttrs (n: _: lib.hasPrefix "acme-renew-" n && n != "acme-renew-audition.mrj.am") timers);
  systemd.units = lib.mapAttrs (_: u: { text = lib.mkOverride 20 u.text; })
    (lib.filterAttrs (n: _: lib.hasPrefix "acme-renew-" n && lib.hasSuffix ".timer" n
      && n != "acme-renew-audition.mrj.am.timer") units);
}
