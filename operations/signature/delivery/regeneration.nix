# Candidate bytes are data. Only the fixed generator runs inside the Nix build.
{sourcePath, pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
let
  python=import ./toolchain.nix {inherit pkgs;};
  source=builtins.path {
    path=sourcePath;name="signature-captured-inputs";
    filter=path: type:
      let name=pkgs.lib.removePrefix (toString sourcePath+"/") (toString path);
      in toString path==toString sourcePath
        || (type=="directory" && builtins.elem name ["fonts" "web" "artwork"])
        || builtins.elem name inputs;
  };
  generator=builtins.fromJSON (builtins.readFile ./generator-provenance.json);
  inputs=["mrjam.sty" "fonts/Parisienne-Regular.ttf" "fonts/Parisienne-OFL.txt"
    "artwork/Echologo.svg" "web/geometry.json" "web/signature.css"
    "web/MrJamSignature.woff2" "web/EchoPoint.woff2"];
in assert builtins.hashFile "sha256" ./reference-generator.py==generator.sha256;
pkgs.runCommand "mrjam-signature-regeneration-qualified-1" {
  nativeBuildInputs=[python];
  passthru={inherit python source;};
} ''
  set -eu
  mkdir -p generated/{fonts,web,artwork,tools}
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    test -f ${source}/${name} && test ! -L ${source}/${name}
  '') inputs}
  ${pkgs.lib.concatMapStringsSep "\n" (name: ''
    cp ${source}/${name} generated/${name}
  '') ["mrjam.sty" "fonts/Parisienne-Regular.ttf" "fonts/Parisienne-OFL.txt" "artwork/Echologo.svg"]}
  cp ${./reference-generator.py} generated/tools/build-web.py
  python3 -I generated/tools/build-web.py
  mkdir "$out"
  python3 -I ${./verify_generated.py} ${source} "$PWD/generated" "$out/verification.json"
  cp ${./generator-provenance.json} "$out/generator.json"
  # Local qualification output only; this derivation is never an app delivery.
  mkdir "$out/generated"
  cp -r generated/web "$out/generated/web"
''
