# Execute check-config in the Nix build sandbox with public retained settings.
# No database, credential, identity endpoint or live service is accessed.
let
  pkgs=import ../../forgejo/locked-toolchain.nix {};
  server=import ./delivery-server-qualification.nix;
in pkgs.callPackage ../../runtime/package.nix {
  slot="green";
  configFile=../../hosts/mrjam-vps/runtime-green.json;
  serverStorePath=builtins.unsafeDiscardStringContext (toString server);
  serverManifestSha256=builtins.hashFile "sha256" (server+"/artifact.json");
}
