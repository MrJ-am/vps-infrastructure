# Desired post-cutover boot policy for the separately reviewed complete candidate.
# Both staged and promoted closures must be built before any maintenance window.
{ lib, ... }:
{
  imports = [ ./candidate.nix ];
  services.mrjamForgejoHost.startAtBoot = true;
  services.mrjamKanidmHost.startAtBoot = true;
  services.mrjamNextcloudHost.startAtBoot = true;
  services.mrjamIdentity.startAtBoot = true;
  services.mrjamIdentityDeletion.startAtBoot = true;
  services.mrjamEmbeddings.promote = true;
  services.mrjamVisionArchive.timer.enable = true;
  services.mrjamVisionCycle.timer.enable = true;
  services.mrjamVisionReplay.timer.enable = true;
  services.mrjamVisionAdmission.admissionsOpen = true;
  mrjamVpsRenewal.timersEnabled = true;
  mrjamVpsBackups.promote = true;
  systemd.targets.postgresql.wantedBy = lib.mkOverride 40 [ "multi-user.target" ];
  systemd.services.nginx.wantedBy = lib.mkOverride 40 [ "multi-user.target" ];
  systemd.services.mrjam-rust-blue.wantedBy = [ "multi-user.target" ];
  systemd.services.mrjam-vision-admission.wantedBy = [ "multi-user.target" ];
  systemd.services.mrjam-vision-closure.wantedBy = [ "multi-user.target" ];
}
