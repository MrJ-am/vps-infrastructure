{ lib, runCommand, python3, binding ? ./binding.json }:
runCommand "mrjam-passkey-nginx-route-1" { } ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./route.py} "$out/lib/route.py"
  cp ${../preflight_passkey_nginx.py} "$out/lib/preflight_passkey_nginx.py"
  cp ${binding} "$out/lib/binding.json"
  cat > "$out/bin/mrjam-passkey-nginx-route" <<'EOF'
  #!${python3}/bin/python3 -I
  import runpy
  runpy.run_path("@out@/lib/route.py", run_name="__main__")
  EOF
  substituteInPlace "$out/bin/mrjam-passkey-nginx-route" --replace-fail '@out@' "$out"
  chmod 0555 "$out/bin/mrjam-passkey-nginx-route"
''
