# Kanidm — point opérationnel avant installation

Le jalon1 est actif et qualifié, avec Keycloak provisoire. Ce dossier prépare
le jalon2 ; son module n'est pas importé dans la configuration active. Aucun
serveur Kanidm, nouveau compte ou rattachement n'a encore été créé.

Le paquet1.11.2 est verrouillé sur la source officielle5479338 et le vendor
publié par NixOS/nixpkgs c79f172. La recette et la toolchain Nixpkgs c5 sont
conservées, provisioning non officiel désactivé. Cargo.lock et741checksums de
registre sont inventoriés ; les licences transitives et la compatibilité de
compilation restent à vérifier sur les sources vendor effectivement récupérées.
L'abaissement MSRV1.96→1.95 provient de cette recette existante : il n'est pas
une preuve que la compilation réussira. Le paquet amont désactive ses tests ;
une substitution ou compilation réussie ne qualifierait donc pas le service.

Le disque Codex32Go n'offre plus qu'environ1,1Go. La tentative précédente a
échoué avant compilation ; une extension d'au moins20Go est demandée. Les
narinfo du paquet et du vendor évalués renvoient404. Ne relancer ni téléchargement
volumineux ni CI de développement pour contourner cette limite. Source, image
Lisp, preuves et candidat actif sont conservés ; voir [REPRISE.md](../REPRISE.md).

Commandes centrales disponibles, dans l'environnement de qualification existant :

```sh
source state/qualification-env.sh
export PATH="$PATH:/home/agent/.nix-profile/bin"
python3 scripts/assemblage.py tester --suite oidc-es256
python3 scripts/assemblage.py tester --suite oidc-transactions
python3 scripts/assemblage.py tester --suite kanidm-configuration
```

Les deux premières exercent le client, avec signatures OpenSSL indépendantes,
claims et transactions SQLite. La troisième évalue le module officiel Nix :
UIDkanidm, état0700, TLSLoadCredential, loopback8443, Unix/LDAP/provisioning désactivés,
trois fixtures de credential refusées. Ce sont des contrôles locaux, pas des
connexions à l'IdP. Pour une reproduction sans cache, utiliser
`python3 scripts/oidc-qualifier.py --sans-cache`, puis `--transactions --sans-cache`.
La bibliothèque reste hors du service actuellement servi.

Reprise après résolution du stockage, sans nouvelle décision d'architecture :

1. Relever les processus et l'espace ; vérifier la cible/marqueur de l'image C.
   Installer le paquet verrouillé, relever effectivement les licences vendor,
   puis démarrer Kanidm localement sur données et TLS synthétiques privés.
2. Exercer discovery/JWKS/ES256, clients distincts, code+S256/state/nonce et
   révocation sur ce serveur. Porter le raccordement et les sessions/OAuth/MCP
   provisoires Python dans le serveur commun, sans reconstruire un IdP.
3. Qualifier les parcours natifs d'enrôlement/récupération et la politique réelle.
   Aucun credential administrateur global dans le monolithe. Les paramètres
   personnels manquants demandent une médiation limitée réellement cloisonnée.
4. Préparer le nouveau propriétaire et son rattachement explicite au compte
   métier stable, sans égalité d'email, cascade d'effacement ou migration d'ancien
   authentificateur. Préparer l'enrôlement personnel réellement nécessaire.
5. Construire et qualifier l'artefact propre, sauvegarde/restauration/retour avec
   données actuelles, puis promotion centrale et sondes réelles. Retirer Keycloak
   et adaptations uniquement après accès et récupération sécurisés.

Points natifs établis dans le code1.11.2, à distinguer d'un parcours testé :

- `server/lib/src/idm/oauth2.rs` : issuer par client, `/ui/oauth2`,
  `/oauth2/token`, JWKS`/oauth2/openid/<client>/public_key.jwk`, ES256/S256.
  Pas de registration_endpoint : le raccordement MCP historique reste nécessaire.
- Connexion : `idm/server.rs` appelle `name_to_uuid` ; `server/mod.rs` cherche
  UUID puis index name2uuid. `entry.rs/get_name2uuid_cands` contient Name/SPN/
  GidNumber, aucun Mail ; `value.rs/INAME_RE` interdit`@` dans Name.
  La connexion par email ne peut pas être déclarée native sur ces preuves.
  L'exigence reste maintenue : adaptation sûre et vérification réelle nécessaires.
- `libs/client/src/person.rs` expose la consultation/révocation des UAT ;
  `group.rs` expose les politiques des groupes. L'existence de ces API ne prouve
  ni libre-service des durées, ni cloisonnement, ni propagation aux clients OIDC.
- Les politiques s'agrègent par la contrainte la plus forte. Les profils7/30/90
  jours, leur valeur effective, MFA/passkey avec vérification utilisateur,
  fraîcheur administrative, suspension/révocation, alertes et récupération restent
  des critères d'acceptation. Ne les afficher ni comme acquis ni comme abandonnés.

Aucune opération personnelle n'a été simulée. Les seules exceptions autorisées
restent l'abandon du lien magique et de la connexion perpétuelle.
