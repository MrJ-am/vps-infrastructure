{ configuration }:
let
  lib = import <nixpkgs/lib>;
  base = import ./mcp-config.nix { inherit configuration; };
  sites = base.invariant.sites;
  vision = sites."vision.mrj.am";
  api = vision.locations."/api/";
in base // {
  # Le comparateur existant isole déjà MCP et le code mrj-auth. La seule
  # exception REST supplémentaire est cet en-tête précis, issu de Basic.
  invariant = base.invariant // {
    sites = sites // {
      "vision.mrj.am" = vision // {
        locations = vision.locations // {
          "/api/" = api // {
            extraConfig = lib.replaceStrings
              [ "proxy_set_header X-Mrj-User $remote_user;" ]
              [ "proxy_set_header X-Mrj-User \"\";" ] api.extraConfig;
          };
        };
      };
    };
  };
}
