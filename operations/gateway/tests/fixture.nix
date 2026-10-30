{ nixpkgs }:
let
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  config = (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ ../../nixos/mrjam-gateway.nix {
      system.stateVersion = "26.05";
      services.nginx = {
        enable = true;
        enableReload = true;
        user = "root";
        group = "root";
        # NixOS runs Nginx as the service User; this fixture invokes it as root
        # without account activation. Override Nginx's compiled nobody:nogroup.
        appendConfig = "user root root;";
        defaultHTTPListenPort = 18081;
        defaultSSLListenPort = 18443;
      };
      services.mrjamRust = {
        enable = true;
        slots.blue = {
          enable = true;
          artifactStorePath = "/nix/store/00000000000000000000000000000000-synthetic-server";
          runtimeConfigStorePath = "/nix/store/11111111111111111111111111111111-synthetic-runtime";
        };
      };
      services.mrjamGateway = {
        enable = true;
        sites = {
          "vision.synthetic.invalid" = { certificateName = "synthetic.invalid"; authenticationBridge = true; mcpOAuthBridge = true; };
          "mateval.synthetic.invalid" = { certificateName = "synthetic.invalid"; maximumBodySize = "5m"; };
        };
      };
    } ];
  }).config;
  runtime = builtins.toJSON {
    nginx = "${pkgs.nginx}/bin/nginx";
    config = "${config.environment.etc."nginx/nginx.conf".source}";
    openssl = "${pkgs.openssl.bin}/bin/openssl";
    python = "${pkgs.python3}/bin/python3";
  };
in pkgs.runCommand "mrjam-gateway-synthetic-test" {
  inherit runtime;
  passAsFile = [ "runtime" ];
} ''
  mkdir -p "$out"
  cp "$runtimePath" "$out/runtime.json"
  cp ${./qualify.py} "$out/qualify.py"
''
