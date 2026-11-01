{ site, paquetMetier, authentication, timers, units, moduleAudition ? ../../modules/audition.nix }:
{ lib, ... }: {
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
  # Ajouter un certificat ne reprogramme pas les renouvellements existants.
  systemd.timers = lib.mapAttrs (_: t: {
    timerConfig.OnCalendar = lib.mkOverride 20 t.timerConfig.OnCalendar;
  }) (lib.filterAttrs (n: _: lib.hasPrefix "acme-renew-" n && n != "acme-renew-audition.mrj.am") timers);
  systemd.units = lib.mapAttrs (_: u: { text = lib.mkOverride 20 u.text; })
    (lib.filterAttrs (n: _: lib.hasPrefix "acme-renew-" n && lib.hasSuffix ".timer" n
      && n != "acme-renew-audition.mrj.am.timer") units);
}
