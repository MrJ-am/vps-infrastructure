# Local validated output only; this does not assert a production signature.
import ./delivery-server.nix {
  rawServer=../../../.local/deployment-20261101/aligned-native-validation-002/artifacts/server;
  expectedSha256="5e183a30c9b33d0ea02302a55515c73b49988ceb60f68879af8934f72e6eb1cb";
  expectedBytes=13383152;
  proposal="04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d";
}
