{ nixpkgs }:
let
  lib = import (nixpkgs + "/lib");
  module = ../nixos/mrjam-inventory.nix;
  fixture = import ./inventory-fixture.nix { };
  eval = extra: (import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [ module fixture extra ];
  }).config;
  enabled = eval { };
  disabled = eval { services.mrjamInventory.enable = lib.mkForce false; };
  policyPasses = cfg: builtins.all
    (item: item.assertion || !(lib.hasPrefix "mrjamInventory" item.message)) cfg.assertions;
  user = enabled.users.users.mrjam-inventory;
  keyFile = enabled.environment.etc."ssh/mrjam-inventory-authorized-keys";
  results = {
    disabledHasNoAccount = !(disabled.users.users ? mrjam-inventory);
    disabledHasNoGroup = !(disabled.users.groups ? mrjam-inventory);
    disabledHasNoKeyFile = !(disabled.environment.etc ? "ssh/mrjam-inventory-authorized-keys");
    disabledHasNoMatch = !(lib.hasInfix "Match User mrjam-inventory" disabled.services.openssh.extraConfig);
    validFixturePasses = policyPasses enabled;
    observedIdsRetained = user.uid == 990 && enabled.users.groups.mrjam-inventory.gid == 990;
    accountRestricted = user.isSystemUser && user.extraGroups == [ ] && user.hashedPassword == "!";
    existingHomePreserved = user.home == "/var/lib/mrjam-inventory-access/home" && !user.createHome;
    immutableLogin = user.shell == "${enabled.services.mrjamInventory.package}/bin/mrjam-inventory-login";
    rootOwnedKeyFile = keyFile.mode == "0444" && keyFile.user == "root" && keyFile.group == "root";
    keyRestrictsCommand = lib.hasPrefix ''restrict,command="mrjam-inventory-v1" ssh-ed25519 '' keyFile.text;
    userEnvironmentDisabled = enabled.services.openssh.settings.PermitUserEnvironment == false;
    fixedCommandInMatch = lib.hasInfix "ForceCommand mrjam-inventory-v1" enabled.services.openssh.extraConfig;
    immutableLockRule = builtins.elem "f /run/mrjam-inventory-lock/operation.lock 0440 root mrjam-inventory -" enabled.systemd.tmpfiles.rules;
    absentIdsRejected = !(policyPasses (eval { services.mrjamInventory.adoption.uid = lib.mkForce null; }));
    absentKeyRejected = !(policyPasses (eval { services.mrjamInventory.publicKeys = lib.mkForce [ ]; }));
    supplementaryGroupRejected = !(policyPasses (eval { users.users.mrjam-inventory.extraGroups = [ "synthetic-group" ]; }));
    otherGroupMemberRejected = !(policyPasses (eval { users.groups.mrjam-inventory.members = [ "synthetic-other" ]; }));
    sshDisabledRejected = !(policyPasses (eval { services.openssh.enable = lib.mkForce false; }));
    stateVersionUnchanged = enabled.system.stateVersion == fixture.system.stateVersion;
  };
in
assert builtins.all (value: value) (builtins.attrValues results);
results
