# Controller-owned infrastructure, independent of application proposals.
# Install together with this recipe: every later staging/promotion generation
# must retain the qualified backup and its independent recovery service.
{ ... }:
{
  imports = [ ../../vise/backup/module.nix ];
  services.mrjamViseCoherentBackup = { enable = true; promote = true; };
}
