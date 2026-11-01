# Shared service composition for the first deployment, without ViSe.
# Import alongside the machine and application declarations, never alone as a VPS.
{ config, lib, pkgs, ... }:
let
  locked = import ../../forgejo/locked-toolchain.nix { system = pkgs.stdenv.hostPlatform.system; };
  packages = import ./preserved-packages.nix { system = pkgs.stdenv.hostPlatform.system; };
  preparation = config.services.mrjamForgejo.preparation;
  tls = domain: {
    forceSSL = true;
    enableACME = false;
    sslCertificate = "/var/lib/acme/${domain}/fullchain.pem";
    sslCertificateKey = "/var/lib/acme/${domain}/key.pem";
  };
in {
  imports = [
    ../../nixos/mrjam-forgejo-host.nix
    ../../nixos/mrjam-kanidm-host.nix
    ../../nixos/mrjam-nextcloud-host.nix
    ./observed-service-identities.nix
  ];

  services.mrjamForgejoHost = {
    enable = true;
    artifactStorePath = builtins.unsafeDiscardStringContext "${locked.forgejo}";
  };
  services.mrjamKanidmHost = {
    enable = true;
    artifactStorePath = builtins.unsafeDiscardStringContext "${packages.kanidm}";
  };
  services.mrjamNextcloudHost.enable = true;
  # Service arguments stay context-free; the system closure nevertheless retains
  # the exact selected executables. Builds take place in the workshop, not at switch.
  system.extraDependencies = [ locked.forgejo packages.kanidm ];

  users.users.postgres.uid = 71;
  users.groups.postgres.gid = 71;
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_17;
    extensions = ps: [ ps.pgvector ];
    dataDir = "/var/lib/postgresql/17";
    enableTCPIP = false;
    settings = {
      listen_addresses = lib.mkForce "";
      unix_socket_directories = "/run/postgresql";
    };
    # Dedicated module rules precede this terminal policy. The upstream defaults
    # remain unreachable; no undeclared role acquires access through local peer.
    authentication = ''
      local all postgres peer
      local all all reject
      host all all 0.0.0.0/0 reject
      host all all ::0/0 reject
    '';
    ensureDatabases = [ ];
    ensureUsers = [ ];
  };
  systemd.services.postgresql = {
    restartIfChanged = false;
    stopIfChanged = false;
    # Refuse an absent/wrong cluster before the upstream initdb branch. Existing
    # PG_VERSION contains only the public on-disk format version, never SQL data.
    preStart = lib.mkBefore ''
      test -d /var/lib/postgresql/17
      test ! -L /var/lib/postgresql/17
      test -s /var/lib/postgresql/17/PG_VERSION
      test ! -L /var/lib/postgresql/17/PG_VERSION
      test "$(cat /var/lib/postgresql/17/PG_VERSION)" = 17
    '';
  };

  services.nginx = {
    enable = true;
    serverTokens = false;
    logError = "/dev/null crit";
    appendHttpConfig = lib.mkAfter ''
      server {
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        return 421;
      }
      server {
        listen 443 ssl default_server;
        listen [::]:443 ssl default_server;
        server_name _;
        ssl_reject_handshake on;
        return 421;
      }
    '';
    virtualHosts."forge.mrj.am" = (tls "forge.mrj.am") // {
      locations."/" = {
        proxyPass = "http://127.0.0.1:3004";
        proxyWebsockets = true;
        extraConfig = ''
          client_max_body_size 256m;
          proxy_read_timeout 300s;
        '';
      };
      locations."^~ /assets/forgejo-org/" = {
        alias = "${preparation}/share/forgejo-org/";
        extraConfig = "expires 1h;";
      };
      extraConfig = ''
        access_log off;
        error_log /dev/null crit;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy same-origin always;
        add_header X-Frame-Options SAMEORIGIN always;
      '';
    };
    # The final application gateway supplies Log's Elm/UI routes. Identity API
    # traffic keeps its own TLS upstream and must not be sent to an HTTP backend.
    virtualHosts."log.mrj.am" = (tls "log.mrj.am") // {
      locations."/" = {
        proxyPass = lib.mkDefault "https://127.0.0.1:8443";
        extraConfig = ''
          client_max_body_size 64k;
          proxy_set_header Host log.mrj.am;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_set_header Connection "";
          proxy_ssl_server_name on;
          proxy_ssl_name log.mrj.am;
          proxy_ssl_verify on;
          proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
          proxy_ssl_verify_depth 3;
        '';
      };
      # Preserve the existing public boundary around identity administration.
      locations."^~ /v1/raw/".return = "404";
      locations."^~ /v1/oauth2/".return = "404";
      locations."^~ /v1/service_account/".return = "404";
      locations."^~ /scim/".return = "404";
      locations."^~ /realms/".return = "410";
      extraConfig = ''
        access_log off;
        error_log /dev/null crit;
        add_header X-Content-Type-Options nosniff always;
      '';
    };
  };
  systemd.services.nginx = { restartIfChanged = false; stopIfChanged = false; };
  networking.firewall.allowedTCPPorts = [ 80 443 2222 ];

  assertions = [
    { assertion = lib.versions.major config.services.postgresql.package.version == "17"
        && config.services.postgresql.dataDir == "/var/lib/postgresql/17";
      message = "mrjamCoreServices: PostgreSQL major and existing cluster directory must be preserved."; }
    { assertion = config.services.postgresql.ensureDatabases == [ ]
        && config.services.postgresql.ensureUsers == [ ]
        && config.services.postgresql.initialScript == null;
      message = "mrjamCoreServices: SQL bootstrap/migrations must remain explicit operations, not startup actions."; }
    { assertion = !(config.services.mrjamVise.enable or false);
      message = "mrjamCoreServices: the first-deployment composition excludes optional ViSe."; }
  ];
}
