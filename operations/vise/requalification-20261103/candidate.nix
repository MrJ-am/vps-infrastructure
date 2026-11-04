# Separately qualified ViSe, preserving the deployed application and CI baseline.
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib = (import nixpkgs { system = "x86_64-linux"; }).lib;
  baseline = import ../../ci/activation-v1/persistent.nix;
  module = { ... }: {
    imports = [ ../../nixos/mrjam-vise.nix ];
    mrjamVpsApplications.allowIndependentVise = true;
    services.mrjamVise = {
      enable = true;
      artifactRoot = "/nix/store/zmb0mvkn59zxpxnc9ny02q4rkaffc5bw-mrjam-vise-0.2.0-8c8ef66f943c";
      adoption = { uid = 981; gid = 981; };
    };
    # Initial activation remains explicit until the real service passes readiness.
    services.nginx.virtualHosts."vise.mrj.am" = {
      forceSSL = true; enableACME = false;
      sslCertificate = "/var/lib/acme/vise.mrj.am/fullchain.pem";
      sslCertificateKey = "/var/lib/acme/vise.mrj.am/key.pem";
      extraConfig = "client_max_body_size 4000000; client_body_timeout 15s; access_log off; error_log /dev/null crit;";
      locations."/" = {
        proxyPass = "http://127.0.0.1:3017";
        recommendedProxySettings = true;
        extraConfig = "proxy_connect_timeout 5s; proxy_read_timeout 20s; proxy_send_timeout 20s;";
      };
    };
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; modules = baseline.modules ++ extra;
  }).config;
  old = evaluate []; current = evaluate [module];
  changed = lib.filter (n: old.systemd.units.${n}.text != current.systemd.units.${n}.text) (builtins.attrNames old.systemd.units);
  checks = {
    baselineExact = toString old.system.build.toplevel == "/nix/store/3fylc2yfjvzzibpi0pf0nzqj0f5lh1hm-nixos-system-srv1982677-26.05pre-git";
    assertionsPass = lib.all (a: a.assertion) current.assertions;
    sameValidationAuthority = old.services.mrjamValidationAuthority.package == current.services.mrjamValidationAuthority.package;
    noAutomaticViseStart = current.systemd.services.vise.wantedBy == [];
    noAutomaticViseBackup = !current.services.mrjamVise.backup.enable;
  };
in {
  modules = baseline.modules ++ [module];
  evaluation = { inherit checks changed; candidate = toString current.system.build.toplevel; failures = map (a: a.message) (lib.filter (a: !a.assertion) current.assertions); };
  toplevel = assert lib.all (x: x) (builtins.attrValues checks); current.system.build.toplevel;
}
