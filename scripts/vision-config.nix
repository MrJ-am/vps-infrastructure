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
  stable = {
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
    postgresqlPackage = toString c.services.postgresql.package;
    postgresqlData = c.services.postgresql.dataDir;
    postgresqlTCP = c.services.postgresql.enableTCPIP;
    postgresqlListen = c.services.postgresql.settings.listen_addresses;
    backupLocation = c.services.postgresqlBackup.location;
    backupSchedule = c.services.postgresqlBackup.startAt;
    mathevalEnvironment = c.systemd.services.matheval.environment;
    mathevalService = c.systemd.services.matheval.serviceConfig;
    mathevalKeys = c.users.users.matheval-deploy.openssh.authorizedKeys.keys;
  };
  vision = if c.services ? vision then {
    enabled = c.services.vision.enable;
    domain = c.services.vision.domain;
    port = c.services.vision.port;
    version = c.services.vision.version;
    commit = c.services.vision.bootstrapCommit;
    service = c.systemd.services.vision.serviceConfig;
    environment = c.systemd.services.vision.environment;
    databases = c.services.postgresqlBackup.databases;
  } else null;
}
