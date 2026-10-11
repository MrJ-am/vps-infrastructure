# Sources exclusivement de développement ; jamais importées par le produit.
{ pkgs }:
let
  lock = builtins.fromJSON (builtins.readFile ./mcp.lock.json);
  projets = map (p: let source = pkgs.fetchzip { inherit (p) url; extension = "tar.gz"; sha256 = p.nix_sha256; };
    in { name = p.nom; path = if p.nom == "cl-tron-mcp" then pkgs.applyPatches {
      name = "cl-tron-mcp-${p.revision}-raccordements";
      src = source; patches = [ ./patches/tron-raccordements-breakpoints.patch ];
    } else source; }) lock.outils;
  bibliotheques = with pkgs.sbcl.pkgs; [ alexandria cl-ppcre yason usocket bordeaux-threads eclector named-readtables hunchentoot swank log4cl closer-mop local-time jzon ];
  closure = ps: let next = pkgs.lib.unique (ps ++ pkgs.lib.concatMap (p: p.lispLibs or []) ps); in if builtins.length next == builtins.length ps then ps else closure next;
  dep = closure bibliotheques;
  conforme = builtins.all (p: builtins.any (l: l.name == p.pname && l.version == p.version && l.src == toString p.src) lock.bibliotheques) dep;
in assert conforme;
pkgs.runCommand "mrjam-sources-outils-mcp" {} ''
  mkdir -p $out/sources
  ${pkgs.lib.concatMapStringsSep "\n" (p: "ln -s ${p.src} $out/sources/${pkgs.lib.strings.sanitizeDerivationName p.pname}") dep}
  ${pkgs.lib.concatMapStringsSep "\n" (p: "ln -s ${p.path} $out/sources/${p.name}") projets}
  cp ${./mcp.lock.json} $out/mcp.lock.json
''
