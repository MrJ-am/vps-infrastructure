# API Vision sur le VPS

État : intégration préparée, non activée. Une fusion sur `main` ne déploie rien.

## Contrat public

- origine : `https://vision.principiipetit.io` ;
- documentation publique : `/docs`, `/openapi.json` et `/privacy` ;
- API protégée par HTTP Basic : `/api/` ;
- santé interne : `/healthz`, liée à `127.0.0.1` et masquée par Nginx ;
- application : commit Vision `b8d1de19be4bdc0db408820853239156117060ca`.

Nginx termine TLS, limite chaque IP à cinq requêtes par seconde avec une rafale
de dix, limite les connexions simultanées, vérifie le fichier `htpasswd`, retire
l'en-tête `Authorization` avant le proxy et ajoute une preuve interne que
l'application vérifie à nouveau. Le service SBCL écoute uniquement sur la boucle
locale et s'exécute avec les protections systemd et sans privilèges.

## Prérequis privés

1. Créer l'enregistrement DNS `A` `vision.principiipetit.io` vers `187.77.95.158`.
2. Dans l'environnement GitHub `vps-production`, définir :
   - `VISION_API_USERNAME` : identifiant ASCII de 1 à 64 caractères ;
   - `VISION_API_PASSWORD` : mot de passe aléatoire d'au moins 24 caractères.
3. Ne jamais placer ces valeurs dans Git, un ticket ou un journal Actions.

Le mot de passe est transformé sur le VPS en bcrypt coût 12. Seul le fichier
`/var/lib/vision/auth/htpasswd`, lisible par root et le groupe Nginx dédié, est
conservé. PostgreSQL reste accessible uniquement par socket Unix avec le rôle
pair `vision`; aucune donnée métier n'est inventée par cette intégration.

## Procédure contrôlée

1. Fusionner la PR après réussite de la CI.
2. Lancer manuellement **Préparer Vision sur le VPS**. Ce workflow sauvegarde
   Matheval, compare les invariants, compile la génération, vérifie Nginx et
   produit un rapport sans activation.
3. Examiner l'artefact `vision-preparation-<commit>`.
4. Lancer manuellement **Activer Vision sur le VPS** avec le SHA préparé.
   L'activation vérifie le DNS et les secrets, teste les accès anonyme et
   authentifié, contrôle les services existants puis enregistre le démarrage.

Si un contrôle échoue, l'ancienne configuration, la génération active et la
génération de démarrage sont rétablies automatiquement. La base Vision peut
rester vide après un retour ; elle n'est jamais supprimée automatiquement.

## ChatGPT

Importer `https://vision.principiipetit.io/openapi.json` comme schéma d'action,
choisir l'authentification HTTP Basic et renseigner les mêmes identifiants. Si
l'interface ne propose qu'un champ secret Basic, y placer le Base64 de
`identifiant:mot-de-passe`, sans préfixe `Basic `.
