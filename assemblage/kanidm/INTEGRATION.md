# Kanidm — point opérationnel avant installation

Le jalon1 est actif et qualifié, avec Keycloak provisoire. Ce dossier prépare
le jalon2 ; son module n'est pas importé dans la configuration active. Aucun
serveur Kanidm, nouveau compte ou rattachement n'a encore été créé.

Préférence propriétaire du12octobre : un seul compte de connexion final, issu
autant que possible de Vision, adresse électronique ajoutée et mot de passe
conservé. Une nouvelle inscription/reconnexion est expressément acceptable si
cela exige une migration complexe. Ne maintenir ni double compte ni ancien
mécanisme d'authentification permanent. Le propriétaire SQL stable et ses données
restent préservés ; leur conservation ne crée pas une seconde connexion.

Voie simple à qualifier : le serveur historique Vision vérifie SHA512-crypt
(`services/mrj-auth/server.py`). Le parseur officiel Kanidm1.11.2 accepte
`{crypt}` suivi de l'empreinte `$6$`, et marque celle-ci à mettre à niveau vers
Argon2id (`libs/crypto/src/lib.rs`, parse_crypt/TryFrom/requires_upgrade ;
`server/lib/src/plugins/cred_import.rs`). Aucun calcul cryptographique réécrit,
aucun mot de passe en clair demandé. Le format effectivement installé et un vrai
import/login synthétique restent à constater avant usage. Acheminer l'empreinte
uniquement entre stockages privés, jamais par argv/log/source/artefact public.
Ne pas importer l'utilisateur ou les authentificateurs Keycloak. L'ancien accès
est retiré après accès/récupération qualifiés ; compte métier et séances intacts.

Le paquet1.11.2 est verrouillé sur la source officielle5479338 et le vendor
publié par NixOS/nixpkgs c79f172. La recette et la toolchain Nixpkgs c5 sont
conservées, provisioning non officiel désactivé. Cargo.lock et741checksums de
registre sont inventoriés ; les licences transitives et la compatibilité de
compilation restent distinctes de l'inventaire effectivement récupéré :741crates
du registre conformes au lock, licences déclarées inventoriées et intégrité Nix
vérifiée dans `vendor-qualification.json`. Le cargoHash officiel s'applique au
staging compact ; le vendor décompressé a son empreinte dérivée propre.
L'abaissement MSRV1.96→1.95 provient de cette recette existante : il n'est pas
une preuve que la compilation réussira. Le paquet amont désactive ses tests ;
une substitution ou compilation réussie ne qualifierait donc pas le service.

Le disque Codex32Go ne peut pas être augmenté. La tentative précédente a échoué
avant compilation avec1,1Go libre. Le nettoyage du12octobre a récupéré4,82Go nets,
soit5,92Go disponibles au relevé : voir [mesures et opérations](../nettoyage-20261012.json).
Source, image Lisp, preuves et candidats actif/retour sont conservés. Les narinfo
du paquet et du vendor précédemment évalués renvoyaient404. Reprendre localement
la compilation native déjà active, sans la répéter. Après ENOSPC du premier build,
le build-dir Nix explicite utilise le tmpfs existant ; TMPDIR seul ne suffisait
pas. Relever RAM/tmpfs et espace persistant séparément. Aucun déport effectué, aucune CI
de développement : voir [REPRISE.md](../REPRISE.md).

Commandes centrales disponibles, dans l'environnement de qualification existant :

```sh
source state/qualification-env.sh
export PATH="$PATH:/home/agent/.nix-profile/bin"
python3 scripts/assemblage.py tester --suite oidc-es256
python3 scripts/assemblage.py tester --suite oidc-transactions
python3 scripts/assemblage.py tester --suite oidc-transport
python3 scripts/assemblage.py tester --suite kanidm-configuration
```

Les trois premières exercent le client, avec signatures OpenSSL indépendantes,
claims, transactions SQLite et fixture HTTPS synthétique (32contrôles/11requêtes).
Elles ne prouvent pas des échanges avec Kanidm. La dernière évalue le module officiel Nix :
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
