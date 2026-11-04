# Candidate parameters from the filtered observation, not an activation proof.
# Keep source declarations in received-profile.json intact. No account is
# created by this module; the adoption services remain disabled by default.
# ViSe identity belongs to the separately selected optional profile.
let
  target = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile ../../targets/mrjam-vps.json));
  reportFile = ../../received/20261101/services-v1.json;
  report = builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile reportFile));
  identity = name:
    let account = report.accounts.${name};
    in assert account.state == "observed";
       { inherit (account) uid gid; };
in
assert builtins.hashFile "sha256" reportFile == target.services_observation.report_sha256;
assert report.schema_version == 1 && report.authority == "unverified_observation";
{
  services.mrjamForgejoHost = identity "forgejo";
  services.mrjamKanidmHost = identity "kanidm";
  services.mrjamNextcloudHost = identity "nextcloud";
}
