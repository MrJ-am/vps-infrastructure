# Independent ViSe boot policy and renewal using the retained ACME account.
let
  nixpkgs = /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source;
  lib = (import nixpkgs { system = "x86_64-linux"; }).lib;
  staged = import ./candidate.nix;
  promotion = { config, pkgs, ... }: {
    # The retained renewal script compares certificate/key bytes with cmp.
    # Supply its missing runtime dependency to every retained renewal unit.
    systemd.services = lib.mapAttrs' (name: _: lib.nameValuePair
      "mrjam-acme-renew-${name}" { path = [ pkgs.diffutils ]; })
      config.mrjamVpsRenewal.certificates // {
        vise.wantedBy = [ "multi-user.target" ];
      };
    mrjamVpsRenewal.certificates."vise.mrj.am" = {
      domain = "vise.mrj.am"; extraDomains = [];
      accountHash = "a96772ab152e39f749f9";
      certificateHash = "748661661a99cbbf91d5";
      server = "https://acme-v02.api.letsencrypt.org/directory";
      keyType = "ec256"; webroot = "/var/lib/acme/acme-challenge";
      interval = "*-*-* 00:00:00"; jitter = "1d";
      reloadServices = [ "nginx.service" ];
    };
  };
  evaluate = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux"; modules = staged.modules ++ extra;
  }).config;
  old = evaluate []; current = evaluate [promotion];
  checks = {
    stagedExact = toString old.system.build.toplevel == "/nix/store/h7gsm02w34zbacxamwjl98qmbqyb3kci-nixos-system-srv1982677-26.05pre-git";
    assertionsPass = lib.all (a: a.assertion) current.assertions;
    viseStartsAtBoot = current.systemd.services.vise.wantedBy == [ "multi-user.target" ];
    renewalStartsAtBoot = current.systemd.timers."mrjam-acme-renew-vise.mrj.am".wantedBy == [ "timers.target" ];
    noAutomaticViseBackup = !current.services.mrjamVise.backup.enable;
    sameValidationAuthority = old.services.mrjamValidationAuthority.package == current.services.mrjamValidationAuthority.package;
  };
in {
  modules = staged.modules ++ [promotion];
  evaluation = { inherit checks; candidate = toString current.system.build.toplevel; };
  toplevel = assert lib.all (x: x) (builtins.attrValues checks); current.system.build.toplevel;
}
