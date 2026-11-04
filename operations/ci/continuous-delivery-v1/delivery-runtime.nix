# Update only artifact bindings in an installed public slot configuration.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}, slot, configFile,
  frontendInventory, serverStorePath, serverManifestSha256 }:
let
  base=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile configFile));
  inventory=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile frontendInventory));
  hosts={
    "audition.mrj.am"="audition";"log.mrj.am"="log";
    "logique.echos.systems"="logique";"principiipetit.io"="mateval";
    "vision.mrj.am"="vision";
  };
  configuration=base // {assets=map (asset:
    let selected=inventory.outputs.${hosts.${asset.host}};
    in asset // {directory=selected.store_path;manifest_sha256=selected.manifest_sha256;}
  ) base.assets;};
  updated=pkgs.writeText "mrjam-delivery-runtime-${slot}.json" (builtins.toJSON configuration);
in assert inventory.schema_version==1 && inventory.deployment_authorized==false;
assert builtins.attrNames inventory.outputs==["audition" "log" "logique" "mateval" "style" "style-logo" "vision"];
assert pkgs.lib.sort builtins.lessThan (map (asset: asset.host) base.assets)==builtins.attrNames hosts;
pkgs.callPackage ../../runtime/package.nix {
  inherit slot serverStorePath serverManifestSha256;
  configFile=updated;
}
