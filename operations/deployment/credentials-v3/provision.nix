{ lib, stdenvNoCC, python3, makeWrapper, kanidm_1_11, systemd, kanidmCaFile }:
assert lib.hasPrefix "/nix/store/" (toString kanidmCaFile);
stdenvNoCC.mkDerivation {
  pname = "mrjam-kanidm-worker-provision";
  version = "3";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [ ./adapt.py ./probe.py ./provision.py ./human_login.py ./test_provision.py ];
  };
  nativeBuildInputs = [ python3 makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    ${python3}/bin/python3 -I -S -m unittest discover -s . -p test_provision.py -v
  '';
  installPhase = ''
    mkdir -p "$out/libexec" "$out/bin"
    install -m644 adapt.py probe.py provision.py human_login.py "$out/libexec/"
    install -m644 ${kanidmCaFile} "$out/libexec/ca.pem"
    cat > "$out/libexec/probe-public.json" <<'JSON'
    ${builtins.toJSON { ca_sha256 = builtins.hashFile "sha256" kanidmCaFile; }}
    JSON
    cat > "$out/libexec/human-public.json" <<'JSON'
    ${builtins.toJSON { kanidm = "${kanidm_1_11}/bin/kanidm"; systemctl = "${systemd}/bin/systemctl"; }}
    JSON
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-kanidm-worker-provision" \
      --add-flags "-I -S $out/libexec/provision.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-kanidm-worker-login" \
      --add-flags "-I -S $out/libexec/human_login.py"
  '';
  meta.platforms = [ "x86_64-linux" ];
}
