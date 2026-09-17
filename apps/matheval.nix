{ config, ... }:
let
  site = (builtins.fromJSON (builtins.readFile ../projects.json)).matheval;
in {
  imports = [ ../vendor/matheval/matheval.nix ];
  assertions = [{
    assertion = site.port == 3000 && site.prefix == "/matheval" &&
      site.domain == "principiipetit.io" && site.service == "matheval" &&
      config.infrastructure.postgresql.projects.matheval.name == "matheval";
    message = "Changement du contrat Matheval : coordonner le module applicatif avant activation.";
  }];
  services.matheval = {
    enable = true;
    domain = site.domain;
    deploymentPublicKeys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIt/Ixp6+O6tVBf6XA8vD6UpwaweiEcvnCog8RlDeWOE matheval-deploiement-20260916"
    ];
    backupRecipient = "age15zfsttzkz0n553mgq07czxk98j65y6pg47563c7gvneq65dmfgjs3x0x0l";
  };
}
