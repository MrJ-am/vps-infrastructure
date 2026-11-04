# Vérification systemd de l'identité

`runtime-systemd.nix` construit une VM NixOS de 2 Go et deux cœurs, avec PostgreSQL,
Kanidm et le broker réels, des certificats et des données exclusivement inventés.
Elle importe le module de production sans élargir ses permissions. Deux
`ExecStartPre` de test vérifient l'accès au credential et la lecture seule du
source depuis le bac à sable effectif. Les diagnostics des services restent
désactivés.

```sh
nix-build operations/identity/runtime-systemd.nix \
  --arg nixpkgs /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source \
  --argstr artifact /nix/store/ARTEFACT-QUALIFIE \
  --argstr acceleration kvm --max-jobs 1 --cores 2 --no-out-link
```

Les neuf groupes couvrent l'absence de démarrage automatique, l'adoption SQLite,
`LoadCredential` sous UID 984, le rôle PostgreSQL limité par `peer`, la projection
minimale 0640, le refus du mauvais UID sur le socket d'admission, un lecteur déjà
ouvert pendant le rafraîchissement de l'inode, la conservation des sessions après
redémarrage et l'activation explicite du timer. Un fichier témoin appartenant à
un autre UID détecte un changement global de propriétaire.

Le reçu final `runtime-result-002.json` rapporte les neuf groupes réussis avec
le binaire `21dd879f5040fbde94a36ffea05ff7a1a055b0fa5a15ad0e45405d750bed243b`.
L'arrêt attend la fin de la projection puis vérifie que les trois services sont
inactifs, sans processus résiduel.

Le reçu `identity-runtime-result.json` lie les empreintes du binaire, du module,
du test et de la fixture. Les premiers échecs et la correction de l'hypothèse
sur la représentation ACL de `LoadCredential` restent consignés dans
`runtime-initial-findings.json`. Une réussite ne qualifie ni les comptes réels,
ni une MFA humaine, ni Nginx, ni la bascule du VPS.
