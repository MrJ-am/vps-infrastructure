# Keep the established service boundaries; replace only their protected recipe.
args@{lib,...}:
let
  mrjamInstalledAuthority=args.mrjamInstalledAuthority or null;
  locked=import ../../forgejo/locked-toolchain.nix {};
  authority=if mrjamInstalledAuthority==null then import ./admission-package.nix {}
    else builtins.storePath mrjamInstalledAuthority;
  binding=if mrjamInstalledAuthority==null then {producer=authority.producer;} else
    builtins.fromJSON (builtins.unsafeDiscardStringContext (builtins.readFile (authority+"/host-binding.json")));
  scope=locked // {callPackage=recipe: supplied:
    assert recipe==../authority-v1/package.nix;authority;};
  original=import ../authority-v1/module.nix (args // {pkgs=scope;});
in original // {
  options=lib.recursiveUpdate original.options {
    services.mrjamValidationAuthority.producerBinding.default=binding.producer;
  };
}
