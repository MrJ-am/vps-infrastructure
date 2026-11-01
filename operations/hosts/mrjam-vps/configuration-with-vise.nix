# Optional later adoption profile, never a prerequisite of the first release.
# Importing this preparation still does not activate ViSe or a complete host.
let
  target = builtins.fromJSON (builtins.readFile ../../targets/mrjam-vps.json);
  reportFile = ../../received/20261101/services-v1.json;
  report = builtins.fromJSON (builtins.readFile reportFile);
in
assert builtins.hashFile "sha256" reportFile == target.services_observation.report_sha256;
assert report.schema_version == 1 && report.authority == "unverified_observation";
assert report.accounts.etp_carnet.state == "observed";
{
  imports = [ ./configuration.nix ../../nixos/mrjam-vise.nix ];
  services.mrjamVise = {
    enable = false;
    adoption = { inherit (report.accounts.etp_carnet) uid gid; };
  };
}
