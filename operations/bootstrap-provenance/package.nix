{ lib, runCommand, python3, bash, coreutils, systemd }:
let
  original = ../probes/adoption-v2;
  runtime = builtins.toJSON {
    python = "${python3}/bin/python3";
    systemd_run = "${systemd}/bin/systemd-run";
    systemctl = "${systemd}/bin/systemctl";
  };
in
assert lib.versionAtLeast python3.version "3.11";
assert builtins.hashFile "sha256" (original + "/adoption_probe.py") == "a93b1abf4b30852b1ac844fce56c7b077a2fd1d382e0eb3ddf95d2189ef2d628";
assert builtins.hashFile "sha256" (original + "/validate_report.py") == "c82e66018ac9f35ccb3b52a33a9ec7ab2f54f55962410a55cd8c50134e1625d1";
runCommand "mrjam-observe-provenance-v1" {
  inherit runtime;
  passAsFile = [ "runtime" ];
  nativeBuildInputs = [ python3 ];
  preferLocalBuild = true;
  allowSubstitutes = false;
} ''
  mkdir -p "$out/bin" "$out/libexec/probe"
  cp ${./observe.py} "$out/libexec/observe.py"
  cp ${./collect.py} "$out/libexec/collect.py"
  cp ${../bootstrap-observation/bounded.py} "$out/libexec/bounded.py"
  cp ${original + "/adoption_probe.py"} "$out/libexec/adoption_probe.py"
  cp ${original + "/validate_report.py"} "$out/libexec/schema_core.py"
  cp "$runtimePath" "$out/libexec/runtime.json"
  cp ${./probe/provenance_probe.py} "$out/libexec/probe/provenance_probe.py"
  cp ${./probe/validate_report.py} "$out/libexec/probe/validate_report.py"
  cp ${./probe/provenance.schema.json} "$out/libexec/probe/provenance.schema.json"
  printf '#!${bash}/bin/bash -p\nexec ${coreutils}/bin/env -i LANG=C LC_ALL=C ${python3}/bin/python3 -I -S %s/libexec/observe.py "$@"\n' "$out" > "$out/bin/mrjam-observe-provenance"
  chmod 0555 "$out/bin/mrjam-observe-provenance"
  ${python3}/bin/python3 -I -S - "$out" <<'PY'
import importlib.util, pathlib, sys
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("provenance_filter", root / "libexec/probe/validate_report.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.schema()
PY
''
