# Diagnostic-only copy; never activate or admit this as the production verifier.
{ pkgs ? import ../../forgejo/locked-toolchain.nix {} }:
let
  original = import ./aligned-validator.nix { inherit pkgs; };
  runtimeText = builtins.readFile original.runtime;
  oldRuntime = builtins.fromJSON (builtins.unsafeDiscardStringContext runtimeText);
  support = pkgs.runCommand "mrjam-aligned-diagnostic-support" {} ''
    mkdir "$out"
    cp -a ${builtins.storePath oldRuntime.support}/. "$out/"
    chmod -R u+w "$out"
    substituteInPlace "$out/pg_stage.py" --replace-fail \
      'env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,' \
      'env=environment, stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr,'
  '';
  runtime = pkgs.writeText "mrjam-aligned-diagnostic-runtime.json" (builtins.appendContext
    (builtins.toJSON (oldRuntime // { support = toString support; })) (builtins.getContext runtimeText));
  package = pkgs.runCommand "mrjam-aligned-local-diagnostic-2" {} ''
    mkdir "$out"
    cp -a ${original}/. "$out/"
    chmod -R u+w "$out"
    substituteInPlace "$out/bin/mrjam-validate" --replace-fail '${original}/lib/runner.py' "$out/lib/runner.py"
    substituteInPlace "$out/lib/runner.py" --replace-fail '${original.runtime}' '${runtime}'
    cat ${./diagnostic_sandbox.py} >> "$out/lib/sandbox.py"
  '';
in { inherit package; closure = pkgs.closureInfo { rootPaths = [ package ]; }; }
