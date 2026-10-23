# Protection PHP — avis du 23 octobre 2026

Le module désactive `session.upload_progress.enabled` dans le php.ini de tous
les pools FPM et dans le wrapper CLI/cron de Nextcloud. Le pool Nextcloud impose
également un `php_admin_flag` désactivé. Le réglage est chargé avant le parsing
des requêtes ; ni `ini_set()` ni `.user.ini` ne servent de protection.
[Avis PHP](https://www.php.net/archive/2026.php#2026-10-23-1).

`apps/nextcloud.nix` importe ce module pour les constructions futures.
L'opérateur de reprise vise exclusivement la génération et le fichier d'entrée
constatés dans `target.json`, avec PHP 8.4.27. Il refuse un changement concurrent,
un autre pool PHP ou Apache, les changements d'authentification, de mémoire et
des services protégés. Il ne met à jour ni Nextcloud, ni ses applications, ni
Nixpkgs. Les sources des correctifs PHP du 21 octobre sont conservées.

Qualification locale :

```sh
SECURITY_NIX_INSTANTIATE=/chemin/nix-instantiate \
SECURITY_NIXPKGS=/chemin/nixpkgs-c5c4a43b0e80 \
python3 scripts/php-upload-progress-qualify.py
```

Évaluations Nix réelles, refus de dix candidats hors périmètre, transport
FastCGI fragmenté et retour obsolète refusé. Les empreintes locales sont
contrôlées avant transport ; ce reçu local n'est pas une attestation externe.

Exploitation par `php-upload-progress.yml`, opérations fermées `audit` et
`apply`, via le secret et la clé d'hôte déjà utilisés par la CI centrale.
La préparation construit et vérifie le candidat avant d'arrêter brièvement
PHP. Sauvegarde chiffrée récupérable par l'hôte et le propriétaire, restauration
isolée et comparaison des données avant réouverture. Le retour indépendant est
exercé par un processus neuf ; en cas d'échec il remet le code précédent avec
PHP bloqué, sans restaurer une ancienne base.

La sonde envoie une requête FastCGI sur le socket Unix au processus FPM réel.
Son fichier temporaire se trouve hors racine Web et est supprimé après usage.
Seuls version, SAPI et état du réglage sont publiés. Statut Nextcloud, OIDC/PKCE,
refus des mots de passe locaux et DAV anonyme sont contrôlés, ainsi que les PID
de Nginx, PostgreSQL, Kanidm, métier, Forgejo, SSH, embeddings et D-Bus.
Une nouvelle exécution `audit` constate séparément l'état actif et de démarrage.
