{ pkgs }:
pkgs.runCommand "mrjam-first-cutover-boot-guard" { } ''
  mkdir -p "$out/libexec" "$out/bin"
  cp ${./cutover.py} "$out/libexec/cutover.py"
  cp ${./system_control.py} "$out/libexec/system_control.py"
  cp ${./boot_guard.py} "$out/libexec/boot_guard.py"
  cat > "$out/bin/mrjam-first-cutover-guard" <<EOF
  #!${pkgs.runtimeShell}
  exec ${pkgs.python3}/bin/python3 -I -S -c 'import sys; sys.path.insert(0, "$out/libexec"); import boot_guard; raise SystemExit(boot_guard.main())' "\$@"
  EOF
  chmod 0555 "$out/bin/mrjam-first-cutover-guard"
''
