{ pkgs, ... }: {
  imports = [ ./base.nix ];
  services.nextcloud.extraApps.contacts = pkgs.nextcloud34Packages.apps.contacts;
}
