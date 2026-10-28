{ pkgs, artefact }:
let
  reference = import ./paquet.nix { inherit pkgs; };
  qualifie = builtins.storePath artefact;
in
# Métadonnées exigées par le module officiel NixOS, même ELF qualifié.
# Cette dérivation ne compile pas Rust et n'ajoute aucun outil ou service.
pkgs.runCommand "kanidm-${reference.version}-qualifie" {
  inherit (reference) meta;
  passthru = {
    inherit (reference) version eolMessage enableSecretProvisioning;
  };
} ''
  mkdir -p "$out"
  for element in ${qualifie}/*; do
    ln -s -- "$element" "$out/"
  done
''
