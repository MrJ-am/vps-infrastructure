{ configuration }:
let
  e = import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ configuration ];
  };
  c = e.config;
in (import ../nextcloud-php-security/evaluation.nix { inherit configuration; }) // {
  phpOptions = c.services.nextcloud.phpOptions;
  fpmOptions = c.services.phpfpm.phpOptions;
  pools = builtins.mapAttrs (_: p: {
    socket = p.socket;
    settings = p.settings;
    user = p.user;
    phpOptions = p.phpOptions;
    version = p.phpPackage.version;
  }) c.services.phpfpm.pools;
  apache = c.services.httpd.enable;
}
