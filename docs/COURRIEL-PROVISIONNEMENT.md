# Installer le courrier privé par Actions

Le code préparé est consultable dans `vision-courriel.yml` et
`scripts/courriel-provisionner.py`. Il installe le jeton Proton déjà fourni,
sans modifier une valeur différente, activer Keycloak ou ouvrir les comptes.
Il ne touche ni les MX, ni les domaines, ni les releases, ni les ACL SQL.

1. Publier ce workflow sur main après réussite de la CI exacte. Ajouter le
   secret Actions `VISION_PROTON_SMTP_TOKEN`, contenant **seulement** le jeton
   SMTP dédié à Automath, pas le mot de passe Proton. Le secret peut appartenir
   à l'environnement `vps-production` ou au dépôt privé. La connexion utilise
   la clé administrative existante ; aucune clé SSH supplémentaire n'est requise.
2. Lancer manuellement « Installer le courrier privé de Vision », sur main,
   en cochant le test. Le runner vérifie la clé d'hôte, transfère le commit
   exact, passe le jeton sur stdin et installe le JSON root 0600 dans
   `/var/lib/mrjam-identite`, répertoire 0700. Aucune donnée privée en artifact.
3. L'envoi exige STARTTLS et un certificat valide. Il utilise la clé publique
   age déjà déclarée pour les sauvegardes Vision, à la révision du workflow.
   Le résultat atteste seulement l'acceptation du relais. Vérifier la présence
   dans la boîte Proton, récupérer la pièce et la déchiffrer avec la clé privée
   correspondante hors VPS. Le témoin ne désigne aucun usager ; ne pas le
   soumettre au rejeu des effacements. Conserver uniquement la preuve technique.
4. Consigner URL Actions, commit, état du fichier privé et confirmation de
   réception/déchiffrement. Une clé privée manquante bloque la qualification
   des sauvegardes, même si l'envoi SMTP réussit. Un refus SMTP ne modifie
   aucun accès utilisateur ; le fichier privé reste disponible pour diagnostic
   opérateur et reprise. Ne pas afficher les réponses privées du relais.

Les outils Work actuels ne permettent ni de créer un secret Actions ni de
déclencher un nouveau workflow manuel. Le réseau Work n'autorise pas SMTP 587.
Ces deux actions d'interface GitHub sont donc les seules manipulations à faire
par l'exploitant pour cette étape ; aucune tentative SSH depuis Work.

Ce contrôle n'achève pas la migration multi-utilisateur. L'import privé,
l'identité initiale avec MFA, la restauration des bases, le retour des owners,
ACL et RLS, les contrats applicables et la réception du registre d'effacement
restent les conditions distinctes du dossier d'activation.

## Témoin sur téléphone du 10 octobre 2026

Le propriétaire a créé une clé AGE localement dans Nix-on-Droid, puis partagé
uniquement sa clé publique :
`age1p95t4z0aafq7j4fl7cc9f0cjz8j03dtlmz56kec4lj6vwxrvzpqqnc53cc`.
Le chiffrement AGE valide sa somme de contrôle. La clé privée reste sur le téléphone,
dans `~/.local/share/mrjam-recovery/cle-privee.age` ; sa possession et le déchiffrement
réel restent à confirmer. Aucun accès au PC Linux n'est nécessaire pour ce témoin.

La phase fermée `vision-telephone` du point d'entrée automatisé utilise le relais
déjà installé, après vérification de demande et CI exacte, sans nouvelle saisie
de secret ni clic Run workflow. Elle envoie uniquement au compte expéditeur
existant la pièce `vision-test-telephone-20261010.json.age`. Le message et le témoin
sont distincts du premier test SMTP. Le contenu est un JSON synthétique avec
`qualification_telephone: true`, la référence `vision-telephone-20261010` et
l'empreinte publique de la clé ; aucune donnée de compte, fiche, item ou identité.

Une intention root0600/fsync précède la remise SMTP et un reçu est écrit seulement
après acceptation du relais. Un rejeu de ce même opérateur terminé ne renvoie
aucun mail ; une remise ambiguë bloque pour diagnostic sans relance automatique.
Les exceptions SMTP ne sont jamais publiées. Les générations active/enregistrée
sont contrôlées avant/après, puis six services, nouvelle SSH et25sites.

La réception et le déchiffrement exigent encore une manipulation du propriétaire.
Ce test ne restaure aucune base et n'atteste aucune copie extérieure complète.
Il ne modifie pas la configuration des sauvegardes, les clés précédentes ou les
copies existantes ; Matheval reste inchangé. La nouvelle clé ne déchiffre pas les
anciens fichiers. Les nouvelles sauvegardes Vision/identité nécessiteront leur
préparation propre et leur vérification avant toute bascule.

Remise réelle réussie le 10 octobre2026 à13:15 Europe/Paris :
[Actions38047719442](https://github.com/MrJ-am/vps-infrastructure/actions/runs/38047719442),
job114200542052, opérateur415e9d7/PR80 après CI exacte38047434345/369tests.
Le relais accepte le nouveau témoin, générations conservées et contrôles finaux
nouvelle SSH/six services/25sites réussis. Aucun secret privé transmis depuis
le téléphone. [Reçu public borné](../operations/vision-telephone-resultat.json).
Réception, déchiffrement, sauvegarde réelle et copie extérieure restent distincts
et non vérifiés par cette opération.
