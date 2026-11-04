{ lib, stdenvNoCC, python3, makeWrapper, systemd, kanidmCaFile }:
let runtime = python3.withPackages (p: [ p.cryptography ]);
in stdenvNoCC.mkDerivation {
  pname = "mrjam-kanidm-passkey-portal";
  version = "1";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./portal.py ./index.html ./portal.js ./style.css ./test_portal.py ];
  };
  nativeBuildInputs = [ runtime makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    ${runtime}/bin/python3 -I -m unittest discover -s . -p test_portal.py -v
  '';
  installPhase = ''
    mkdir -p "$out/libexec" "$out/bin"
    install -m644 portal.py index.html portal.js style.css "$out/libexec/"
    install -m644 ${kanidmCaFile} "$out/libexec/ca.pem"
    cat > "$out/libexec/public.json" <<'JSON'
    ${builtins.toJSON { ca_sha256 = builtins.hashFile "sha256" kanidmCaFile; systemctl = "${systemd}/bin/systemctl"; }}
    JSON
    makeWrapper ${runtime}/bin/python3 "$out/bin/mrjam-kanidm-passkey-portal" \
      --add-flags "-I $out/libexec/portal.py"
  '';
  meta.platforms = [ "x86_64-linux" ];
}
