# Preserve the reviewed application versions independently of the host pin.
{ system ? "x86_64-linux" }:
let
  input = (builtins.fromJSON (builtins.readFile ../../compatibility/nixpkgs-vps-observed.lock.json)).input;
  baseline = builtins.fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/${input.rev}.tar.gz";
    sha256 = input.narHash;
  };
  old = import baseline { inherit system; config = { }; overlays = [ ]; };
  locked = import ../../forgejo/locked-toolchain.nix { inherit system; };
  nextcloud = old.nextcloud34.overrideAttrs (_: {
    version = "34.0.4";
    src = old.fetchurl {
      url = "https://download.nextcloud.com/server/releases/nextcloud-34.0.4.tar.bz2";
      hash = "sha256-APIm5jZPluCRirBhVxWPZmAbjO3CWvd39e5aMFb0K4M=";
    };
  });
in
assert system == "x86_64-linux";
assert input.rev == "c5c4a43b0e8056328ec4529f735cabdb8f1942bb";
assert input.narHash == "sha256-u6z9VTZA4Kf3RkHQo9sQI7NI4Ei/uiU9vrMqOiwWP1Y=";
assert locked.php84.version == "8.4.27";
assert locked.kanidm_1_11.version == "1.11.2";
assert old.nextcloud34Packages.apps.user_oidc.name == "nextcloud-app-user_oidc-8.10.1";
{
  inherit nextcloud;
  php = locked.php84;
  kanidm = locked.kanidm_1_11.override { enableSecretProvisioning = false; };
  nextcloudApps = { inherit (old.nextcloud34Packages.apps) user_oidc spreed; };
}
