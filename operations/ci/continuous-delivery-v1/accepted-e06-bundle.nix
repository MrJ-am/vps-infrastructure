# Exact signed run5 artifacts received over authenticated SSH, hashes checked.
# Qualification/build input only; activation separately verifies live authority.
import ./delivery-bundle.nix {
  artifactRoot=../../../.local/deployment-20261101/accepted-e06-artifacts;
  proposal="e06f030310aed4f8ff1cb0c5b836848dfcd9d4e99b926c841f7619b477fdd7e7";
  serverSha256="5e183a30c9b33d0ea02302a55515c73b49988ceb60f68879af8934f72e6eb1cb";
  serverBytes=13383152;
  frontendSha256="6867aa7273682361e79dfa2fb968b0d269f70e6b27ccd28953310d7a192fe8ad";
  reportPolicy=../../../.local/deployment-20261101/accepted-e06-artifacts/policy.json;
  reportPolicySha256="4f31c738c7353ef477a6ea0fc5472ea60a7d8da5d9bec8a618be23c3478ecd4f";
  toolchainsSha256="27c05033dd0a7347ccdba0afb4caed5bb359eaeeeb1dd1fedb92ef8dc5701eae";
  slot="blue";configFile=../../hosts/mrjam-vps/runtime-blue.json;
}
