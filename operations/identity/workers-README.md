# Qualification indépendante des travailleurs natifs

`workers-result-001.json` conserve le reçu inchangé du passage réussi : neuf
groupes en 36,30 secondes, avec les 24 tests de l'adopteur SQLite dans la VM.
La dérivation est
`/nix/store/1mlbnx5wz3nybvxyh6d3b2k3la21jq2z-vm-test-run-mrjam-native-workers-independent.drv` ;
son résultat est
`/nix/store/psqqjm0pb86c0zvypqabmyys4i41dk8z-vm-test-run-mrjam-native-workers-independent`.

```sh
nix-build operations/identity/workers-native-systemd.nix \
  --arg nixpkgs /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source \
  --argstr admissionAdoption /nix/store/9dn05bap085d5c7bjzilqs4bwd4ql4gg-mrjam-admission-native-adoption-1 \
  --max-jobs 1 --cores 2 --no-out-link
```

La VM de 2 Go utilise les modules de production, PostgreSQL17 et Kanidm1.11.2
réels, le broker `21dd879f…` et les cinq ELF natifs `kbqmlal…`. Ses interfaces
réseau QEMU et ses VLAN sont retirés : seules les communications loopback et
la console du test restent disponibles. Les personnes, comptes de service,
certificats, credentials et contenus sont entièrement inventés.

Les critères sont fixés dans `workers-contract.json` depuis les contrats
historiques. Le test vérifie l'adoption sans réécriture des preuves, les ACL
systemd et Unix peer, les capacités distinctes des tokens, la confirmation avant
création de personne, la reprise après panne du socket, l'enrôlement Kanidm réel,
les mêmes MIME après redémarrage et l'invitation consommée une fois. Le cycle
lit la vraie adresse native ; le refus SMTP ne démarre aucun délai. L'archive
est chiffrée puis déchiffrée par age avec la clé inventée. Fermeture et rejeu
reprennent une purge interrompue, retirent la personne et préservent un compte
tiers. L'adopteur de journal conserve les deux issuers et les époques, puis
refuse atomiquement une collision et une sélection ambiguë.

Les acquittements SMTP sont des événements de fixture explicitement injectés
dans la file. Le vrai worker doit ensuite les rattacher aux intentions SQL.
Ce test ne prouve pas une livraison Proton, une archive extérieure, l'adoption
des données réelles, une MFA humaine ou une autorité de déploiement. Les deux
profils NixOS permettent de vérifier adoption fermée puis ouverture explicite.
Le refus d'un autre UID sur le socket est couvert par le test identité distinct
`runtime-result-002.json` ; cette VM utilise réellement l'UID947 autorisé.

`workers-initial-findings.json` conserve les six échecs antérieurs du harnais,
leurs causes et corrections. Aucun n'a nécessité de modification du candidat.
Le dernier corrige une hypothèse de protocole d'après la source primaire :
Kanidm retourne `200/null` pour une personne absente (`person_id_get`). Le test
exige aussi son absence de la liste opérateur et le reçu SQL de rejeu.
