{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  evaluate = modules: (import (nixpkgs + "/nixos/lib/eval-config.nix") { system = "x86_64-linux"; inherit modules; }).config;
  a = evaluate [ ../../hosts/mrjam-vps/candidate-promoted.nix ];
  b = evaluate [ ../../hosts/mrjam-vps/candidate-promoted.nix ../forgejo-host-actions.nix ];
  names = x: y: lib.unique (builtins.attrNames x ++ builtins.attrNames y);
  changed = x: y: f: lib.filter (name: !(builtins.hasAttr name x && builtins.hasAttr name y) || f x.${name} != f y.${name}) (names x y);
in {
  builds = { before = a.system.build.toplevel.drvPath; after = b.system.build.toplevel.drvPath;
    etcBefore = a.system.build.etc.drvPath; etcAfter = b.system.build.etc.drvPath;
    systemPathBefore = a.system.path.drvPath; systemPathAfter = b.system.path.drvPath; };
  units = changed a.systemd.units b.systemd.units (u: u.text);
  users = changed a.users.users b.users.users (u: builtins.toJSON { inherit (u) uid group extraGroups hashedPassword home; });
  groups = changed a.users.groups b.users.groups (g: builtins.toJSON { inherit (g) gid members; });
  etc = changed a.environment.etc b.environment.etc (e: builtins.toJSON { source = toString e.source; inherit (e) mode user group; });
  activation = changed a.system.activationScripts b.system.activationScripts (s: if builtins.isAttrs s then s.text else s);
  tmpfilesEqual = a.systemd.tmpfiles.rules == b.systemd.tmpfiles.rules;
  settingsEqual = a.services.mrjamForgejoHost.settings == b.services.mrjamForgejoHost.settings;
}
