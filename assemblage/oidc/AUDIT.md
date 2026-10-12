# Client OIDC — dépendances et limite de qualification

Ces sources Nixpkgs `c5c4a43b0e8056328ec4529f735cabdb8f1942bb`, leurs NAR,
licences et dépendances sont verrouillées dans `dependances.lock.json`.
Les six bibliothèques communes reprennent les sources déjà auditées de l'atelier,
avec une portée produit explicitement distincte. Aucun MCP, Swank, Quicklisp,
runtime Python ou Node n'est une dépendance du client.

Ironclad v0.61, tag `d4fe172e4a44b2ac5ab73cf97372314f98e8b8a7`, BSD-3-Clause :
comparaison de tous les fichiers du tag avec la source Nix identique. Le graphe
retenu est `ironclad/public-key/secp256r1` et son core, sans chargement de la
collection complète. Le core crée un verrou et un objet PRNG OS, des définitions
et VOP SBCL ; l'ouverture de `/dev/urandom` est différée jusqu'à son utilisation.
La vérification utilise un inverse aveuglé et peut donc lire cet aléa. Aucun
thread applicatif, daemon, connexion réseau ou migration au chargement.

`src/public-key/secp256r1.lisp` : la méthode `verify-signature` reçoit un digest,
pas le texte ; clé SEC1 non compressée `04 || x || y`, signature JWS `r || s`.
L'adaptateur fournit exactement 32/65/64 octets et vérifie les domaines scalaires
et coordonnées avant les méthodes optimisées. Les paramètres privés de courbe
employés pour ces bornes sont liés à cette révision. Le code de courbe vérifie
l'appartenance du point. Les tests indépendants doivent exercer aussi les entrées
invalides. Cet examen ciblé ne constitue pas un audit cryptographique exhaustif.

`cl-base64` permet des entrées permissives : l'adaptateur doit imposer l'alphabet
URL sans remplissage, les limites et l'égalité du réencodage canonique. Le JSON
Vision refuse déjà les clés dupliquées ; une borne de profondeur précède son
appel dans ce client. Aucun parseur ni algorithme de signature réécrit.

La source JOSE `fukamachi/jose`, révision
`345d8cf67ea7f137534e97954d1993d69bae8791`, a été examinée puis écartée :
`jws.lisp` ne fournit pas ES256. Elle n'est ni chargée ni une dépendance produit.
Cela ne justifie pas l'activation du mode RSA de compatibilité de Kanidm.

Les tests de signature et claims ne prouvent pas la connexion à Kanidm.
Restent à exercer sur Kanidm réel : récupération HTTPS des métadonnées/JWKS,
issuer par client, discovery, PKCE/state/nonce, expiration, révocation, audiences,
sessions et MCP. Aucun secret ni identité de production dans les fixtures.
