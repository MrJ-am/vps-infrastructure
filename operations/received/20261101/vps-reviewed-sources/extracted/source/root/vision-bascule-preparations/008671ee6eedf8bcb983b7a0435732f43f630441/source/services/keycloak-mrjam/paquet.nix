{ pkgs }:
# Le VPS conserve son Nixpkgs 26.05 et ses dépendances. Seuls la version
# et le hash de l'archive officielle changent, comme dans la recette qualifiée.
assert builtins.elem pkgs.keycloak.version [ "26.7.2" "26.7.3" ];
pkgs.keycloak.overrideAttrs (_: {
  version = "26.7.3";
  src = pkgs.fetchzip {
    url = "https://github.com/keycloak/keycloak/releases/download/26.7.3/keycloak-26.7.3.zip";
    hash = "sha256-SmzyvfVPaaUSbyH7/+XjCzwsz+YT5m6rpnLKJULSR/4=";
  };
})
