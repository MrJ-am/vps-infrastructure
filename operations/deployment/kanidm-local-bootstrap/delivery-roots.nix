# Delivery preserves the already-upgraded V3 unit. No service is started.
{
  package = builtins.storePath "/nix/store/5yqv8fsy6qhw45qs53qnirib9vl3cjhq-mrjam-kanidm-worker-provision-2";
  unit = builtins.storePath "/nix/store/w25djyzhrrbkc46fvzb7zjcbp1c2j549-unit-mrjam-kanidm-worker-provision.service";
  bootstrapPackage = builtins.storePath "/nix/store/y7viyzl5v93ac9jr1pzavjqx0n3knlnw-mrjam-kanidm-local-bootstrap-1";
}
