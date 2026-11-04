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
      expected = "/nix/store/cxqicl1y5i8fcbclbvyrx0mdhkf2z215-nixos-system-srv1982677-26.05pre-git";
    };
    promoted = {
      module = ../../hosts/mrjam-vps/candidate-promoted.nix;
      expected = "/nix/store/fi48cx2j57lmjqsydjn9biwfb5ikx6jg-nixos-system-srv1982677-26.05pre-git";
    };
  };
  results = builtins.mapAttrs (_: item:
    let a = evaluate [ item.module ];
        b = evaluate [ item.module ../forgejo-host-actions.nix ];
        reset = c: c.systemd.services.systemd-tmpfiles-resetup.serviceConfig.ExecStart;
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
      resetupUnitOnlyChangesGeneratedScript = lib.replaceStrings [ (reset a) ] [ "TMPFILES_SCRIPT" ] a.systemd.units."systemd-tmpfiles-resetup.service".text
        == lib.replaceStrings [ (reset b) ] [ "TMPFILES_SCRIPT" ] b.systemd.units."systemd-tmpfiles-resetup.service".text;
      onlyGeneratedTmpfilesEtcChanges = changed a.environment.etc b.environment.etc (e: builtins.toJSON {
        source = toString e.source; inherit (e) mode user group; }) == [ "systemd/system" "tmpfiles.d" ];
      sameTmpfilesRuleContents = builtins.sort builtins.lessThan a.systemd.tmpfiles.rules
        == builtins.sort builtins.lessThan b.systemd.tmpfiles.rules;
      exactlyTwoForgejoRulesRepositioned = builtins.length (lib.filter hostRule a.systemd.tmpfiles.rules) == 2
        && lib.filter hostRule a.systemd.tmpfiles.rules == lib.filter hostRule b.systemd.tmpfiles.rules
        && lib.filter (rule: !hostRule rule) a.systemd.tmpfiles.rules == lib.filter (rule: !hostRule rule) b.systemd.tmpfiles.rules;
    }) pairs;
in results
