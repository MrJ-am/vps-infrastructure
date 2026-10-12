{ pkgs, ... }: {
  imports = [ ../hosts/hostinger/configuration.nix ];
  infrastructure.identite = { enable = true; preconditionsValidees = true; };
  infrastructure.visionMultiutilisateur.enable = true;
  infrastructure.courriel.enable = true;
  infrastructure.visionCycle.enable = true;
  infrastructure.admission.enable = true;
  infrastructure.fermeture.enable = true;
  infrastructure.metier = {
    enable = true;
    paquet = pkgs.writeShellScriptBin "ancien-metier-qualification" "exit 125";
    documentVision = "/srv/qualification/vision-ancien";
    ressourcesMatheval = "/srv/qualification/matheval-ancien";
    bankVersion = "fixture-ancien";
  };
  # Processus auxiliaire déjà installé dans la référence réelle ; cette
  # fixture de configuration ne lance pas de fournisseur d'embeddings.
  systemd.services.vision-embeddings.serviceConfig.ExecStart = "${pkgs.coreutils}/bin/false";
}
