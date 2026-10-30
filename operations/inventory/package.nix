{ lib, runCommand, python3, bash, coreutils, uid, gid, publicKeys }:
let
  runtime = builtins.toJSON {
    inherit uid gid publicKeys;
    python = "${python3}/bin/python3";
    bash = "${bash}/bin/bash";
    legacyRunnerSha256 = "5e888ab7ae7a7a3ecef742941ff0f47720790979ffe9c1ff744e4b879665a201";
  };
in
assert lib.assertMsg (lib.versionAtLeast python3.version "3.11") "Inventory requires Python >= 3.11";
runCommand "mrjam-inventory-v1" {
  inherit runtime;
  passAsFile = [ "runtime" ];
  nativeBuildInputs = [ python3 ];
  preferLocalBuild = true;
  allowSubstitutes = false;
} ''
  mkdir -p "$out/bin" "$out/libexec/probe"
  cp ${./runner.py} "$out/libexec/runner.py"
  cp ${./policy.json} "$out/libexec/policy.json"
  cp ${./public_keys.py} "$out/libexec/public_keys.py"
  cp ${./adoption.py} "$out/libexec/adoption.py"
  cp ${./effective_ssh.py} "$out/libexec/effective_ssh.py"
  cp "$runtimePath" "$out/libexec/runtime.json"
  cp ${./probe/inventory.py} "$out/libexec/probe/inventory.py"
  cp ${./probe/validate_report.py} "$out/libexec/probe/validate_report.py"
  cp ${./probe/inventory.schema.json} "$out/libexec/probe/inventory.schema.json"
  substitute ${./login.sh.in} "$out/bin/mrjam-inventory-login" \
    --replace-fail '@bash@' '${bash}' \
    --replace-fail '@coreutils@' '${coreutils}' \
    --replace-fail '@python@' '${python3}' \
    --replace-fail '@out@' "$out"
  for entry in adoption effective_ssh; do
    printf '#!${bash}/bin/bash -p\nexec ${coreutils}/bin/env -i LANG=C LC_ALL=C ${python3}/bin/python3 -I -S %s/libexec/%s.py "$@"\n' "$out" "$entry" > "$out/bin/mrjam-inventory-$entry"
  done
  chmod 0555 "$out/bin/"*
  python3 - "$out" <<'PY'
import hashlib, importlib.util, json, pathlib, sys
root = pathlib.Path(sys.argv[1]) / "libexec"
policy = json.loads((root / "policy.json").read_text())
for item in policy["files"]:
    data = (root / "probe" / item["name"]).read_bytes()
    assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"], "PROBE_INTEGRITY_FAILED"
spec = importlib.util.spec_from_file_location("keys", root / "public_keys.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
runtime = json.loads((root / "runtime.json").read_text())
assert 1 <= len(runtime["publicKeys"]) <= 4 and len(set(runtime["publicKeys"])) == len(runtime["publicKeys"]) and all(module.valid(key) for key in runtime["publicKeys"]), "INVALID_PUBLIC_KEY"
assert type(runtime["uid"]) is int and type(runtime["gid"]) is int and runtime["uid"] > 0 and runtime["gid"] > 0, "INVALID_ACCOUNT_ID"
PY
''
