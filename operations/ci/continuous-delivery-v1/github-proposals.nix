{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
pkgs.runCommand "mrjam-github-proposal-discovery-1" {
  nativeBuildInputs = [ pkgs.makeWrapper pkgs.python3 ];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./github-app-receive.py} "$out/lib/github_app_auth.py"
  cp ${./github-proposals.py} "$out/lib/github_proposals.py"
  substituteInPlace "$out/lib/github_app_auth.py" --replace-fail \
    '/nix/store/fya253x5ky7rhfz6rkgdwjr1fzf7fy71-openssl-3.6.5-bin/bin/openssl' '${pkgs.openssl}/bin/openssl'
  cat > "$out/lib/entry.py" <<'PY'
  import json,re,sys,traceback
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parent))
  import github_proposals
  try:github_proposals.main()
  except Exception as failure:
      frames=traceback.extract_tb(failure.__traceback__)
      code=str(failure) if isinstance(failure,github_proposals.A.Refused) else 'PROPOSAL_DISCOVERY_FAILED'
      if not re.fullmatch('[A-Z_]{1,80}',code):code='PROPOSAL_DISCOVERY_FAILED'
      print(json.dumps({'code':code,'exception_type':type(failure).__name__,
          'source':Path(frames[-1].filename).name,'line':frames[-1].lineno}))
      raise SystemExit(1) from None
  PY
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-github-discover" \
    --add-flags "-I -S $out/lib/entry.py"
  python3 - "$out/lib" <<'PY'
  import ast,pathlib,sys
  for path in pathlib.Path(sys.argv[1]).glob('*.py'):ast.parse(path.read_bytes())
  PY
''
