# Only the root-owned current-state descriptor may select this installed graph.
{stackPath, control}:
args@{config,lib,pkgs,...}:
let
  store=p: builtins.isString p && builtins.match "/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._-]+" p!=null;
  stack=builtins.storePath stackPath;
  descriptor=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (stack+"/descriptor.json")));
  packages=descriptor.packages;
  anchor=builtins.storePath packages.anchor;
  binding=builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (anchor+"/host-binding.json")));
  frozen=builtins.storePath "/nix/store/dnir95r62s6xi57dcygv80fqhirkhzas-mrjam-protected-delivery-recipe-1";
  backup=(import ../../hosts/mrjam-vps/backups.nix {inherit config lib pkgs;}).config;
in
assert store stackPath;
assert builtins.attrNames descriptor==["deployment_authorized" "enableVise" "packages" "schema_version"];
assert descriptor.schema_version==1 && descriptor.deployment_authorized==false && builtins.isBool descriptor.enableVise;
assert builtins.attrNames packages==["acceptance" "admission" "anchor" "preparation" "promotion" "staging"];
assert lib.all store (builtins.attrValues packages);
assert lib.all (n: control.${n}==packages.${n}) ["acceptance" "preparation" "staging"];
assert builtins.attrNames binding==["policy" "producer" "schema_version"] && binding.schema_version==1;
assert binding.policy.producer==binding.producer;
{
  disabledModules=[(frozen+"/operations/ci/continuous-delivery-v1/admission-module.nix")];
  imports=[(moduleArgs: import ./admission-module.nix (moduleArgs // {mrjamInstalledAuthority=packages.anchor;}))];
  services.mrjamValidationAuthority.policy=lib.mkOverride (-10) (builtins.removeAttrs binding.policy ["producer"]);
  environment.etc."mrjam-validation-authority/producer.json".text=lib.mkOverride (-10) (builtins.toJSON binding.producer);
  environment.etc."mrjam-delivery-stack".source=stack;
  # Reuse the exact VM-qualified script; retain the installed schedule,
  # credentials, paths and service isolation. App deliveries import this graph.
  systemd.services.forgejo-backup.script=lib.mkOverride (-10)
    (assert backup._type=="if" && backup.condition;
      backup.content.systemd.services.forgejo-backup.script);
  # Requires=forgejo stops the coordinator during coherent backups. Starting
  # Forgejo again must pull it back in, without changing Restart=no or isolation.
  systemd.services.mrjam-forgejo-runner.wantedBy=lib.mkOverride (-10)
    ["multi-user.target" "forgejo.service"];
  services.mrjamAdmissionController.package=lib.mkOverride (-10) (builtins.storePath packages.admission);
  systemd.services.mrjam-promotion={
    serviceConfig.ExecStart=lib.mkOverride (-10) "${builtins.storePath packages.promotion}/bin/mrjam-promotion";
    unitConfig.ConditionPathExists=lib.mkOverride (-10)
      (if descriptor.enableVise then [] else "/var/lib/mrjam-promotion/plan.json");
  };
}
