# Connexion Kanidm et gestion des quotas

La politique demandée utilise uniquement **Kanidm sur https://log.mrj.am/** pour
les connexions Web. Forgejo conserve son propre identifiant de compte et ses droits.
`MrJam` est le compte administrateur existant renommé, rattaché à l'UUID de
l'identité propriétaire déjà présente dans Kanidm. Aucun rattachement par simple
égalité de courriel, aucune réinitialisation de l'authentification du propriétaire.

## Connexion

Sur https://forge.mrj.am/user/login, utiliser **Kanidm** et s'authentifier sur
`log.mrj.am` avec les moyens habituels. Le formulaire de mot de passe Forgejo et
l'authentification Basic par mot de passe sont désactivés côté serveur. L'ancien
OpenID est désactivé ; la seule source OAuth/OIDC active doit être Kanidm.
Les créations de compte locales restent fermées. Une identité autorisée par
Kanidm peut obtenir son compte Forgejo à sa première connexion ; elle devient
utilisatrice ordinaire, sans rôle administrateur automatique.

Le client confidentiel `mrjam-forgejo` utilise la découverte OIDC, PKCE S256 et
l'URI stricte `https://forge.mrj.am/user/oauth2/Kanidm/callback`. La politique MFA
et la récupération des moyens de connexion restent gérées par Kanidm.
Il n'existe pas de connexion Web locale de secours ; l'exploitation root/Nix et
les générations de retour restent le canal de réparation indépendant.

Les clés SSH et les jetons d'accès personnels restent les moyens techniques pour
Git (SSH2222, HTTPS443) et l'API. Les jetons personnels se créent dans les paramètres
Applications après connexion Kanidm. Le mot de passe Kanidm n'est jamais transmis
à Git ou à Forgejo. Les sondes d'exploitation utilisent un jeton temporaire créé
localement par root puis révoqué, sans le publier.

## Deux contrôles différents

**Nombre de dépôts** : défaut global Nix et surcharge par compte dans
Administration du site → Comptes utilisateurs → Modifier → nombre maximal de
dépôts. `-1` hérite du défaut global ; `0` interdit la création. Les comptes
administrateurs sont exemptés de cette limite native. La création d'organisations
par les comptes ordinaires est désactivée pour éviter un espace de stockage
supplémentaire sans politique explicite.

**Stockage** : les quotas natifs s'appliquent à la somme des dépôts et autres
ressources d'un propriétaire, avec des règles/groupes et des exceptions par compte.
La gestion des règles/groupes se fait par l'API administrative dans cette version ;
le programme `scripts/forgejo-quotas.py` fournit une commande par personne.
La consommation est visible dans `/user/settings/storage_overview`.

Aucune limite chiffrée arbitraire n'est imposée initialement : les deux défauts
restent illimités (`-1`), avec le moteur de quotas activé. Exemple de politique
**à appliquer explicitement** dans Nix :

```nix
infrastructure.forgejo.quotas = {
  maxRepositories = 20;
  totalStorage = "5 GiB";
};
```

Pour définir une exception par compte, enregistrer un jeton administrateur dans
un fichier privé hors dépôt, par exemple `~/.config/forgejo/admin-token` (0600),
puis depuis VPS Infrastructure :

```sh
python3 scripts/forgejo-quotas.py \
  --token-file ~/.config/forgejo/admin-token \
  --user alice --max-repositories 20 --storage 5GiB
```

Sans les deux options de limite, la commande affiche la consommation et les groupes.
Le stockage crée une règle et un groupe `personal-alice`. Si d'autres groupes de
quotas sont déjà affectés, la commande demande de les examiner ; l'option explicite
`--replace-quota-groups` remplace ces affectations. Cela évite de conserver un autre
groupe qui autoriserait davantage de stockage : entre groupes, l'autorisation la
plus permissive peut l'emporter. Les limites personnalisées restent dans PostgreSQL
et sont incluses dans les sauvegardes ; les défauts d'instance restent dans Nix.

## Limites natives vérifiées

Le quota de stockage n'est **pas un plafond strict par dépôt**. Il est vérifié
avant écriture à partir du stockage déjà comptabilisé : une écriture peut dépasser
le seuil, puis les suivantes sont refusées. Les suppressions permettant de réduire
l'utilisation restent possibles. Ne pas utiliser ce mécanisme comme garantie
absolue d'espace disque ; superviser aussi la capacité du VPS.

Le test du plafond de nombre via l'API de Forgejo16.0.3 refuse effectivement le
dépôt supplémentaire, mais renvoie HTTP500 avec une erreur interne « maximum limit
of repositories » au lieu d'une erreur fonctionnelle4xx. Aucun dépôt n'est créé.
Le contrôle et la surcharge par compte ont été exercés sur le vrai programme.
Aucun correctif fragile de Forgejo n'est ajouté pour changer ce statut amont.

## Secrets, sauvegarde et maintenance

`forgejo-identity` utilise l'opérateur natif existant pour provisionner uniquement
le client OIDC. Seul le compte technique `idm_admin` est récupéré ponctuellement
par le socket privé, puis désactivé ; le compte personnel, ses facteurs MFA et les
autres clients ne sont pas modifiés. Le secret OIDC reste hors Git/store/arguments,
dans `/var/lib/forgejo-identity/client.json` (root0700/fichier0600) et la base Forgejo.
Le compte est rattaché par UUID ; le renommage passe par l'API officielle.
Les paramètres CLI temporaires résident dans l'état mutable, pas dans le store.

Les sauvegardes incluent l'état Forgejo, les dépôts, le dump PostgreSQL et l'état
`forgejo-identity`, dans la même archive chiffrée. Le code de déploiement conserve
le système et sa configuration précédents ; un retour ne restaure jamais une
ancienne base sur des données courantes. Conserver les chaînes d'imports root
et la configuration Kanidm existante avec les autres sauvegardes d'infrastructure.

La qualification locale OIDC emploie Forgejo16.0.3 et le paquet Kanidm1.11.1 du
Nixpkgs verrouillé ; la production conserve son Kanidm1.11.2. L'étape UI IdP locale
est médiée par les API natives avec une session réellement authentifiée par MFA :
le code, PKCE, l'échange et la vérification ES256 sont réels. Cela ne remplace pas
une première connexion personnelle sur le Kanidm de production. Les reçus de
production distinguent redirection réelle, API/Git et connexion personnelle.

La suspension d'une identité Kanidm n'est pas, à elle seule, une révocation
immédiate de toutes les sessions Forgejo, clés SSH et jetons déjà émis. En cas de
retrait d'accès, bloquer aussi le compte Forgejo et révoquer ses accès techniques.
Ce raccordement configure le fournisseur de connexion ; il n'ajoute pas de moteur
de synchronisation ou de révocation continue des comptes.
