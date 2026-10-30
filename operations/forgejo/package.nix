{ lib, stdenvNoCC, fetchurl, writeShellScript, formats, pandoc, coreutils, python3, forgejo, forgejo-runner }:
let
  lock = builtins.fromJSON (builtins.readFile ./versions.lock.json);
  sources = builtins.fromJSON (builtins.readFile ./sources.lock.json);
  archive = name: fetchurl { inherit (lock.assets.${name}) url hash; };
  render = writeShellScript "forgejo-pandoc-org" ''
    set -eu
    ulimit -v 1048576
    exec ${coreutils}/bin/timeout 20s ${pandoc}/bin/pandoc \
      --sandbox --from=org --to=html5 --mathjax --wrap=none \
      --lua-filter=${./org-links.lua}
  '';
  settings = import ./settings.nix { renderCommand = toString render; };
  ini = (formats.ini { }).generate "forgejo-candidate.ini" settings;
in
assert lib.assertMsg (forgejo.version == lock.candidate.forgejo) "Forgejo candidate version changed; requalify first";
assert lib.assertMsg (forgejo-runner.version == lock.candidate.forgejo_runner) "Runner candidate version changed; requalify first";
assert lib.assertMsg (pandoc.version == lock.candidate.pandoc) "Pandoc candidate version changed; requalify first";
assert lib.assertMsg (builtins.all (entry:
  builtins.hashFile "sha256" (./. + "/${entry.destination}") == entry.sha256
) sources.files) "Audited Forgejo static source changed";
stdenvNoCC.mkDerivation {
  pname = "mrjam-forgejo-preparation";
  version = "20261030";
  dontUnpack = true;
  nativeBuildInputs = [ python3 ];
  buildCommand = ''
    mkdir -p "$out/share/forgejo-org/mathjax" "$out/share/forgejo-org/font" "$out/review"
    tar -xzf ${archive "mathjax"} --strip-components=1 -C "$out/share/forgejo-org/mathjax"
    tar -xzf ${archive "font"} --strip-components=1 -C "$out/share/forgejo-org/font"
    cp ${./assets/config.js} "$out/share/forgejo-org/config.js"
    cp ${./assets/org.css} "$out/share/forgejo-org/org.css"
    cp ${./assets/footer.tmpl} "$out/review/footer.tmpl"
    cp ${ini} "$out/review/forgejo-candidate.ini"
    cp ${./runtime-references.json} "$out/review/runtime-references.json"
    cp ${./runner-policy.json} "$out/review/runner-policy.json"
    cp ${./sources.lock.json} "$out/review/sources.lock.json"
    cp ${./versions.lock.json} "$out/review/versions.lock.json"
    cp ${./README.org} "$out/review/README.org"
    test -s "$out/share/forgejo-org/mathjax/tex-chtml.js"
    test -d "$out/share/forgejo-org/font/chtml/woff2"
    test -s "$out/share/forgejo-org/config.js"
    python3 ${./tests/check_output.py} "$out"
  '';
  passthru = { inherit settings render; };
  meta.description = "Non-activating Forgejo settings and assets for independent review";
}
