{ pkgs }:
let
  commands = builtins.toJSON {
    systemctl = "${pkgs.systemd}/bin/systemctl";
    psql = "${pkgs.postgresql_17}/bin/psql";
    pg_dump = "${pkgs.postgresql_17}/bin/pg_dump";
    pg_restore = "${pkgs.postgresql_17}/bin/pg_restore";
    age = "${pkgs.age}/bin/age";
    age_keygen = "${pkgs.age}/bin/age-keygen";
    tar = "${pkgs.gnutar}/bin/tar";
  };
in pkgs.runCommand "mrjam-vise-coherent-backup-1" {} ''
  mkdir -p "$out/bin" "$out/lib"
  cp ${./capture.py} "$out/lib/capture.py"
  cp ${./envelope.py} "$out/lib/envelope.py"
  cp ${./transaction.py} "$out/lib/transaction.py"
  cp ${./retention.py} "$out/lib/retention.py"
  substitute ${./service.py} "$out/lib/service.py" \
    --replace-fail '@commands_json@' ${pkgs.lib.escapeShellArg commands}
  for action in capture recover; do
    cat > "$out/bin/mrjam-vise-backup-$action" <<SH
  #!${pkgs.runtimeShell}
  test "\$#" -eq 0 || exit 64
  exec ${pkgs.python3}/bin/python3 -B -E -s "$out/lib/service.py" $action
  SH
    chmod +x "$out/bin/mrjam-vise-backup-$action"
  done
''
