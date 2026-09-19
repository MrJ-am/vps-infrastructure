{ config, ... }:
let
  site = (builtins.fromJSON (builtins.readFile ../projects.json)).vision;
in {
  imports = [ ../vendor/vision/vision.nix ];
  assertions = [{
    assertion = site.port == 3001 && site.prefix == "" &&
      site.domain == "vision.principiipetit.io" && site.service == "vision" &&
      site.auth.prefix == "/api/" &&
      site.auth.basicUserFile == "/var/lib/vision/auth/htpasswd" &&
      site.privateHealthPath == "/healthz" &&
      config.infrastructure.postgresql.projects.vision.name == "vision";
    message = "Changement du contrat Vision : coordonner le module applicatif avant activation.";
  }];
  services.vision = {
    enable = true;
    domain = site.domain;
    port = site.port;
    version = "1.0.0";
    bootstrapSource = ../vendor/vision/source;
    bootstrapCommit = "c2bb07a67fdd74fcf3fabd7f4217767864da9cae";
    deploymentPublicKeys = [];
    backupRecipient = "age15zfsttzkz0n553mgq07czxk98j65y6pg47563c7gvneq65dmfgjs3x0x0l";
  };
}
