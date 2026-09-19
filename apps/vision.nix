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
    bootstrapCommit = "b8d1de19be4bdc0db408820853239156117060ca";
    deploymentPublicKeys = [];
    backupRecipient = "age15zfsttzkz0n553mgq07czxk98j65y6pg47563c7gvneq65dmfgjs3x0x0l";
  };
}
