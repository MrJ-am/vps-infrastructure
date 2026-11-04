{ pkgs }:
pkgs.runCommand "mrjam-vise-backup-components-tests" {
  VISE_BACKUP_TEST_TOOLS = builtins.toJSON {
    age = "${pkgs.age}/bin/age";
    age_keygen = "${pkgs.age}/bin/age-keygen";
    tar = "${pkgs.gnutar}/bin/tar";
  };
} ''
  mkdir source
  cp ${./capture.py} source/capture.py
  cp ${./envelope.py} source/envelope.py
  cp ${./transaction.py} source/transaction.py
  cp ${./retention.py} source/retention.py
  cp ${./test_capture.py} source/test_capture.py
  cp ${./test_envelope.py} source/test_envelope.py
  cp ${./test_transaction.py} source/test_transaction.py
  cp ${./test_retention.py} source/test_retention.py
  cp ${./test_child_identity.py} source/test_child_identity.py
  ${pkgs.python3}/bin/python3 -B -m unittest discover -s source -v
  mkdir "$out"
  printf '%s\n' '26 tests passed; synthetic files, keys and snapshots only; no real SQL or systemd qualification' > "$out/result.txt"
''
