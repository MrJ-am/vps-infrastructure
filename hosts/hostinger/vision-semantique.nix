{ lib, ... }:
{
  imports = [ ./logique.nix ../../vendor/vision-embeddings/embeddings.nix ];
  infrastructure.postgresql.visionSemantique = true;
  services.visionEmbeddings = {
    enable = true;
    source = builtins.path {
      path = /srv/vision/releases/c0bfcac66b9ee52e282bb895ec6aed3921a86266;
      name = "vision-fournisseur-c0bfcac";
      filter = path: type: type == "directory"
        || lib.hasSuffix "/scripts/embeddings.py" path
        || lib.hasSuffix "/scripts/backfill_embeddings.py" path;
    };
  };
  # Le runner réalise la migration sous arrêt des écritures, puis le backfill.
  # Ne pas laisser switch-to-configuration déclencher les nouvelles migrations
  # avant l'essai sur restauration. La commande est conservée pour les prochains boots.
  systemd.services.vision-migrate.restartIfChanged = false;
}
