# Reconstructed from the reviewed VPS source, not from Spectre's hardware.
# This machine fragment is deliberately not an activatable complete host.
{ config, lib, pkgs, modulesPath, ... }:
let
  facts = builtins.fromJSON (builtins.readFile ./received-profile.json);
  received = ../../received/20261101/vps-reviewed-sources/extracted/source;
  # Machine/network facts do not depend on the independently received ViSe adapter.
  machineSources = builtins.filter (name: name != "etc/nixos/vise-hosting/module.nix")
    (builtins.attrNames facts.source_hashes);
  sourcesMatch = lib.all (name:
    builtins.hashFile "sha256" (received + "/${name}") == facts.source_hashes.${name}
  ) machineSources;
in {
  imports = [ (modulesPath + "/profiles/qemu-guest.nix") ];
  assertions = [
    { assertion = sourcesMatch;
      message = "mrjamVpsMachine: reviewed source bytes changed."; }
    { assertion = config.system.stateVersion == facts.state_version;
      message = "mrjamVpsMachine: stateVersion must preserve the received declaration; never infer an upgrade from nixpkgs."; }
    { assertion = config.nixpkgs.hostPlatform.system == facts.system;
      message = "mrjamVpsMachine: only the received x86_64-linux machine profile is prepared."; }
    { assertion = false;
      message = "mrjamVpsMachine: complete host activation blocked. Service composition, installed-state adoption, backup/restore and cutover are not qualified. This gate requires a reviewed code change, not an approval flag."; }
  ];
  system.stateVersion = facts.state_version;
  nixpkgs.hostPlatform = lib.mkDefault facts.system;
  networking.hostName = facts.hostname;
  boot.loader.grub = { enable = true; device = facts.grub_device; };
  boot.growPartition = true;
  boot.initrd.availableKernelModules = [ "ata_piix" "uhci_hcd" "virtio_pci" "virtio_scsi" "sd_mod" "sr_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ ];
  boot.extraModulePackages = [ ];
  boot.kernelParams = [ "console=tty0" "console=ttyS0,115200" "earlyprintk=ttyS0,115200"
    "consoleblank=0" "memhp_default_state=online" ];
  fileSystems."/" = { device = facts.root_device; fsType = facts.root_fs_type; autoResize = true; };
  swapDevices = [ ];

  networking.useDHCP = false;
  networking.useNetworkd = true;
  services.resolved.enable = true;
  services.qemuGuest.enable = true;
  systemd.network.networks."05-matheval-eth0" = {
    matchConfig = { Name = facts.interface; MACAddress = facts.mac_address; };
    address = facts.addresses;
    networkConfig.DHCP = "no";
    dns = facts.dns;
    domains = [ "localhost" ];
    routes = map (gateway: { Gateway = gateway; }) facts.gateways;
  };
  services.cloud-init = {
    enable = true;
    network.enable = true;
    settings = { datasource_list = [ "NoCloud" "ConfigDrive" ]; ssh.emit_keys_to_console = false; };
  };
  systemd.services.cloud-init-local.restartIfChanged = false;
  systemd.services.cloud-init.restartIfChanged = false;
  systemd.services.cloud-config.restartIfChanged = false;
  systemd.services.cloud-final.restartIfChanged = false;
  services.openssh = {
    enable = true;
    settings = { PermitRootLogin = "prohibit-password"; PasswordAuthentication = false; KbdInteractiveAuthentication = false; };
  };
  users.users.root.openssh.authorizedKeys.keys = [ facts.root_public_key ];
  environment.systemPackages = with pkgs; [ git curl jq ripgrep ];
}
