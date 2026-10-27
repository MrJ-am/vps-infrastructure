# Additive hosting adapter. ViSe is outside the shared application/SSO graph.
{ config, lib, pkgs, ... }:
let
  target = builtins.fromJSON (builtins.readFile ./target.json);
  release = "/var/lib/vise/releases/${target.sha256}";
  pg = config.services.postgresql.finalPackage;
  baseline = (import <nixpkgs/nixos/lib/eval-config.nix> {
    modules = [ (builtins.toPath target.baselineConfiguration) ];
  }).config;
in {
  # Keep existing HBA rules exact; add only this peer-authenticated database.
  services.postgresql.authentication = lib.mkOverride 40
    ("local etp_carnet etp_carnet peer\n" + baseline.services.postgresql.authentication);
  users.groups.etp_carnet = {};
  users.users.etp_carnet = { isSystemUser = true; group = "etp_carnet"; };
  # No modification to shared registry, existing DB owners, or backup selection.
  systemd.services.vise-provision = {
    after = [ "postgresql.service" ]; requires = [ "postgresql.service" ];
    path = [ pg ];
    serviceConfig = { Type = "oneshot"; User = "postgres"; RemainAfterExit = true; };
    script = builtins.readFile ./provision.sh;
  };
  systemd.services.vise = {
    description = "ViSe — independent encrypted ETP notebook";
    wantedBy = [ "multi-user.target" ];
    after = [ "postgresql.service" "vise-provision.service" ];
    requires = [ "postgresql.service" "vise-provision.service" ];
    environment = {
      CARNET_BIND = "127.0.0.1:3017";
      CARNET_DIST = "${release}/dist";
      CARNET_DB_HOST = "/run/postgresql";
      CARNET_DB_NAME = "etp_carnet";
      CARNET_DB_USER = "etp_carnet";
      CARNET_DB_PASSWORD = ""; # Unix peer authentication, no stored password.
      CARNET_PUBLIC_URL = "https://vise.mrj.am";
      CARNET_SECURE_COOKIE = "true";
      CARNET_DELETION_LEDGER = "/var/lib/etp-carnet/deletions.log";
    };
    serviceConfig = {
      ExecStart = "${release}/server";
      User = "etp_carnet"; Group = "etp_carnet";
      StateDirectory = "etp-carnet"; StateDirectoryMode = "0700";
      UMask = "0077"; NoNewPrivileges = true; PrivateTmp = true;
      ProtectSystem = "strict"; ProtectHome = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      Restart = "on-failure"; MemoryMax = "512M";
    };
  };
  services.nginx.virtualHosts."vise.mrj.am" = {
    forceSSL = true; enableACME = true;
    extraConfig = "client_max_body_size 4000000; client_body_timeout 15s; access_log off;";
    locations."/" = {
      proxyPass = "http://127.0.0.1:3017";
      extraConfig = "proxy_connect_timeout 5s; proxy_read_timeout 20s; proxy_send_timeout 20s;";
    };
  };
  systemd.services.vise-backup = {
    description = "Encrypted ViSe SQL and deletion ledger backup";
    path = [ pg pkgs.age pkgs.util-linux pkgs.gnutar pkgs.coreutils ];
    environment.VISE_BACKUP_RECIPIENT = target.backupRecipient;
    serviceConfig = { Type = "oneshot"; UMask = "0077"; };
    script = builtins.readFile ./backup.sh;
  };
  systemd.timers.vise-backup = {
    wantedBy = [ "timers.target" ];
    timerConfig = { OnCalendar = "daily"; Persistent = true; };
  };
}
