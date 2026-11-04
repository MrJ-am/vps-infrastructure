# Amorçage technique Forgejo 17

Composant local fermé, préparé sans accès au VPS. Les essais utilisent des
comptes, dépôts et contenus inventés. Ils ne constatent aucun état de production
et n'accordent aucune autorité sur les règles de gouvernance protégées.

`module.nix` déclare deux opérations root explicites, sans activation au démarrage :

- `mrjam-forgejo-probe.service` ne crée ni compte, organisation ni dépôt. Sa sortie
  JSON contient exclusivement une version fixe, des booléens et des inconnues
  pour le compte technique, l'organisation `MrJ-am` et les neuf dépôts autorisés.
- `mrjam-forgejo-bootstrap.service` crée, séparément, le seul compte technique
  `mrjam-governance-bootstrap`. Un compte existant sans attestation locale est
  refusé. Aucun compte personnel n'est utilisé, renommé ou réinitialisé.

Les exécutables `mrjam-forgejo-{probe,bootstrap,cleanup}` refusent tout argument.
Le service exige Forgejo 17.0.1, PostgreSQL local par socket Unix, UID 982,
`AUTO_MIGRATION=false`, connexion interne Web et Basic désactivées, et courriel
de notification désactivé. Il utilise la configuration privée déjà produite par
`mrjam-forgejo-host.nix`. Le mot de passe technique aléatoire de 64 caractères
généré par Forgejo reste uniquement dans la sortie capturée du sous-processus ;
il n'est ni fourni en argument, ni conservé, ni exporté.

Le compte est administrateur de Forgejo. Le jeton de constat a les permissions
`read:user,read:organization,read:repository`. Le contexte Python interne
`governance_lease()` fournit au seul backend revu les permissions
`read:user,write:organization,write:repository`. La CLI Forgejo crée des jetons
applicables à tous les dépôts ; les restrictions aux neuf dépôts sont donc celles
du contrôleur fermé `operations/forgejo/reconcile.py`, pas des ACL du jeton.
Ce contexte ne doit jamais devenir un outil renvoyant un jeton ou acceptant une
requête arbitraire. Il n'accorde ni permission API `admin`, ni écriture `user`.

Les jetons restent en mémoire. Le journal root 0600 ne contient que le nom fixe
du compte et une étiquette aléatoire. Avant émission, le nombre de jetons portant
cette étiquette doit être zéro. La révocation est une requête SQL littérale,
limitée au compte et à cette étiquette ; elle n'en lit jamais la valeur secrète.
Après révocation, le nombre doit être zéro et le jeton connu doit recevoir un
refus HTTP 401. La CLI 17 ne propose aucune commande de révocation ; l'API de
révocation personnelle exige Basic, désactivé dans ce profil. Aucun SQL fourni
par l'appelant n'est accepté.

`ExecStopPost` effectue le nettoyage même après interruption ; un journal restant
est également traité avant la prochaine opération. Une panne de PostgreSQL peut
empêcher ce nettoyage : le backend doit maintenir l'ouverture publique fermée
jusqu'à sa réussite, ou effectuer le retour apparié prévu. Une création interrompue
avant l'attestation finale du compte échoue de façon fermée ; elle ne permet pas
d'adopter automatiquement un compte homonyme. Les journaux d'intention et d'état
doivent appartenir au même retour apparié que la base Forgejo.

Ordre d'intégration : adoption/migration explicite de la base et des secrets
existants ; démarrage privé de Forgejo 17 ; constat ; amorçage technique distinct
si nécessaire ; nouveau constat ; plans et application des sources/protections
par le backend revu ; révocation confirmée avant ouverture publique. L'amorçage
ne crée pas l'organisation. Sa création éventuelle et l'import de sources restent
des opérations distinctes du backend ; les membres et autres dépôts sont conservés.

Le profil privé refuse également l'API de version anonyme. Avant émission d'un
jeton, le contrôle lit le fichier PID fixe et vérifie l'UID et le chemin exact de
l'ELF Nix du processus. La version API est ensuite contrôlée avec le jeton ; une
différence provoque le refus et la révocation, sans poursuivre les opérations.

Les sorties sont bornées, les requêtes ont des délais, les URL/API/SQL/comptes sont
fixes, les redirections et mandataires sont refusés. Les erreurs publiées sont des
codes fermés ; aucun corps d'erreur Forgejo ou sous-processus n'est exporté.

Qualification : `test_core.py` et `systemd-test.nix` avec Forgejo/PostgreSQL réels,
réseau VM isolé. Le reçu final doit être associé aux empreintes exactes du code,
du module et des fixtures ; `initial-findings.json` conserve les premiers échecs.
La fixture de sources contient seulement du texte inventé. Elle prouve le
fonctionnement du contrôleur existant, pas l'adoption des véritables sources.

Résultat figé : [result-002.json](result-002.json), 8 groupes VM et 19 tests
réussis en 42,60 s. Sortie VM :
`/nix/store/dq79kbsacig9mg45bj9ncji2407455ns-vm-test-run-mrjam-forgejo-closed-technical-bootstrap`.
Paquet qualifié :
`/nix/store/8pkxq7pahlmhlmf6v890q2ica69cflsy-mrjam-forgejo-technical-bootstrap-1`.
Le reçu conserve les empreintes exactes ; tous les services testés et la VM ont
été arrêtés. Le module borne les capacités root requises ; SETUID est demandé
explicitement pour descendre les sous-processus à UID 982 sous systemd 260.

Le reçu001 reste conservé pour la fixture UID/GID977 ; seul le reçu002 correspond
au profil982. Le paquet est lié aux UID/GID publics déclarés par ForgejoHost,
sans sélection possible à travers les commandes du composant.
