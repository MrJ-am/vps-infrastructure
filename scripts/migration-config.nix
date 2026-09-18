{ configuration }:
let
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
in {
  toplevel = toString c.system.build.toplevel;
  nginx = {
    binary = "${c.services.nginx.package}/bin/nginx";
    command = c.systemd.services.nginx.serviceConfig.ExecStart;
  };
  invariant = {
    kernel = toString c.boot.kernelPackages.kernel;
    kernelParams = c.boot.kernelParams;
    grubDevice = c.boot.loader.grub.device;
    stateVersion = c.system.stateVersion;
    hostName = c.networking.hostName;
    useDHCP = c.networking.useDHCP;
    useNetworkd = c.networking.useNetworkd;
    firewallTCP = c.networking.firewall.allowedTCPPorts;
    ssh = c.services.openssh.settings;
    rootKeys = c.users.users.root.openssh.authorizedKeys.keys;
    deploymentKeys = c.users.users.matheval-deploy.openssh.authorizedKeys.keys;
    postgresqlPackage = toString c.services.postgresql.package;
    postgresqlData = c.services.postgresql.dataDir;
    postgresqlTCP = c.services.postgresql.enableTCPIP;
    postgresqlListen = c.services.postgresql.settings.listen_addresses;
    backupDatabases = c.services.postgresqlBackup.databases;
    backupLocation = c.services.postgresqlBackup.location;
    backupSchedule = c.services.postgresqlBackup.startAt;
    mathevalEnvironment = c.systemd.services.matheval.environment;
    mathevalService = c.systemd.services.matheval.serviceConfig;
    backupRecipient = c.services.matheval.backupRecipient;
    sudo = c.security.sudo.extraRules;
  };
}
