# No default release: the production manifest and delivery proof are separate.
{ pkgs, releaseFile, releaseSha256 }:
assert builtins.match "[a-f0-9]{64}" releaseSha256 != null;
assert builtins.hashFile "sha256" releaseFile == releaseSha256;
let
  binding = pkgs.runCommand "mrjam-first-release-binding-1" { } ''
    mkdir -p "$out"
    install -m0444 ${releaseFile} "$out/release.json"
  '';
in pkgs.stdenvNoCC.mkDerivation {
  pname = "mrjam-first-release-controller";
  version = "1";
  src = pkgs.lib.fileset.toSource {
    root = ./.;
    fileset = pkgs.lib.fileset.unions [
      ./release_entrypoint.py ./test_release_entrypoint.py
      ./release_backend.py ./cutover.py ./recovery.py ./generation.py
      ./snapshot.py ./system_control.py ./stage_adoption.py ./stage_credentials.py
    ];
  };
  nativeBuildInputs = [ pkgs.python3 pkgs.makeWrapper ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    ${pkgs.python3}/bin/python3 -I -m unittest discover -s . -p test_release_entrypoint.py -v
  '';
  releaseBindingPath = "${binding}/release.json";
  releaseHash = releaseSha256;
  installPhase = ''
    mkdir -p "$out/libexec" "$out/bin"
    install -m0444 release_backend.py cutover.py recovery.py generation.py \
      snapshot.py system_control.py stage_adoption.py stage_credentials.py "$out/libexec/"
    ${pkgs.python3}/bin/python3 -I - <<'PY'
    import os
    from pathlib import Path
    source = Path('release_entrypoint.py').read_text()
    for mode in ('deploy', 'recover'):
        text = source
        for name, value in (('RELEASE_PATH', os.environ['releaseBindingPath']),
                            ('RELEASE_SHA256', os.environ['releaseHash']), ('OPERATION', mode)):
            old = name + ' = None'
            assert text.count(old) == 1
            text = text.replace(old, name + ' = ' + repr(value))
        target = Path(os.environ['out']) / 'libexec' / (mode + '.py')
        compile(text, str(target), 'exec')
        target.write_text(text)
        target.chmod(0o444)
    PY
    for mode in deploy recover; do
      makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-first-release-$mode" \
        --add-flags "-I $out/libexec/$mode.py"
    done
  '';
  passthru = { inherit binding releaseSha256; };
  meta.platforms = [ "x86_64-linux" ];
}
