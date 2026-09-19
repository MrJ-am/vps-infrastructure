# API Vision sur le VPS

État : intégration préparée, non activée. Une fusion sur `main` ne déploie rien.

## Contrat public

- origine : `https://vision.mrj.am` ;
- documentation publique : `/docs`, `/openapi.json` et `/privacy` ;
- contrat public du test Mobile Live : `/mobile-live-test-openapi.json` ;
- API protégée par HTTP Basic : `/api/` ;
- santé interne : `/healthz`, liée à `127.0.0.1` et masquée par Nginx ;
- application : commit Vision `d11c199fab58c7afa080b1d99899e3997a523102`.

Nginx termine TLS, limite chaque IP à cinq requêtes par seconde avec une rafale
de dix, limite les connexions simultanées, vérifie le fichier `htpasswd`, retire
l'en-tête `Authorization` avant le proxy et ajoute une preuve interne que
l'application vérifie à nouveau. Le service SBCL écoute uniquement sur la boucle
locale et s'exécute avec les protections systemd et sans privilèges.

`GET /api/v1/mobile-live-test` est une exception exacte et volontaire : son
fichier `htpasswd` est distinct, ses identifiants jetables ne fonctionnent sur
aucune autre route et sa réponse est une constante sans donnée applicative. La
route est limitée à deux connexions et une petite rafale, n'est pas mise en
cache et demande aux robots de ne pas l'indexer. Seul le condensat du mot de
passe se trouve dans Git ; la valeur dictable est transmise au propriétaire
dans la conversation de test puis doit être retirée avec cette route.

## Prérequis privés

1. Vérifier l'enregistrement DNS `A` `vision.mrj.am` vers `187.77.95.158`.
2. Pour rendre l'API générale immédiatement utilisable, définir dans
   l'environnement GitHub `vps-production` :
   - `VISION_API_USERNAME` : identifiant ASCII de 1 à 64 caractères ;
   - `VISION_API_PASSWORD` : mot de passe aléatoire d'au moins 24 caractères.
   Pour le seul essai Mobile Live, les deux secrets peuvent rester absents :
   l'activation crée alors un verrou aléatoire éphémère, vérifie l'API puis en
   oublie la valeur. Seule la route de test jetable reste utilisable.
3. Ne jamais définir un seul des deux secrets ni placer leurs valeurs dans Git,
   un ticket ou un journal Actions.

Le mot de passe est transformé sur le VPS en bcrypt coût 12. Seul le fichier
`/var/lib/vision/auth/htpasswd`, lisible par root et le groupe Nginx dédié, est
conservé. PostgreSQL reste accessible uniquement par socket Unix avec le rôle
pair `vision`; aucune donnée métier n'est inventée par cette intégration.

Quand le verrou éphémère est utilisé, son mot de passe n'est conservé ni dans
GitHub ni dans un artefact : il ne sert qu'aux contrôles de l'activation. Pour
ouvrir ensuite l'API générale, définir les deux secrets durables et lancer
**Renouveler les identifiants Vision**.

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

Pour une rotation ultérieure, remplacer les deux secrets dans l'environnement
GitHub puis lancer **Renouveler les identifiants Vision**. L'ancien hash est
restauré automatiquement si les nouveaux identifiants ne passent pas le test
HTTPS.

## Test Mobile Live ponctuel

1. Ouvrir d'abord `/mobile-live-test-openapi.json` pour vérifier que la
   documentation publique est lisible.
2. Demander à Mobile Live d'appeler exactement
   `GET https://vision.mrj.am/api/v1/mobile-live-test` avec les
   identifiants jetables fournis séparément.
3. Le seul succès attendu contient `VISION-MOBILE-LIVE-AUTH-OK` et
   `"scope":"test-only"`.
4. Vérifier que les mêmes identifiants reçoivent `401` sur `/api/v1/health`.
5. Après l'essai, supprimer la route, le fichier `htpasswd` dédié et son
   condensat de l'infrastructure.

## ChatGPT

Importer `https://vision.mrj.am/openapi.json` comme schéma d'action,
choisir l'authentification HTTP Basic et renseigner les mêmes identifiants. Si
l'interface ne propose qu'un champ secret Basic, y placer le Base64 de
`identifiant:mot-de-passe`, sans préfixe `Basic `.
