{ pkgs }:
pkgs.runCommand "synthetic-delivery-migration-program" { } ''
  mkdir -p "$out/bin"
  cat > "$out/bin/apply" <<'PY'
  #!${pkgs.python3}/bin/python3
  import os,sys
  from pathlib import Path
  root=Path(os.environ['MRJAM_MIGRATION_FIXTURE'])
  if not (root/'.synthetic').is_file(): raise SystemExit(2)
  action=Path(sys.argv[0]).name
  with (root/'calls').open('a') as stream: stream.write(action+'\n')
  if action=='quiesce': (root/'paused').touch()
  if action=='apply': (root/'changed').touch()
  if action=='verify' and (root/'fail_verify').exists(): raise SystemExit(3)
  if action=='resume':
      (root/'paused').unlink(missing_ok=True)
      if (root/'fail_resume').exists(): raise SystemExit(4)
  if action=='recover':
      (root/'changed').unlink(missing_ok=True)
      (root/'paused').unlink(missing_ok=True)
  PY
  chmod +x "$out/bin/apply"
  for action in check verify recover quiesce resume; do
    ln -s apply "$out/bin/$action"
  done
''
