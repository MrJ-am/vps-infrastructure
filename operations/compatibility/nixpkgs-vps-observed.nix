let
  lock = builtins.fromJSON (builtins.readFile ./nixpkgs-vps-observed.lock.json);
  file = ../received/20261101/provenance-v1.json;
  observation = builtins.fromJSON (builtins.readFile file);
in
assert builtins.hashFile "sha256" file == lock.observation_sha256;
assert observation.authority == "unverified_observation";
assert observation.nixpkgs_revision.state == "observed";
assert observation.nixpkgs_revision.value == lock.input.rev;
assert lock.input.owner == "NixOS" && lock.input.repo == "nixpkgs" && lock.input.type == "github";
# An input pin, not evidence of a complete installed configuration.
(builtins.fetchTree lock.input).outPath
