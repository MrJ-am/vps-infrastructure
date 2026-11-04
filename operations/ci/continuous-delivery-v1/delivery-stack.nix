# A single dependency graph for the protected services. Building is not adoption.
{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {},
 anchorControl, enableVise ? false}:
let
  anchor=if builtins.isAttrs anchorControl then anchorControl else builtins.storePath anchorControl;
  admission=import ./admission-controller.nix {inherit pkgs enableVise;anchorControl=anchor;};
  acceptance=import ./acceptance-services.nix {
    inherit pkgs enableVise;anchorControl=anchor;admissionController=admission;
  };
  preparation=import ./delivery-preparation-package.nix {
    inherit pkgs enableVise;admissionControl=anchor;admissionController=admission;
  };
  staging=import ./staging-service.nix {
    inherit pkgs;anchorControl=anchor;admissionController=admission;acceptanceServices=acceptance;
  };
  promotion=import ./promotion-service.nix {
    inherit pkgs enableVise;anchorControl=anchor;admissionController=admission;
  };
  descriptor=pkgs.writeText "mrjam-delivery-stack.json" (builtins.toJSON {
    schema_version=1;deployment_authorized=false;inherit enableVise;
    packages=builtins.mapAttrs (_: value: toString value) {
      inherit anchor admission acceptance preparation staging promotion;
    };
  });
in pkgs.runCommand "mrjam-protected-delivery-stack-1" {
  passthru={inherit anchor admission acceptance preparation staging promotion descriptor;};
} ''
  mkdir "$out"
  cp ${descriptor} "$out/descriptor.json"
  ${pkgs.lib.concatMapStringsSep "\n" (name: "ln -s " + toString {
    inherit anchor admission acceptance preparation staging promotion;
  }.${name} + " \"$out/${name}\"") ["anchor" "admission" "acceptance" "preparation" "staging" "promotion"]}
''
