# Publication de l'interface ElmUI de Vision

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

Après lecture du rapport et de la simulation, `operation: activer` avec le
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
