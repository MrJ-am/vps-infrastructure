{ config, lib, ... }:
{
  # Le POST natif exige une origine réelle. « no-referrer » la transforme en
  # « null » dans le navigateur. Ne transmettre que l'origine HTTPS, jamais
  # le chemin ou les paramètres d'un lien d'enrôlement/récupération.
  config = lib.mkIf config.infrastructure.log.enable {
    services.nginx.virtualHosts."log.mrj.am" = {
      # Priorité explicite pour superposer aussi cette correction à une
      # génération Native déjà qualifiée, sans remplacer ses autres modules.
      extraConfig = lib.mkOverride 40 ''
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header Referrer-Policy "strict-origin" always;
        access_log off;
        error_log /dev/null emerg;
      '';
      locations = lib.mkForce {
        "/".extraConfig = lib.mkAfter ''
          proxy_hide_header Referrer-Policy;
        '';
      };
    };
  };
}
