{ pkgs }:
let
  verrou = builtins.fromJSON (builtins.readFile ./modele.lock.json);
  fichiers = map (f: f // {
    source = pkgs.fetchurl {
      url = "https://huggingface.co/${verrou.modele}/resolve/${verrou.revision}/${f.chemin}";
      sha256 = f.sha256;
    };
  }) verrou.fichiers;
in pkgs.runCommand "vision-modele-multilingue-${builtins.substring 0 12 verrou.revision}" {
  passthru = { inherit (verrou) modele revision; };
} (pkgs.lib.concatMapStringsSep "\n" (f: ''
  destination="$out"/${pkgs.lib.escapeShellArg f.chemin}
  mkdir -p "$(dirname "$destination")"
  cp -- ${f.source} "$destination"
'') fichiers)
