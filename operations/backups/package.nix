{ pkgs }:
let
  commands = builtins.toJSON {
    systemctl = "${pkgs.systemd}/bin/systemctl";
    runuser = "${pkgs.util-linux}/bin/runuser";
    pg_dump = "${pkgs.postgresql_17}/bin/pg_dump";
    pg_restore = "${pkgs.postgresql_17}/bin/pg_restore";
    age = "${pkgs.age}/bin/age";
    age_keygen = "${pkgs.age}/bin/age-keygen";
    tar = "${pkgs.gnutar}/bin/tar";
  };
in pkgs.runCommand "mrjam-native-component-backup-1" { } ''
  mkdir -p "$out/bin" "$out/libexec"
  substitute ${./native.py} "$out/libexec/native.py" \
    --replace-fail '@commands_json@' ${pkgs.lib.escapeShellArg commands}
  cat > "$out/bin/mrjam-native-backup" <<SH
  #!${pkgs.runtimeShell}
  exec ${pkgs.python3}/bin/python3 "$out/libexec/native.py" "\$@"
  SH
  chmod +x "$out/bin/mrjam-native-backup"
''
