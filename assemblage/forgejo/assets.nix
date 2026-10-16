{ pkgs }:
let
  lock = builtins.fromJSON (builtins.readFile ./versions.json);
  archive = name: pkgs.fetchurl { inherit (lock.assets.${name}) url hash; };
in pkgs.runCommand "forgejo-org-mathjax-${lock.assets.mathjax.version}" {} ''
  mkdir -p $out/mathjax $out/font
  tar -xzf ${archive "mathjax"} --strip-components=1 -C $out/mathjax
  tar -xzf ${archive "font"} --strip-components=1 -C $out/font
  cp ${./assets/config.js} $out/config.js
  cp ${./assets/org.css} $out/org.css
''
