# Evaluation/build fixture only. Never a VPS configuration or real key.
{ ... }: {
  system.stateVersion = "26.05"; # synthetic fixture, no production stateVersion inferred
  boot.loader.grub.enable = false;
  fileSystems."/" = { device = "/dev/disk/by-label/synthetic-root"; fsType = "ext4"; };
  services.openssh.enable = true;
  services.openssh.openFirewall = false;
  services.mrjamInventory = {
    enable = true;
    adoption = { uid = 990; gid = 990; };
    publicKeys = [ "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f synthetic-never-authorize" ];
  };
}
