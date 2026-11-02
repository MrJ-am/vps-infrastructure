{ lib, stdenvNoCC, python3, makeWrapper, openssl, kanidmCaFile }:
assert lib.hasPrefix "/nix/store/" (toString kanidmCaFile);
stdenvNoCC.mkDerivation {
  pname = "mrjam-kanidm-capability-probe";
  version = "1";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./adapt.py ./probe.py ./test_probe.py ];
  };
  nativeBuildInputs = [ python3 makeWrapper openssl ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    ${python3}/bin/python3 -I -S -m unittest discover -s . -p 'test_probe.py' -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm644 probe.py "$out/libexec/probe.py"
    install -m644 adapt.py "$out/libexec/adapt.py"
    install -m644 ${kanidmCaFile} "$out/libexec/ca.pem"
    cat > "$out/libexec/probe-public.json" <<'JSON'
    ${builtins.toJSON { ca_sha256 = builtins.hashFile "sha256" kanidmCaFile; }}
    JSON
    mkdir -p "$out/bin"
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-kanidm-capability-probe" \
      --add-flags "-I -S $out/libexec/probe.py"
    runHook postInstall
  '';
  meta.platforms = [ "x86_64-linux" ];
}
