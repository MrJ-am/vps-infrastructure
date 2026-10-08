{ pkgs }:
assert pkgs.keycloak.version == "26.7.3";
pkgs.runCommand "mrjam-keycloak-26.7.3" {
  nativeBuildInputs = [ pkgs.jdk21_headless ];
} ''
  mkdir -p "$out"
  sh ${./.}/compiler.sh ${pkgs.keycloak.src}/lib/lib/main "$out/mrjam-identite.jar"
''
