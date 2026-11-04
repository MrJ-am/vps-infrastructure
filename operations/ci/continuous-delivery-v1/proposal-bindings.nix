# Only the protected constructor supplies these arguments. Candidate Nix is
# never evaluated: the input is an exact source manifest and generated policy.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {}, preparedSource, policyFile, proposal
, cargoVendor ? builtins.storePath /nix/store/ivbh7z3jxnh58sc15klrmhg4z8jhiqf4-cargo-vendor-dir
}:
assert builtins.match "[0-9a-f]{64}" proposal != null;
assert builtins.hashFile "sha256" (preparedSource+"/manifest.json") == proposal;
let
  validator=import ./aligned-validator.nix {inherit pkgs policyFile cargoVendor;};
  report=builtins.fromJSON (builtins.readFile policyFile);
  source=pkgs.runCommand ("mrjam-admitted-source-"+builtins.substring 0 12 proposal) {
    nativeBuildInputs=[pkgs.python3];
    inputSource=preparedSource;
  } ''
    mkdir "$out"
    cp ${../../forgejo/stage_sources.py} stage_sources.py
    cp ${../../forgejo/worker.py} worker.py
    python3 -I -S - "$PWD" "$inputSource" "$out" <<'PY'
    import hashlib,os,pathlib,sys
    sys.path.insert(0,sys.argv[1]);import stage_sources as S
    root=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3])
    # Store ownership is remapped inside some Nix build namespaces. The
    # trusted derivation supplies this read-only store path, not a PR argument.
    S.require(str(root).startswith('/nix/store/') and root.parent==pathlib.Path('/nix/store'),'STORE_INPUT_REQUIRED')
    owner=root.lstat().st_uid
    raw=S.source_bytes(root/'manifest.json',S.MAX_MANIFEST,owner)
    manifest,names,directories=S.manifest(raw,'${proposal}','${report.rules_revision}')
    S.source_tree(root,names,directories,owner)
    for entry in manifest['files']:
        data=S.source_bytes(root/entry['path'],S.MAX_BYTES,owner)
        S.require(len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],'SOURCE_BYTES_REFUSED')
        destination=out/entry['path'];destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(data);destination.chmod(0o444)
    (out/'manifest.json').write_bytes(raw);(out/'manifest.json').chmod(0o444)
    PY
  '';
  closure=pkgs.closureInfo {rootPaths=[validator];};
in {inherit validator source proposal closure;}
