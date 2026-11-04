# All newly packaged local validation artifacts; no live slot is installed.
let
  server=import ./delivery-server-qualification.nix;
  frontends=import ./delivery-frontends-qualification.nix;
in import ./delivery-runtime.nix {
  slot="green";configFile=../../hosts/mrjam-vps/runtime-green.json;
  frontendInventory=frontends+"/inventory.json";
  serverStorePath=builtins.unsafeDiscardStringContext (toString server);
  serverManifestSha256=builtins.hashFile "sha256" (server+"/artifact.json");
}
