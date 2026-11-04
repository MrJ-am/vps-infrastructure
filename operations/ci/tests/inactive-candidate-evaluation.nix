# Evaluation only. Importing the post-cutover variant changes declaration order
# of its two Forgejo tmpfiles rules; it must not change their content or any
# application unit, identity, package or setting in either frozen generation.
{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    inherit modules;
  }).config;
  changed = x: y: f: lib.filter (name:
    !(builtins.hasAttr name x && builtins.hasAttr name y) || f x.${name} != f y.${name})
    (lib.unique (builtins.attrNames x ++ builtins.attrNames y));
  hostRule = rule: lib.hasPrefix "d /var/lib/forgejo/custom/templates/custom " rule
    || lib.hasPrefix "L+ /var/lib/forgejo/custom/templates/custom/footer.tmpl " rule;
  pairs = {
    staged = {
      module = ../../hosts/mrjam-vps/candidate.nix;
      expected = "/nix/store/hbfh9zzrv35kxck3p56yv7pxxw22fb3y-nixos-system-srv1982677-26.05pre-git";
    };
    promoted = {
      module = ../../hosts/mrjam-vps/candidate-promoted.nix;
      expected = "/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git";
    };
    deployedUnicast = {
      module = ../../hosts/mrjam-vps/candidate-unicast.nix;
      expected = "/nix/store/phi68cwg38madbq8p805yvrsyry8g8wr-nixos-system-srv1982677-26.05pre-git";
    };
  };
  results = builtins.mapAttrs (_: item:
    let a = evaluate [ item.module ];
        b = evaluate [ item.module ../forgejo-host-actions.nix ];
        unitLines = c: lib.splitString "\n" c.systemd.units."systemd-tmpfiles-resetup.service".text;
        isTrigger = line: lib.hasPrefix "X-Restart-Triggers=" line;
        noTrigger = c: lib.filter (line: !isTrigger line) (unitLines c);
    in {
      frozenGenerationUnchanged = toString a.system.build.toplevel == item.expected;
      sameSystemPackages = a.system.path.drvPath == b.system.path.drvPath;
      sameForgejoSettings = a.services.mrjamForgejoHost.settings == b.services.mrjamForgejoHost.settings;
      actionsStillDisabled = !b.services.mrjamForgejoHost.settings.actions.ENABLED;
      sameUsers = changed a.users.users b.users.users (u: builtins.toJSON {
        inherit (u) uid group extraGroups hashedPassword home; }) == [ ];
      sameGroups = changed a.users.groups b.users.groups (g: builtins.toJSON { inherit (g) gid members; }) == [ ];
      onlyTmpfilesResetupUnitDiffers = changed a.systemd.units b.systemd.units (u: u.text)
        == [ "systemd-tmpfiles-resetup.service" ];
      resetupUnitOnlyChangesRestartTrigger = noTrigger a == noTrigger b
        && builtins.length (lib.filter isTrigger (unitLines a)) == 1
        && builtins.length (lib.filter isTrigger (unitLines b)) == 1;
      onlyGeneratedTmpfilesEtcChanges = changed a.environment.etc b.environment.etc (e: builtins.toJSON {
        source = toString e.source; inherit (e) mode user group; }) == [ "systemd/system" "tmpfiles.d" ];
      sameTmpfilesRuleContents = builtins.sort builtins.lessThan a.systemd.tmpfiles.rules
        == builtins.sort builtins.lessThan b.systemd.tmpfiles.rules;
      exactlyTwoForgejoRulesRepositioned = builtins.length (lib.filter hostRule a.systemd.tmpfiles.rules) == 2
        && lib.filter hostRule a.systemd.tmpfiles.rules == lib.filter hostRule b.systemd.tmpfiles.rules
        && lib.filter (rule: !hostRule rule) a.systemd.tmpfiles.rules == lib.filter (rule: !hostRule rule) b.systemd.tmpfiles.rules;
    }) pairs;
in assert builtins.all (group: builtins.all (value: value) (builtins.attrValues group)) (builtins.attrValues results); results
