{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../nixos/mrjam-gateway.nix { system.stateVersion = "26.05"; } extra ];
  }).config;
  fixture = {
    services.nginx.enable = true;
    services.mrjamRust = {
      enable = true;
      slots.blue = {
        enable = true;
        artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-server";
        runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-config";
      };
    };
    services.mrjamGateway = {
      enable = true;
      sites = {
        "vision.synthetic.invalid" = { certificateName = "synthetic.invalid"; authenticationBridge = true; mcpOAuthBridge = true; };
        "mateval.synthetic.invalid" = { certificateName = "synthetic.invalid"; maximumBodySize = "5m"; };
      };
    };
  };
  enabled = evaluate fixture;
  disabled = evaluate { };
  host = enabled.services.nginx.virtualHosts."vision.synthetic.invalid";
  mateval = enabled.services.nginx.virtualHosts."mateval.synthetic.invalid";
  headers = host.locations."/".extraConfig;
  valid = cfg: builtins.all (entry: entry.assertion || !(lib.hasPrefix "mrjamGateway" entry.message)) cfg.assertions;
  results = {
    disabledKeepsNginxOff = !disabled.services.nginx.enable;
    disabledCreatesNoRustUnits = !(disabled.systemd.services ? mrjam-rust-blue);
    fixtureValid = valid enabled;
    preservedCertificateReferences = host.sslCertificate == "/var/lib/acme/synthetic.invalid/fullchain.pem"
      && host.sslCertificateKey == "/var/lib/acme/synthetic.invalid/key.pem" && !host.enableACME;
    tlsRequired = host.forceSSL;
    privateProxy = host.locations."/".proxyPass == "http://127.0.0.1:38101";
    internalHealthNotPublished = host.locations."= /healthz".return == "404" && host.locations."= /readyz".return == "404";
    cookieAndCsrfForwarded = lib.hasInfix "proxy_set_header Cookie $http_cookie;" headers
      && lib.hasInfix "proxy_set_header X-CSRF-Token $http_x_csrf_token;" headers;
    originAndBearerForwarded = lib.hasInfix "proxy_set_header Origin $http_origin;" headers
      && lib.hasInfix "proxy_set_header Authorization $http_authorization;" headers;
    identityHeadersRemoved = lib.hasInfix ''proxy_set_header X-Mrj-User "";'' headers
      && lib.hasInfix ''proxy_set_header X-Forwarded-User "";'' headers;
    canonicalHost = lib.hasInfix "proxy_set_header Host vision.synthetic.invalid;" headers;
    foreignHostRejected = lib.hasInfix "if ($host != vision.synthetic.invalid) { return 421; }" host.extraConfig;
    separateAuthBridge = host.locations."/auth/".proxyPass == "http://127.0.0.1:3002";
    oauthDiscoveryPreserved = host.locations."= /.well-known/oauth-authorization-server".proxyPass == "http://127.0.0.1:3002"
      && host.locations."= /.well-known/oauth-protected-resource/mcp".proxyPass == "http://127.0.0.1:3002";
    oauthDelegationIsClosed = host.locations."= /oauth/token".proxyPass == "http://127.0.0.1:3002"
      && !(host.locations ? "/oauth/");
    matevalAuthNotRerouted = !(mateval.locations ? "/auth/");
    requestLogsSuppressed = lib.hasInfix "access_log off;" host.extraConfig && lib.hasInfix "error_log /dev/null crit;" host.extraConfig;
    matevalBodyLimitPreserved = lib.hasInfix "client_max_body_size 5m;" mateval.extraConfig;
    noFirewallMutation = enabled.networking.firewall.allowedTCPPorts == disabled.networking.firewall.allowedTCPPorts;
    sourceVersionPreserved = enabled.system.stateVersion == "26.05";
    absentRustRejected = !(valid (evaluate (lib.recursiveUpdate fixture { services.mrjamRust.enable = false; })));
    absentNginxRejected = !(valid (evaluate (lib.recursiveUpdate fixture { services.nginx.enable = false; })));
    authLoopRejected = !(valid (evaluate (lib.recursiveUpdate fixture { services.mrjamGateway.authenticationPort = 38101; })));
    oauthWithoutIdentityRejected = !(valid (evaluate (lib.recursiveUpdate fixture {
      services.mrjamGateway.sites."vision.synthetic.invalid".authenticationBridge = false;
    })));
  };
in assert builtins.all (v: v) (builtins.attrValues results); results
