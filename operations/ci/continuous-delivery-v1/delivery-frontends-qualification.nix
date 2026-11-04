# Local validation artifacts, not a production release authorization.
import ./delivery-frontends.nix {
  archive=../../../.local/deployment-20261101/aligned-native-validation-002/artifacts/frontend.tar;
  expectedSha256="f3db1448bf4dfb9e88dace2d3e5b6932f19bde9033947f8e31a85d0e132ae8f6";
  proposal="04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
  reportPolicy=/nix/store/wpwr3rby105fha7vckv6dywfnyqmsr8n-mrjam-aligned-validator-policy.json;
  reportPolicySha256="be4a54ba570c87dcc53f4522e77c748e14b9fe1aa5fb9995a7600a949510a8e9";
  toolchainsSha256="27c05033dd0a7347ccdba0afb4caed5bb359eaeeeb1dd1fedb92ef8dc5701eae";
}
