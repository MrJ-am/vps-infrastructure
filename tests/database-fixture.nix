# Deux projets dans un cluster jetable de CI, jamais des données de production.
import ../lib/databases.nix {
  matheval.name = "matheval";
  vision.name = "vision";
}
