# Nextcloud — connexion Log / Kanidm

Le compte Nextcloud existant `MrJam` est rattaché explicitement à l'identité
Kanidm propriétaire déjà utilisée par Forgejo. Son UID et ses données restent
inchangés. Le compte historique `admin` est conservé sans connexion Web locale.
La récupération administrative passe par le canal root/CI existant.

Le client confidentiel `mrjam-nextcloud` utilise OpenID Connect, PKCE S256 et les
signatures ES256 natives. Un groupe dédié contient uniquement l'UUID propriétaire.
La claim administrative `nextcloud_uid` désigne le compte existant ; aucune
association par adresse mail, création de compte ni synchronisation de groupes.
Deux callbacks exacts sont acceptés, selon l'usage des URL réécrites Nextcloud :
`https://cloud.mrj.am/apps/user_oidc/code` et la variante avec `/index.php`.

`user_oidc` 8.10.1 vient du Nixpkgs de production verrouillé, archive SHA256
49ced1fe192302f4540b869438b6ccb9ca0d69b717b76ed7075a70aa5cf666fd.
Nextcloud reste en 34.0.4. Les moyens de connexion Kanidm personnels ne sont
jamais récupérés ni réinitialisés. Le secret client passe par un fichier privé
éphémère puis le stockage chiffré natif de Nextcloud, jamais par Git ou argv.

Le formulaire local est masqué et ses POST, y compris `?direct=1`, sont refusés
par Nginx. Les mots de passe ordinaires sont refusés pour DAV/API ; les jetons
d'application existants restent utilisables. Le hash historique n'est pas
modifié, pour préserver ces jetons et le retour arrière. La récupération et la
connexion passent par Log. La déconnexion Nextcloud ne ferme pas les autres
applications ; la révocation Kanidm n'est pas une révocation immédiate de tous
les jetons d'application Nextcloud.

L'opération manuelle `nextcloud-sso-preparer`, puis `nextcloud-sso-deployer`, du
workflow central `monolithe-deploiement.yml` construit la configuration sans
changer les autres applications. Le descripteur central verrouille les sources.
Avant activation : accès Web et cron arrêtés par une condition systemd temporaire,
sauvegarde en mode maintenance, puis maintenance désactivée pour les commandes
`occ upgrade` du setup NixOS et `user_oidc:provider`. La condition empêche leur
redémarrage jusqu’à la fin de la configuration. Sauvegarde fichiers/base chiffrée avec clé
age enveloppée pour le destinataire existant, déchiffrement et restauration dans
une base séparée, empreintes des comptes/fichiers/partages/carnets/calendriers.
Un timer indépendant rétablit le code/configuration en cas d'échec, sans restaurer
une ancienne base sur les écritures récentes. `nextcloud-sso-retour` permet le
même retour manuel. Les sauvegardes restent privées sur le VPS.

Qualification locale : conteneurs officiels Nextcloud34.0.4 et Kanidm1.11.2,
module user_oidc exact, Nginx réel, TLS vérifié avec CA de test, vrais MFA/code/
PKCE/ES256 et compte préexistant. L'étape UI de Kanidm est médiée par son API
native. Aucune connexion personnelle de production n'est simulée.

Déployé le 19 octobre 2026 : [opération 39330935764](https://github.com/MrJ-am/vps-infrastructure/actions/runs/39330935764).
Le reçu `qualification-production.json` consigne l'artefact, les sondes et leurs
limites ; le parcours personnel de production reste à effectuer par son titulaire.
La configuration Contacts préparée auparavant est conservée sans activation.
