{ lib, stdenvNoCC, python3, makeWrapper, provisionPackage }:
# Use the derivation, or builtins.storePath for an already qualified package.
# A bare Nix path would copy/rename the package and break the exact binding.
assert !(builtins.isPath provisionPackage);
assert lib.hasPrefix "/nix/store/" (toString provisionPackage);
stdenvNoCC.mkDerivation {
  pname = "mrjam-kanidm-worker-result-probe";
  version = "1";
  src = lib.fileset.toSource { root = ./.; fileset = ./result_probe.py; };
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/libexec" "$out/bin"
    install -m644 result_probe.py "$out/libexec/result_probe.py"
    cat > "$out/libexec/result-public.json" <<'JSON'
    ${builtins.toJSON { provision_module = "${provisionPackage}/libexec/provision.py"; }}
    JSON
    makeWrapper ${python3}/bin/python3 "$out/bin/mrjam-kanidm-worker-result-probe" \
      --add-flags "-I -S $out/libexec/result_probe.py"
  '';
  meta.platforms = [ "x86_64-linux" ];
}
