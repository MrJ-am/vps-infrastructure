{ lib, pkgs, ... }:
{
  # Même branche PHP 8.4 et même Nixpkgs ; publication officielle du 21 octobre.
  # Les surcharges PHP Nixpkgs propagent aussi la source à ses extensions.
  services.nextcloud.phpPackage = lib.mkForce (pkgs.php84.overrideAttrs (_: {
    version = "8.4.27";
    src = pkgs.fetchurl {
      url = "https://www.php.net/distributions/php-8.4.27.tar.bz2";
      hash = "sha256-slMKh3xyL0sIyeF0owywi6wrfhkD7m6eMV8KqfX4LCQ=";
    };
  }));
}
