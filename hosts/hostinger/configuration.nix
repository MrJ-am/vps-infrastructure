# Source extraite de Matheval ; à comparer au VPS avant toute activation.
{ config, lib, pkgs, ... }:
{
  imports = [
    ./hardware-configuration.nix
    ../../apps/matheval.nix
    ../../modules/gateway.nix
    ../../modules/postgresql.nix
  ];

  # Configuration reconstituée sur le VPS 1982677 le 17 septembre 2026.
  # Le canal installé (26.05) et le noyau 6.18 sont conservés.
  system.stateVersion = "26.05";
  networking.hostName = "nixos";
  boot.loader.grub = { enable = true; device = "/dev/sda"; };
  boot.growPartition = true;
  fileSystems."/".autoResize = true;
  boot.kernelParams = [
    "console=tty0" "console=ttyS0,115200" "earlyprintk=ttyS0,115200"
    "consoleblank=0" "memhp_default_state=online"
  ];

  networking.useDHCP = false;
  networking.useNetworkd = true;
  services.resolved.enable = true;
  services.qemuGuest.enable = true;
  systemd.network.networks."05-matheval-eth0" = {
    matchConfig = { Name = "eth0"; MACAddress = "d4:e8:d4:c3:50:d5"; };
    address = [ "187.77.95.158/24" "2a02:4780:41:cf57::1/48" ];
    networkConfig.DHCP = "no";
    dns = [ "153.92.2.6" "1.1.1.1" "8.8.4.4" ];
    domains = [ "localhost" ];
    routes = [
      { Gateway = "187.77.95.254"; }
      { Gateway = "2a02:4780:41::1"; }
    ];
  };

  # Préserver les services de l'image Hostinger sans les rejouer lors d'une
  # activation. La déclaration réseau ci-dessus précède le fichier cloud-init.
  services.cloud-init = {
    enable = true;
    network.enable = true;
    settings = {
      datasource_list = [ "NoCloud" "ConfigDrive" ];
      ssh.emit_keys_to_console = false;
    };
  };
  systemd.services.cloud-init-local.restartIfChanged = false;
  systemd.services.cloud-init.restartIfChanged = false;
  systemd.services.cloud-config.restartIfChanged = false;
  systemd.services.cloud-final.restartIfChanged = false;

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "prohibit-password";
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
    };
  };
  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMXMNrDpVvr2nl2yn2VgxTtKByqcg4iPR4N/oxUsLAPR matheval-administration-20260916"
  ];


  environment.systemPackages = with pkgs; [ git curl jq ripgrep ];
}
