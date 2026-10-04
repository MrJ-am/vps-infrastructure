{ configuration }:
let
  lib = import <nixpkgs/lib>;
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
in {
  systeme = toString c.system.build.toplevel;
  postgres = toString c.services.postgresql.finalPackage;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
  fournisseur = if c.systemd.services ? vision-embeddings then c.systemd.services.vision-embeddings.serviceConfig.ExecStart else "";
  invariant = {
    noyau = toString c.boot.kernelPackages.kernel;
    parametres = c.boot.kernelParams;
    demarrage = c.boot.loader.grub.device;
    reseau = lib.mapAttrs (_: f: toString f.source)
      (lib.filterAttrs (n: _: lib.hasPrefix "systemd/network" n) c.environment.etc);
    pareFeu = c.networking.firewall.allowedTCPPorts;
    cles = c.users.users.root.openssh.authorizedKeys.keys;
    publication = c.users.users.matheval-deploy.openssh.authorizedKeys.keys;
    sudo = c.security.sudo.extraRules;
    postgres = {
      version = c.services.postgresql.package.version;
      dataDir = c.services.postgresql.dataDir;
      hba = c.services.postgresql.authentication;
      settings = c.services.postgresql.settings;
      bases = c.services.postgresql.ensureDatabases;
      roles = c.services.postgresql.ensureUsers;
      sauvegardes = c.services.postgresqlBackup.databases;
    };
    services = map (n: c.systemd.units."${n}.service".text)
      [ "sshd" "matheval" "mrj-auth" "phpfpm-nextcloud" "redis-nextcloud" "nextcloud-setup" "nextcloud-cron" "nextcloud-backup" ];
    sites = map (n: builtins.removeAttrs c.services.nginx.virtualHosts.${n}
      [ "sslCertificate" "sslCertificateKey" ]) (builtins.attrNames c.services.nginx.virtualHosts);
  };
}
