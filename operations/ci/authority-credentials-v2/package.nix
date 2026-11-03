{ pkgs, authorityPolicy, producerBinding }:
let base = pkgs.callPackage ../authority-v1/package.nix { inherit authorityPolicy producerBinding; };
in base.overrideAttrs (old: {
  name = "mrjam-validation-authority-credentials-2";
  buildCommand = old.buildCommand + ''
    cp ${./reader.py} "$out/lib/signing_credential.py"
    ${pkgs.python3}/bin/python3 -I -S - "$out/lib" <<'PY'
    import ast,pathlib,sys
    root=pathlib.Path(sys.argv[1]);path=root/'signer.py';source=path.read_text()
    changes={
      'import collector as S': 'import collector as S\nimport signing_credential as K',
      'key=C.regular_file(private_key_path,owner=os.getuid(),mode=0o400,maximum=4096)': 'key=K.read_key(private_key_path)',
    }
    for before,after in changes.items():
      assert source.count(before)==1
      source=source.replace(before,after)
    path.write_text(source)
    ast.parse(source);ast.parse((root/'signing_credential.py').read_bytes())
    PY
  '';
})
