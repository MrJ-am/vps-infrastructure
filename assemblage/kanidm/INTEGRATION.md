# Kanidm — installation locale et intégration en cours

Le jalon1 est actif et qualifié, avec Keycloak provisoire. Ce dossier prépare
le jalon2 ; son module n'est pas importé dans la configuration active. Aucun
serveur Kanidm, nouveau compte ou rattachement de production n'a encore été créé.
Paquet officiel1.11.2 installé/vérifié localement ; scénarios natifs ci-dessous
réussis, sans constituer la deuxième bascule.

Préférence propriétaire du12octobre : un seul compte de connexion final, issu
autant que possible de Vision, adresse électronique ajoutée et mot de passe
conservé. Une nouvelle inscription/reconnexion est expressément acceptable si
cela exige une migration complexe. Ne maintenir ni double compte ni ancien
mécanisme d'authentification permanent. Le propriétaire SQL stable et ses données
restent préservés ; leur conservation ne crée pas une seconde connexion.

Voie simple qualifiée localement : le serveur historique Vision vérifie SHA512-crypt
(`services/mrj-auth/server.py`). Le parseur officiel Kanidm1.11.2 accepte
`{crypt}` suivi de l'empreinte `$6$`, et marque celle-ci à mettre à niveau vers
Argon2id (`libs/crypto/src/lib.rs`, parse_crypt/TryFrom/requires_upgrade ;
`server/lib/src/plugins/cred_import.rs`). Aucun calcul cryptographique réécrit,
aucun mot de passe en clair demandé. Format installé constaté et import/login
synthétiques réellement réussis, rounds implicites5000 et explicites656000.
Le fichier de migration ordinaire refuse PasswordImport par AccessDenied : aucun
correctif amont ni ACL élargie. API officielle ponctuelle sync_account/token/Sync/
_finalise utilisée ; capacité ensuite401/403, parent de sync absent. Jamais
_terminate, qui effacerait les comptes importés. Aucun service ni passerelle
permanents ajoutés. UUID/email/password, mauvais password refusé, Argon2id et
session après restart vérifiés dans tests/kanidm_reel.py. Acheminer l'empreinte
uniquement entre stockages privés, jamais par argv/log/source/artefact public.
Ne pas importer l'utilisateur ou les authentificateurs Keycloak. L'ancien accès
est retiré après accès/récupération qualifiés ; compte métier et séances intacts.

Constat réel du12octobre : [référence38237108531](reference-proprietaire-20261012.json)
à la révision354ceb0, même génération active. Un compte métier actif/administrateur,
un propriétaire d'items et une identité ; zéro orphelin/lien croisé. Un compte
historique éligible, SHA512-crypt reconnu, aucun doublon/format inconnu. Aucun
identifiant ou hash individuel exporté. Cela vérifie le format installé, pas encore
l'import personnel Kanidm. Les trois participations Matheval restent ouvertes.

Propriété : `vision_gestion.comptes` possède déjà un `id` UUID stable et un
`utilisateur` historique. Ne pas remplacer ce propriétaire textuel dans les
contenus. `vision_gestion.identites` impose un seul rattachement par utilisateur
(Vision migrations019/020) : remplacer explicitement le rattachement, pas ajouter
une seconde identité. La fonction `effacer_identite_cycle` de migration025 efface
les contenus : ne jamais l'employer pour retirer l'ancien fournisseur.

Le paquet1.11.2 est verrouillé sur la source officielle5479338 et le vendor
publié par NixOS/nixpkgs c79f172. La recette et la toolchain Nixpkgs c5 sont
conservées, provisioning non officiel désactivé. Cargo.lock et741checksums de
registre sont inventoriés ; les licences transitives et la compatibilité de
compilation restent distinctes de l'inventaire effectivement récupéré :741crates
du registre conformes au lock, licences déclarées inventoriées et intégrité Nix
vérifiée dans `vendor-qualification.json`. Le cargoHash officiel s'applique au
staging compact ; le vendor décompressé a son empreinte dérivée propre.
L'abaissement MSRV1.96→1.95 de la recette existante est effectivement compatible :
compilation release93m27s à un cœur et démarrage réussis, Rust officiel inchangé.
Le paquet amont désactive ses tests ; scénarios natifs réels séparés et limités.
Paquet/NAR/références : installation-locale.json ; aucune conformité globale.

Le disque Codex32Go ne peut pas être augmenté. La tentative précédente a échoué
avant compilation avec1,1Go libre. Le nettoyage du12octobre a récupéré4,82Go nets,
soit5,92Go disponibles au relevé : voir [mesures et opérations](../nettoyage-20261012.json).
Source, image Lisp, preuves et candidats actif/retour sont conservés. Les narinfo
du paquet et du vendor précédemment évalués renvoyaient404. Reprendre localement
le paquet natif déjà construit, sans répéter le build. Après ENOSPC du premier build,
le build-dir Nix explicite utilise le tmpfs existant ; TMPDIR seul ne suffisait
pas. Relever RAM/tmpfs et espace persistant séparément. Aucun déport effectué, aucune CI
de développement : voir [REPRISE.md](../REPRISE.md).

Commandes centrales disponibles, dans l'environnement de qualification existant :

```sh
source state/qualification-env.sh
export PATH="$PATH:/home/agent/.nix-profile/bin"
export MRJAM_KANIDM=/nix/store/0aqnq3k20yq30hf0bch64ghy3nj9bd66-kanidm-1.11.2
export MRJAM_CURL=/nix/store/a2ai6rhqhmba55arai7mxrs7mlwzlxfw-mrjam-outils-qualification/curl/bin/curl
python3 scripts/assemblage.py tester --suite oidc-es256
python3 scripts/assemblage.py tester --suite oidc-transactions
python3 scripts/assemblage.py tester --suite oidc-transport
python3 scripts/assemblage.py tester --suite kanidm-configuration
python3 scripts/assemblage.py tester --suite kanidm-proprietaire
```

Les trois premières exercent le client, avec signatures OpenSSL indépendantes,
claims, transactions SQLite et fixture HTTPS synthétique (32contrôles/11requêtes).
Elles ne prouvent pas des échanges avec Kanidm. La quatrième évalue le module officiel Nix :
UIDkanidm, état0700, TLSLoadCredential, loopback8443, Unix/LDAP/provisioning désactivés,
trois fixtures de credential refusées. Ce sont des contrôles locaux, pas des
connexions à l'IdP. La dernière connecte un IdP local réel isolé, importe les hashes,
finalise/révoque la capacité et vérifie les reprises. Suites aux clés/états
éphémères non réutilisables automatiquement ; candidat exact qualifié séparément.
Pour une reproduction sans cache, utiliser
`python3 scripts/oidc-qualifier.py --sans-cache`, puis `--transactions --sans-cache`.
La bibliothèque reste hors du service actuellement servi.

Reprise sans nouvelle décision d'architecture :

1. Relever les processus et l'espace ; vérifier la cible/marqueur de l'image C.
   Réutiliser le paquet verrouillé construit et ses preuves ; serveurs synthétiques
   arrêtés en fin de suite, image Lisp C conservée.
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
