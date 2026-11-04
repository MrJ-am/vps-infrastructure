# Incomplete historical preparation remains blocked. The complete candidate
# imports the same machine profile directly after the reviewed composition change.
{ ... }:
{
  imports = [ ./machine-profile.nix ];
  assertions = [
    { assertion = false;
      message = "mrjamVpsMachine: complete host activation blocked. Service composition, installed-state adoption, backup/restore and cutover are not qualified. This gate requires a reviewed code change, not an approval flag."; }
  ];
}
