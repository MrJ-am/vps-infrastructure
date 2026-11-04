{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  digest="e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7";
  source=builtins.path {path=../../../.local/deployment-20261101/accepted-e06-source;name="mrjam-adopted-source-e06f030310ae";};
  policy=builtins.path {path=../../../.local/deployment-20261101/accepted-e06-artifacts/policy.json;name="mrjam-adopted-policy-e06f030310ae.json";};
in assert builtins.hashFile "sha256" (source+"/manifest.json")==digest;
assert builtins.hashFile "sha256" policy=="4f31c738c7353ef477a6ea0fc5472ea60a7d8da5d9bec8a618be23c3478ecd4f";
pkgs.writeText "mrjam-adopted-source.json" (builtins.toJSON {
  schema_version=1;inherit source policy;proposal_sha256=digest;
})
