{ lib, runCommand, python3, bash, coreutils, systemd, nix }:
let
  runtime = builtins.toJSON {
    python = "${python3}/bin/python3";
    systemd_run = "${systemd}/bin/systemd-run";
    systemctl = "${systemd}/bin/systemctl";
    nix = "${nix}/bin/nix";
  };
in
assert lib.versionAtLeast python3.version "3.11";
runCommand "mrjam-observe-services-v1" {
  inherit runtime; passAsFile = [ "runtime" ];
  nativeBuildInputs = [ python3 ];
  preferLocalBuild = true; allowSubstitutes = false;
} ''
  mkdir -p "$out/bin" "$out/libexec"
  cp ${./observe.py} "$out/libexec/observe.py"
  cp ${./collect.py} "$out/libexec/collect.py"
  cp ${./contract.py} "$out/libexec/contract.py"
  cp ${./validate_report.py} "$out/libexec/validate_report.py"
  cp ${../bootstrap-observation/bounded.py} "$out/libexec/bounded.py"
  cp "$runtimePath" "$out/libexec/runtime.json"
  printf '#!${bash}/bin/bash -p\nexec ${coreutils}/bin/env -i LANG=C LC_ALL=C ${python3}/bin/python3 -I -S %s/libexec/observe.py "$@"\n' "$out" > "$out/bin/mrjam-observe-services"
  chmod 0555 "$out/bin/mrjam-observe-services"
''
