# Publication de l'interface ElmUI de Vision

L'interface a été actualisée le 22 septembre 2026 à la révision
`dbf5fcb3b1c70ec8ee1717db8e17527619840245`, style
`b2177c0fd2c46c6f528266d30f7b933d3add1566`.
L'[activation 35720088997](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35720088997)
a vérifié chaque fichier servi, les polices, deux formats d'écran, la connexion
réelle, le cookie, CSRF, l'origine, Basic, la lecture PostgreSQL et la révocation.
Le serveur Vision reste `151ab64bd5c9c5c54297e88dbe4d548343cc4928` ; aucune
écriture métier ni migration de ses données. L'ancien artefact reste disponible.
Lire [l'état courant](ETAT.md). Les références qui suivent décrivent la première
publication, conservée comme historique.

**Publié le 21 septembre 2026 à 22:32 UTC** : [activation vérifiée](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35663052741).
Les références installées sont consignées dans [ETAT.md](ETAT.md).

Cette opération remplace uniquement les fichiers publics de Vision et leurs
routes Nginx. Le serveur Common Lisp 1.3, les migrations, PostgreSQL, les
comptes, sessions et routes Basic/MCP restent en place.

Le propriétaire a demandé la reprise complète jusqu'au déploiement de Vision,
en signalant la publication parallèle d'Apprendre à démontrer. Le workflow
`vision-interface.yml` utilise le même groupe `vps-administration` pour éviter
les opérations système simultanées. La préparation importe l'entrée NixOS
réellement active et compare ses invariants avant de construire. Elle refuse
une nouvelle génération ou une autre publication entre préparation et bascule.

L'artefact est conservé dans `vendor/vision-interface`, avec son manifeste
provenant de la CI applicative. Son JavaScript n'est pas reconstruit au moment
de l'activation. Les empreintes incluent les ressources communes, le logo et
les polices de Signature ; leur utilisation reste strictement réservée.

Les cinq routes ajoutées sont `/`, `/app.js`, `/app.css`,
`/interface-manifest.json` et `/assets/mrjam/`. Nginx sert
`/srv/vision-interface/current`. Les fichiers sont publics et ne contiennent
pas les fiches. Le CSP autorise les styles inline nécessaires à ElmUI et les
polices locales, mais aucun script inline. Une ressource absente reste une
404 ; les routes de sessions et de données ne sont pas interceptées.

## Procédure

Après CI verte sur une révision exacte, une demande dans
`operations/vision-interface.json`, sur `main`, indique `operation: preparer`
et `revision: <SHA complet>`. Le workflow vérifie la CI de ce SHA, utilise la
clé administrative déjà configurée et `scripts/connect.sh` depuis le runner.

La préparation vérifie les services, conserve la génération et l'entrée,
produit des sauvegardes chiffrées, contrôle l'artefact, construit avec le
Nixpkgs déjà installé, teste Nginx avec les vrais certificats et conserve la
simulation d'activation. Un timer indépendant est effectivement déclenché
sur un témoin privé. Aucun lien actif n'est remplacé pendant cette étape.

La demande `operation: controler` relit la simulation du candidat construit en
conservant aussi sa sortie d'erreur, puis revérifie les sites sans activation.
Après lecture du rapport et de cette simulation, `operation: activer` avec le
même SHA active le candidat déjà construit. Un retour autonome est armé à
quinze minutes. Les publications Matheval et Vision sont verrouillées pendant
la bascule. La nouvelle connexion du runner vérifie tous les sites enregistrés,
puis le navigateur vérifie les fichiers servis, la signature, le compte réel,
le cookie commun, CSRF, la lecture PostgreSQL, Basic et la révocation.
Aucune donnée de test n'est créée en production. Seule la page de connexion
vide est capturée ; les réponses privées ne sont ni journalisées ni archivées.

La génération exacte est ensuite enregistrée pour le démarrage. Le retour
rétablit l'entrée et les générations conservées ainsi que le lien de cette
opération ; il ne restaure pas les bases ni les comptes. Après enregistrement,
ce retour devient inopérant. Toute publication suivante possède sa propre
préparation et son retour. Les sources, générations et preuves restent conservées.

Le succès d'une CI ne prouve pas une mise en service. Consigner ici et dans
`ETAT.md` les exécutions de préparation et d'activation réellement réussies.

## Preuves de cette publication

- CI de l'infrastructure : [35662112254](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662112254), candidat `d224ab32928c43ef7f9445804077a2dbfb0fdfba`.
- Préparation : [35662657824](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662657824).
- Simulation complète : [35662944719](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662944719), seul `nginx.service` redémarre.
- Activation, navigateur réel et enregistrement : [35663052741](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35663052741).
- Artefact de preuve final : `10667782223`, SHA-256 `6cce2d539374ab062a7c732168e8d8d35bc122f819d0d816658ed18dba880d1d`.

La première connexion du runner a expiré avant le transfert
([35662539453](https://github.com/MrJ-am/vps-infrastructure/actions/runs/35662539453)) ;
la reprise ci-dessus a réussi. La première simulation ne conservait que stdout ;
la relecture complète, effectuée avant activation, a capturé stderr également.
Le candidat préparé n'a pas été modifié. Les sources de procédure corrigent
la capture pour les prochaines préparations.

`hosts/hostinger/configuration.nix` importe désormais le module Vision.
Les prochaines opérations, notamment Logique, doivent reconstruire depuis
la nouvelle génération et conserver ce routage. L'opération déjà terminée
refuse une nouvelle activation ; son ancien retour est inopérant.
