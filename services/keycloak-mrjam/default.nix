{ pkgs }:
let keycloak = import ./paquet.nix { inherit pkgs; };
in
assert keycloak.version == "26.7.3";
pkgs.runCommand "mrjam-keycloak-26.7.3" {
  nativeBuildInputs = [ pkgs.jdk21_headless ];
} ''
  mkdir -p "$out"
  sh ${./.}/compiler.sh ${keycloak.src}/lib/lib/main "$out/mrjam-identite.jar"
''
