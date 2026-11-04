# Separate post-release generation: only LLMNR is disabled.
# CI imports are omitted because even disabled imports reorder tmpfiles rules.
{ ... }: {
  imports = [ ./candidate-promoted.nix ./resolver-unicast.nix ];
}
