{ pkgs }:
let kanidm = builtins.storePath "/nix/store/64r3qy45dngms51i718ddna9p08lczd2-kanidm-1.11.2";
in pkgs.runCommand "mrjam-native-kanidm-backup-restore-synthetic" {
  nativeBuildInputs = [ pkgs.python3 pkgs.openssl ];
} ''
  mkdir "$out"
  python3 ${./kanidm_qualification.py} ${kanidm}/bin/kanidmd ${pkgs.openssl}/bin/openssl "$out/result.json"
''
