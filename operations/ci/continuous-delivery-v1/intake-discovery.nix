{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let original=import ./github-proposals.nix {inherit pkgs;};
in pkgs.runCommand "mrjam-persistent-intake-discovery-1" {nativeBuildInputs=[pkgs.makeWrapper pkgs.python3];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${original}/lib/github_app_auth.py ${original}/lib/github_proposals.py "$out/lib/"
  cp ${./intake_queue.py} "$out/lib/intake_queue.py"
  cp ${./source_snapshot.py} "$out/lib/source_snapshot.py"
  cat > "$out/lib/entry.py" <<'PY'
  import json,os,re,sys,time
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parent))
  import github_proposals as P
  import intake_queue as Q
  try:
      P.main()
      state=Path(os.environ['STATE_DIRECTORY']).resolve(strict=True)
      snapshot=json.loads((state/'proposals.json').read_bytes())
      queue=Q.Queue(state)
      try:queue.observe(snapshot['proposals'],int(time.time()))
      finally:queue.close()
      print(json.dumps({'code':'PROPOSALS_QUEUED','proposals':len(snapshot['proposals']),'admission_performed':False}))
  except Exception as error:
      code=str(error) if isinstance(error,(Q.S.Refused,P.A.Refused)) else 'PERSISTENT_INTAKE_DISCOVERY_FAILED'
      if not re.fullmatch('[A-Z_]{1,80}',code):code='PERSISTENT_INTAKE_DISCOVERY_FAILED'
      print(json.dumps({'code':code,'exception_type':type(error).__name__}))
      raise SystemExit(1) from None
  PY
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/mrjam-github-discover" --add-flags '-I -S' --add-flags "$out/lib/entry.py"
  python3 -I -S - "$out/lib" <<'PY'
  import sys
  sys.path.insert(0,sys.argv[1])
  import intake_queue
  PY
''
