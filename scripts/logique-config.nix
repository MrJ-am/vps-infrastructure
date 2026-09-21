{ configuration }:
let
  c = (import <nixpkgs/nixos/lib/eval-config.nix> {
    system = "x86_64-linux";
    modules = [ (builtins.toPath configuration) ];
  }).config;
in {
  systeme = toString c.system.build.toplevel;
  nginx = c.systemd.services.nginx.serviceConfig.ExecStart;
  invariant = {
    noyau = toString c.boot.kernelPackages.kernel;
    parametres = c.boot.kernelParams;
    demarrage = c.boot.loader.grub.device;
    reseau = c.systemd.network.networks;
    pareFeu = c.networking.firewall.allowedTCPPorts;
    cles = c.users.users.root.openssh.authorizedKeys.keys;
    publication = c.users.users.matheval-deploy.openssh.authorizedKeys.keys;
    sudo = c.security.sudo.extraRules;
    services = map (nom: c.systemd.units."${nom}.service".text)
      [ "sshd" "postgresql" "postgresql-setup" "matheval" "vision"
        "vision-migrate" "mrj-auth" "postgresqlBackup-matheval" "postgresqlBackup-vision" ];
    sauvegardes = map (nom: c.systemd.units."postgresqlBackup-${nom}.timer".text)
      [ "matheval" "vision" ];
    sites = map (nom: c.services.nginx.virtualHosts.${nom})
      [ "principiipetit.io" "www.principiipetit.io" "vision.mrj.am" ];
  };
}
