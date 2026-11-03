# Parameterized post-release installation. No fixture policy is a default.
# All new service/socket starts remain explicit; Actions starts disabled.
{ rulesRevision, controllerRevision, validator, proposals, authorityPolicy
, policyTokenFile, registrationTokenFile, signingKeyFile
, enableBoundedActions ? false
}:
{ config, lib, pkgs, ... }:
let
  users = {
    mrjam-forgejo-registration = 949;
    mrjam-forgejo-runner = 950;
    mrjam-validation-worker = 951;
    mrjam-validation-collector = 952;
    mrjam-validation-authority = 953;
  };
  groups = users // { mrjam-validation-submitters = 954; mrjam-validation-requesters = 955; };
in {
  imports = [ ./forgejo-host-actions.nix ./preserve-input-firewall.nix
    ../hosts/mrjam-vps/resolver-unicast.nix ];
  assertions = [
    { assertion = rulesRevision != "93bd67666a3b4be9657c333931fa25b2359e165b";
      message = "The historical orphan CI fixture must not become the host rules revision."; }
    { assertion = authorityPolicy.collector_uid == 952 && authorityPolicy.signer_uid == 953
        && authorityPolicy.requester_uid == 950;
      message = "The authority policy must bind the separately observed host identities."; }
    { assertion = config.networking.nftables.flushRuleset == false
        && config.networking.firewall.backend == "iptables"
        && config.networking.firewall.package == pkgs.iptables;
      message = "CI output filtering must preserve the deployed input firewall and unrelated nftables tables."; }
    { assertion = config.services.mrjamValidationCoordinatorAttestation.enable
        && config.services.mrjamValidationAuthority.enable;
      message = "The host coordinator requires the independently bound content authority."; }
  ];
  users.users = lib.mapAttrs (_: uid: { inherit uid; hashedPassword = "!"; }) users;
  users.groups = lib.mapAttrs (_: gid: { inherit gid; }) groups;
  services.mrjamForgejoHost = { inherit enableBoundedActions; };
  services.mrjamForgejoPolicy = {
    enable = true; mode = "plan"; phase = "operate-validation";
    inherit rulesRevision controllerRevision;
    repositories = [ "Signature" "apprendre-a-demontrer" "etp-vie-affective" "matheval"
      "mrjam-plateforme" "mrjam-validation" "style-mrjam" "vision" "vps-infrastructure" ];
    tokenFile = policyTokenFile;
  };
  services.mrjamForgejoRunner = {
    enable = true; inherit rulesRevision registrationTokenFile;
    registrarUid = 949; coordinatorUid = 950;
  };
  services.mrjamValidationWorker = { enable = true; inherit rulesRevision validator; };
  services.mrjamValidationCollector = { enable = true; inherit rulesRevision; };
  services.mrjamValidationStaging = { enable = true; inherit proposals; };
  services.mrjamValidationAuthority = { enable = true; policy = authorityPolicy; inherit signingKeyFile; };
  services.mrjamValidationCoordinatorAttestation.enable = true;
}
