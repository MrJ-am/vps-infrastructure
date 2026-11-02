# Public ISRG roots extracted from the preserved host's nss-cacert 3.126.
# X1 DER: 96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6
# X2 DER: 69729b8e15a86efc177a57afb7171dfc64add28c2fca8cf1507e34453ccb1470
{ pkgs }:
assert builtins.hashFile "sha256" ./public-ca.pem == "0cd98d2dd7a71afe5e2e93673933f15254c5a41a9be4682f27ec582e72c52ce0";
pkgs.writeTextDir "ca.pem" (builtins.readFile ./public-ca.pem)
