# Trusted controller composition only. No candidate Nix, activation or admission.
# Retain this module across promotion: routing is a separate transition.
{ slot, serverStorePath, runtimeStorePath }:
{ config, lib, ... }:
let
  valid = value: builtins.isString value && !(builtins.hasContext value)
    && builtins.match "/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+" value != null;
in assert builtins.elem slot [ "blue" "green" ];
assert valid serverStorePath && valid runtimeStorePath;
{
  assertions = [{
    assertion = config.mrjamVpsApplications.enable
      && builtins.hasAttr slot config.mrjamVpsApplications.slots;
    message = "Ordinary delivery can replace only an already installed slot.";
  }];
  # Do not change the historical assembly's global serverStorePath: it would
  # replace both units. Runtime packaging retains its exact frontend references.
  mrjamVpsApplications.slots.${slot} = lib.mkForce runtimeStorePath;
  services.mrjamRust.slots.${slot}.artifactStorePath = lib.mkForce serverStorePath;
  system.extraDependencies = map builtins.storePath [ serverStorePath runtimeStorePath ];
}
