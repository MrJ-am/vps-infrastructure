{ lib, runCommandNoCC, python3, materialized, artifactLock, expectedLockSha256
, runtimeReferences }:
let
  frontendOutputs = {
    audition = "audition"; log = "log"; logique = "logique"; mateval = "mateval";
    style = "style"; logo = "style-logo"; vision = "vision";
  };
  lock = builtins.fromJSON (builtins.readFile artifactLock);
  inputs = builtins.path {
    path = materialized;
    name = "mrjam-qualified-public-artifacts";
    filter = path: type:
      (type == "directory" && path == toString materialized) ||
      (type == "regular" && builtins.elem (builtins.baseNameOf path)
        [ "server" "frontend.tar" "verification.json" ]);
  };
in
assert lib.assertMsg (builtins.hashFile "sha256" artifactLock == expectedLockSha256)
  "The artifact import lock differs from its reviewed bytes.";
assert lib.assertMsg (runtimeReferences != [ ])
  "The qualified ELF's exact runtime references must be supplied, not inferred from a version label.";
runCommandNoCC "mrjam-qualified-artifacts-${builtins.substring 0 12 lock.proposal_sha256}" {
  outputs = [ "out" ] ++ builtins.attrNames frontendOutputs;
  nativeBuildInputs = [ python3 ];
  # Retain the exact already-built runtime paths used by the qualified ELF.
  buildInputs = runtimeReferences;
  disallowedReferences = [ inputs ];
  passthru = { inherit expectedLockSha256 frontendOutputs; productionAuthorized = false; };
} ''
  ${python3}/bin/python3 -I -S ${./import_qualified.py} \
    ${inputs} ${artifactLock} ${lib.escapeShellArg expectedLockSha256} "$out"
  ${lib.concatStringsSep "\n" (lib.mapAttrsToList (output: site: ''
    # Runtime configuration accepts immutable store roots, not arbitrary paths.
    # Each frontend therefore has its own output containing its exact manifest.
    test -f "$out/share/mrjam/frontends/${site}/artifact.json"
    mkdir -p "$${output}"
    cp -R "$out/share/mrjam/frontends/${site}/." "$${output}/"
    cmp "$out/share/mrjam/frontends/${site}/artifact.json" "$${output}/artifact.json"
  '') frontendOutputs)}
  # runCommandNoCC has no strip, patchelf, minifier or compiler phase.
''
