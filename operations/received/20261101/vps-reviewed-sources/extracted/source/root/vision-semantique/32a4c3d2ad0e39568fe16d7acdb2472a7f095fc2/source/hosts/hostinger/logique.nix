{
  imports = [ ./configuration.nix ../../apps/logique.nix ];
  infrastructure.logique.phase = "https";
}
