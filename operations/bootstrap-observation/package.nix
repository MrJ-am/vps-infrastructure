{ lib, runCommand, python3, bash, coreutils, systemd }:
let
  probe = ../probes/adoption-v2;
  pins = {
    "adoption_probe.py" = "a93b1abf4b30852b1ac844fce56c7b077a2fd1d382e0eb3ddf95d2189ef2d628";
    "validate_report.py" = "c82e66018ac9f35ccb3b52a33a9ec7ab2f54f55962410a55cd8c50134e1625d1";
    "adoption.schema.json" = "4cd2b1949bb2229a3254ae5f0dd98608ce5683bf5e7bee28a297ad95b3d03036";
  };
  runtime = builtins.toJSON {
    python = "${python3}/bin/python3";
    systemd_run = "${systemd}/bin/systemd-run";
    systemctl = "${systemd}/bin/systemctl";
  };
in
assert lib.assertMsg (lib.versionAtLeast python3.version "3.11") "Python 3.11+ required";
assert lib.assertMsg (lib.all (name: builtins.hashFile "sha256" (probe + "/${name}") == pins.${name}) (builtins.attrNames pins)) "Pinned V2 probe differs";
runCommand "mrjam-observe-adoption-v2" {
  inherit runtime;
  passAsFile = [ "runtime" ];
  preferLocalBuild = true;
  allowSubstitutes = false;
} ''
  mkdir -p "$out/bin" "$out/libexec/probe"
  cp ${./observe.py} "$out/libexec/observe.py"
  cp ${./collect.py} "$out/libexec/collect.py"
  cp ${./bounded.py} "$out/libexec/bounded.py"
  cp "$runtimePath" "$out/libexec/runtime.json"
  cp ${probe}/adoption_probe.py ${probe}/validate_report.py ${probe}/adoption.schema.json "$out/libexec/probe/"
  printf '#!${bash}/bin/bash -p\nexec ${coreutils}/bin/env -i LANG=C LC_ALL=C ${python3}/bin/python3 -I -S %s/libexec/observe.py "$@"\n' "$out" > "$out/bin/mrjam-observe-adoption"
  chmod 0555 "$out/bin/mrjam-observe-adoption"
''
