# New Rust proxy only; no historical gateway import, certificate creation or data access.
{ config, lib, ... }:
let
  cfg = config.services.mrjamGateway;
  domainType = lib.types.strMatching "[a-z0-9]([a-z0-9.-]*[a-z0-9])?";
  siteType = lib.types.submodule {
    options = {
      certificateName = lib.mkOption {
        type = domainType;
        description = "Existing certificate directory under /var/lib/acme; no key is read at evaluation.";
      };
      authenticationBridge = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Preserve /auth/ routes on the separately qualified existing mrj-auth service.";
      };
      mcpOAuthBridge = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Preserve only the exact OAuth discovery and MCP authorization endpoints of mrj-auth.";
      };
      maximumBodySize = lib.mkOption {
        type = lib.types.enum [ "64k" "128k" "1m" "5m" ];
        default = "64k";
      };
    };
  };
  port = config.services.mrjamRust.slots.${cfg.activeSlot}.port;
  forwardedHeaders = domain: ''
    proxy_http_version 1.1;
    proxy_set_header Host ${domain};
    proxy_set_header X-Forwarded-Host ${domain};
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Origin $http_origin;
    proxy_set_header X-CSRF-Token $http_x_csrf_token;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Mrj-User "";
    proxy_set_header X-User-Id "";
    proxy_set_header X-Authenticated-User "";
    proxy_set_header X-Forwarded-User "";
    proxy_set_header X-Vision-Authenticated "";
    proxy_set_header X-Vision-Browser "";
    proxy_set_header X-Original-Method "";
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_connect_timeout 5s;
  '';
  safeDomain = domain: builtins.match "[a-z0-9]([a-z0-9.-]*[a-z0-9])?" domain != null
    && lib.all (part: part != "" && builtins.stringLength part <= 63
      && !(lib.hasPrefix "-" part) && !(lib.hasSuffix "-" part)) (lib.splitString "." domain)
    && builtins.stringLength domain <= 253;
in {
  imports = [ ./mrjam-rust.nix ];
  options.services.mrjamGateway = {
    enable = lib.mkEnableOption "qualified Rust gateway, preserving the existing TLS material";
    activeSlot = lib.mkOption { type = lib.types.enum [ "blue" "green" ]; default = "blue"; };
    sites = lib.mkOption { type = lib.types.attrsOf siteType; default = { }; };
    authenticationPort = lib.mkOption { type = lib.types.port; default = 3002; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.nginx.enable;
        message = "mrjamGateway requires the existing Nginx service; it never enables it implicitly."; }
      { assertion = config.services.mrjamRust.enable && config.services.mrjamRust.slots.${cfg.activeSlot}.enable;
        message = "mrjamGateway requires the selected declared Rust slot."; }
      { assertion = cfg.sites != { } && builtins.length (builtins.attrNames cfg.sites) <= 8;
        message = "mrjamGateway requires a bounded explicit public host registry."; }
      { assertion = lib.all safeDomain (builtins.attrNames cfg.sites)
          && lib.all (site: safeDomain site.certificateName) (builtins.attrValues cfg.sites);
        message = "mrjamGateway refuses invalid host or certificate names."; }
      { assertion = cfg.authenticationPort != port;
        message = "mrjamGateway identity bridge must be separate from the application."; }
      { assertion = lib.all (site: !site.mcpOAuthBridge || site.authenticationBridge) (builtins.attrValues cfg.sites);
        message = "mrjamGateway OAuth MCP discovery requires the declared identity bridge."; }
    ];
    services.nginx.virtualHosts = lib.mapAttrs (domain: site: {
      forceSSL = true;
      enableACME = false;
      sslCertificate = "/var/lib/acme/${site.certificateName}/fullchain.pem";
      sslCertificateKey = "/var/lib/acme/${site.certificateName}/key.pem";
      extraConfig = ''
        if ($host != ${domain}) { return 421; }
        access_log off;
        error_log /dev/null crit;
        client_max_body_size ${site.maximumBodySize};
        add_header X-Content-Type-Options nosniff always;
      '';
      locations = {
        "= /healthz".return = "404";
        "= /readyz".return = "404";
        "/" = {
          proxyPass = "http://127.0.0.1:${toString port}";
          extraConfig = forwardedHeaders domain;
        };
      } // lib.optionalAttrs site.authenticationBridge {
        "/auth/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.authenticationPort}";
          extraConfig = forwardedHeaders domain + ''
            client_max_body_size 8k;
          '';
        };
      } // lib.optionalAttrs site.mcpOAuthBridge (lib.genAttrs [
        "= /.well-known/oauth-authorization-server"
        "= /.well-known/oauth-protected-resource"
        "= /.well-known/oauth-protected-resource/mcp"
        "= /oauth/authorize"
        "= /oauth/token"
        "= /oauth/register"
      ] (_: {
        proxyPass = "http://127.0.0.1:${toString cfg.authenticationPort}";
        extraConfig = forwardedHeaders domain + ''
          client_max_body_size 64k;
        '';
      }));
    }) cfg.sites;
  };
}
