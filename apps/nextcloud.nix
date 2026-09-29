{ config, pkgs, ... }:
let
  site = (builtins.fromJSON (builtins.readFile ../projects.json)).nextcloud;

  # Rétroport exact de la révision stable NixOS 26.05 utilisée en CI
  # (nixpkgs 4c7870105e7f1fdf9c48688c8d7efc21abf0688a).
  # Le module Nextcloud est identique à celui du Nixpkgs installé ; seule
  # la maintenance 34.0.3 -> 34.0.4 et son empreinte changent.
  nextcloud34 = pkgs.nextcloud34.overrideAttrs (_: {
    version = "34.0.4";
    src = pkgs.fetchurl {
      url = "https://download.nextcloud.com/server/releases/nextcloud-34.0.4.tar.bz2";
      hash = "sha256-APIm5jZPluCRirBhVxWPZmAbjO3CWvd39e5aMFb0K4M=";
    };
  });
in {
  assertions = [
    {
      assertion =
        site.type == "native" &&
        site.domain == "cloud.mrj.am" &&
        site.prefix == "" &&
        config.infrastructure.postgresql.projects.nextcloud.name == "nextcloud";
      message = "Changement du contrat Nextcloud : coordonner domaine et base avant activation.";
    }
  ];

  services.nextcloud = {
    enable = true;
    package = nextcloud34;
    hostName = site.domain;
    https = true;
    configureRedis = true;
    maxUploadSize = "2G";

    database.createLocally = false;
    config = {
      dbtype = "pgsql";
      dbhost = "/run/postgresql";
      dbname = "nextcloud";
      dbuser = "nextcloud";
      adminuser = null;
      adminpassFile = null;
    };

    settings = {
      default_phone_region = "FR";
      maintenance_window_start = 2;
      log_type = "systemd";
    };
  };

  # La base est gérée par le module PostgreSQL partagé, donc ces dépendances
  # doivent être explicites.
  systemd.services.nextcloud-setup = {
    after = [ "postgresql.service" "postgresql-setup.service" ];
    requires = [ "postgresql.service" "postgresql-setup.service" ];
  };
}
